from __future__ import annotations

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from unlawful.desktop import youtube


class SubtitleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.info = {
            "id": "example", "title": "Пример видео", "language": "ru",
            "automatic_captions": {"ru-orig": [{"ext": "json3", "name": "Russian (Original)"}],
                                   "en": [{"ext": "json3", "name": "English"}]},
            "subtitles": {},
        }
        self.calls = []
        self.caption_failure = False
        self.metadata_code = 0

    def run_tool(self, command, **kwargs):
        self.calls.append(command)
        if "--dump-single-json" in command:
            return subprocess.CompletedProcess(command, self.metadata_code, json.dumps(self.info), "network error" if self.metadata_code else "")
        if command[0] == "ffmpeg":
            for argument in command:
                if argument.endswith(("audio.mp3", "finished.mov", "finished.mp4")):
                    Path(argument).write_bytes(b"converted")
            return subprocess.CompletedProcess(command, 0)
        stage = Path(command[command.index("--paths") + 1])
        if "--skip-download" in command:
            if self.caption_failure:
                return subprocess.CompletedProcess(command, 1)
            (stage / "captions.ru-orig.json3").write_text(json.dumps({"events": [
                {"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "Привет мир"}]},
                {"tStartMs": 1000, "dDurationMs": 2000, "segs": [{"utf8": "мир снова"}]},
            ]}), encoding="utf-8")
        else:
            (stage / "media.webm").write_bytes(b"original")
        return subprocess.CompletedProcess(command, 0)

    def invoke(self, flags, *, missing=()):
        with patch.object(youtube.shutil, "which", side_effect=lambda name: None if name in missing else name), patch.object(
            youtube.subprocess, "run", side_effect=self.run_tool
        ), redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()) as err:
            code = youtube.main(["download", "https://youtu.be/example?si=test", "--output", str(self.root), *flags])
        return code, out.getvalue(), err.getvalue()

    def test_original_subtitles_without_ffmpeg_and_source_link_first(self):
        code, out, err = self.invoke(["--sub"], missing=("ffmpeg", "ffprobe"))
        self.assertEqual(code, 0, err)
        files = list(self.root.iterdir())
        self.assertEqual(len(files), 1)
        text = files[0].read_text()
        self.assertEqual(text.splitlines()[0], "<https://youtu.be/example?si=test>")
        self.assertIn("Привет мир снова", text)
        self.assertIn("automatic", text)
        self.assertTrue(files[0].name.endswith("ru-orig.md"))
        self.assertTrue(all("--skip-download" in call for call in self.calls))
        self.assertIn("--load-info-json", self.calls[1])
        self.assertIn("^ru\\-orig$", self.calls[1])

    def test_sub_lang_without_value_and_explicit_original(self):
        for flags in (["--sub-lang"], ["--sub-lang", "original"]):
            with self.subTest(flags=flags):
                code, _, err = self.invoke(flags)
                self.assertEqual(code, 0, err)
                self.assertTrue(any(self.root.glob("*.ru-orig.md")))

    def test_unknown_language_lists_available_without_media_download(self):
        code, _, err = self.invoke(["--sub-lang", "incorrect"])
        self.assertEqual(code, 2)
        self.assertIn("Available languages", err)
        self.assertIn("ru-orig", err)
        self.assertIn("en", err)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_authored_original_preferred_and_live_chat_excluded(self):
        self.info['subtitles'] = {"ru": [{"ext": "vtt"}], "live_chat": [{"ext": "json"}]}
        self.assertEqual(youtube._select_subtitle(self.info, None), ("ru", False))
        self.assertNotIn("live_chat", youtube._caption_tracks(self.info))
        self.assertEqual(youtube._select_subtitle(self.info, "en"), ("en", True))
        self.assertEqual(youtube._select_subtitle(self.info, "RU"), ("ru", False))

    def test_full_downloads_media_once_and_reads_it_once_for_video_and_mp3(self):
        code, _, err = self.invoke(["--full", "--quality", "720", "--format", "mp4"])
        self.assertEqual(code, 0, err)
        self.assertEqual({path.suffix for path in self.root.iterdir()}, {".md", ".mp3", ".mp4"})
        media_calls = [call for call in self.calls if call[0] != 'ffmpeg' and "--skip-download" not in call]
        self.assertEqual(len(media_calls), 1)
        self.assertIn("bestvideo*[height<=720]+bestaudio/best[height<=720]", media_calls[0])
        ffmpeg_calls = [call for call in self.calls if call[0] == 'ffmpeg']
        self.assertEqual(len(ffmpeg_calls), 1)
        self.assertEqual(ffmpeg_calls[0].count("-i"), 1)
        self.assertEqual(sum("--dump-single-json" in call for call in self.calls), 1)

    def test_full_raw_keeps_source_and_extracts_only_mp3(self):
        code, _, err = self.invoke(["--full", "--format", "raw"])
        self.assertEqual(code, 0, err)
        self.assertEqual({path.suffix for path in self.root.iterdir()}, {".md", ".mp3", ".webm"})
        ffmpeg = next(call for call in self.calls if call[0] == 'ffmpeg')
        self.assertNotIn("libx264", ffmpeg)
        self.assertEqual(next(self.root.glob("*.webm")).read_bytes(), b"original")

    def test_missing_subtitles_returns_failure_and_full_retains_media(self):
        self.info['automatic_captions'] = {}
        code, _, err = self.invoke(["--sub"])
        self.assertEqual(code, 1)
        self.assertIn("No subtitles", err)
        self.assertEqual(list(self.root.iterdir()), [])
        code, _, err = self.invoke(["--full"])
        self.assertEqual(code, 1)
        self.assertIn("Incomplete", err)
        self.assertEqual({path.suffix for path in self.root.iterdir()}, {".mov", ".mp3"})

    def test_failed_captions_do_not_block_full_media(self):
        self.caption_failure = True
        code, _, err = self.invoke(["--full"])
        self.assertEqual(code, 1)
        self.assertIn("Incomplete", err)
        self.assertEqual({path.suffix for path in self.root.iterdir()}, {".mov", ".mp3"})

    def test_existing_outputs_are_not_modified(self):
        self.assertEqual(self.invoke(["--full"])[0], 0)
        snapshots = {path: path.read_bytes() for path in self.root.iterdir()}
        self.calls.clear()
        code, _, err = self.invoke(["--full"])
        self.assertEqual(code, 0, err)
        self.assertEqual({path: path.read_bytes() for path in self.root.iterdir()}, snapshots)
        self.assertEqual(len(self.calls), 1, 'only metadata is fetched on repeat')

    def test_metadata_failure_preserves_external_exit_code(self):
        self.metadata_code = 7
        code, _, err = self.invoke(["--sub"])
        self.assertEqual(code, 7)
        self.assertIn("network error", err)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_conflicting_modes_and_video_options_do_not_run(self):
        for flags in (["--sub", "--full"], ["--audio", "--sub"], ["--sub", "--quality", "720"],
                      ["--sub-lang", "ru", "--format", "mp4"], ["--audio", "--sub-lang"], ["--full", "--audio"]):
            self.calls.clear()
            with self.subTest(flags=flags):
                code, _, _ = self.invoke(flags)
                self.assertEqual(code, 2)
                self.assertEqual(self.calls, [])

    def test_vtt_cleanup_preserves_nonoverlapping_spoken_repeats(self):
        path = self.root / "test.vtt"
        path.write_text('WEBVTT\n\nNOTE metadata\nignore\n\n1\n00:00:00.000 --> 00:00:02.000\n<c>Hello &amp; world</c>\n\n2\n00:00:01.000 --> 00:00:03.000\nworld again\n\n3\n00:00:04.000 --> 00:00:05.000\nagain\n')
        self.assertEqual(youtube._subtitle_text(path), 'Hello & world again again')

    def test_sound_and_speaker_markers_are_removed(self):
        path = self.root / 'cues.json3'
        path.write_text(json.dumps({'events': [
            {'tStartMs': 0, 'dDurationMs': 1000, 'segs': [{'utf8': '[музыка] >> Hello [Music] world'}]}
        ]}))
        self.assertEqual(youtube._subtitle_text(path), 'Hello world')
        path.write_text('[]')
        with self.assertRaises(ValueError):
            youtube._subtitle_text(path)

    def test_raw_bundle_repeat_does_not_download_again(self):
        self.assertEqual(self.invoke(['--full', '--format', 'raw'])[0], 0)
        self.calls.clear()
        self.assertEqual(self.invoke(['--full', '--format', 'raw'])[0], 0)
        self.assertEqual(len(self.calls), 1)

    def test_srt_multiline_and_empty_captions(self):
        path = self.root / "test.srt"
        path.write_text('1\n00:00:00,000 --> 00:00:01,000\nHello\nworld\n')
        self.assertEqual(youtube._subtitle_text(path), 'Hello world')
        path.write_text('')
        with self.assertRaises(ValueError):
            youtube._subtitle_text(path)

    def test_publish_never_overwrites_existing_file(self):
        source = self.root / 'staged.md'
        destination = self.root / 'existing.md'
        source.write_text('new')
        destination.write_text('original')
        with redirect_stdout(StringIO()):
            youtube._publish(source, destination)
        self.assertEqual(destination.read_text(), 'original')

    def test_safe_names_do_not_escape_output_and_keep_utf8(self):
        name = youtube._safe_name('../' + 'я' * 200 + '\\x')
        self.assertNotIn('/', name)
        self.assertNotIn('\\', name)
        self.assertLessEqual(len(name.encode()), 180)


if __name__ == '__main__':
    unittest.main()
