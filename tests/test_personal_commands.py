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


class TodoCommandTests(ConfiguredTestCase):
    def test_list_numbers_tasks_and_preserves_multiline_detail(self) -> None:
        from unlawful.todo import main

        output = io.StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(output):
            self.assertEqual(main([]), 0)
        rendered = output.getvalue()
        self.assertIn("To do", rendered)
        self.assertIn("1. [ ] First task", rendered)
        self.assertIn("continued detail", rendered)
        self.assertIn("4. [x] Old task", rendered)

    def test_add_inserts_task_into_requested_column_without_damaging_footer(self) -> None:
        from unlawful.todo import main

        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["add", "Ship", "Unlaw", "--column", "In progress"]), 0)
        text = (self.vault / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("## In progress\n\n- [ ] Active task\n- [ ] Ship Unlaw", text)
        self.assertIn("%% kanban:settings", text)

    def test_move_moves_the_entire_multiline_task_block(self) -> None:
        from unlawful.todo import main

        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["move", "1", "In progress"]), 0)
        text = (self.vault / "TODO.md").read_text(encoding="utf-8")
        self.assertNotIn("## To do\n\n- [ ] First task", text)
        self.assertIn("## In progress\n\n- [ ] Active task\n- [ ] First task\n\tcontinued detail", text)

    def test_done_checks_and_moves_task_to_completed(self) -> None:
        from unlawful.todo import main

        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["done", "2"]), 0)
        text = (self.vault / "TODO.md").read_text(encoding="utf-8")
        self.assertNotIn("- [ ] Second task", text)
        self.assertRegex(text, r"- \[x\] Second task  \[completion:: \d{4}-\d{2}-\d{2}\]")

    def test_search_is_case_insensitive_and_does_not_edit(self) -> None:
        from unlawful.todo import main

        before = (self.vault / "TODO.md").read_text(encoding="utf-8")
        output = io.StringIO()
        with patch.dict(os.environ, self.env, clear=False), redirect_stdout(output):
            self.assertEqual(main(["search", "ACTIVE"]), 0)
        self.assertIn("Active task", output.getvalue())
        self.assertEqual((self.vault / "TODO.md").read_text(encoding="utf-8"), before)


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


class CaptureCommandTests(ConfiguredTestCase):
    def test_screenshot_uses_native_screencapture_and_creates_parent(self) -> None:
        from unlawful import capture

        target = self.root / "captures" / "shot.png"
        completed = subprocess.CompletedProcess([], 0)
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            capture.subprocess, "run", return_value=completed
        ) as run:
            self.assertEqual(capture.main(["screenshot", str(target)]), 0)
        self.assertTrue(target.parent.is_dir())
        self.assertEqual(run.call_args.args[0], ["screencapture", "-x", str(target)])

    def test_screen_recording_writes_pid_and_stop_removes_it(self) -> None:
        from unlawful import capture

        process = Mock(pid=4242)
        target = self.root / "captures" / "screen.mov"
        with patch.dict(os.environ, self.env, clear=False), patch.object(
            capture.subprocess, "Popen", return_value=process
        ):
            self.assertEqual(capture.main(["screen", str(target)]), 0)
            self.assertTrue(capture.recording_state_file().is_file())
        with patch.dict(os.environ, self.env, clear=False), patch.object(capture.os, "kill") as kill:
            self.assertEqual(capture.main(["stop"]), 0)
        kill.assert_called_once_with(4242, capture.signal.SIGINT)
        self.assertFalse(capture.recording_state_file().exists())

    def test_camera_and_audio_commands_use_configured_avfoundation_devices(self) -> None:
        from unlawful.capture import recording_command

        self.assertEqual(
            recording_command("camera", Path("camera.mov"), camera_device="2", audio_device="1"),
            [
                "ffmpeg", "-y", "-f", "avfoundation", "-framerate", "30",
                "-i", "2:1", "-c:v", "h264_videotoolbox", "-c:a", "aac", "camera.mov",
            ],
        )
        self.assertEqual(
            recording_command("audio", Path("voice.m4a"), camera_device="2", audio_device="1"),
            ["ffmpeg", "-y", "-f", "avfoundation", "-i", ":1", "-c:a", "aac", "voice.m4a"],
        )


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




if __name__ == "__main__":
    unittest.main()
