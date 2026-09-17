from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ShellIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {"XDG_CONFIG_HOME": str(self.root / "config")}
        self.project = self.root / "HearMe"
        self.project.mkdir()

    def test_launch_zed_then_chatgpt(self) -> None:
        from unlawful.shell_integration import launch_workspace_template
        from unlawful.workspace_templates import WorkspaceTemplate

        template = WorkspaceTemplate("hearme", self.project, "zed", True)
        completed = subprocess.CompletedProcess([], 0)
        with patch.dict(os.environ, self.env, clear=False), patch(
            "unlawful.shell_integration.load_config",
            return_value={"apps": {"editor": "Zed"}},
        ), patch(
            "unlawful.shell_integration.subprocess.run", return_value=completed
        ) as run:
            self.assertEqual(launch_workspace_template(template), 0)
        self.assertEqual(
            run.call_args_list,
            [
                call(["open", "-a", "Zed", str(self.project)], check=False),
                call(["open", "-a", "ChatGPT"], check=False),
            ],
        )

    def test_launch_obsidian_without_ai(self) -> None:
        from unlawful.shell_integration import launch_workspace_template
        from unlawful.workspace_templates import WorkspaceTemplate

        template = WorkspaceTemplate("hearme", self.project, "obsidian", False)
        completed = subprocess.CompletedProcess([], 0)
        with patch(
            "unlawful.shell_integration.subprocess.run", return_value=completed
        ) as run:
            self.assertEqual(launch_workspace_template(template), 0)
        run.assert_called_once_with(
            ["open", "-a", "Obsidian", str(self.project)], check=False
        )

    def test_editor_failure_stops_before_ai(self) -> None:
        from unlawful.shell_integration import launch_workspace_template
        from unlawful.workspace_templates import WorkspaceTemplate

        template = WorkspaceTemplate("hearme", self.project, "zed", True)
        failed = subprocess.CompletedProcess([], 5)
        with patch(
            "unlawful.shell_integration.load_config",
            return_value={"apps": {"editor": "Zed"}},
        ), patch(
            "unlawful.shell_integration.subprocess.run", return_value=failed
        ) as run:
            self.assertEqual(launch_workspace_template(template), 5)
        self.assertEqual(run.call_count, 1)

    def test_launch_rejects_missing_saved_directory(self) -> None:
        from unlawful.shell_integration import ShellIntegrationError, template_path
        from unlawful.workspace_templates import create_workspace_template

        with patch.dict(os.environ, self.env, clear=False):
            create_workspace_template("hearme", self.project, "zed", False)
            self.project.rmdir()
            with self.assertRaisesRegex(ShellIntegrationError, "does not exist"):
                template_path("hearme")

    def test_rendered_zsh_changes_directory_then_launches(self) -> None:
        from unlawful.shell_integration import render_zsh_integration

        script = render_zsh_integration()
        self.assertIn('builtin cd -- "$_unlaw_path"', script)
        self.assertIn('command ul _template-launch "$1"', script)
        self.assertNotIn("Terminal", script)
        self.assertLess(
            script.index("builtin cd --"),
            script.index('command ul _template-launch "$1"'),
        )

    def test_install_zsh_integration_preserves_content_and_is_idempotent(self) -> None:
        from unlawful.shell_integration import install_zsh_integration

        zshrc = self.root / ".zshrc"
        zshrc.write_text("export KEEP=1\n", encoding="utf-8")
        self.assertTrue(install_zsh_integration(zshrc))
        first = zshrc.read_text(encoding="utf-8")
        self.assertIn("export KEEP=1", first)
        self.assertIn("Unlaw shell integration", first)
        self.assertIn('eval "$(command ul _shell-init zsh)"', first)
        self.assertFalse(install_zsh_integration(zshrc))
        self.assertEqual(zshrc.read_text(encoding="utf-8"), first)

    def test_install_zsh_integration_replaces_managed_block(self) -> None:
        from unlawful.shell_integration import install_zsh_integration

        zshrc = self.root / ".zshrc"
        zshrc.write_text(
            "before\n# >>> Unlaw shell integration >>>\nold\n"
            "# <<< Unlaw shell integration <<<\nafter\n",
            encoding="utf-8",
        )
        self.assertTrue(install_zsh_integration(zshrc))
        text = zshrc.read_text(encoding="utf-8")
        self.assertNotIn("\nold\n", text)
        self.assertIn("before", text)
        self.assertIn("after", text)

    def test_ensure_venv_creates_missing_environment(self) -> None:
        from unlawful.shell_integration import ensure_venv

        root = self.project.resolve() / ".venv"
        activation = root / "bin" / "activate"

        def create(path: Path) -> None:
            self.assertEqual(path, root)
            activation.parent.mkdir(parents=True)
            activation.write_text("# activate\n", encoding="utf-8")

        with patch("unlawful.shell_integration.venv.EnvBuilder.create", side_effect=create) as make:
            self.assertEqual(ensure_venv(self.project), activation.resolve())
        make.assert_called_once_with(root)

    def test_ensure_venv_reuses_valid_environment(self) -> None:
        from unlawful.shell_integration import ensure_venv

        activation = self.project / ".venv" / "bin" / "activate"
        activation.parent.mkdir(parents=True)
        activation.write_text("# activate\n", encoding="utf-8")
        with patch("unlawful.shell_integration.venv.EnvBuilder.create") as make:
            self.assertEqual(ensure_venv(self.project), activation.resolve())
        make.assert_not_called()

    def test_ensure_venv_rejects_invalid_existing_directory(self) -> None:
        from unlawful.shell_integration import ShellIntegrationError, ensure_venv

        (self.project / ".venv").mkdir()
        with self.assertRaisesRegex(ShellIntegrationError, "Invalid virtual environment"):
            ensure_venv(self.project)

    def test_ensure_venv_reports_creation_failure(self) -> None:
        from unlawful.shell_integration import ShellIntegrationError, ensure_venv

        with patch(
            "unlawful.shell_integration.venv.EnvBuilder.create",
            side_effect=OSError("disk full"),
        ), self.assertRaisesRegex(ShellIntegrationError, "disk full"):
            ensure_venv(self.project)

    def test_rendered_zsh_sources_venv_in_current_shell(self) -> None:
        from unlawful.shell_integration import render_zsh_integration

        script = render_zsh_integration()
        self.assertIn('if [[ "$1" == "venv" ]]', script)
        self.assertIn('command ul _venv-path', script)
        self.assertIn('source "$_unlaw_activation"', script)


if __name__ == "__main__":
    unittest.main()
