from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ulbin import CoreTestCase  # noqa: E402


class SystemCommandTests(CoreTestCase):
    def test_commands_lists_system_builtin_and_user_commands_sorted(self) -> None:
        self.command("zebra", "print('zebra')\n")
        names = self.ok("commands").stdout.splitlines()
        self.assertEqual(names, sorted(names))
        self.assertTrue({"commands", "create", "doctor", "git", "venv", "zebra"} <= set(names))

    def test_non_system_commands_resolve_only_from_config_commands_folder(self) -> None:
        output = self.ok("which", "git").stdout
        self.assertEqual(output, f"git: config {self.unlaw / 'commands' / 'git' / 'main.py'}\n")

    def test_create_command_writes_working_template(self) -> None:
        self.ok("create", "command", "music2")
        script = self.unlaw / "commands" / "music2" / "main.py"
        source = script.read_text()
        self.assertIn("def main", source)
        self.assertTrue(source.startswith('"""Custom Unlaw command."""\n'))
        for variable in ("UNLAW_COMMAND", "UNLAW_COMMAND_DIR", "UNLAW_CONFIG_DIR", "UNLAW_STORAGE"):
            self.assertIn(variable, source)
        self.assertIn("Usage: ul music2", self.ok("music2", "--help").stdout)
        self.assertEqual(self.ok("music2", "a").stdout, "Command arguments: a\n")
        self.assertIn("music2           Custom Unlaw command.", self.ok("commands", "--describe").stdout)

    def test_create_command_rejects_unsafe_name(self) -> None:
        for name in ("../escape", "Upper", "doctor"):
            with self.subTest(name=name):
                self.assertEqual(self.ul("create", "command", name).returncode, 2)
        self.assertFalse((self.root / "escape").exists())

    def test_create_command_refuses_to_overwrite(self) -> None:
        self.ok("create", "command", "mine")
        script = self.unlaw / "commands" / "mine" / "main.py"
        script.write_text("sentinel\n")
        self.assertEqual(self.ul("create", "command", "mine").returncode, 1)
        self.assertEqual(script.read_text(), "sentinel\n")
        self.command("shelly", "echo hi\n", "main.sh")
        self.assertEqual(self.ul("create", "command", "shelly").returncode, 1)
        self.assertFalse((self.unlaw / "commands" / "shelly" / "main.py").exists())

    def test_create_command_prefers_user_template(self) -> None:
        template = self.unlaw / "templates" / "commands" / "main.py"
        template.parent.mkdir(parents=True)
        template.write_text("print('custom template')\n")
        self.ok("create", "command", "custom")
        self.assertEqual((self.unlaw / "commands" / "custom" / "main.py").read_text(), "print('custom template')\n")

    def _template(self, name: str) -> str:
        return (self.unlaw / "templates" / "projects" / f"{name}.toml").read_text()

    def test_create_named_project_template_prompts_for_app_and_ai(self) -> None:
        project = self.root / "HearMe"
        project.mkdir()
        result = self.ok("create", "template", "hearme", input="zed\ny\n", cwd=project)
        self.assertEqual(self._template("hearme"), f'path = "{project}"\napp = "zed"\nai = true\n')
        self.assertIn("Created template 'hearme'", result.stdout)
        self.assertIn("Open with (zed/obsidian) > ", result.stdout)

    def test_create_project_template_prompts_for_missing_name(self) -> None:
        project = self.root / "Dante"
        project.mkdir()
        self.ok("create", "template", input="dante\nobsidian\nn\n", cwd=project)
        self.assertEqual(self._template("dante"), f'path = "{project}"\napp = "obsidian"\nai = false\n')

    def test_create_project_template_reprompts_invalid_choices(self) -> None:
        project = self.root / "Dante"
        project.mkdir()
        result = self.ok("create", "template", "dante", input="code\nZED\nmaybe\nn\n", cwd=project)
        self.assertIn('app = "zed"', self._template("dante"))
        self.assertIn("zed or obsidian", result.stderr)
        self.assertIn("y or n", result.stderr)

    def test_create_project_template_cancellation_writes_nothing(self) -> None:
        result = self.ul("create", "template", input="")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cancelled", result.stderr.lower())
        result = self.ul("create", "template", "half", input="zed\n")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.ok("templates").stdout, "")

    def test_create_project_template_rejects_all_name_conflicts(self) -> None:
        project = self.root / "project"
        project.mkdir()
        self.ok("config", "set", "aliases.shortcut", '["git"]')
        self.save_template("saved", project)
        for name in ("doctor", "git", "shortcut", "saved"):
            with self.subTest(name=name):
                result = self.ul("create", "template", name, input="zed\nn\n", cwd=project)
                self.assertEqual(result.returncode, 1)
                self.assertIn("already in use", result.stderr)

    def test_templates_and_list_have_separate_sorted_sections(self) -> None:
        project = self.root / "project"
        project.mkdir()
        self.save_template("zeta", project)
        self.save_template("alpha", project, "obsidian", True)
        self.assertEqual(self.ok("templates").stdout, "alpha\nzeta\n")
        listing = self.ok("list").stdout
        self.assertTrue(listing.startswith("Templates\nalpha\nzeta\n\nCommands\n"))
        self.assertNotIn("\nalpha\n", listing.split("Commands\n", 1)[1])

    def test_templates_empty_is_success_and_list_keeps_headings(self) -> None:
        self.assertEqual(self.ok("templates").stdout, "")
        self.assertTrue(self.ok("list").stdout.startswith("Templates\n\nCommands\n"))

    def test_invalid_template_manifests_are_reported(self) -> None:
        self.ok("init")
        projects = self.unlaw / "templates" / "projects"
        cases = (
            ('path = "/tmp"\napp = "zed"\nai = true\nextra = 1\n', "unknown fields: extra"),
            ('path = "/tmp"\napp = "zed"\n', "missing fields: ai"),
            ('path = "/tmp"\napp = "code"\nai = true\n', "app must be zed or obsidian"),
            ('path = "/tmp"\napp = "zed"\nai = "yes"\n', "ai must be true or false"),
            ("not = [valid toml", "Could not read template demo"),
        )
        for text, message in cases:
            with self.subTest(message=message):
                (projects / "demo.toml").write_text(text)
                result = self.ul("templates")
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
        (projects / "demo.toml").unlink()
        (projects / "Bad Name.toml").write_text('path = "/tmp"\napp = "zed"\nai = false\n')
        self.assertIn("Invalid template name", self.ul("templates").stderr)

    def test_init_prints_paths(self) -> None:
        output = self.ok("init").stdout
        self.assertIn(f"Unlaw configuration: {self.unlaw}", output)
        self.assertIn(f"Storage: {self.unlaw / 'data'}", output)


class DoctorTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env["PATH"] = str(self.bin)

    def doctor(self, *args: str):
        return self.ul("doctor", *args, timeout=60)

    def records(self) -> dict[str, dict[str, object]]:
        result = self.doctor("--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return {record["name"]: record for record in json.loads(result.stdout)}

    def test_doctor_json_is_machine_readable(self) -> None:
        records = self.records()
        self.assertTrue({"Configuration", "Python", "Git", "Cargo", "CMake", "macOS Harness", "Node.js"} <= records.keys())
        self.assertTrue(all({"name", "available", "required", "detail"} <= r.keys() for r in records.values()))
        self.assertTrue(records["Python"]["available"])
        self.assertIn(sys.executable, records["Python"]["detail"])

    def test_doctor_distinguishes_present_and_missing_tools(self) -> None:
        self.tool("git", "#!/bin/sh\n")
        self.tool("macos-harness", "#!/bin/sh\necho 'permission check failed'\nexit 1\n")
        result = self.doctor()
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = {line.split("  ")[0].strip(): line for line in result.stdout.splitlines()}
        self.assertIn("✓", lines["Git"])
        self.assertIn("○", lines["uv"])
        self.assertIn("✓", lines["macOS Harness"])
        self.assertIn("○", lines["macOS permissions"])

    def test_doctor_verbose_includes_config_path(self) -> None:
        self.assertIn(str(self.unlaw / "config.toml"), self.doctor("--verbose").stdout)

    def test_doctor_checks_configured_harness_executable(self) -> None:
        executable = self.root / "custom-harness"
        executable.write_text("#!/bin/sh\necho ready\nexit 0\n")
        executable.chmod(0o755)
        self.ok("config", "set", "mac.executable", str(executable))
        permissions = self.records()["macOS permissions"]
        self.assertEqual((permissions["available"], permissions["detail"]), (True, "ready"))

    def test_doctor_requires_python_311(self) -> None:
        old = self.tool("python-old", "#!/bin/sh\necho 3.9.6\n")
        result = self.ul("doctor", "--json", env={"UNLAW_PYTHON": str(old)})
        self.assertEqual(result.returncode, 1)
        python = next(record for record in json.loads(result.stdout) if record["name"] == "Python")
        self.assertFalse(python["available"])
        self.assertIn("3.11", python["detail"])

    def test_doctor_reports_invalid_configuration(self) -> None:
        self.ok("init")
        (self.unlaw / "config.toml").write_text('[core]\nverbose = "loud"\n')
        result = self.doctor("--json")
        self.assertEqual(result.returncode, 1)
        configuration = next(r for r in json.loads(result.stdout) if r["name"] == "Configuration")
        self.assertIn("core.verbose", configuration["detail"])

    def test_doctor_fix_installs_integration_path_defaults_and_storage(self) -> None:
        self.ok("init")
        config = self.unlaw / "config.toml"
        config.write_text("# keep me\n[capture]\nscreenshot_dir = \"/old\"\n")
        zshrc = self.home / ".zshrc"
        zshrc.write_text("export EDITOR=zed\n")
        result = self.doctor("--fix")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FIXED  Installed current-shell integration", result.stdout)
        text = zshrc.read_text()
        self.assertIn("export EDITOR=zed", text)
        self.assertIn('eval "$(command ul _shell-init zsh)"', text)
        self.assertEqual(text.count("# Unlaw CLI (managed by `unlaw doctor --fix`)"), 1)
        settings = config.read_text()
        self.assertTrue(settings.startswith("# keep me\n"))
        self.assertNotIn("screenshot_dir", settings)
        self.assertIn('python = "auto"', settings)
        self.assertTrue((self.unlaw / "data" / "runtime").is_dir())
        again = self.doctor("--fix")
        self.assertIn("No automatic fixes were needed.", again.stdout)
        self.assertEqual(zshrc.read_text(), text)


if __name__ == "__main__":
    unittest.main()
