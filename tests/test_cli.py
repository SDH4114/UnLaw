from __future__ import annotations

import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ulbin import CoreTestCase  # noqa: E402


class CliTests(CoreTestCase):
    def test_user_command_receives_arguments_and_exit_code(self) -> None:
        output = self.root / "args.txt"
        self.command(
            "echoargs",
            "import pathlib, sys\n"
            f"pathlib.Path({str(output)!r}).write_text('|'.join(sys.argv[1:]))\n"
            "raise SystemExit(7)\n",
        )
        self.assertEqual(self.ul("echoargs", "hello", "world").returncode, 7)
        self.assertEqual(output.read_text(), "hello|world")

    def test_user_command_overrides_builtin(self) -> None:
        self.command("app", "print('custom')\n")
        self.assertEqual(self.ok("app").stdout, "custom\n")
        self.assertEqual((self.unlaw / "commands" / "app" / "main.py").read_text(), "print('custom')\n")

    def test_help_is_shown_without_command(self) -> None:
        result = self.ok()
        self.assertIn("Usage: ul", result.stdout)
        self.assertIn("ul create template", result.stdout)
        self.assertIn("ul venv", result.stdout)

    def test_unknown_command_is_an_error(self) -> None:
        result = self.ul("missing-command")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown command", result.stderr)

    def test_cli_reports_version_3_with_the_build_commit(self) -> None:
        line = self.ok("--version").stdout
        self.assertRegex(line, r"^Unlaw 3\.5\.0( \([0-9a-f]{7}\))?\n$")
        self.assertEqual(self.ok("version").stdout, line)
        self.assertIn(line.strip().replace("Unlaw ", "version "), self.ok("doctor", "--verbose", timeout=60).stdout)

    def test_direct_template_invocation_requires_shell_integration(self) -> None:
        project = self.root / "HearMe"
        project.mkdir()
        self.save_template("hearme", project)
        result = self.ul("hearme")
        self.assertEqual(result.returncode, 1)
        self.assertIn("doctor --fix", result.stderr)

    def test_hidden_template_helpers_resolve_and_launch(self) -> None:
        project = self.root / "HearMe"
        project.mkdir()
        self.save_template("hearme", project)
        self.assertEqual(self.ok("_template-path", "hearme").stdout.strip(), str(project))
        self.assertEqual(self.ul("_template-path", "missing").returncode, 3)
        log = self.recording_tool("open", exit_code=6)
        self.assertEqual(self.ul("_template-launch", "hearme").returncode, 6)
        self.assertEqual(self.calls(log), [["-a", "Zed", str(project)]])

    def test_hidden_template_helpers_reject_extra_arguments(self) -> None:
        self.assertEqual(self.ul("_template-path", "one", "two").returncode, 2)
        self.assertEqual(self.ul("_template-launch", "one", "two").returncode, 2)

    def test_hidden_venv_helper_returns_activation_path(self) -> None:
        project = self.root / "project"
        project.mkdir()
        activation = project / ".venv" / "bin" / "activate"
        activation.parent.mkdir(parents=True)
        activation.write_text("# activate\n")
        self.assertEqual(self.ok("_venv-path", cwd=project).stdout.strip(), str(activation))

    def test_hidden_venv_helper_rejects_arguments(self) -> None:
        self.assertEqual(self.ul("_venv-path", "extra").returncode, 2)

    def test_direct_venv_command_requires_shell_integration(self) -> None:
        result = self.ul("venv")
        self.assertEqual(result.returncode, 1)
        self.assertIn("doctor --fix", result.stderr)


class CommandContractTests(CoreTestCase):
    """What a command author can rely on, whatever language they write in."""

    def test_commands_receive_unlaw_environment(self) -> None:
        output = self.root / "env.json"
        self.command(
            "envdump",
            "import json, os, pathlib\n"
            f"pathlib.Path({str(output)!r}).write_text(json.dumps("
            "{key: os.environ.get(key) for key in ('UNLAW_COMMAND', 'UNLAW_COMMAND_DIR', 'UNLAW_CONFIG_DIR', 'UNLAW_STORAGE')}))\n",
        )
        self.ok("config", "set", "storage.root", str(self.root / "store"))
        self.ok("envdump")
        self.assertEqual(
            json.loads(output.read_text()),
            {
                "UNLAW_COMMAND": "envdump",
                "UNLAW_COMMAND_DIR": str(self.unlaw / "commands" / "envdump"),
                "UNLAW_CONFIG_DIR": str(self.unlaw),
                "UNLAW_STORAGE": str(self.root / "store"),
            },
        )

    def test_shell_script_without_executable_bit_runs_with_sh(self) -> None:
        self.command("hello", "# Greet someone.\necho \"hi $1 from $UNLAW_COMMAND\"\nexit 3\n", "main.sh")
        result = self.ul("hello", "Haos")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, "hi Haos from hello\n")

    def test_executable_main_runs_directly(self) -> None:
        self.command("bin", f"#!{sys.executable}\nimport sys\nprint('native', *sys.argv[1:])\n", "main", executable=True)
        self.assertEqual(self.ok("bin", "x").stdout, "native x\n")

    def test_non_executable_main_is_not_a_command(self) -> None:
        self.command("plain", "data\n", "main")
        self.assertEqual(self.ul("plain").returncode, 2)

    @unittest.skipIf(shutil.which("node") is None, "node is not installed")
    def test_javascript_command_runs_with_node(self) -> None:
        self.command("js", "// Print arguments.\nconsole.log(process.argv.slice(2).join(','))\n", "main.js")
        self.assertEqual(self.ok("js", "a", "b").stdout, "a,b\n")

    def test_main_py_wins_over_other_entry_points(self) -> None:
        self.command("both", "print('python')\n")
        self.command("both", "echo shell\n", "main.sh")
        self.assertEqual(self.ok("both").stdout, "python\n")

    def test_seeding_never_shadows_a_command_rewritten_in_another_language(self) -> None:
        self.ok("init")
        (self.unlaw / "commands" / "lofi" / "main.py").unlink()
        self.command("lofi", "echo my lofi\n", "main.sh")
        self.assertEqual(self.ok("lofi").stdout, "my lofi\n")
        self.assertFalse((self.unlaw / "commands" / "lofi" / "main.py").exists())

    def test_descriptions_come_from_files_without_running_commands(self) -> None:
        marker = self.root / "ran"
        self.command(
            "doc",
            f'#!/usr/bin/env python3\n"""Python docstring summary.\n\nMore."""\nopen({str(marker)!r}, "w")\n',
        )
        self.command("shell", "#!/bin/sh\n# Shell comment summary.\ntouch " + str(marker) + "\n", "main.sh")
        self.command("helped", f"open({str(marker)!r}, 'w')\n")
        (self.unlaw / "commands" / "helped" / "help.txt").write_text("\nFrom help.txt.\nUsage: ul helped\n")
        self.command("bare", "print(1)\n")
        lines = {
            line.split(None, 1)[0]: (line.split(None, 1) + [""])[1]
            for line in self.ok("commands", "--describe").stdout.splitlines()
        }
        self.assertEqual(lines["doc"], "Python docstring summary.")
        self.assertEqual(lines["shell"], "Shell comment summary.")
        self.assertEqual(lines["helped"], "From help.txt.")
        self.assertEqual(lines["bare"], "")
        self.assertEqual(lines["yt"], "Open YouTube, search, or download one YouTube video.")
        self.assertEqual(lines["doctor"], "Check Unlaw configuration, tools and shell integration.")
        records = json.loads(self.ok("commands", "--json").stdout)
        self.assertEqual(next(r for r in records if r["name"] == "doc")["summary"], "Python docstring summary.")
        completion = self.ok("_complete", "1").stdout.splitlines()
        self.assertIn("doc:Python docstring summary.", completion)
        self.assertFalse(marker.exists())

    def test_completion_offers_subcommands(self) -> None:
        self.assertIn("set:Set and validate a value", self.ok("_complete", "2", "config").stdout.splitlines())
        self.assertIn("template:Save the current project as a template", self.ok("_complete", "2", "create").stdout)
        self.assertEqual(self.ok("_complete", "2", "yt").stdout, "")


if __name__ == "__main__":
    unittest.main()
