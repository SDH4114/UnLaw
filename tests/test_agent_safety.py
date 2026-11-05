"""Agent mutation approvals, incoming file names and bounded reads use isolated data."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from tests.test_agent import FakeServer
from unlawful import agent


class AgentSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        home, bindir = self.root / "home", self.root / "bin"
        home.mkdir()
        bindir.mkdir()
        self.changed = self.root / "mutated"
        ul = bindir / "ul"
        ul.write_text(
            f'#!{sys.executable}\nfrom pathlib import Path\nPath({str(self.changed)!r}).write_text("changed")\nprint("changed")\n'
        )
        ul.chmod(0o755)
        isolated = patch.dict(
            os.environ,
            {
                "HOME": str(home),
                "XDG_CONFIG_HOME": str(self.root / "config"),
                "PATH": str(bindir),
                "UNLAW_BIN": str(ul),
            },
        )
        isolated.start()
        self.addCleanup(isolated.stop)
        self.config = agent.load_config()
        self.config["agent"]["roots"] = [str(self.root)]
        self.config["telegram"]["chat_id"] = "42"
        self.config["agent"]["allowed_ids"] = ["8"]
        self.config["agent"]["users"] = {"8": "read"}

    def test_declining_model_mutations_keeps_todo_and_schedule_unchanged(self) -> None:
        class Decline:
            can_send_files = False

            def confirm(self, *args, **kwargs):
                return False

        schedule = agent.Schedule()
        job = schedule.add(
            "keep", agent.now() + dt.timedelta(hours=1), "once", "terminal"
        )
        before = schedule.path.read_bytes()
        tools = agent.Tools(self.config, Decline(), "terminal", "full", self.root)
        for name, arguments in (
            ("todo_add", {"text": "unexpected"}),
            ("todo_done", {"id": 1}),
            ("schedule", {"prompt": "unexpected", "when": "in 5m"}),
            ("unschedule", {"id": job["id"]}),
        ):
            with self.subTest(tool=name):
                self.changed.unlink(missing_ok=True)
                schedule.path.write_bytes(before)
                result = tools.call(name, arguments)
                self.assertFalse(
                    self.changed.exists(), "a denied TODO action must never execute ul"
                )
                self.assertEqual(
                    schedule.path.read_bytes(),
                    before,
                    "a denied action must preserve the schedule",
                )
                self.assertIn("declined", result)

    def test_received_filenames_cannot_escape_downloads(self) -> None:
        def route(method, path, body, headers):
            if path.endswith("/getFile"):
                return 200, {"ok": True, "result": {"file_path": "files/fake.bin"}}
            return 200, {"content": "local fake download"}

        server = FakeServer(route)
        self.addCleanup(server.close)

        class Model:
            def transcribe(self, path):
                return "heard"

        bot = agent.Bot(self.config, agent.Telegram("DUMMY", server.url), Model())
        bot.send = lambda *args, **kwargs: None
        downloads = agent.storage_path("telegram", "downloads")
        escaped = downloads.parent.parent.parent / "escaped.txt"
        for filename in ("../../../escaped.txt", str(self.root / "absolute.txt")):
            with self.subTest(filename=filename):
                bot._content(
                    {"document": {"file_id": "FAKE", "file_name": filename}}, "", "8"
                )
                self.assertFalse(escaped.exists())
                self.assertFalse((self.root / "absolute.txt").exists())
                self.assertTrue(
                    (
                        agent.storage_path("telegram", "downloads")
                        / Path(filename).name
                    ).is_file()
                )
        outside = self.root / "escaped-audio" / "voice.ogg"
        bot._content({"audio": {"file_id": "FAKE", "file_name": str(outside)}}, "", "8")
        self.assertFalse(
            outside.parent.exists(),
            "audio must not write outside downloads before deleting its temporary file",
        )

    def test_damaged_schedule_skips_incompatible_dates_and_shapes(self) -> None:
        schedule = agent.Schedule()
        good = schedule.add(
            "keep", agent.now() + dt.timedelta(hours=1), "once", "terminal"
        )
        invalid = {**good, "id": "aware", "next": "2099-01-01T00:00:00+00:00"}
        schedule.path.write_text(json.dumps({"jobs": [invalid, good]}))
        self.assertEqual(schedule.jobs(), [good])
        self.assertEqual(schedule.take_due(agent.now()), [])

    def test_damaged_schedule_ignores_nonlist_jobs(self) -> None:
        schedule = agent.Schedule()
        schedule.path.parent.mkdir(parents=True, exist_ok=True)
        for value in (None, 3, "bad"):
            with self.subTest(jobs=value):
                schedule.path.write_text(json.dumps({"jobs": value}))
                self.assertEqual(schedule.jobs(), [])

    def test_text_reads_allocate_by_read_limit_not_total_file_size(self) -> None:
        file = self.root / "large.log"
        with file.open("wb") as handle:
            handle.write(b"bounded\n" * 2000)
            handle.truncate(16 * 1024 * 1024)
        tools = agent.Tools(self.config, None, "terminal", "full", self.root)
        for read in (
            lambda: tools._read_file(str(file)),
            lambda: agent.attach("@" + str(file), self.root),
        ):
            with self.subTest(reader=read):
                tracemalloc.start()
                try:
                    text = read()
                    _current, peak = tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()
                self.assertIn("bounded", text)
                self.assertLess(
                    peak,
                    4 * 1024 * 1024,
                    "reading a 200 KB excerpt must not allocate the whole 16 MB file",
                )

    def test_add_and_remove_keep_entries_the_server_cannot_read(self) -> None:
        schedule = agent.Schedule()
        schedule.path.parent.mkdir(parents=True, exist_ok=True)
        broken = [{"id": 5, "prompt": "bad id"}, "junk"]
        later = (agent.now() + dt.timedelta(hours=2)).isoformat()
        good = {"id": "aaaaaa", "prompt": "keep", "next": later, "repeat": "once"}
        schedule.path.write_text(json.dumps({"jobs": [*broken, good]}))
        added = schedule.add("new", agent.now() + dt.timedelta(hours=1), "once", "terminal")
        stored = json.loads(schedule.path.read_text())["jobs"]
        for entry in broken:
            self.assertIn(entry, stored)
        self.assertEqual({job["id"] for job in schedule.jobs()}, {"aaaaaa", added["id"]})
        schedule.remove(added["id"])
        stored = json.loads(schedule.path.read_text())["jobs"]
        for entry in broken:
            self.assertIn(entry, stored)
        self.assertEqual([job["id"] for job in schedule.jobs()], ["aaaaaa"])

    def test_taking_due_jobs_keeps_entries_the_server_cannot_read(self) -> None:
        schedule = agent.Schedule()
        schedule.path.parent.mkdir(parents=True, exist_ok=True)
        broken = {"id": 5, "prompt": "bad id"}
        past = (agent.now() - dt.timedelta(minutes=1)).isoformat()
        schedule.path.write_text(json.dumps({"jobs": [broken, {"id": "bbbbbb", "prompt": "due", "next": past}]}))
        self.assertEqual([job["id"] for job in schedule.take_due(agent.now())], ["bbbbbb"])
        self.assertEqual(json.loads(schedule.path.read_text())["jobs"], [broken])


    def test_protected_paths_ignore_letter_case_and_cover_common_tokens(self) -> None:
        home = Path.home().resolve()
        guard = agent.protected()
        blocked = [
            home / ".SSH" / "id_ed25519",
            home / "notes" / ".Env.local",
            home / ".AWS" / "credentials",
            agent.config_dir().resolve().parent / agent.config_dir().name.upper() / "CONFIG.toml",
            Path(str(guard[1]).upper()) / "audit.log",
            home / ".config" / "GH" / "hosts.yml",
            home / ".cache" / "huggingface" / "token",
            home / ".docker" / "config.json",
            home / ".npmrc",
            home / ".zsh_history",
            home / "backup" / "ID_RSA.old",
            home / "Library" / "keychains" / "login.keychain-db",
        ]
        for path in blocked:
            with self.subTest(path=str(path)):
                self.assertIsNotNone(agent.denied(path, guard))
        for path in (home / "notes" / "ssh-guide.md", home / ".config" / "ghostty" / "config", home / "history.md"):
            with self.subTest(path=str(path)):
                self.assertIsNone(agent.denied(path, guard))

if __name__ == "__main__":
    unittest.main()
