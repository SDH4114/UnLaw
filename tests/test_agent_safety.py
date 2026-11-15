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

    def test_a_cut_off_schedule_is_kept_aside_not_overwritten(self) -> None:
        schedule = agent.Schedule()
        schedule.path.parent.mkdir(parents=True, exist_ok=True)
        cut = '{"jobs": [{"id": "aaaaaa", "prompt": "keep me", "next": "2099-01-01T10:00:00", "repeat": "once"}'
        schedule.path.write_text(cut)
        self.assertEqual(schedule.jobs(), [], "reading never fails")
        self.assertEqual(schedule.take_due(agent.now()), [])
        self.assertEqual(schedule.path.read_text(), cut, "reading never rewrites")
        with patch.object(sys, "stderr"):
            added = schedule.add("new", agent.now() + dt.timedelta(hours=1), "once", "terminal")
        self.assertEqual(schedule.jobs(), [added])
        kept = list(schedule.path.parent.glob("schedule.json.damaged-*"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(), cut)

    def test_writes_keep_the_mode_of_the_file(self) -> None:
        class Approve:
            can_send_files = False

            def confirm(self, *args, **kwargs):
                return True

        tools = agent.Tools(self.config, Approve(), "terminal", "full", self.root)
        script, private = self.root / "run.sh", self.root / "notes.txt"
        script.write_text("#!/bin/sh\necho one\n")
        script.chmod(0o755)
        private.write_text("mine")
        private.chmod(0o600)
        self.assertIn("Edited", tools.call("edit_file", {"path": str(script), "old": "one", "new": "two"}))
        self.assertIn("Wrote", tools.call("write_file", {"path": str(private), "content": "still mine"}))
        self.assertEqual(script.stat().st_mode & 0o777, 0o755)
        self.assertEqual(private.stat().st_mode & 0o777, 0o600)
        self.assertEqual(private.read_text(), "still mine")

    def test_a_web_page_instead_of_json_does_not_stop_the_telegram_server(self) -> None:
        # A captive portal or proxy answers 200 with HTML; json.loads used to raise through Bot.run.
        import http.server
        import threading

        answers = []

        class Portal(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                first = not answers
                answers.append(self.path)
                body = b'{"ok": true, "result": []}' if first else b"<html>Sign in to Wi-Fi</html>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Portal)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        telegram = agent.Telegram("123:TOKEN", f"http://127.0.0.1:{server.server_port}")
        self.config["agent"]["digest_time"] = ""
        bot = agent.Bot(self.config, telegram, agent.Model(self.config))
        bot.poll_timeout = 0
        lines: list[str] = []
        bot.log = lines.append
        with patch.object(agent.time, "sleep"), patch.object(agent, "load_config", return_value=self.config):
            self.assertEqual(bot.run(polls=2), 0)
        self.assertEqual(len(answers), 3, "the backlog call and two polls")
        self.assertEqual(len(lines), 2)
        self.assertTrue(all("not JSON" in line and "TOKEN" not in line for line in lines), lines)
        with self.assertRaises(RuntimeError):
            telegram.call("getMe", {})

    def test_updates_of_an_odd_shape_are_skipped(self) -> None:
        server = FakeServer(lambda method, path, body, headers: (200, {"ok": True, "result": [7, {"no": "id"}, {"update_id": 5, "message": "text"}]}))
        self.addCleanup(server.close)
        bot = agent.Bot(self.config, agent.Telegram("123:TOKEN", server.url), agent.Model(self.config))
        lines: list[str] = []
        bot.log = lines.append
        updates = bot.fetch(0)
        self.assertEqual([update["update_id"] for update in updates], [5])
        with patch.object(agent, "load_config", return_value=self.config):
            bot.safe_handle(updates[0])  # "message" is not an object: logged, never raised
        self.assertEqual(len(lines), 1)
        self.assertIn("update 5 failed", lines[0])

    def test_a_model_server_that_is_gone_is_an_ordinary_error(self) -> None:
        import socket

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with patch.dict(os.environ, {"UNLAW_AGENT_LM_URL": f"http://127.0.0.1:{port}"}):
            model = agent.Model(self.config)
        with self.assertRaises(RuntimeError) as failure:
            model.chat([{"role": "user", "content": "hi"}], [])
        self.assertIn("local model", str(failure.exception))

    def test_logins_of_other_tools_and_browser_profiles_are_blocked(self) -> None:
        home = Path.home().resolve()
        guard = agent.protected()
        for relative in (
            ".claude/.credentials.json", ".codex/auth.json", ".config/gcloud/credentials.db", ".azure/accessTokens.json",
            "Library/Application Support/Google/Chrome/Default/Cookies", "Library/Application Support/Firefox/Profiles/x/logins.json",
            "Library/Mail/V10/x.emlx", "Library/Safari/History.db", "Library/Group Containers/x/data", ".password-store/a.gpg",
        ):
            with self.subTest(path=relative):
                self.assertIsNotNone(agent.denied(home / relative, guard))
        for relative in (".claude/settings.json", "Library/Application Support/Zed/settings.json", "Mail drafts/note.md"):
            with self.subTest(path=relative):
                self.assertIsNone(agent.denied(home / relative, guard))

    def test_a_timeout_stops_everything_the_command_started(self) -> None:
        import signal
        import subprocess as sp

        pidfile = self.root / "child.pid"
        with self.assertRaises(sp.TimeoutExpired):
            agent.run_group(["/bin/sh", "-c", f"/bin/sleep 30 & echo $! > {pidfile}; wait"], 1)
        pid = int(pidfile.read_text())
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            import time

            time.sleep(0.05)
        else:
            os.kill(pid, signal.SIGKILL)
            self.fail("the grandchild outlived the timeout")
        done = agent.run_group(["/bin/sh", "-c", "echo out; echo err >&2; exit 3"], 10)
        self.assertEqual((done.returncode, done.stdout, done.stderr), (3, "out\n", "err\n"))

    def test_help_of_a_command_outside_agent_commands_needs_approval(self) -> None:
        asked: list[str] = []

        class Decline:
            can_send_files = False

            def confirm(self, title, *args, **kwargs):
                asked.append(title)
                return False

        self.config["agent"]["commands"] = ["yt"]
        tools = agent.Tools(self.config, Decline(), "terminal", "full", self.root)
        self.assertIn("exit 0", tools.call("ul", {"args": ["yt", "--help"]}))
        self.assertEqual(asked, [], "help of a listed command runs without a question")
        self.changed.unlink()
        self.assertIn("declined", tools.call("ul", {"args": ["mything", "--help"]}))
        self.assertEqual(asked, ["Run: ul mything --help"])
        self.assertFalse(self.changed.exists(), "a declined help run never starts the command")

    def test_delete_of_a_symlink_trashes_the_link_not_its_target(self) -> None:
        class Approve:
            can_send_files = False

            def confirm(self, *args, **kwargs):
                return True

        target = self.root / "real.txt"
        target.write_text("keep")
        link = self.root / "link.txt"
        link.symlink_to(target)
        tools = agent.Tools(self.config, Approve(), "terminal", "full", self.root)
        self.assertIn("Moved", tools.call("delete", {"path": "link.txt"}))
        self.assertEqual(target.read_text(), "keep")
        self.assertFalse(link.is_symlink())
        trashed = Path.home() / ".Trash" / "link.txt"
        self.assertTrue(trashed.is_symlink())
        outside = self.root.parent / "elsewhere-link"
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        outside.symlink_to(target)
        self.assertIn("outside the allowed folders", tools.call("delete", {"path": str(outside)}))

    def test_labels_and_the_log_cannot_drive_the_terminal(self) -> None:
        label = agent.tool_label("run", {"command": "ls\x1b[2J\x1b]0;title\x07"})
        self.assertNotIn("\x1b", label)
        self.assertNotIn("\x07", label)
        log = agent.agent_dir("audit.log")
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text('[1]\n{"time": "t"}\n{"time": "t", "who": "w", "action": "a", "outcome": "ok", "detail": "\\u001b[31m"}\n')
        text = agent.log_text()
        self.assertNotIn("\x1b", text)
        self.assertEqual(len(text.splitlines()), 2)

    def test_the_audit_log_is_rotated(self) -> None:
        with patch.object(agent, "AUDIT_LIMIT", 200):
            for number in range(10):
                agent.audit("terminal", "read_file", "x" * 50, f"ok{number}")
        log = agent.agent_dir("audit.log")
        self.assertTrue(log.with_name("audit.log.1").exists())
        self.assertLess(log.stat().st_size, 400)
        self.assertIn("ok9", log.read_text())

    def test_extra_words_after_server_or_setup_are_a_usage_error(self) -> None:
        from contextlib import redirect_stderr
        from io import StringIO

        for args in (["server", "now"], ["setup", "again"], ["serve", "x"]):
            with self.subTest(args=args), redirect_stderr(StringIO()) as error:
                self.assertEqual(agent.main(args), 2)
            self.assertIn("takes no arguments", error.getvalue())

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


class AgentUiRobustnessTests(unittest.TestCase):
    def test_at_menu_with_an_unknown_user_and_odd_names(self) -> None:
        import tempfile

        from unlawful import agent_ui

        self.assertEqual(agent_ui.path_items("@~nosuchuser-xyz/", Path.cwd()), [])
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "a\x1b[2Jb.txt").write_text("x")
            items = agent_ui.path_items("@a", Path(folder))
        self.assertEqual(len(items), 1)
        self.assertNotIn("\x1b", items[0].label)

    def test_a_damaged_history_file_does_not_stop_the_console(self) -> None:
        import tempfile

        from unlawful import agent_ui

        with tempfile.TemporaryDirectory() as folder:
            history = Path(folder) / "history.txt"
            history.write_bytes(b"first\nbroken \\u00\n\xff\xfe raw\nlast \\u00e9\n")
            editor = agent_ui.Editor(lambda text, *styles: text, history, lambda text, cursor: ([], 0, 0))
            self.assertEqual(editor.history[0], "first")
            self.assertEqual(editor.history[-1], "last \u00e9")
            editor._remember("new entry")
            self.assertEqual(history.read_text().splitlines()[-1], "new entry")
            self.assertEqual(sorted(path.name for path in Path(folder).iterdir()), ["history.txt"])
