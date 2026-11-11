"""`ul create command` scaffolds for AI agents, the reserved names and the authoring page of `ul skills`."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

from ulbin import CoreTestCase, binary

from unlawful.config import DEFAULT_COMMAND_NAMES

RETIRED_NAMES = ("todo", "game", "zip", "app", "browser", "lm")


class CreateCommandScaffoldTests(CoreTestCase):
    def folder(self, name: str) -> Path:
        return self.unlaw / "commands" / name

    def test_a_new_command_comes_with_rules_for_agents(self) -> None:
        self.ok("create", "command", "hello")
        folder = self.folder("hello")
        self.assertEqual((folder / "CLAUDE.md").read_text(), "@AGENTS.md\n")
        rules = (folder / "AGENTS.md").read_text()
        for needle in (
            "ul hello",
            "--help",
            "UNLAW_STORAGE",
            "UNLAW_COMMAND_DIR",
            "ul skills show authoring",
            "Do not edit Unlaw",
            "config.toml",
        ):
            self.assertIn(needle, rules)
        self.assertNotIn("{{", rules)
        self.assertLess(
            len(rules.splitlines()), 40, "short and specific to this folder"
        )

    def test_the_python_template_is_a_good_starting_point(self) -> None:
        self.ok("create", "command", "hello")
        source = (self.folder("hello") / "main.py").read_text()
        for variable in (
            "UNLAW_COMMAND",
            "UNLAW_COMMAND_DIR",
            "UNLAW_CONFIG_DIR",
            "UNLAW_STORAGE",
            "UNLAW_BIN",
        ):
            self.assertIn(variable, source)
        for flag in ("-h", "--help"):
            result = self.ok("hello", flag)
            self.assertIn("Usage: ul hello", result.stdout)
        self.assertEqual(self.ok("hello", "a", "b").stdout, "Command arguments: a b\n")
        usage = self.ul("hello", "--no-such-option")
        self.assertEqual(usage.returncode, 2)
        self.assertIn("Usage: ul hello", usage.stderr)

    def test_existing_files_are_never_overwritten(self) -> None:
        folder = self.folder("hello")
        folder.mkdir(parents=True)
        (folder / "AGENTS.md").write_text("mine\n")
        self.ok("create", "command", "hello")
        self.assertEqual((folder / "AGENTS.md").read_text(), "mine\n")
        self.assertTrue((folder / "main.py").is_file())
        self.assertTrue((folder / "CLAUDE.md").is_file())

    def test_a_command_that_exists_is_left_alone(self) -> None:
        self.command("hello", "print('mine')\n")
        result = self.ul("create", "command", "hello")
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.folder("hello") / "AGENTS.md").exists())

    def test_user_templates_still_win(self) -> None:
        templates = self.unlaw / "templates" / "commands"
        templates.mkdir(parents=True)
        (templates / "main.py").write_text('"""From my template."""\n')
        (templates / "AGENTS.md").write_text("My rules for {{command_name}}\n")
        self.ok("create", "command", "hello")
        self.assertEqual(
            (self.folder("hello") / "main.py").read_text(), '"""From my template."""\n'
        )
        self.assertEqual(
            (self.folder("hello") / "AGENTS.md").read_text(), "My rules for hello\n"
        )

    def test_names_of_default_retired_system_and_alias_commands_are_refused(
        self,
    ) -> None:
        self.ok("config", "set", "aliases.mine", '["tg", "send"]')
        names = [
            *DEFAULT_COMMAND_NAMES,
            *RETIRED_NAMES,
            "config",
            "doctor",
            "mine",
            "authoring",
        ]
        for name in names:
            with self.subTest(name=name):
                result = self.ul("create", "command", name)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("choose another name", result.stderr)
                self.assertFalse((self.folder(name) / "AGENTS.md").exists())

    def test_a_removed_default_command_name_stays_reserved(self) -> None:
        self.ok("init")
        self.ok("remove", "music", "--yes")
        self.assertEqual(self.ul("create", "command", "music").returncode, 2)
        self.assertFalse((self.folder("music") / "AGENTS.md").exists())

    def test_rust_commands_get_the_same_files(self) -> None:
        if shutil.which("cargo") is None:
            self.skipTest("cargo is not installed")
        self.ok("create", "command", "fast", "--lang", "rust", timeout=300)
        folder = self.folder("fast")
        self.assertEqual((folder / "CLAUDE.md").read_text(), "@AGENTS.md\n")
        self.assertIn("ul fast", (folder / "AGENTS.md").read_text())
        self.assertIn("UNLAW_BIN", (folder / "src" / "main.rs").read_text())
        self.assertIn("Usage: ul fast", self.ok("fast", "--help").stdout)


class AuthoringGuideTests(CoreTestCase):
    def skill(self) -> Path:
        return self.home / ".agents" / "skills" / "unlaw"

    def test_show_prints_the_guide_with_the_hard_rules(self) -> None:
        text = self.ok("skills", "show", "authoring").stdout
        self.assertTrue(
            text.startswith("# Creating or changing commands and templates")
        )
        for needle in (
            "ul create command <name>",
            "ul config set",
            "main.py",
            "UNLAW_BIN",
            "$UNLAW_STORAGE/<name>/",
            "config.toml",
            "--help",
            "ul template edit",
            "templates/commands/",
            "ul commands --describe",
            "ul doctor",
            "Ask the owner before installing any third-party dependency",
        ):
            self.assertIn(needle, text)

    def test_entry_points_are_listed_in_the_order_unlaw_checks_them(self) -> None:
        text = self.ok("skills", "show", "authoring").stdout
        positions = [
            text.index(f"`{entry}`")
            for entry in ("main.py", "main.sh", "main.js", "Cargo.toml", "main")
        ]
        self.assertEqual(positions, sorted(positions))

    def test_install_writes_the_page_and_skill_md_points_to_it(self) -> None:
        self.ok("skills", "install")
        page = self.skill() / "reference" / "authoring.md"
        self.assertEqual(
            page.read_text(), self.ok("skills", "show", "authoring").stdout
        )
        skill = (self.skill() / "SKILL.md").read_text()
        self.assertIn("## Creating or changing commands and templates", skill)
        self.assertIn("reference/authoring.md", skill)
        self.assertIn("ul create command <name>", skill)
        self.assertIn("Never edit Unlaw", skill)
        self.assertLess(
            skill.index("## Creating or changing"), skill.index("## Commands")
        )

    def test_a_hand_made_command_called_authoring_cannot_shadow_the_guide(self) -> None:
        self.command("authoring", '"""Mine."""\nprint(1)\n')
        self.ok("skills", "install")
        self.assertTrue(
            self.skill()
            .joinpath("reference", "authoring.md")
            .read_text()
            .startswith("# Creating or changing")
        )
        self.assertTrue(
            self.ok("skills", "show", "authoring").stdout.startswith(
                "# Creating or changing"
            )
        )

    def test_removing_the_skill_removes_the_page(self) -> None:
        self.ok("skills", "install")
        self.ok("skills", "remove")
        self.assertFalse(self.skill().exists())


class CommandsCheckTests(CoreTestCase):
    def test_an_unedited_scaffold_fails_on_its_placeholder_description(self) -> None:
        self.ok("create", "command", "hello")
        result = self.ul("commands", "check", "hello")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("--help exits 0", result.stdout)
        self.assertIn("Usage line", result.stdout)
        self.assertIn(
            "FAIL  description is still the scaffold placeholder", result.stdout
        )

    def test_a_placeholder_only_in_the_help_text_fails_too(self) -> None:
        self.ok("create", "command", "hello")
        script = self.unlaw / "commands" / "hello" / "main.py"
        script.write_text(
            script.read_text().replace(
                '"""Custom Unlaw command."""', '"""Says hello."""', 1
            )
        )
        result = self.ul("commands", "check", "hello")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("help text is still the scaffold placeholder", result.stdout)

    def test_an_edited_scaffold_passes(self) -> None:
        self.ok("create", "command", "hello")
        script = self.unlaw / "commands" / "hello" / "main.py"
        script.write_text(
            script.read_text().replace("Custom Unlaw command.", "Says hello.")
        )
        result = self.ok("commands", "check", "hello")
        self.assertIn("description: Says hello.", result.stdout)
        self.assertNotIn("FAIL", result.stdout)

    def test_a_background_process_holding_the_pipes_does_not_stall_the_check(
        self,
    ) -> None:
        self.command(
            "bg",
            '#!/bin/sh\n# Background.\n(sleep 25 &)\necho "Usage: ul bg"\nexit 0\n',
            "main.sh",
        )
        started = time.monotonic()
        result = self.ul("commands", "check", "bg", "--timeout", "3", timeout=20)
        self.assertLess(time.monotonic() - started, 12)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_ctrl_c_stops_the_checked_command(self) -> None:
        pidfile = self.root / "pid"
        self.command(
            "napper",
            f"#!/bin/sh\n# Naps.\necho $$ > {pidfile}\nexec sleep 47\n",
            "main.sh",
        )
        process = subprocess.Popen(
            [str(binary()), "commands", "check", "napper", "--timeout", "40"],
            env=self.env,
            cwd=self.root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        for _ in range(100):
            if pidfile.exists() and pidfile.read_text().strip():
                break
            time.sleep(0.1)
        child = int(pidfile.read_text())
        process.send_signal(signal.SIGINT)
        process.communicate(timeout=15)
        for _ in range(50):
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            os.kill(child, signal.SIGKILL)
            self.fail("the checked command survived Ctrl-C")
        self.assertEqual(process.returncode, 130)

    def test_problems_are_reported_and_fail(self) -> None:
        cases = {
            "silent": ("print('hi')\n", ["no Usage line"]),
            "badexit": (
                "import sys\nprint('Usage: ul badexit')\nsys.exit(3)\n",
                ["--help exited with 3"],
            ),
            "nousage": (
                '"""Does a thing."""\nprint("hello there")\n',
                ["no Usage line"],
            ),
            "nodoc": ("print('Usage: ul nodoc')\n", ["no description"]),
        }
        for name, (body, expected) in cases.items():
            with self.subTest(name=name):
                self.command(name, body)
                result = self.ul("commands", "check", name)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("FAIL", result.stdout)
                self.assertTrue(
                    any(text in result.stdout for text in expected), result.stdout
                )

    def test_a_command_that_waits_is_stopped_and_gets_no_stdin(self) -> None:
        self.command(
            "slow",
            '"""Slow."""\nimport time\nprint("Usage: ul slow")\ntime.sleep(30)\n',
        )
        result = self.ul("commands", "check", "slow", "--timeout", "1", timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertIn("did not finish within 1 s", result.stdout)
        self.command(
            "reader",
            '"""Reads."""\nimport sys\nprint("Usage: ul reader")\nsys.exit(1 if sys.stdin.read() else 0)\n',
        )
        self.ok("commands", "check", "reader", input="typed")

    def test_usage_errors(self) -> None:
        self.assertEqual(self.ul("commands", "check").returncode, 2)
        missing = self.ul("commands", "check", "nothing-here")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("not a command you can check", missing.stderr)
        self.assertEqual(self.ul("commands", "check", "doctor").returncode, 2)
        self.assertEqual(
            self.ul("commands", "check", "x", "--timeout", "0").returncode, 2
        )
        self.assertIn("ul commands check", self.ok("commands", "--help").stdout)


if __name__ == "__main__":
    unittest.main()
