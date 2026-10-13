from __future__ import annotations

import gzip
import os
import shutil
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

from unlawful import archive  # noqa: E402

SEVEN_ZIP = archive._seven_zip()


class ArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        environment = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config")})
        environment.start()
        self.addCleanup(environment.stop)
        self.project = self.root / "work" / "project"
        (self.project / "sub").mkdir(parents=True)
        (self.project / "a.txt").write_text("hello " * 500, encoding="utf-8")
        (self.project / "sub" / "b.txt").write_text("nested", encoding="utf-8")
        (self.project / ".DS_Store").write_bytes(b"junk")
        (self.project / "sub" / "._b.txt").write_bytes(b"junk")

    def zip(self, *args: str) -> tuple[int, str, str]:
        with redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()) as error:
            code = archive.main(list(args))
        return code, output.getvalue(), error.getvalue()

    def files(self, directory: Path) -> set[str]:
        return {str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()}

    def round_trip(self, format_name: str, suffix: str) -> None:
        code, output, error = self.zip(str(self.project), "-f", format_name)
        self.assertEqual(code, 0, error)
        created = self.project.parent / f"project{suffix}"
        self.assertTrue(created.is_file(), output)
        self.assertIn("Created", output)
        destination = self.root / "out"
        code, output, error = self.zip("x", str(created), "-o", str(destination))
        self.assertEqual(code, 0, error)
        self.assertEqual(self.files(destination / "project"), {"a.txt", "sub/b.txt"})
        self.assertEqual((destination / "project" / "a.txt").read_text(encoding="utf-8"), "hello " * 500)
        self.assertEqual(self.zip("test", str(created))[0], 0)

    def test_help_has_no_side_effects(self) -> None:
        for args in ([], ["--help"], ["-h"], ["help"], ["x", "missing.zip", "--help"]):
            with self.subTest(args=args), patch("subprocess.run", side_effect=AssertionError), patch(
                "subprocess.Popen", side_effect=AssertionError
            ):
                code, output, _ = self.zip(*args)
                self.assertEqual(code, 0)
                self.assertIn("ul zip", output)

    def test_zip_is_the_default_and_drops_macos_junk(self) -> None:
        self.round_trip("zip", ".zip")
        code, _, _ = self.zip(str(self.project))
        self.assertEqual(code, 0)
        self.assertTrue((self.project.parent / "project 2.zip").is_file())

    @unittest.skipUnless(SEVEN_ZIP, "7-Zip is not installed")
    def test_7z_round_trip(self) -> None:
        self.round_trip("7z", ".7z")

    def test_tar_round_trips(self) -> None:
        formats = [("tar.gz", ".tar.gz"), ("tar.xz", ".tar.xz")]
        if shutil.which("zstd"):
            formats.append(("tar.zst", ".tar.zst"))
        for format_name, suffix in formats:
            with self.subTest(format=format_name):
                self.round_trip(format_name, suffix)
                shutil.rmtree(self.root / "out")

    def test_auto_mode_extracts_next_to_archive_without_overwriting(self) -> None:
        self.assertEqual(self.zip(str(self.project))[0], 0)
        created = self.project.parent / "project.zip"
        code, output, error = self.zip(str(created))
        self.assertEqual(code, 0, error)
        restored = self.project.parent / "project 2"
        self.assertEqual(self.files(restored), {"a.txt", "sub/b.txt"})
        self.assertIn("project 2", output)
        self.assertFalse(any(path.name.startswith(".unlaw-") for path in self.project.parent.iterdir()))

    def test_several_items_extract_into_folder_or_here(self) -> None:
        other = self.root / "work" / "notes.md"
        other.write_text("notes", encoding="utf-8")
        self.assertEqual(self.zip(str(self.project), str(other), "-o", str(self.root / "pack"))[0], 0)
        pack = self.root / "pack.zip"
        self.assertTrue(pack.is_file())
        self.assertEqual(self.zip("x", str(pack), "-o", str(self.root / "a"))[0], 0)
        self.assertEqual(self.files(self.root / "a" / "pack"), {"notes.md", "project/a.txt", "project/sub/b.txt"})
        self.assertEqual(self.zip("x", str(pack), "-o", str(self.root / "b"), "--here")[0], 0)
        self.assertEqual(self.files(self.root / "b"), {"notes.md", "project/a.txt", "project/sub/b.txt"})

    def test_single_compressed_stream(self) -> None:
        source = self.root / "log.txt.gz"
        with gzip.open(source, "wb") as handle:
            handle.write(b"line\n")
        self.assertEqual(self.zip(str(source))[0], 0)
        self.assertEqual((self.root / "log.txt").read_bytes(), b"line\n")
        self.assertEqual(self.zip("test", str(source))[0], 0)
        source.write_bytes(source.read_bytes()[:-6])
        self.assertEqual(self.zip("test", str(source))[0], 1)

    @unittest.skipUnless(SEVEN_ZIP, "7-Zip is not installed")
    def test_password_round_trip(self) -> None:
        with patch("sys.stdin.isatty", return_value=True), patch("getpass.getpass", return_value="s3cret"):
            code, output, error = self.zip(str(self.project), "-f", "7z", "-p")
            self.assertEqual(code, 0, error)
            self.assertIn("encrypted", output)
            created = self.project.parent / "project.7z"
            self.assertNotIn(b"a.txt", created.read_bytes())
            code, _, error = self.zip("x", str(created), "-o", str(self.root / "out"))
            self.assertEqual(code, 0, error)
        self.assertEqual(self.files(self.root / "out" / "project"), {"a.txt", "sub/b.txt"})
        with patch("sys.stdin.isatty", return_value=True), patch("getpass.getpass", return_value="wrong"):
            code, _, _ = self.zip("x", str(created), "-o", str(self.root / "bad"))
        self.assertNotEqual(code, 0)
        self.assertEqual(list((self.root / "bad").iterdir()), [])

    def test_fallback_without_seven_zip(self) -> None:
        with patch.object(archive, "_seven_zip", return_value=None):
            self.round_trip("zip", ".zip")
            code, _, error = self.zip(str(self.project), "-f", "7z")
        self.assertEqual(code, 1)
        self.assertIn("brew install sevenzip", error)

    def test_levels_map_to_native_settings(self) -> None:
        self.assertEqual([archive.parse_level(value) for value in ("ultra", "max", "store", "4", 6)], [9, 7, 0, 4, 6])
        for bad in ("10", "huge", -1, True):
            with self.subTest(bad=bad), self.assertRaises(archive.ArchiveError):
                archive.parse_level(bad)
        temporary = self.root / "x"
        command = lambda format_name, level: archive.create_commands(  # noqa: E731
            [self.project], temporary, format_name, level, password=False, keep_junk=False, seven_zip="/bin/7z"
        )
        self.assertIn("-mx=9", command("7z", 9)[0])
        self.assertIn("-mx=0", command("zip", 0)[0])
        with patch("shutil.which", return_value="/bin/tool"):
            self.assertEqual(command("tar.zst", 9)[1][:4], ["zstd", "--ultra", "-22", "--long=27"])
            self.assertEqual(command("tar.zst", 0)[1][:2], ["zstd", "-1"])
            self.assertIn("-m4", command("rar", 7)[0])
            self.assertIn("-m0", command("rar", 0)[0])
        self.assertIn("xz:compression-level=9,xz:threads=0", command("tar.xz", 9)[0])
        self.assertIn("gzip:compression-level=1", command("tar.gz", 0)[0])

    def test_level_flags_and_default(self) -> None:
        for args, expected in (([], "level 7 (max)"), (["-3"], "level 3 (fast)"), (["--ultra"], "level 9 (ultra)"),
                               (["-l", "store"], "level 0 (store)"), (["--level", "2"], "level 2,")):
            with self.subTest(args=args):
                code, output, error = self.zip(str(self.project), "-o", str(self.root / "levels" / "a.zip"), *args)
                self.assertEqual(code, 0, error)
                self.assertIn(expected, output)
        code, _, error = self.zip(str(self.project), "-l", "11")
        self.assertEqual(code, 1)
        self.assertIn("Invalid level", error)

    def test_media_heavy_input_drops_to_level_one_unless_level_is_explicit(self) -> None:
        media = self.root / "photos"
        media.mkdir()
        (media / "a.heic").write_bytes(os.urandom(200_000))
        (media / "note.txt").write_text("caption", encoding="utf-8")
        code, output, error = self.zip(str(media), "-f", "7z")
        self.assertEqual(code, 0, error)
        self.assertIn("already-compressed media", error)
        self.assertIn("level 1 (fastest)", output)
        code, output, error = self.zip(str(media), "-f", "7z", "-9")
        self.assertEqual(code, 0, error)
        self.assertNotIn("already-compressed", error)
        self.assertIn("level 9 (ultra)", output)

    def test_config_accepts_numeric_and_named_levels(self) -> None:
        import copy

        from unlawful.config import DEFAULT_CONFIG, validate_config

        for value, valid in ((9, True), (0, True), ("ultra", True), ("max", True), (10, False), ("huge", False), (True, False)):
            with self.subTest(value=value):
                config = copy.deepcopy(DEFAULT_CONFIG)
                config["zip"]["level"] = value
                self.assertEqual(not validate_config(config), valid)

    def test_naming_and_format_inference(self) -> None:
        file = self.root / "photo.png"
        file.write_bytes(b"png")
        self.assertEqual(archive.archive_target([file], None, "zip"), self.root / "photo.zip")
        self.assertEqual(archive.archive_target([self.project], str(self.root), "7z"), self.root / "project.7z")
        self.assertEqual(archive.archive_target([file], str(self.root / "x"), "tar.zst"), self.root / "x.tar.zst")
        self.assertEqual(archive.archive_stem(Path("a.tar.gz")), "a")
        self.assertEqual(archive.archive_stem(Path("movie.part1.rar")), "movie")
        self.assertEqual(archive.archive_stem(Path("log.txt.gz")), "log.txt")
        self.assertEqual(archive.normalize_format("tgz"), "tar.gz")
        code, _, error = self.zip(str(file), "-o", str(self.root / "pack.7z"), "-f", "zip")
        self.assertEqual(code, 1)
        self.assertIn("conflicts", error)

    def test_refuses_archive_inside_source_and_create_only_flags(self) -> None:
        code, _, error = self.zip(str(self.project), "-o", str(self.project / "self.zip"))
        self.assertEqual(code, 1)
        self.assertIn("inside the folder", error)
        code, _, error = self.zip("x", "a.zip", "-f", "7z")
        self.assertEqual(code, 1)
        self.assertIn("only applies when creating", error)

    def test_rar_command_and_missing_tool(self) -> None:
        temporary = self.root / ".tmp.rar"
        with patch("shutil.which", return_value=None):
            with self.assertRaisesRegex(archive.ArchiveError, "brew install --cask rar"):
                archive.create_commands([self.project], temporary, "rar", 9, password=True, keep_junk=False, seven_zip=None)
        with patch("shutil.which", return_value="/usr/local/bin/rar"):
            [command] = archive.create_commands(
                [self.project], temporary, "rar", 9, password=True, keep_junk=False, seven_zip=None
            )
        self.assertEqual(command[:3], ["rar", "a", "-m5"])
        self.assertIn("-hp", command)
        self.assertEqual(command[-2:], [str(temporary), str(self.project)])

    def test_seeded_standalone_command_round_trip(self) -> None:
        from unlawful.config import ensure_layout

        script = ensure_layout() / "commands" / "zip" / "main.py"
        source = script.read_text(encoding="utf-8")
        self.assertNotIn("unlawful", source.replace("unlaw zip", ""))
        self.assertIn("DEFAULT_CONFIG", source)
        environment = {**os.environ, "PYTHONPATH": ""}
        run = lambda *args: subprocess.run(  # noqa: E731
            [sys.executable, "-I", str(script), *args], capture_output=True, text=True, env=environment, check=False
        )
        created = run(str(self.project))
        self.assertEqual(created.returncode, 0, created.stderr)
        extracted = run("x", str(self.project.parent / "project.zip"), "-o", str(self.root / "seeded"))
        self.assertEqual(extracted.returncode, 0, extracted.stderr)
        self.assertEqual(self.files(self.root / "seeded" / "project"), {"a.txt", "sub/b.txt"})


if __name__ == "__main__":
    unittest.main()
