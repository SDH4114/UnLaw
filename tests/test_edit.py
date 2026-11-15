from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ulbin import ROOT, CoreTestCase  # noqa: E402


def ule_binary() -> Path:
    subprocess.run(["cargo", "build", "--quiet", "-p", "ule"], cwd=ROOT, check=True)
    return ROOT / "target" / "debug" / "ule"


class EditTests(CoreTestCase):
    def fake_editor(self) -> Path:
        """An editor that records its arguments instead of opening anything."""
        log = self.root / "editor.log"
        self.tool("fakeedit", f"#!/bin/sh\nprintf '%s\\n' \"$@\" >> {log}\n")
        return log

    def test_help_is_side_effect_free(self) -> None:
        for flag in ("--help", "-h"):
            result = self.ok("edit", flag)
            self.assertIn("Usage: ul edit", result.stdout)
            self.assertIn("core.editor", result.stdout)

    def test_core_editor_opens_files(self) -> None:
        log = self.fake_editor()
        self.ok("config", "set", "core.editor", "fakeedit --wait")
        self.ok("edit", "a.txt", "src/main.rs:12")
        self.assertEqual(
            log.read_text().splitlines(), ["--wait", "a.txt", "src/main.rs:12"]
        )

    def test_config_edit_uses_the_editor_and_checks_the_result(self) -> None:
        log = self.fake_editor()
        self.ok("config", "set", "core.editor", "fakeedit")
        result = self.ok("config", "edit")
        self.assertEqual(log.read_text().strip(), str(self.unlaw / "config.toml"))
        self.assertIn("config.toml is valid", result.stdout)
        # A broken config is reported right after editing, and `ul edit` still works to fix it.
        (self.unlaw / "config.toml").write_text(
            '[core]\neditor = "fakeedit"\ncolor = "yes"\n'
        )
        result = self.ul("config", "edit")
        self.assertEqual(result.returncode, 1)
        self.assertIn("core.color", result.stderr)

    def test_auto_falls_back_to_visual_without_ule(self) -> None:
        log = self.fake_editor()
        env = {"VISUAL": "fakeedit -f"}
        result = self.ul_without_ule("edit", "x.md", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(log.read_text().splitlines(), ["-f", "x.md"])
        result = self.ul_without_ule("doctor", "--verbose", env=env)
        self.assertIn("ule is not installed", result.stdout)

    def test_an_editor_path_with_spaces_works_quoted_or_whole(self) -> None:
        folder = self.root / "My Apps"
        folder.mkdir()
        log = self.root / "spaced.log"
        editor = folder / "edit tool"
        editor.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" >> {log}\n")
        editor.chmod(0o755)
        self.ok("config", "set", "core.editor", str(editor))
        self.ok("edit", "a.txt")
        self.ok("config", "set", "core.editor", f"'{editor}' --wait")
        self.ok("edit", "b.txt")
        self.assertEqual(log.read_text().splitlines(), ["a.txt", "--wait", "b.txt"])

    def test_config_edit_with_open_does_not_check_an_unedited_file(self) -> None:
        # `open -t` returns at once; "config.toml is valid" would describe the old file.
        self.tool("open", "#!/bin/sh\nexit 0\n")
        result = self.ul_without_ule("config", "edit")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("is valid", result.stdout)
        self.assertIn("ul config check", result.stdout)

    def test_unknown_option(self) -> None:
        result = self.ul("edit", "--bogus")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown option", result.stderr)


class UleBinaryTests(CoreTestCase):
    def ule(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ule_binary()), *args],
            env=self.env,
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def test_help_version_and_config_path(self) -> None:
        if shutil.which("cargo") is None:
            self.skipTest("cargo is required")
        help_text = self.ule("--help")
        self.assertEqual(help_text.returncode, 0)
        self.assertIn("Usage: ule", help_text.stdout)
        version = self.ule("--version").stdout.strip()
        self.assertEqual(version, f"ule {self.ok('--version').stdout.split()[1]}")
        self.assertEqual(
            self.ule("--config").stdout.strip(), str(self.unlaw / "ule.toml")
        )

    def test_health_reports_tools_and_config_errors(self) -> None:
        if shutil.which("cargo") is None:
            self.skipTest("cargo is required")
        self.unlaw.mkdir(parents=True, exist_ok=True)
        (self.unlaw / "ule.toml").write_text('[editor]\ntab_width = "wide"\n')
        result = self.ule("--health")
        self.assertEqual(result.returncode, 0)
        self.assertIn("rust", result.stdout)
        self.assertIn("tab_width", result.stdout)
        self.assertIn("python", self.ule("--health", "python").stdout)

    def test_refuses_without_a_terminal_and_rejects_unknown_options(self) -> None:
        if shutil.which("cargo") is None:
            self.skipTest("cargo is required")
        self.assertEqual(self.ule("file.txt").returncode, 1)
        result = self.ule("--nope")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown option", result.stderr)


    def test_a_kill_keeps_unsaved_work_and_restores_the_terminal(self) -> None:
        import os
        import pty
        import select
        import signal
        import time

        if shutil.which("cargo") is None:
            self.skipTest("cargo is required")
        program = ule_binary()
        note = self.root / "note.txt"
        note.write_text("original\n")
        for number in (signal.SIGTERM, signal.SIGHUP):
            with self.subTest(signal=number.name):
                pid, master = pty.fork()
                if pid == 0:
                    os.chdir(self.root)
                    os.execve(str(program), [str(program), str(note)], {**self.env, "TERM": "xterm-256color"})
                screen = b""

                def read_for(seconds: float) -> None:
                    nonlocal screen
                    deadline = time.monotonic() + seconds
                    while time.monotonic() < deadline:
                        if select.select([master], [], [], 0.05)[0]:
                            try:
                                screen += os.read(master, 65536)
                            except OSError:
                                return

                try:
                    deadline = time.monotonic() + 10
                    while b"\x1b[c" not in screen and time.monotonic() < deadline:
                        read_for(0.1)
                    # Answer the keyboard query like a terminal without the kitty protocol.
                    os.write(master, b"\x1b[?62c")
                    read_for(1.0)
                    os.write(master, b"Oedited by hand\x1b")
                    read_for(0.8)
                    os.kill(pid, number)
                    read_for(1.5)
                    _, status = os.waitpid(pid, 0)
                finally:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    os.close(master)
                self.assertEqual(os.waitstatus_to_exitcode(status), 128 + number)
                self.assertEqual(note.read_text(), "original\n", "the file itself is not saved")
                copies = sorted((self.unlaw / "data" / "ule" / "recovered").glob("note.txt.*"))
                self.assertTrue(copies, "no recovery copy")
                self.assertEqual(copies[-1].read_text(), "edited by hand\noriginal\n")
                self.assertEqual(copies[-1].stat().st_mode & 0o777, 0o600)
                if number == signal.SIGTERM:
                    self.assertIn(b"\x1b[?1049l", screen, "the alternate screen was not left")
                    self.assertIn(b"kept as", screen)
                for copy in copies:
                    copy.unlink()


if __name__ == "__main__":
    unittest.main()
