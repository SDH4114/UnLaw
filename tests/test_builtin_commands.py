"""The built-in Rust commands (zip, game), migration from their Python seeds, and Rust user commands."""

from __future__ import annotations

import fcntl
import gzip
import os
import pty
import select
import shutil
import struct
import subprocess
import sys
import termios
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ulbin import CoreTestCase, binary  # noqa: E402

SEVEN_ZIP = shutil.which("7zz") or shutil.which("7z") or shutil.which("7za")


class ZipTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = self.root / "work" / "project"
        (self.project / "sub").mkdir(parents=True)
        (self.project / "a.txt").write_text("hello " * 500)
        (self.project / "sub" / "b.txt").write_text("nested")
        (self.project / ".DS_Store").write_bytes(b"junk")
        (self.project / "sub" / "._b.txt").write_bytes(b"junk")

    def zip(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return self.ul("zip", *args, env=env, cwd=self.root)

    def files(self, directory: Path) -> set[str]:
        return {str(path.relative_to(directory)) for path in directory.rglob("*") if path.is_file()}

    def round_trip(self, format_name: str, suffix: str, env: dict[str, str] | None = None) -> None:
        created = self.zip(str(self.project), "-f", format_name, env=env)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertIn("Created", created.stdout)
        archive = self.project.parent / f"project{suffix}"
        self.assertTrue(archive.is_file())
        destination = self.root / f"out-{format_name}"
        extracted = self.zip("x", str(archive), "-o", str(destination), env=env)
        self.assertEqual(extracted.returncode, 0, extracted.stderr)
        self.assertEqual(self.files(destination / "project"), {"a.txt", "sub/b.txt"})
        self.assertEqual((destination / "project" / "a.txt").read_text(), "hello " * 500)
        self.assertEqual(self.zip("test", str(archive), env=env).returncode, 0)

    def test_help_has_no_side_effects(self) -> None:
        for args in ([], ["--help"], ["-h"], ["help"], ["x", "missing.zip", "--help"]):
            with self.subTest(args=args):
                result = self.zip(*args)
                self.assertEqual(result.returncode, 0)
                self.assertIn("ul zip", result.stdout)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["bin", "config", "home", "work"])

    def test_zip_is_the_default_drops_junk_and_never_overwrites(self) -> None:
        self.round_trip("zip", ".zip")
        self.assertEqual(self.zip(str(self.project)).returncode, 0)
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

    def test_auto_mode_extracts_next_to_the_archive_without_overwriting(self) -> None:
        self.assertEqual(self.zip(str(self.project)).returncode, 0)
        result = self.zip(str(self.project.parent / "project.zip"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.files(self.project.parent / "project 2"), {"a.txt", "sub/b.txt"})
        self.assertIn("project 2", result.stdout)
        self.assertFalse(any(path.name.startswith(".unlaw-") for path in self.project.parent.iterdir()))

    def test_several_items_extract_into_a_folder_or_here(self) -> None:
        other = self.root / "work" / "notes.md"
        other.write_text("notes")
        self.assertEqual(self.zip(str(self.project), str(other), "-o", str(self.root / "pack")).returncode, 0)
        pack = self.root / "pack.zip"
        self.assertEqual(self.zip("x", str(pack), "-o", str(self.root / "a")).returncode, 0)
        self.assertEqual(self.files(self.root / "a" / "pack"), {"notes.md", "project/a.txt", "project/sub/b.txt"})
        self.assertEqual(self.zip("x", str(pack), "-o", str(self.root / "b"), "--here").returncode, 0)
        self.assertEqual(self.files(self.root / "b"), {"notes.md", "project/a.txt", "project/sub/b.txt"})
        self.assertIn("project", self.zip("ls", str(pack)).stdout)

    def test_single_compressed_streams(self) -> None:
        source = self.root / "log.txt.gz"
        with gzip.open(source, "wb") as handle:
            handle.write(b"line\n")
        self.assertEqual(self.zip(str(source)).returncode, 0)
        self.assertEqual((self.root / "log.txt").read_bytes(), b"line\n")
        self.assertEqual(self.zip("test", str(source)).returncode, 0)
        self.assertIn("(single compressed file)", self.zip("ls", str(source)).stdout)
        source.write_bytes(source.read_bytes()[:-6])
        result = self.zip("test", str(source))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Test failed", result.stderr)

    def test_fallback_without_seven_zip(self) -> None:
        env = {"PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"}
        self.round_trip("zip", ".zip", env=env)
        result = self.zip(str(self.project), "-f", "7z", env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("brew install sevenzip", result.stderr)
        result = self.zip(str(self.project), "-p", env=env)
        self.assertIn("AES-256", result.stderr)

    def test_level_flags_default_and_errors(self) -> None:
        for args, expected in (
            ([], "level 7 (max)"),
            (["-3"], "level 3 (fast)"),
            (["--ultra"], "level 9 (ultra)"),
            (["-l", "store"], "level 0 (store)"),
            (["--level=2"], "level 2,"),
        ):
            with self.subTest(args=args):
                result = self.zip(str(self.project), "-o", str(self.root / "levels" / "a.zip"), *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)
        result = self.zip(str(self.project), "-l", "11")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Invalid level", result.stderr)
        self.ok("config", "set", "zip.level", "3")
        self.assertIn("level 3 (fast)", self.zip(str(self.project), "-o", str(self.root / "cfg.zip")).stdout)

    def test_media_heavy_input_drops_to_level_one_unless_a_level_is_given(self) -> None:
        media = self.root / "photos"
        media.mkdir()
        (media / "a.heic").write_bytes(os.urandom(200_000))
        (media / "note.txt").write_text("caption")
        result = self.zip(str(media), "-f", "tar.gz")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already-compressed media", result.stderr)
        self.assertIn("level 1 (fastest)", result.stdout)
        result = self.zip(str(media), "-f", "tar.gz", "-9")
        self.assertNotIn("already-compressed", result.stderr)
        self.assertIn("level 9 (ultra)", result.stdout)

    def test_naming_conflicts_and_refusals(self) -> None:
        photo = self.root / "photo.png"
        photo.write_bytes(b"png")
        self.assertEqual(self.zip(str(photo)).returncode, 0)
        self.assertTrue((self.root / "photo.zip").is_file())
        result = self.zip(str(photo), "-o", str(self.root / "pack.7z"), "-f", "zip")
        self.assertEqual(result.returncode, 1)
        self.assertIn("conflicts", result.stderr)
        result = self.zip(str(self.project), "-o", str(self.project / "self.zip"))
        self.assertIn("inside the folder", result.stderr)
        result = self.zip("x", "a.zip", "-f", "7z")
        self.assertIn("only applies when creating", result.stderr)
        self.assertIn("--here only applies when extracting", self.zip(str(self.project), "--here").stderr)
        self.assertIn("do not apply to ls/test", self.zip("ls", "a.zip", "-o", "x").stderr)
        self.assertIn("Not found", self.zip("c", str(self.root / "missing")).stderr)
        self.assertIn("Archive not found", self.zip("x", str(self.root / "missing.zip")).stderr)
        twin = self.root / "other" / "project"
        twin.mkdir(parents=True)
        self.assertIn("share the name", self.zip(str(self.project), str(twin)).stderr)
        self.assertEqual(self.zip("--bogus", "x").returncode, 2)
        self.assertIn("Unknown format", self.zip(str(self.project), "-f", "cpio").stderr)

    def test_rar_needs_the_rar_tool(self) -> None:
        result = self.zip(str(self.project), "-f", "rar", env={"PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("brew install --cask rar", result.stderr)

    def test_password_without_a_terminal_is_refused(self) -> None:
        if not SEVEN_ZIP:
            self.skipTest("7-Zip is not installed")
        result = self.zip(str(self.project), "-f", "7z", "-p")
        self.assertEqual(result.returncode, 1)
        self.assertIn("needs an interactive terminal", result.stderr)
        self.assertFalse((self.project.parent / "project.7z").exists())

    @unittest.skipUnless(SEVEN_ZIP, "7-Zip is not installed")
    def test_password_round_trip_through_a_terminal(self) -> None:
        def run_with_tty(args: list[str], answers: list[bytes]) -> tuple[int, bytes]:
            master, slave = pty.openpty()
            process = subprocess.Popen(
                [str(binary()), "zip", *args], stdin=slave, stdout=subprocess.PIPE, stderr=slave, env=self.env, cwd=self.root
            )
            os.close(slave)
            seen = b""
            pending = list(answers)
            while process.poll() is None:
                ready, _, _ = select.select([master], [], [], 0.2)
                if ready:
                    try:
                        seen += os.read(master, 1024)
                    except OSError:
                        break
                if pending and seen.count(b"password:") >= len(answers) - len(pending) + 1:
                    os.write(master, pending.pop(0))
            output = process.stdout.read() if process.stdout else b""
            process.wait(timeout=30)
            os.close(master)
            return process.returncode, seen + output

        code, output = run_with_tty([str(self.project), "-f", "7z", "-p"], [b"s3cret\n", b"s3cret\n"])
        self.assertEqual(code, 0, output)
        self.assertIn(b"encrypted", output)
        self.assertNotIn(b"s3cret", output, "the password is never echoed")
        archive = self.project.parent / "project.7z"
        self.assertNotIn(b"a.txt", archive.read_bytes(), "7z hides file names")
        code, output = run_with_tty(["x", str(archive), "-o", str(self.root / "out")], [b"s3cret\n"])
        self.assertEqual(code, 0, output)
        self.assertEqual(self.files(self.root / "out" / "project"), {"a.txt", "sub/b.txt"})
        code, _ = run_with_tty(["x", str(archive), "-o", str(self.root / "bad")], [b"wrong\n"])
        self.assertNotEqual(code, 0)
        self.assertEqual(list((self.root / "bad").iterdir()), [], "nothing is left behind")


class GameTests(CoreTestCase):
    def test_help_and_argument_errors(self) -> None:
        help_text = self.ok("game", "--help").stdout
        self.assertIn("Usage: ul game", help_text)
        self.assertIn("Mouse:", help_text)
        self.assertIn("really hard", help_text)
        for args in (["pong"], ["snake", "easy", "extra"]):
            with self.subTest(args=args):
                self.assertEqual(self.ul("game", *args).returncode, 2)
        result = self.ul("game", "snake", "insane")
        self.assertEqual(result.returncode, 2)
        self.assertIn("easy, normal, or hard", result.stderr)

    def test_needs_a_terminal(self) -> None:
        result = self.ul("game", "tetris")
        self.assertEqual(result.returncode, 1)
        self.assertIn("must be a terminal", result.stderr)

    def test_quitting_from_the_menu_in_a_real_terminal(self) -> None:
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
        process = subprocess.Popen([str(binary()), "game"], stdin=slave, stdout=slave, stderr=slave, env=self.env, cwd=self.root)
        os.close(slave)
        seen = b""
        while b"A R C A D E" not in seen and process.poll() is None:
            if select.select([master], [], [], 5)[0]:
                seen += os.read(master, 65536)
            else:
                break
        os.write(master, b"q")
        # Keep draining the terminal, or ul blocks writing its frames.
        deadline = time.monotonic() + 10
        while process.poll() is None and time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    seen += os.read(master, 65536)
                except OSError:
                    break
        process.wait(timeout=5)
        os.close(master)
        self.assertIn(b"A R C A D E", seen)
        self.assertEqual(process.returncode, 0)


class BuiltinMigrationTests(CoreTestCase):
    def test_builtins_are_listed_and_resolved(self) -> None:
        self.assertEqual(self.ok("which", "zip").stdout, "zip: builtin (Rust)\n")
        self.assertIn("zip              Compress files", self.ok("commands", "--describe").stdout)
        self.assertIn("game", self.ok("commands").stdout.splitlines())
        self.assertFalse((self.unlaw / "commands" / "zip").exists())
        self.assertIn("game:Play a terminal arcade game", self.ok("_complete", "1").stdout)
        self.assertEqual(self.ul("create", "command", "zip").returncode, 2)

    def test_untouched_python_seeds_are_retired_but_edits_win(self) -> None:
        sys.path.insert(0, str(HERE.parent / "src"))
        from unlawful.command_sources import RETIRED_NORMALIZED_HASHES  # noqa: F401

        legacy = self.unlaw / "commands" / "zip" / "main.py"
        legacy.parent.mkdir(parents=True)
        legacy.write_text(
            "from unlawful.built_in_commands.zip.main import main\n\nif __name__ == \"__main__\":\n    raise SystemExit(main())\n"
        )
        self.ok("init")
        self.assertFalse(legacy.parent.exists(), "an untouched official zip seed is removed")
        edited = self.command("game", "print('my own game')\n")
        self.assertEqual(self.ok("game").stdout, "my own game\n")
        self.assertTrue(edited.exists())


@unittest.skipUnless(shutil.which("cargo"), "cargo is not installed")
class RustCommandTests(CoreTestCase):
    def test_create_build_run_and_rebuild_on_change(self) -> None:
        created = self.ul("create", "command", "fast", "--lang", "rust", timeout=300)
        self.assertEqual(created.returncode, 0, created.stderr)
        project = self.unlaw / "commands" / "fast"
        self.assertTrue((project / "Cargo.toml").is_file())
        self.assertIn('name = "unlaw-command-fast"', (project / "Cargo.toml").read_text())
        self.assertIn("ul fast [arguments]", (project / "src" / "main.rs").read_text())
        self.assertEqual(self.ok("fast", "a", "b").stdout, "Command arguments: a b\n")
        self.assertIn("Usage: ul fast", self.ok("fast", "--help").stdout)
        source = project / "src" / "main.rs"
        source.write_text(source.read_text().replace("Command arguments", "Rust says"))
        rebuilt = self.ok("fast", "x", timeout=300)
        self.assertEqual(rebuilt.stdout, "Rust says: x\n")
        self.assertIn("building fast", rebuilt.stderr)
        again = self.ok("fast", "y")
        self.assertNotIn("building", again.stderr, "no rebuild when nothing changed")
        self.assertIn("fast             Custom Unlaw command.", self.ok("commands", "--describe").stdout)
        self.assertEqual(self.ok("which", "fast").stdout, f"fast: config {project / 'Cargo.toml'}\n")
        self.assertEqual(self.ul("create", "command", "fast", "--lang", "rust").returncode, 1)

    def test_a_global_cargo_target_dir_does_not_move_the_binary(self) -> None:
        elsewhere = self.root / "shared-target"
        result = self.ul("create", "command", "moved", "--lang", "rust", env={"CARGO_TARGET_DIR": str(elsewhere)}, timeout=300)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.ok("moved", "ok", env={"CARGO_TARGET_DIR": str(elsewhere)}).stdout, "Command arguments: ok\n")
        self.assertTrue((self.unlaw / "commands" / "moved" / "target" / "release" / "main").is_file())

    def test_build_errors_are_reported(self) -> None:
        project = self.unlaw / "commands" / "broken"
        (project / "src").mkdir(parents=True)
        (project / "Cargo.toml").write_text('[package]\nname = "broken"\nversion = "0.1.0"\nedition = "2021"\n[workspace]\n')
        (project / "src" / "main.rs").write_text("fn main() { this is not rust }\n")
        result = self.ul("broken", timeout=300)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("building broken failed", result.stderr)


class CreateLanguageTests(CoreTestCase):
    def test_language_flag_validation_and_missing_cargo(self) -> None:
        self.assertEqual(self.ul("create", "command", "x", "--lang", "cobol").returncode, 2)
        self.assertEqual(self.ul("create", "command", "x", "--lang").returncode, 2)
        self.ok("create", "command", "--lang", "python", "pyfirst")
        self.assertTrue((self.unlaw / "commands" / "pyfirst" / "main.py").is_file())
        result = self.ul("create", "command", "rs", "--lang", "rust", env={"PATH": str(self.bin)})
        self.assertEqual(result.returncode, 1)
        self.assertIn("need cargo", result.stderr)
        self.assertFalse((self.unlaw / "commands" / "rs").exists())

    def test_custom_rust_template_without_a_manifest_is_refused(self) -> None:
        template = self.unlaw / "templates" / "commands" / "rust" / "src"
        template.mkdir(parents=True)
        (template / "main.rs").write_text("fn main() {}\n")
        self.tool("cargo", "#!/bin/sh\nexit 0\n")
        result = self.ul("create", "command", "custom", "--lang", "rust")
        self.assertEqual(result.returncode, 1)
        self.assertIn("has no Cargo.toml", result.stderr)


if __name__ == "__main__":
    unittest.main()
