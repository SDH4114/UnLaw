from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class HelpAndYouTubeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.env = {"XDG_CONFIG_HOME": str(self.root / "config")}
        self.environment = patch.dict(os.environ, self.env)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_every_seeded_command_help_is_standalone_and_has_no_side_effects(self):
        from unlawful.config import DEFAULT_COMMAND_NAMES, ensure_layout
        from unlawful.command_help import COMMAND_HELP
        root = ensure_layout()
        for name in DEFAULT_COMMAND_NAMES:
            script = root / "commands" / name / "main.py"
            module_name = f"help_test_{name}"
            spec = importlib.util.spec_from_file_location(module_name, script)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            self.addCleanup(sys.modules.pop, module_name, None)
            spec.loader.exec_module(module)
            for flag in ("--help", "-h", "help"):
                with self.subTest(name=name, flag=flag), redirect_stdout(StringIO()) as output, patch(
                    "subprocess.run", side_effect=AssertionError("help must not run a process")
                ), patch.object(module, "load_config", side_effect=AssertionError("help must not read config"), create=True):
                    self.assertEqual(module.main([flag]), 0)
                    self.assertEqual(output.getvalue(), COMMAND_HELP[name])
                    self.assertIn(f"ul {name}", output.getvalue())
                    self.assertIn("Example", output.getvalue())

    def test_every_system_command_has_help(self):
        from unlawful.cli import SYSTEM_COMMANDS
        from unlawful.command_help import COMMAND_HELP
        for name, function in SYSTEM_COMMANDS.items():
            with self.subTest(name=name), redirect_stdout(StringIO()) as output, patch(
                "subprocess.run", side_effect=AssertionError("help must not run a process")
            ):
                self.assertEqual(function(["--help"]), 0)
                self.assertEqual(output.getvalue(), COMMAND_HELP[name])

    def test_cli_help_alias_and_new_command_template(self):
        from unlawful.cli import main
        from unlawful.config import set_config_value
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(main(["help", "yt"]), 0)
            self.assertEqual(main(["create", "command", "hello"]), 0)
        # run_command inherits stdout, so capture via actual isolated subprocess.
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        result = subprocess.run([sys.executable, "-m", "unlawful.cli", "hello", "--help"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage: ul hello", result.stdout)
        set_config_value("aliases", {"youtube": ["yt"]})
        result = subprocess.run([sys.executable, "-m", "unlawful.cli", "youtube", "--help"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ul yt download", result.stdout)

    def test_template_help_does_not_launch_project(self):
        from unlawful.cli import main
        from unlawful.workspace_templates import create_workspace_template
        from unlawful.config import ensure_layout
        ensure_layout()
        create_workspace_template("demo", self.root, "zed", False)
        with redirect_stdout(StringIO()) as output, patch("subprocess.run", side_effect=AssertionError("no launch")):
            self.assertEqual(main(["demo", "--help"]), 0)
        self.assertIn("Usage: ul demo", output.getvalue())

    def _download(self, args, *, missing=(), returncode=0):
        def completed(command, **kwargs):
            if returncode == 0 and "--print-to-file" in command:
                stage = Path(command[command.index("--paths") + 1])
                media = stage / "fake.mov"
                media.write_bytes(b"media")
                manifest = Path(command[command.index("--print-to-file") + 2])
                manifest.write_text(json.dumps(str(media)))
            return subprocess.CompletedProcess(command, returncode)
        from unlawful.desktop import youtube
        with patch.object(youtube.shutil, "which", side_effect=lambda name: None if name in missing else f"/tools/{name}"), patch.object(
            youtube.subprocess, "run", side_effect=completed
        ) as run, redirect_stdout(StringIO()), redirect_stderr(StringIO()) as error:
            code = youtube.main(["download", *args])
        return code, run, error.getvalue()

    def test_video_quality_output_and_failure_exit_code(self):
        target = self.root / "videos with spaces"
        code, run, _ = self._download(["https://youtu.be/example", "--quality", "1080", "--output", str(target)], returncode=7)
        self.assertEqual(code, 7)
        args = run.call_args.args[0]
        self.assertTrue(target.is_dir())
        self.assertEqual(args[-2:], ["--", "https://youtu.be/example"])
        self.assertEqual(args[args.index("--format") + 1], "bestvideo*[height<=1080]+bestaudio/best[height<=1080]")
        for flag in ("--no-playlist", "--no-overwrites", "--no-post-overwrites", "--ignore-config"):
            self.assertIn(flag, args)
        self.assertEqual(Path(args[args.index("--paths") + 1]).parent, target)
        self.assertEqual(args[args.index("--recode-video") + 1], "mov")

    def test_media_conversion_never_overwrites_existing_destination(self):
        destination = self.root / 'fake.mov'
        destination.write_bytes(b'my original video')
        code, _, error = self._download(['https://youtu.be/example', '--output', str(self.root)])
        self.assertEqual(code, 0, error)
        self.assertEqual(destination.read_bytes(), b'my original video')
        self.assertFalse(list(self.root.glob('.unlaw-yt-*')))

    def test_video_container_choices(self):
        for container in ("mov", "mp4", "raw"):
            with self.subTest(container=container):
                code, run, _ = self._download(["https://youtu.be/example", "--format", container, "--output", str(self.root)])
                self.assertEqual(code, 0)
                args = run.call_args.args[0]
                if container == "raw":
                    self.assertNotIn("--recode-video", args)
                    self.assertNotIn("--postprocessor-args", args)
                    self.assertNotIn("--merge-output-format", args)
                else:
                    self.assertEqual(args[args.index("--recode-video") + 1], container)
                    self.assertIn("libx264", args[args.index("--postprocessor-args") + 1])

    def test_audio_mp3_and_configured_storage(self):
        from unlawful.config import ensure_layout, set_config_value
        ensure_layout()
        target = self.root / "storage"
        set_config_value("storage.root", str(target))
        code, run, _ = self._download(["https://www.youtube.com/watch?v=example&list=playlist", "--audio"])
        self.assertEqual(code, 0)
        args = run.call_args.args[0]
        self.assertIn("--extract-audio", args)
        self.assertNotIn("--recode-video", args)
        self.assertEqual(args[args.index("--audio-format") + 1], "mp3")
        self.assertEqual(Path(args[args.index("--paths") + 1]).parent, target / "youtube")

    def test_invalid_download_arguments_do_not_launch_or_create_output(self):
        cases = [["https://youtu.be/example", "--format", "webm"],
                 ["https://youtu.be/example", "--audio", "--format", "mp4"], [], ["https://[invalid"], ["https://evil.example/video"], ["file:///tmp/video"], ["--quality", "1080"],
                 ["https://youtu.be/example", "--quality", "0"], ["https://youtu.be/example", "--quality", "abc"],
                 ["https://youtu.be/example", "--audio", "--quality", "720"], ["https://youtu.be/example", "--output"],
                 ["https://youtu.be/example", "--unknown"], ["https://youtube.com/playlist?list=all"],
                 ["https://youtube.com/@someone"], ["https://youtube.com.evil.example/watch?v=x"]]
        for args in cases:
            with self.subTest(args=args):
                code, run, _ = self._download(args)
                self.assertEqual(code, 2)
                run.assert_not_called()

    def test_missing_tools_have_install_instructions(self):
        for tool in ("yt-dlp", "ffmpeg", "ffprobe"):
            with self.subTest(tool=tool):
                code, run, error = self._download(["https://youtu.be/example"], missing=(tool,))
                self.assertEqual(code, 1)
                self.assertIn(tool, error)
                self.assertIn("brew install", error)
                run.assert_not_called()

    def test_download_help_needs_no_dependencies(self):
        code, run, error = self._download(["--help"], missing=("yt-dlp", "ffmpeg", "ffprobe"))
        self.assertEqual(code, 0)
        run.assert_not_called()
        self.assertEqual(error, "")

    def test_official_previous_sources_upgrade_and_edits_survive(self):
        from unlawful.config import ensure_layout
        from unlawful.command_sources import is_replaceable_command_source, LEGACY_SOURCE_HASHES
        root = ensure_layout()
        script = root / "commands" / "yt" / "main.py"
        custom = script.read_text() + "\n# My custom change\n"
        script.write_text(custom)
        self.assertFalse(is_replaceable_command_source(custom, "yt"))
        ensure_layout()
        self.assertEqual(script.read_text(), custom)
        self.assertIn("1a1cc7ec191f33960644a15553cf02b796af6deffd5380f245e408561c8998cb", LEGACY_SOURCE_HASHES["yt"])

    def test_real_seeded_download_launches_external_tool(self):
        from unlawful.config import ensure_layout
        root = ensure_layout()
        tools = self.root / "bin"
        tools.mkdir()
        capture = self.root / "arguments.json"
        for name in ("yt-dlp", "ffmpeg", "ffprobe"):
            script = tools / name
            script.write_text(f"#!{sys.executable}\nimport sys,json,pathlib\nargs=sys.argv[1:]\npathlib.Path({str(capture)!r}).write_text(json.dumps(args))\nif '--print-to-file' in args:\n    media=pathlib.Path(args[args.index('--paths')+1])/'fake.mp3'\n    media.write_bytes(b'media')\n    pathlib.Path(args[args.index('--print-to-file')+2]).write_text(json.dumps(str(media)))\n")
            script.chmod(0o755)
        target = self.root / "download"
        result = subprocess.run([sys.executable, str(root / "commands/yt/main.py"), "download", "https://youtu.be/example", "--audio", "--output", str(target)], env={**os.environ, "PATH": str(tools)}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(capture.read_text())
        self.assertIn("--extract-audio", args)
        self.assertEqual(Path(args[args.index("--paths") + 1]).parent, target)
        self.assertTrue((target / "fake.mp3").exists())


if __name__ == "__main__":
    unittest.main()
