"""Error and edge paths of the seeded command modules, run with fake external tools."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from unlawful import capture  # noqa: E402
from unlawful.built_in_commands.cpp import main as cpp_command  # noqa: E402
from unlawful.built_in_commands.git import main as git_command  # noqa: E402
from unlawful.built_in_commands.py import main as py_command  # noqa: E402
from unlawful.built_in_commands.rust import main as rust_command  # noqa: E402
from unlawful.config import config_file, ensure_layout, set_config_value, storage_path  # noqa: E402
from unlawful.desktop import music, work  # noqa: E402


class ToolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        environment = patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": str(self.root / "config"), "PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"},
        )
        environment.start()
        self.addCleanup(environment.stop)
        cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)
        ensure_layout()

    def tool(self, name: str, *, exit_code: int = 0, body: str = "") -> Path:
        log = self.root / f"{name}.log"
        script = self.bin / name
        script.write_text(
            f"#!{sys.executable}\nimport sys\n"
            f"open({str(log)!r}, 'a').write('|'.join(sys.argv[1:]) + '\\n')\n{body}"
            f"raise SystemExit({exit_code})\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return log

    def lines(self, log: Path) -> list[str]:
        return log.read_text().splitlines() if log.exists() else []

    def run_main(self, main, args: list[str]) -> tuple[int, str, str]:
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def break_config(self) -> None:
        config_file().write_text("[apps\nbroken")


class GitTests(ToolTestCase):
    def test_passthrough_rejects_extra_arguments(self) -> None:
        log = self.tool("git")
        code, _, error = self.run_main(git_command.main, ["status", "extra"])
        self.assertEqual(code, 2)
        self.assertIn("Usage: ul git", error)
        self.assertEqual(self.lines(log), [])
        self.assertEqual(self.run_main(git_command.main, ["pull"])[0], 0)
        self.assertEqual(self.lines(log), ["pull"])

    def test_prompt_cancel_and_empty_message_stop_before_commit(self) -> None:
        log = self.tool("git")
        for side_effect, message in ((EOFError, "commit cancelled"), (["  "], "cannot be empty"), (KeyboardInterrupt, "cancelled")):
            with self.subTest(message=message), patch("builtins.input", side_effect=side_effect):
                code, _, error = self.run_main(git_command.main, [])
                self.assertEqual(code, 2)
                self.assertIn(message, error)
        self.assertEqual(set(self.lines(log)), {"add|."})

    def test_failures_stop_the_workflow(self) -> None:
        log = self.tool("git", exit_code=1)
        self.assertEqual(self.run_main(git_command.main, ["sync", "msg"])[0], 1)
        self.assertEqual(self.lines(log), ["pull|--rebase"])
        os.environ["PATH"] = "/nonexistent"
        code, _, error = self.run_main(git_command.main, ["commit", "x"])
        self.assertEqual(code, 1)
        self.assertIn("unlaw git:", error)

    def test_commit_message_tokens_are_joined(self) -> None:
        log = self.tool("git")
        self.assertEqual(self.run_main(git_command.main, ["fix", "the", "bug"])[0], 0)
        self.assertEqual(self.lines(log), ["add|.", "commit|-m|fix the bug", "push"])


class CaptureTests(ToolTestCase):
    def test_usage_and_argument_errors(self) -> None:
        code, out, _ = self.run_main(capture.main, [])
        self.assertEqual(code, 2)
        self.assertIn("Usage", out)
        cases = {
            ("dance",): "Unknown capture action: dance",
            ("screen", "--duration"): "--duration requires seconds",
            ("screen", "--duration", "0"): "duration must be positive",
            ("screen", "--duration", "abc"): "invalid literal",
            ("screenshot", "a.png", "b.png"): "only one output path is allowed",
        }
        for args, message in cases.items():
            with self.subTest(args=args):
                code, _, error = self.run_main(capture.main, list(args))
                self.assertEqual(code, 2)
                self.assertIn(message, error)

    def test_screenshots_use_timestamped_default_paths(self) -> None:
        log = self.tool("screencapture")
        for mode, flags in (("screenshot", "-x"), ("area", "-i|-s"), ("window", "-i|-W")):
            with self.subTest(mode=mode):
                code, out, _ = self.run_main(capture.main, [mode])
                self.assertEqual(code, 0)
                path = Path(out.strip())
                self.assertEqual(path.parent, storage_path("captures", "screenshots"))
                self.assertRegex(path.name, rf"^{mode}-\d{{8}}-\d{{6}}\.png$")
                self.assertEqual(self.lines(log)[-1], f"{flags}|{path}")
        self.tool("screencapture", exit_code=1)
        code, out, _ = self.run_main(capture.main, ["screenshot", str(self.root / "x.png")])
        self.assertEqual((code, out), (1, ""))

    def test_recording_lifecycle_with_a_real_process(self) -> None:
        self.tool("screencapture", body="import time\ntime.sleep(30)\n")
        code, out, _ = self.run_main(capture.main, ["screen", "--duration", "5"])
        self.assertEqual(code, 0)
        state = json.loads(capture.recording_state_file().read_text())
        self.assertEqual(state["mode"], "screen")
        self.assertIn("-V5", state["command"])
        self.assertTrue(state["output"].endswith(".mov"))
        code, _, error = self.run_main(capture.main, ["camera"])
        self.assertEqual(code, 1)
        self.assertIn("already active", error)
        code, out, _ = self.run_main(capture.main, ["stop"])
        self.assertEqual(code, 0)
        self.assertIn("Saved:", out)
        self.assertFalse(capture.recording_state_file().exists())
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(state["pid"], 0)
            except ProcessLookupError:
                break
            try:
                os.waitpid(state["pid"], os.WNOHANG)
            except ChildProcessError:
                pass
            time.sleep(0.05)
        else:
            self.fail("recording process ignored SIGINT")

    def test_stop_without_or_with_a_broken_recording(self) -> None:
        code, _, error = self.run_main(capture.main, ["stop"])
        self.assertEqual(code, 1)
        self.assertIn("no active recording", error)
        state = capture.recording_state_file()
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text("{not json")
        code, _, error = self.run_main(capture.main, ["stop"])
        self.assertEqual(code, 1)
        self.assertIn("could not stop recording", error)
        self.assertFalse(state.exists(), "a broken state file must not block new recordings")

    def test_camera_audio_and_devices_need_ffmpeg(self) -> None:
        for args in (["camera"], ["audio"]):
            with self.subTest(args=args):
                code, _, error = self.run_main(capture.main, args)
                self.assertEqual(code, 1)
                self.assertIn("ffmpeg is required", error)
        code, _, error = self.run_main(capture.main, ["devices"])
        self.assertEqual(code, 2)
        self.assertIn("ffmpeg is not installed", error)
        log = self.tool("ffmpeg")
        self.assertEqual(self.run_main(capture.main, ["devices"])[0], 0)
        self.assertEqual(self.lines(log), ["-f|avfoundation|-list_devices|true|-i|"])

    def test_last_opens_the_newest_capture(self) -> None:
        code, _, error = self.run_main(capture.main, ["last"])
        self.assertEqual(code, 2)
        self.assertIn("no captures found", error)
        old = storage_path("captures", "recordings", "old.mov")
        new = storage_path("captures", "screenshots", "new.png")
        old.write_bytes(b"1")
        new.write_bytes(b"2")
        os.utime(old, (1, 1))
        log = self.tool("open")
        self.assertEqual(self.run_main(capture.main, ["last"])[0], 0)
        self.assertEqual(self.lines(log), [str(new)])

    def test_unknown_recording_mode(self) -> None:
        with self.assertRaises(ValueError):
            capture.recording_command("hologram", Path("x"), camera_device="0", audio_device="0")
        command = capture.recording_command("screen", Path("x.mov"), camera_device="0", audio_device="0", screen_audio=False, show_clicks=False)
        self.assertEqual(command, ["screencapture", "-v", "x.mov"])

    def test_invalid_config_is_reported(self) -> None:
        self.break_config()
        code, _, error = self.run_main(capture.main, ["screenshot"])
        self.assertEqual(code, 2)
        self.assertIn("Could not read", error)


class MusicAndWorkTests(ToolTestCase):
    def test_music_query_is_escaped_for_applescript(self) -> None:
        log = self.tool("osascript")
        set_config_value("apps.spotify_autoplay_delay", 0.5)
        self.assertEqual(self.run_main(music.main, ['say "hi" \\ now'])[0], 0)
        script = log.read_text().split("|", 1)[1]
        self.assertIn('set searchQuery to "say \\"hi\\" \\\\ now"', script)
        self.assertIn("spotify:search:say%20%22hi%22%20%5C%20now", script)
        self.assertIn("delay 0.5", script)

    def test_music_failures(self) -> None:
        self.tool("osascript", exit_code=1)
        code, _, error = self.run_main(music.main, ["song"])
        self.assertEqual(code, 1)
        self.assertIn("Accessibility", error)
        code, _, error = self.run_main(music.main, ["  "])
        self.assertEqual(code, 2)
        (self.bin / "osascript").unlink()
        os.environ["PATH"] = str(self.bin)
        self.assertEqual(self.run_main(music.main, ["song"])[0], 1)
        self.break_config()
        self.assertEqual(self.run_main(music.main, [])[0], 2)

    def test_work_stops_when_the_browser_fails(self) -> None:
        log = self.tool("open", exit_code=3)
        self.assertEqual(self.run_main(work.main, [])[0], 3)
        self.assertEqual(len(self.lines(log)), 1)
        self.assertEqual(self.run_main(work.main, ["extra"])[0], 2)
        self.break_config()
        code, _, error = self.run_main(work.main, [])
        self.assertEqual(code, 1)
        self.assertIn("unlaw work:", error)


class ProjectGeneratorTests(ToolTestCase):
    def test_invalid_names_and_flags(self) -> None:
        for main, args in (
            (py_command.main, ["9bad"]),
            (py_command.main, ["ok", "--uv", "--venv"]),
            (py_command.main, ["ok", "--weird"]),
            (rust_command.main, []),
            (rust_command.main, ["ok", "--bin", "--lib"]),
            (cpp_command.main, ["ok", "--std"]),
            (cpp_command.main, ["ok", "--std", "98"]),
        ):
            with self.subTest(args=args):
                self.assertEqual(self.run_main(main, args)[0], 2)

    def test_existing_destination_is_never_overwritten(self) -> None:
        for main, name in ((py_command.main, "taken-py"), (rust_command.main, "taken-rs"), (cpp_command.main, "taken-cpp")):
            with self.subTest(name=name):
                (self.root / name).mkdir()
                (self.root / name / "keep.txt").write_text("mine")
                code, _, error = self.run_main(main, [name])
                self.assertEqual(code, 1, error)
                self.assertEqual((self.root / name / "keep.txt").read_text(), "mine")

    def test_missing_tools_are_reported(self) -> None:
        os.environ["PATH"] = str(self.bin)
        code, _, error = self.run_main(rust_command.main, ["needs-cargo"])
        self.assertNotEqual(code, 0)
        self.assertTrue(error)
        self.assertFalse((self.root / "needs-cargo" / "src").exists())

    def test_invalid_config_is_reported(self) -> None:
        self.tool("cargo")
        self.break_config()
        for main, args in ((py_command.main, ["p"]), (rust_command.main, ["r"]), (cpp_command.main, ["c"])):
            with self.subTest(args=args):
                self.assertEqual(self.run_main(main, args)[0], 2)

    def test_cpp_git_initialisation(self) -> None:
        log = self.tool("git")
        code, _, error = self.run_main(cpp_command.main, ["engine", "--std", "17", "--git"])
        self.assertEqual(code, 0, error)
        self.assertIn("CMAKE_CXX_STANDARD 17", (self.root / "engine" / "CMakeLists.txt").read_text())
        self.assertEqual(self.lines(log)[0].split("|")[0], "init")


if __name__ == "__main__":
    unittest.main()
