from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ulbin import CoreTestCase  # noqa: E402


class ShellIntegrationTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = self.root / "HearMe"
        self.project.mkdir()

    def test_launch_zed_then_chatgpt(self) -> None:
        self.save_template("hearme", self.project, "zed", True)
        log = self.recording_tool("open")
        self.ok("config", "set", "apps.editor", "Zed Preview")
        self.ok("_template-launch", "hearme")
        self.assertEqual(self.calls(log), [["-a", "Zed Preview", str(self.project)], ["-a", "ChatGPT"]])

    def test_launch_obsidian_without_ai(self) -> None:
        self.save_template("hearme", self.project, "obsidian", False)
        log = self.recording_tool("open")
        self.ok("_template-launch", "hearme")
        self.assertEqual(self.calls(log), [["-a", "Obsidian", str(self.project)]])

    def test_editor_failure_stops_before_ai(self) -> None:
        self.save_template("hearme", self.project, "zed", True)
        log = self.recording_tool("open", exit_code=5)
        self.assertEqual(self.ul("_template-launch", "hearme").returncode, 5)
        self.assertEqual(len(self.calls(log)), 1)

    def test_launch_rejects_missing_saved_directory(self) -> None:
        self.save_template("hearme", self.project)
        self.project.rmdir()
        result = self.ul("_template-path", "hearme")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stderr)

    def test_template_help_does_not_launch_project(self) -> None:
        self.save_template("demo", self.project)
        log = self.recording_tool("open")
        self.assertIn("Usage: ul demo", self.ok("demo", "--help").stdout)
        self.assertEqual(self.calls(log), [])

    def test_rendered_zsh_changes_directory_then_launches(self) -> None:
        script = self.ok("_shell-init", "zsh").stdout
        self.assertIn('builtin cd -- "$_unlaw_path"', script)
        self.assertIn('command ul _template-launch "$1"', script)
        self.assertNotIn("Terminal", script)
        self.assertLess(script.index("builtin cd --"), script.index('command ul _template-launch "$1"'))
        self.assertEqual(self.ul("_shell-init", "bash").returncode, 2)

    def test_rendered_zsh_sources_venv_in_current_shell(self) -> None:
        script = self.ok("_shell-init", "zsh").stdout
        self.assertIn('if [[ "$1" == "venv" ]]', script)
        self.assertIn("command ul _venv-path", script)
        self.assertIn('source "$_unlaw_activation"', script)

    def _install(self) -> str:
        self.ok("doctor", "--fix", timeout=60)
        return (self.home / ".zshrc").read_text()

    def test_install_zsh_integration_preserves_content_and_is_idempotent(self) -> None:
        (self.home / ".zshrc").write_text("export KEEP=1\n")
        first = self._install()
        self.assertIn("export KEEP=1", first)
        self.assertIn("Unlaw shell integration", first)
        self.assertIn('eval "$(command ul _shell-init zsh)"', first)
        self.assertEqual(self._install(), first)

    def test_install_zsh_integration_replaces_managed_block(self) -> None:
        (self.home / ".zshrc").write_text(
            "before\n# >>> Unlaw shell integration >>>\nold\n# <<< Unlaw shell integration <<<\nafter\n"
        )
        text = self._install()
        self.assertNotIn("\nold\n", text)
        self.assertIn("before\n# >>> Unlaw shell integration >>>\neval", text)
        self.assertIn("# <<< Unlaw shell integration <<<\nafter\n", text)


class VirtualEnvironmentTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = self.root / "project"
        self.project.mkdir()
        self.log = self.root / "python.log"
        # Stands in for `python -m venv <dir>` without creating a real venv.
        self.python = self.tool(
            "fake-python",
            f"#!{sys.executable}\nimport pathlib, sys\n"
            f"pathlib.Path({str(self.log)!r}).write_text(' '.join(sys.argv[1:]))\n"
            "if sys.argv[1:3] != ['-m', 'venv']: raise SystemExit(9)\n"
            "root = pathlib.Path(sys.argv[3])\n"
            "if root.parent.name == 'broken': raise SystemExit(4)\n"
            "(root / 'bin').mkdir(parents=True)\n"
            "(root / 'bin' / 'activate').write_text('# activate')\n",
        )
        self.env["UNLAW_PYTHON"] = str(self.python)

    def test_ensure_venv_creates_missing_environment(self) -> None:
        activation = self.project / ".venv" / "bin" / "activate"
        self.assertEqual(self.ok("_venv-path", cwd=self.project).stdout.strip(), str(activation))
        self.assertEqual(self.log.read_text(), f"-m venv {self.project / '.venv'}")

    def test_ensure_venv_reuses_valid_environment(self) -> None:
        activation = self.project / ".venv" / "bin" / "activate"
        activation.parent.mkdir(parents=True)
        activation.write_text("# activate\n")
        self.assertEqual(self.ok("_venv-path", cwd=self.project).stdout.strip(), str(activation))
        self.assertFalse(self.log.exists())

    def test_ensure_venv_rejects_invalid_existing_directory(self) -> None:
        (self.project / ".venv").mkdir()
        result = self.ul("_venv-path", cwd=self.project)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Invalid virtual environment", result.stderr)

    def test_ensure_venv_reports_creation_failure(self) -> None:
        broken = self.root / "broken"
        broken.mkdir()
        result = self.ul("_venv-path", cwd=broken)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Could not create", result.stderr)

    def test_configured_python_is_used(self) -> None:
        self.env.pop("UNLAW_PYTHON")
        self.ok("config", "set", "core.python", str(self.python))
        self.ok("_venv-path", cwd=self.project)
        self.assertTrue(self.log.exists())


if __name__ == "__main__":
    unittest.main()
