from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


KANBAN = """---
kanban-plugin: board
---

## To do

- [ ] First task
\tcontinued detail
- [ ] Second task

## In progress

- [ ] Active task

## Completed

- [x] Old task

%% kanban:settings
```json
{}
```
%%
"""


class ConfiguredTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        (self.vault / "TODO.md").write_text(KANBAN, encoding="utf-8")
        self.env = {
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "HOME": str(self.root / "home"),
        }
        self.env_patch = patch.dict(os.environ, self.env, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        from unlawful.config import ensure_layout, set_config_value

        ensure_layout()
        set_config_value("todo.vault_path", str(self.vault))
        set_config_value("todo.file", "TODO.md")


class DeskTerminalTests(ConfiguredTestCase):
    """`ul desk list/show/add/move/done`: the board from the terminal, for people and agents."""

    def desk(self, *args: str) -> tuple[int, str, str]:
        from unlawful.desk import main

        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(output), redirect_stderr(errors):
            code = main(list(args))
        return code, output.getvalue(), errors.getvalue()

    def board(self) -> str:
        return (self.vault / "TODO.md").read_text(encoding="utf-8")

    def test_show_numbers_tasks_and_keeps_multiline_detail(self) -> None:
        code, rendered, _ = self.desk("show")
        self.assertEqual(code, 0)
        self.assertIn(f"Board: {(self.vault / 'TODO.md').resolve()}", rendered)
        self.assertIn("To do\n  1. [ ] First task\n     continued detail\n  2. [ ] Second task", rendered)
        self.assertIn("4. [x] Old task", rendered)

    def test_show_json_has_ids_columns_and_the_version(self) -> None:
        import json

        from unlawful.kanban import version_of

        code, output, _ = self.desk("show", "--json")
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(data["version"], version_of((self.vault / "TODO.md").read_bytes()))
        self.assertEqual([column["name"] for column in data["columns"]], ["To do", "In progress", "Completed"])
        first = data["columns"][0]["cards"][0]
        self.assertEqual((first["id"], first["title"], first["checked"]), (1, "First task", False))
        self.assertEqual(first["details"], ["continued detail"])
        self.assertTrue(data["columns"][2]["cards"][0]["checked"])

    def test_show_and_changes_take_a_named_board(self) -> None:
        self.assertEqual(self.desk("new", "Work")[0], 0)
        code, _, errors = self.desk("add", "Plan", "the", "week", "-b", "Work")
        self.assertEqual(code, 0, errors)
        code, output, _ = self.desk("show", "Work")
        self.assertIn("To do\n  1. [ ] Plan the week", output)
        self.assertNotIn("Plan the week", self.board())
        code, output, _ = self.desk("list")
        self.assertEqual(code, 0)
        self.assertIn("Work", output)
        self.assertIn(str((self.vault / "TODO.md").resolve()), output)

    def test_list_json(self) -> None:
        import json

        self.desk("new", "Ideas")
        code, output, _ = self.desk("list", "--json")
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertEqual(data["default"], str((self.vault / "TODO.md").resolve()))
        self.assertEqual([board["name"] for board in data["boards"]], ["Ideas"])
        self.assertIn("reminders", data)

    def test_add_goes_to_the_first_column_or_the_requested_one_without_damaging_footer(self) -> None:
        self.assertEqual(self.desk("add", "Ship", "Unlaw", "--column", "in progress")[0], 0)
        self.assertEqual(self.desk("add", "Plain")[0], 0)
        text = self.board()
        self.assertIn("## In progress\n\n- [ ] Active task\n- [ ] Ship Unlaw", text)
        self.assertIn("- [ ] Second task\n- [ ] Plain", text)
        self.assertIn("%% kanban:settings", text)

    def test_move_moves_the_entire_multiline_task_block(self) -> None:
        self.assertEqual(self.desk("move", "1", "In", "progress")[0], 0)
        text = self.board()
        self.assertNotIn("## To do\n\n- [ ] First task", text)
        self.assertIn("## In progress\n\n- [ ] Active task\n- [ ] First task\n\tcontinued detail", text)

    def test_done_checks_and_moves_task_to_completed(self) -> None:
        code, output, _ = self.desk("done", "2")
        self.assertEqual(code, 0)
        self.assertIn("Completed #2: Second task", output)
        text = self.board()
        self.assertNotIn("- [ ] Second task", text)
        self.assertRegex(text, r"- \[x\] Second task  \[completion:: \d{4}-\d{2}-\d{2}\]")

    def test_done_uses_the_boards_done_column_when_completed_is_missing(self) -> None:
        (self.vault / "TODO.md").write_text(self.board().replace("## Completed", "## Done"), encoding="utf-8")
        self.assertEqual(self.desk("done", "1")[0], 0)
        self.assertRegex(self.board(), r"## Done\n\n- \[x\] Old task\n- \[x\] First task")

    def test_bad_input_changes_nothing(self) -> None:
        before = self.board()
        for args in (
            ("done", "9"),
            ("done", "x"),
            ("move", "1", "Nowhere"),
            ("add",),
            ("add", "text", "--column", "Nowhere"),
            ("show", "missing-board"),
            ("add", "x", "-b"),
        ):
            code, _, errors = self.desk(*args)
            self.assertEqual(code, 2, args)
            self.assertTrue(errors.startswith("unlaw desk: "), (args, errors))
        self.assertEqual(self.board(), before)
        self.assertEqual(self.desk("show", "--bogus")[0], 2)

    def test_help_is_short(self) -> None:
        code, output, _ = self.desk("--help")
        self.assertEqual(code, 0)
        self.assertLessEqual(len(output.splitlines()), 30)
        for action in ("list", "show", "add", "move", "done", "pomodoro", "--reminders"):
            self.assertIn(action, output)


class DesktopCommandTests(ConfiguredTestCase):
    def test_music_without_query_opens_spotify(self) -> None:
        from unlawful.desktop import music

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(music.subprocess, "run", return_value=completed) as run:
            self.assertEqual(music.main([]), 0)
        run.assert_called_once_with(["open", "-a", "Spotify"], check=False)

    def test_music_query_runs_spotify_search_automation(self) -> None:
        from unlawful.desktop import music

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(music.subprocess, "run", return_value=completed) as run:
            self.assertEqual(music.main(["Killer", "Queen"]), 0)
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["osascript", "-e"])
        self.assertIn("Killer Queen", command[2])
        self.assertIn('tell application "Spotify"', command[2])

    def test_work_opens_lofi_and_current_directory_in_zed(self) -> None:
        from unlawful.desktop import work

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(work.subprocess, "run", return_value=completed) as run, patch.object(
            work.Path, "cwd", return_value=Path("/tmp/project")
        ):
            self.assertEqual(work.main([]), 0)
        self.assertEqual(
            [item.args[0] for item in run.call_args_list],
            [
                ["open", "https://lofi-engine.vercel.app/"],
                ["open", "-a", "Zed", "/tmp/project"],
            ],
        )

    def test_youtube_encodes_search_query(self) -> None:
        from unlawful.desktop import youtube

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(youtube.subprocess, "run", return_value=completed) as run:
            self.assertEqual(youtube.main(["omarchy", "linux"]), 0)
        self.assertEqual(
            run.call_args.args[0],
            ["open", "https://www.youtube.com/results?search_query=omarchy+linux"],
        )

    def test_youtube_without_query_opens_homepage(self) -> None:
        from unlawful.desktop import youtube

        completed = subprocess.CompletedProcess([], 0)
        with patch.object(youtube.subprocess, "run", return_value=completed) as run:
            self.assertEqual(youtube.main([]), 0)
        self.assertEqual(run.call_args.args[0], ["open", "https://www.youtube.com/"])


class TelegramCommandTests(ConfiguredTestCase):
    def test_message_builds_send_message_request(self) -> None:
        from unlawful import telegram
        from unlawful.config import set_config_value

        response = {"ok": True, "result": {"message_id": 9}}
        with patch.dict(os.environ, self.env, clear=False):
            set_config_value("telegram.chat_id", "123")
        with (
            patch.dict(os.environ, self.env, clear=False),
            patch.object(telegram, "read_token", return_value="secret"),
            patch.object(telegram.TelegramClient, "request", return_value=response) as request,
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(telegram.main(["hello", "there"]), 0)
        request.assert_called_once_with("sendMessage", {"chat_id": "123", "text": "hello there"})

    def test_chat_id_is_discovered_from_latest_bot_update(self) -> None:
        from unlawful.telegram import discover_chat_id

        client = Mock()
        client.request.return_value = {
            "ok": True,
            "result": [
                {"message": {"chat": {"id": 111}}},
                {"message": {"chat": {"id": 222}}},
            ],
        }
        self.assertEqual(discover_chat_id(client), "222")

    def test_file_payload_selects_photo_video_or_document(self) -> None:
        from unlawful.telegram import classify_file

        self.assertEqual(classify_file(Path("shot.png")), ("sendPhoto", "photo"))
        self.assertEqual(classify_file(Path("clip.mov")), ("sendVideo", "video"))
        self.assertEqual(classify_file(Path("report.pdf")), ("sendDocument", "document"))

    def test_multipart_contains_file_bytes_and_form_fields(self) -> None:
        from unlawful.telegram import encode_multipart

        body, content_type = encode_multipart(
            {"chat_id": "123"}, "document", "note.txt", b"hello", boundary="BOUNDARY"
        )
        self.assertEqual(content_type, "multipart/form-data; boundary=BOUNDARY")
        self.assertIn(b'name="chat_id"\r\n\r\n123', body)
        self.assertIn(b'filename="note.txt"', body)
        self.assertIn(b"hello", body)

    def test_capture_sends_newest_unlaw_capture(self) -> None:
        from unlawful import telegram
        from unlawful.config import set_config_value

        storage = self.root / "storage"
        captures = storage / "captures" / "screenshots"
        captures.mkdir(parents=True)
        screenshot = captures / "latest.png"
        screenshot.write_bytes(b"png")
        with patch.dict(os.environ, self.env, clear=False):
            set_config_value("telegram.chat_id", "123")
            set_config_value("storage.root", str(storage))
        response = {"ok": True, "result": {"message_id": 10}}
        with (
            patch.dict(os.environ, self.env, clear=False),
            patch.object(telegram, "read_token", return_value="secret"),
            patch.object(telegram.TelegramClient, "request", return_value=response) as request,
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(telegram.main(["capture"]), 0)
        self.assertEqual(request.call_args.args[0], "sendPhoto")
        self.assertEqual(request.call_args.args[2][1], screenshot)




class CaptureTimeTests(unittest.TestCase):
    def test_times_accept_seconds_and_clock_forms_only(self) -> None:
        from unlawful.capture import CaptureError, _seconds

        self.assertEqual(_seconds("90"), 90)
        self.assertEqual(_seconds("1:30"), 90)
        self.assertEqual(_seconds("0:01:30.5"), 90.5)
        for bad in ("nan", "inf", "-inf", "1e999", "1:-30", "-5", "1:nan", "1:2:3:4", ""):
            with self.subTest(text=bad), self.assertRaises(CaptureError):
                _seconds(bad)


class TelegramConfigWriteTests(ConfiguredTestCase):
    def config_path(self) -> Path:
        return self.root / "config" / "unlaw" / "config.toml"

    def test_chat_id_is_saved_through_ul_config_set_keeping_comments(self) -> None:
        from tests import ulbin
        from unlawful import telegram

        path = self.config_path()
        path.write_text("# my note\nunknown_key = 1\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
        with patch.dict(os.environ, {**self.env, "UNLAW_BIN": str(ulbin.binary())}, clear=False):
            telegram._save_chat_id("555")
            self.assertEqual(telegram._settings()["chat_id"], "555")
        text = path.read_text(encoding="utf-8")
        self.assertIn("# my note", text)
        self.assertIn("unknown_key = 1", text)

    def test_without_ul_the_chat_id_is_still_saved(self) -> None:
        from unlawful import telegram

        with patch.dict(os.environ, self.env, clear=False):
            os.environ.pop("UNLAW_BIN", None)
            telegram._save_chat_id("777")
            self.assertEqual(telegram._settings()["chat_id"], "777")

    def test_a_failing_ul_reports_its_error(self) -> None:
        from unlawful import telegram

        fake = self.root / "fake-ul"
        fake.write_text("#!/bin/sh\necho boom >&2\nexit 3\n", encoding="utf-8")
        fake.chmod(0o755)
        with patch.dict(os.environ, {**self.env, "UNLAW_BIN": str(fake)}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                telegram._save_chat_id("1")


if __name__ == "__main__":
    unittest.main()
