"""Error paths and edge cases of the Rust core, driven through the real binary."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ulbin import CoreTestCase, binary  # noqa: E402


class UsageErrorTests(CoreTestCase):
    def test_bad_arguments_print_usage_and_exit_2(self) -> None:
        cases = {
            ("commands", "--bad"): "Usage: ul commands",
            ("templates", "x"): "Usage: ul templates",
            ("list", "x"): "Usage: ul list",
            ("init", "x"): "Usage: ul init",
            ("which",): "Usage: ul which",
            ("which", "a", "b"): "Usage: ul which",
            ("version", "x"): "Usage: ul version",
            ("venv", "x"): "Usage: ul venv",
            ("completion", "bash"): "Usage: ul completion zsh",
            ("create",): "Usage: ul create command",
            ("create", "thing"): "Usage: ul create command",
            ("create", "command"): "Usage: ul create command <name>",
            ("create", "template", "a", "b"): "Usage: ul create template",
            ("doctor", "--bad"): "Usage: ul doctor",
            ("config", "nope"): "Usage: ul config",
            ("config", "get"): "Usage: ul config",
            ("config", "set", "only-key"): "Usage: ul config",
            ("_shell-init",): "Usage: ul _shell-init zsh",
            ("_template-path",): "Usage: ul _template-path",
            ("_template-launch",): "Usage: ul _template-launch",
        }
        for args, message in cases.items():
            with self.subTest(args=args):
                result = self.ul(*args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(message, result.stderr)

    def test_bare_config_prints_usage_on_stdout(self) -> None:
        result = self.ul("config")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage: ul config path|show|get|set|edit|check|reset", result.stdout)

    def test_global_help_forms(self) -> None:
        for args in ((), ("-h",), ("--help",), ("help",), ("--no-color", "--verbose")):
            with self.subTest(args=args):
                self.assertIn("Global options:", self.ok(*args).stdout)


class ConfigEdgeTests(CoreTestCase):
    def test_edit_uses_visual_then_editor_then_open(self) -> None:
        # Without ule installed (core.editor = "auto"): $VISUAL, then $EDITOR, then `open -t`.
        log = self.recording_tool("fake-editor", exit_code=4)
        result = self.ul_without_ule("config", "edit", env={"EDITOR": "fake-editor --wait"})
        self.assertEqual(result.returncode, 4)
        self.assertEqual(self.calls(log), [["--wait", str(self.unlaw / "config.toml")]])
        visual = self.recording_tool("fake-visual")
        self.assertEqual(self.ul_without_ule("config", "edit", env={"VISUAL": "fake-visual", "EDITOR": "fake-editor"}).returncode, 0)
        self.assertEqual(len(self.calls(visual)), 1)
        open_log = self.recording_tool("open")
        self.assertEqual(self.ul_without_ule("config", "edit").returncode, 0)
        self.assertEqual(self.calls(open_log), [["-t", str(self.unlaw / "config.toml")]])

    def test_missing_editor_is_reported(self) -> None:
        result = self.ul_without_ule("config", "edit", env={"EDITOR": "no-such-editor-xyz"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("could not start no-such-editor-xyz", result.stderr)

    def test_show_check_and_new_keys(self) -> None:
        self.ok("config", "set", "custom.nested.answer", "42")
        self.assertIn("[custom.nested]\nanswer = 42", self.ok("config", "show").stdout)
        self.assertEqual(self.ok("config", "get", "custom.nested.answer").stdout, "42\n")
        self.assertIn("Configuration is valid", self.ok("config", "check").stdout)
        for key in ("a..b", ".a", "a."):
            with self.subTest(key=key):
                result = self.ul("config", "set", key, "1")
                self.assertEqual(result.returncode, 2)
                self.assertIn("Invalid configuration key", result.stderr)

    def test_unreadable_config_is_an_error_everywhere(self) -> None:
        self.ok("init")
        (self.unlaw / "config.toml").write_text("[core\nbroken")
        for args in (("config", "get", "core.color"), ("config", "check"), ("git",), ("commands",), ("which", "x")):
            with self.subTest(args=args):
                result = self.ul(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("Could not read", result.stderr)

    def test_inline_table_values_become_sections(self) -> None:
        self.ok("config", "set", "aliases", '{ yt2 = ["yt"], g = ["git", "status"] }')
        text = (self.unlaw / "config.toml").read_text()
        self.assertIn('[aliases]\nyt2 = ["yt"]\ng = ["git", "status"]', text)
        self.assertEqual(self.ok("which", "g").stdout, "g: alias -> git status\n")

    def test_empty_xdg_config_home_falls_back_to_home(self) -> None:
        self.ok("init", env={"XDG_CONFIG_HOME": ""})
        self.assertTrue((self.home / ".config" / "unlaw" / "config.toml").is_file())

    def test_unwritable_config_location_fails_cleanly(self) -> None:
        blocker = self.root / "file"
        blocker.write_text("not a directory")
        result = self.ul("commands", env={"XDG_CONFIG_HOME": str(blocker)})
        self.assertEqual(result.returncode, 1)
        self.assertIn("Could not initialize configuration", result.stderr)


class DispatchTests(CoreTestCase):
    def test_alias_may_point_to_a_system_command(self) -> None:
        self.ok("config", "set", "aliases.cm", '["commands", "--json"]')
        self.assertIsInstance(json.loads(self.ok("cm").stdout), list)

    def test_alias_cannot_override_a_system_command(self) -> None:
        self.ok("config", "set", "aliases.doctor", '["git"]')
        self.assertIn("Check Unlaw configuration", self.ok("doctor", "--help").stdout)
        records = json.loads(self.ok("commands", "--json").stdout)
        self.assertEqual(next(r for r in records if r["name"] == "doctor")["source"], "system")
        self.assertEqual(self.ok("which", "doctor").stdout, "doctor: system\n")

    def test_dry_run_shows_alias_expansion_and_quotes(self) -> None:
        script = self.command("echo2", "print(1)\n")
        self.ok("config", "set", "aliases.e", '["echo2", "it\'s"]')
        self.assertEqual(self.ok("--dry-run", "e", "x").stdout, f"DRY RUN: {sys.executable} {script} 'it'\"'\"'s' x\n")

    def test_commands_verbose_lists_sources(self) -> None:
        script = self.command("mine", "print(1)\n")
        lines = self.ok("commands", "--verbose").stdout.splitlines()
        self.assertIn(f"{'mine':<16} config  {script}", lines)
        self.assertIn(f"{'doctor':<16} system", lines)

    def test_hidden_directories_and_folders_without_entry_points_are_ignored(self) -> None:
        self.command(".secret", "print(1)\n")
        (self.unlaw / "commands" / "empty").mkdir(parents=True)
        names = self.ok("commands").stdout.splitlines()
        self.assertNotIn(".secret", names)
        self.assertNotIn("empty", names)
        self.assertEqual(self.ul(".secret").returncode, 2)


class RunTests(CoreTestCase):
    def test_missing_interpreters_have_clear_errors(self) -> None:
        self.command("py", "print(1)\n")
        for flags in ((), ("--verbose",)):
            with self.subTest(flags=flags):
                result = self.ul(*flags, "py", env={"UNLAW_PYTHON": "/nonexistent/python3"})
                self.assertEqual(result.returncode, 1)
                self.assertIn("Could not run py: /nonexistent/python3 not found; install Python 3.11+", result.stderr)
        self.command("js", "console.log(1)\n", "main.js")
        result = self.ul("js", env={"PATH": str(self.bin)})
        self.assertEqual(result.returncode, 1)
        self.assertIn("Could not run js: node not found", result.stderr)

    def test_signals_become_shell_exit_codes(self) -> None:
        self.command("die", "import os, signal\nos.kill(os.getpid(), signal.SIGTERM)\n")
        self.assertEqual(self.ul("--verbose", "die").returncode, 143)
        self.assertEqual(self.ul("die").returncode, -signal.SIGTERM, "exec mode: ul becomes the command")

    def test_ctrl_c_reaches_the_command_while_ul_waits(self) -> None:
        ready = self.root / "ready"
        self.command(
            "wait",
            f"import pathlib, time\npathlib.Path({str(ready)!r}).touch()\n"
            "try:\n    time.sleep(30)\nexcept KeyboardInterrupt:\n    print('interrupted', flush=True)\n    raise SystemExit(5)\n",
        )
        process = subprocess.Popen(
            [str(binary()), "--verbose", "wait"],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        deadline = time.monotonic() + 15
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        os.killpg(process.pid, signal.SIGINT)
        stdout, stderr = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 5, stderr)
        self.assertIn("interrupted", stdout)
        self.assertIn("unlaw: finished in", stderr, "ul itself survived SIGINT")

    def test_storage_variable_follows_relative_storage_root(self) -> None:
        output = self.root / "storage.txt"
        self.command("st", f"import os, pathlib\npathlib.Path({str(output)!r}).write_text(os.environ['UNLAW_STORAGE'])\n")
        self.ok("config", "set", "storage.root", "files")
        self.ok("st")
        self.assertEqual(output.read_text(), str(self.unlaw / "files"))


class TemplateEdgeTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = self.root / "proj"
        self.project.mkdir()

    def test_template_errors(self) -> None:
        self.save_template("demo", self.project)
        result = self.ul("demo", "extra")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage: ul demo", result.stderr)
        self.assertEqual(self.ul("_template-path", "Bad Name").returncode, 3)
        result = self.ul("_template-launch", "missing")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Could not read template missing", result.stderr)

    def test_broken_template_blocks_unknown_command_lookup(self) -> None:
        self.ok("init")
        (self.unlaw / "templates" / "projects" / "bad.toml").write_text("app = 1\n")
        result = self.ul("not-a-command")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Invalid template bad", result.stderr)
        self.assertEqual(self.ul("list").returncode, 2)
        self.assertEqual(self.ul("create", "template", "x", input="zed\nn\n", cwd=self.project).returncode, 2)

    def test_create_template_validates_name_and_config(self) -> None:
        result = self.ul("create", "template", "Bad Name", cwd=self.project)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Invalid template name", result.stderr)
        self.ok("init")
        (self.unlaw / "config.toml").write_text('[core]\nverbose = "x"\n')
        self.assertEqual(self.ul("create", "template", "ok", cwd=self.project).returncode, 2)

    def test_completion_lists_templates_and_help_targets(self) -> None:
        self.save_template("demo", self.project)
        self.assertIn(f"demo:project template ({self.project})", self.ok("_complete", "1").stdout.splitlines())
        help_targets = self.ok("_complete", "2", "help").stdout
        self.assertIn("yt:Open YouTube", help_targets)
        self.assertIn("--fix:", self.ok("_complete", "2", "doctor").stdout)
        self.assertIn("zsh:", self.ok("_complete", "2", "completion").stdout)
        self.assertIn("--describe:", self.ok("_complete", "2", "commands").stdout)
        self.assertEqual(self.ok("_complete", "3", "config", "get").stdout, "")


class LayoutEdgeTests(CoreTestCase):
    def test_non_utf8_command_files_are_left_alone(self) -> None:
        script = self.unlaw / "commands" / "git" / "main.py"
        script.parent.mkdir(parents=True)
        script.write_bytes(b"\xff\xfe binary")
        self.ok("init")
        self.assertEqual(script.read_bytes(), b"\xff\xfe binary")

    def test_create_command_with_unreadable_or_invalid_user_template(self) -> None:
        template = self.unlaw / "templates" / "commands" / "main.py"
        template.parent.mkdir(parents=True)
        template.write_bytes(b"\xff\xfe not utf-8")
        result = self.ul("create", "command", "fresh")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Could not read", result.stderr)
        self.assertFalse((self.unlaw / "commands" / "fresh").exists())
        template.unlink()
        template.mkdir()
        self.ok("create", "command", "fresh")
        self.assertIn("Custom Unlaw command.", (self.unlaw / "commands" / "fresh" / "main.py").read_text())

    def test_doctor_fix_moves_the_legacy_recording_log(self) -> None:
        self.ok("init")
        (self.unlaw / "recording.log").write_text("old log")
        result = self.ul("doctor", "--fix", env={"PATH": str(self.bin)})
        self.assertIn("Moved", result.stdout)
        self.assertEqual((self.unlaw / "data" / "runtime" / "recording.log").read_text(), "old log")
        self.assertFalse((self.unlaw / "recording.log").exists())

    def test_doctor_reports_an_unrunnable_python(self) -> None:
        broken = self.tool("broken-python", "#!/bin/sh\nexit 3\n")
        result = self.ul("doctor", "--json", env={"UNLAW_PYTHON": str(broken), "PATH": str(self.bin)})
        python = next(r for r in json.loads(result.stdout) if r["name"] == "Python")
        self.assertFalse(python["available"])
        self.assertIn("could not be run", python["detail"])
        self.assertEqual(result.returncode, 1)

    def test_doctor_sees_a_running_lm_server_but_not_other_listeners(self) -> None:
        import socket
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class UlServer(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("X-Unlaw", "lm")
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args: object) -> None:
                pass

        def lm_record() -> dict[str, object]:
            records = json.loads(self.ul("doctor", "--json", env={"PATH": str(self.bin)}).stdout)
            return next(r for r in records if r["name"] == "Local model server")

        with socket.socket() as other:  # e.g. LM Studio or Ollama on the port
            other.bind(("127.0.0.1", 0))
            other.listen()
            self.ok("config", "set", "lm.port", str(other.getsockname()[1]))
            self.assertFalse(lm_record()["available"])
        server = ThreadingHTTPServer(("127.0.0.1", 0), UlServer)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        self.ok("config", "set", "lm.port", str(port))
        record = lm_record()
        self.assertEqual((record["available"], record["detail"]), (True, f"listening at 127.0.0.1:{port}"))
        records = json.loads(self.ul("doctor", "--json", env={"PATH": str(self.bin)}).stdout)
        names = [r["name"] for r in records]
        self.assertIn("Local model engine", names)
        self.assertFalse(any("LM Studio" in name for name in names))

if __name__ == "__main__":
    unittest.main()
