"""Regression cases from the core review; every external tool is a fake."""

from __future__ import annotations

import os
import resource
import signal
import subprocess
import sys
import time

from tests.ulbin import CoreTestCase, binary


class CoreReviewTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env["PATH"] = str(self.bin)

    def test_storage_failure_does_not_block_config_recovery(self) -> None:
        blocked = self.root / "not-a-directory"
        blocked.write_text("keep\n")
        self.ok("config", "set", "storage.root", str(blocked))
        self.ok("config", "set", "storage.root", "data")
        self.assertEqual(self.ok("config", "get", "storage.root").stdout, "data\n")
        self.ok("config", "set", "storage.root", str(blocked))
        self.ok("config", "reset", "--yes")
        self.assertEqual(blocked.read_text(), "keep\n")

    def test_new_skill_install_does_not_hide_an_older_stale_install(self) -> None:
        self.ok("skills", "install")
        self.command("hello", '"""Say hello."""\n')
        self.ok("skills", "install", "--path", str(self.root / "second"))
        self.ok("commands")
        first = self.home / ".agents" / "skills" / "unlaw" / "reference" / "hello.md"
        second = self.root / "second" / "unlaw" / "reference" / "hello.md"
        self.assertTrue(first.is_file(), "the first install must still refresh")
        self.assertTrue(second.is_file())

    def test_create_command_refuses_dangling_template_output_symlinks(self) -> None:
        self.ok("init")
        self.tool("cargo", "#!/bin/sh\nexit 0\n")
        for name, entry, flags in (("pythonlink", "main.py", ()), ("rustlink", "Cargo.toml", ("--lang", "rust"))):
            with self.subTest(name=name):
                directory = self.unlaw / "commands" / name
                directory.mkdir()
                outside = self.root / f"{name}-outside"
                (directory / entry).symlink_to(outside)
                result = self.ul("create", "command", name, *flags)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertFalse(outside.exists(), "command creation must not follow the dangling link")
                self.assertTrue((directory / entry).is_symlink())

    def test_failed_seed_write_leaves_no_truncated_command(self) -> None:
        def limit_writes() -> None:
            resource.setrlimit(resource.RLIMIT_FSIZE, (10240, 10240))
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)

        result = subprocess.run(
            [str(binary()), "init"], env=self.env, input="", capture_output=True,
            text=True, timeout=30, preexec_fn=limit_writes, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Could not initialize configuration", result.stderr)
        self.ok("init")
        self.assertIn("Usage:", self.ok("agent", "--help").stdout)

    def test_failed_python_seed_write_leaves_no_truncated_command(self) -> None:
        def limit_writes() -> None:
            resource.setrlimit(resource.RLIMIT_FSIZE, (10240, 10240))
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)

        source = str(binary().parents[2] / "src")
        script = f"import sys; sys.path.insert(0, {source!r}); from unlawful.config import ensure_layout; ensure_layout()"
        result = subprocess.run(
            [sys.executable, "-c", script], env=self.env, input="", capture_output=True,
            text=True, timeout=30, preexec_fn=limit_writes, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("File too large", result.stderr)
        self.ok("init")
        self.assertIn("Usage:", self.ok("agent", "--help").stdout)

    def test_the_newest_python_on_path_runs_commands_even_past_3_14(self) -> None:
        self.command("which-python", "import sys\nprint(sys.argv[0] and __import__('os').environ.get('MARK'))\n")
        mark = self.root / "py-mark"
        self.tool("python3.15", f"#!/bin/sh\necho 3.15 > {mark}\nexec {sys.executable} \"$@\"\n")
        env = {key: value for key, value in self.env.items() if key != "UNLAW_PYTHON"}
        env["PATH"] = f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"
        result = subprocess.run([str(binary()), "which-python"], env=env, cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(mark.read_text().strip(), "3.15")

    def test_sigterm_to_ul_reaches_the_command(self) -> None:
        # A `kill` of ul used to leave the command running as an orphan.
        started = self.root / "started"
        caught = self.root / "caught"
        self.command(
            "longrun",
            "import pathlib, signal, sys, time\n"
            f"signal.signal(signal.SIGTERM, lambda *a: (pathlib.Path({str(caught)!r}).write_text('yes'), sys.exit(7)))\n"
            f"pathlib.Path({str(started)!r}).write_text(str(__import__('os').getpid()))\n"
            "time.sleep(30)\n",
        )
        for timeout in ("0", "60"):
            with self.subTest(timeout=timeout):
                started.unlink(missing_ok=True)
                caught.unlink(missing_ok=True)
                self.ok("config", "set", "core.command_timeout", timeout)
                process = subprocess.Popen([str(binary()), "longrun"], env=self.env, cwd=self.root,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.addCleanup(lambda: process.poll() is None and process.kill())
                deadline = time.monotonic() + 10
                while not started.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(started.exists(), "the command did not start")
                process.send_signal(signal.SIGTERM)
                self.assertEqual(process.wait(timeout=10), 7)
                self.assertEqual(caught.read_text(), "yes")

    def test_command_timeout_stops_spawned_children(self) -> None:
        child_pid = self.root / "child.pid"
        self.command(
            "slowtree",
            "import pathlib, subprocess, sys, time\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], "
            "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
            f"pathlib.Path({str(child_pid)!r}).write_text(str(child.pid))\n"
            "time.sleep(30)\n",
        )
        self.ok("config", "set", "core.command_timeout", "1")
        pid = None
        try:
            result = self.ul("slowtree")
            self.assertEqual(result.returncode, 124, result.stderr)
            pid = int(child_pid.read_text())
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.02)
            else:
                self.fail("a timed-out command left its child running")
        finally:
            if pid is None and child_pid.exists():
                pid = int(child_pid.read_text())
            if pid is not None:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_timed_command_still_receives_ctrl_c(self) -> None:
        ready = self.root / "ready"
        self.command(
            "interruptible",
            f"import pathlib, time\npathlib.Path({str(ready)!r}).touch()\n"
            "try:\n    time.sleep(30)\nexcept KeyboardInterrupt:\n    raise SystemExit(5)\n",
        )
        self.ok("config", "set", "core.command_timeout", "10")
        process = subprocess.Popen(
            [str(binary()), "interruptible"], env=self.env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(ready.exists(), "command never became ready")
            os.killpg(process.pid, signal.SIGINT)
            _, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 5, stderr)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    def tty_run(self, name: str, keys: bytes | None, seconds: float = 8.0) -> tuple[int, str]:
        """Run `ul name` on a pseudo-terminal it owns, like a shell would; returns (exit, output)."""
        import pty
        import select

        pid, fd = pty.fork()
        if pid == 0:  # the child is a session leader in the terminal's foreground
            os.execve(str(binary()), [str(binary()), name], self.env)
        output, sent, deadline = b"", False, time.monotonic() + seconds
        try:
            while time.monotonic() < deadline:
                if select.select([fd], [], [], 0.05)[0]:
                    try:
                        chunk = os.read(fd, 1024)
                    except OSError:
                        chunk = b""
                    output += chunk
                if keys is not None and not sent and b"?" in output:
                    os.write(fd, keys)
                    sent = True
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    while select.select([fd], [], [], 0.05)[0]:
                        try:
                            chunk = os.read(fd, 1024)
                        except OSError:
                            break
                        if not chunk:
                            break
                        output += chunk
                    return os.waitstatus_to_exitcode(status), output.decode(errors="replace")
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            self.fail(f"`ul {name}` hung on the terminal: {output!r}")
        finally:
            os.close(fd)

    def test_timed_command_owns_the_terminal(self) -> None:
        self.command("ask", 'name = input("name? ")\nprint("hello", name)\n')
        self.command(
            "wait",
            'import time\nprint("ready?", flush=True)\n'
            "try:\n    time.sleep(30)\nexcept KeyboardInterrupt:\n    raise SystemExit(5)\n",
        )
        self.command("hang", "import time\ntime.sleep(30)\n")
        self.ok("config", "set", "core.command_timeout", "20")
        code, output = self.tty_run("ask", b"Haos\n")
        self.assertEqual(code, 0, output)
        self.assertIn("hello Haos", output, "a timed command must be able to read the keyboard")
        code, output = self.tty_run("wait", b"\x03")
        self.assertEqual(code, 5, "Ctrl-C from the terminal reaches the command")
        self.ok("config", "set", "core.command_timeout", "1")
        code, output = self.tty_run("hang", None)
        self.assertEqual(code, 124, output)
        self.assertIn("timed out", output)
