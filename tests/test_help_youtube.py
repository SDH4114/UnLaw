from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
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


    def test_podcast_saves_small_tagged_mp3_into_podcast_dir(self):
        from unlawful.config import ensure_layout, set_config_value
        ensure_layout()
        (self.root / "iCloud").mkdir()
        folder = self.root / "iCloud" / "Podcasts"
        set_config_value("yt.podcast_dir", str(folder))
        code, run, error = self._download(["https://youtu.be/example", "--podcast"])
        self.assertEqual(code, 0, error)
        args = run.call_args.args[0]
        self.assertEqual(Path(args[args.index("--paths") + 1]).parent, folder)
        self.assertEqual(args[args.index("--audio-format") + 1], "mp3")
        self.assertEqual(args[args.index("--audio-quality") + 1], "64K")
        self.assertEqual(args[args.index("--postprocessor-args") + 1], "ExtractAudio+ffmpeg_o:-ac 1")
        for flag in ("--extract-audio", "--embed-metadata", "--embed-thumbnail", "--no-playlist", "--no-overwrites"):
            self.assertIn(flag, args)
        self.assertNotIn("--recode-video", args)
        self.assertTrue((folder / "fake.mov").exists())

    def test_podcast_output_overrides_podcast_dir(self):
        target = self.root / "elsewhere"
        code, run, error = self._download(["https://youtu.be/example", "--podcast", "--output", str(target)])
        self.assertEqual(code, 0, error)
        args = run.call_args.args[0]
        self.assertEqual(Path(args[args.index("--paths") + 1]).parent, target)

    def test_podcast_refuses_missing_icloud_drive(self):
        from unlawful.config import ensure_layout, set_config_value
        ensure_layout()
        folder = self.root / "no-icloud" / "Podcasts"
        set_config_value("yt.podcast_dir", str(folder))
        code, run, error = self._download(["https://youtu.be/example", "--podcast"])
        self.assertEqual(code, 1)
        self.assertIn("iCloud Drive", error)
        self.assertFalse(folder.parent.exists())
        run.assert_not_called()
        set_config_value("yt.podcast_dir", "relative/Podcasts")
        code, run, error = self._download(["https://youtu.be/example", "--podcast"])
        self.assertEqual(code, 2)
        self.assertIn("absolute", error)
        run.assert_not_called()

    def test_podcast_rejects_video_and_other_modes(self):
        for extra in (["--audio"], ["--sub"], ["--full"], ["--format", "mp4"], ["--quality", "720"], ["--sub-lang", "en"]):
            with self.subTest(extra=extra):
                code, run, error = self._download(["https://youtu.be/example", "--podcast", *extra])
                self.assertEqual(code, 2)
                run.assert_not_called()

    def test_seeded_podcast_default_is_icloud_drive(self):
        from unlawful.config import ensure_layout
        root = ensure_layout()
        tools = self.root / "bin"
        tools.mkdir()
        for name in ("yt-dlp", "ffmpeg", "ffprobe"):
            script = tools / name
            script.write_text(f"#!{sys.executable}\nraise SystemExit(9)\n")
            script.chmod(0o755)
        home = self.root / "home"
        home.mkdir()
        result = subprocess.run(
            [sys.executable, str(root / "commands/yt/main.py"), "download", "https://youtu.be/example", "--podcast"],
            env={**os.environ, "PATH": str(tools), "HOME": str(home)}, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(str(home / "Library/Mobile Documents/com~apple~CloudDocs"), result.stderr)
        self.assertIn("iCloud Drive", result.stderr)



class DownloadFlowTests(unittest.TestCase):
    """The plain download: one metadata probe, then the download; fake yt-dlp, no network."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.commands = []
        self.stop_download = None

    def tool(self, command, **kwargs):
        self.commands.append(command)
        stage = Path(command[command.index("--paths") + 1])
        if "--write-info-json" in command:
            (stage / "Clip [abc].info.json").write_text("{}")
            return subprocess.CompletedProcess(command, 0, "", "")
        if self.stop_download is not None:
            (stage / "partial.part").write_bytes(b"half")
            raise self.stop_download
        media = stage / ("Clip [abc].mp3" if "--extract-audio" in command else "Clip [abc].mov")
        media.write_bytes(b"media")
        Path(command[command.index("--print-to-file") + 2]).write_text(json.dumps(str(media)))
        return subprocess.CompletedProcess(command, 0)

    def download(self, *flags):
        from unlawful.desktop import youtube
        with patch.object(youtube.shutil, "which", side_effect=lambda name: f"/tools/{name}"), patch.object(
            youtube.subprocess, "run", side_effect=self.tool
        ), redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()) as error:
            code = youtube.main(["download", "https://youtu.be/abc", "--output", str(self.root), *flags])
        return code, out.getvalue(), error.getvalue()

    def test_an_existing_file_is_found_before_anything_is_downloaded(self):
        (self.root / "Clip [abc].mov").write_bytes(b"mine")
        code, out, _ = self.download()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.commands), 1, "only the metadata probe may run")
        self.assertIn("Already exists", out)
        self.assertEqual((self.root / "Clip [abc].mov").read_bytes(), b"mine")
        (self.root / "Clip [abc].mp3").write_bytes(b"mine")
        self.commands.clear()
        self.assertEqual(self.download("--audio")[0], 0)
        self.assertEqual(len(self.commands), 1)

    def test_the_download_reuses_the_probed_metadata(self):
        code, out, _ = self.download()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.commands), 2)
        download = self.commands[1]
        self.assertEqual(Path(download[download.index("--load-info-json") + 1]).name, "Clip [abc].info.json")
        self.assertNotIn("https://youtu.be/abc", download)
        self.assertEqual((self.root / "Clip [abc].mov").read_bytes(), b"media")
        self.assertIn("Saved:", out)

    def test_json_prints_one_result_object_and_keeps_messages_off_stdout(self):
        code, out, error = self.download("--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"ok": True, "exit": 0, "files": [{"path": str(self.root / "Clip [abc].mov"), "status": "saved"}]})
        self.assertIn("Saved:", error)
        code, out, _ = self.download("--json")
        self.assertEqual(json.loads(out)["files"], [{"path": str(self.root / "Clip [abc].mov"), "status": "exists"}])
        from unlawful.desktop import youtube
        with redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()):
            code = youtube.main(["download", "https://example.com/x", "--json"])
        self.assertEqual(json.loads(out.getvalue()), {"ok": False, "exit": 2, "files": []})

    def test_a_terminated_download_removes_its_staging_folder(self):
        from unlawful.desktop import youtube
        self.stop_download = youtube._Stopped(15)
        code, _, error = self.download()
        self.assertEqual(code, 143)
        self.assertIn("cancelled", error)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_stale_staging_folders_are_swept_and_fresh_ones_kept(self):
        stale, fresh, other = self.root / ".unlaw-yt-old", self.root / ".unlaw-yt-new", self.root / "keep"
        for folder in (stale, fresh, other):
            folder.mkdir()
            (folder / "x.part").write_bytes(b"x")
        two_days_ago = time.time() - 2 * 24 * 3600
        os.utime(stale, (two_days_ago, two_days_ago))
        os.utime(other, (two_days_ago, two_days_ago))
        self.assertEqual(self.download()[0], 0)
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.is_dir() and other.is_dir())


if __name__ == "__main__":
    unittest.main()
