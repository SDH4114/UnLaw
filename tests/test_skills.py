"""`ul skills`: generated Agent Skill for coding agents."""

from __future__ import annotations

import json
import os

from tests.ulbin import CoreTestCase


class SkillsTests(CoreTestCase):
    def skill(self):
        return self.home / ".agents" / "skills" / "unlaw"

    def test_help_has_no_side_effects(self) -> None:
        for flag in ("--help", "-h"):
            result = self.ok("skills", flag)
            self.assertIn("ul skills install", result.stdout)
        self.assertFalse((self.home / ".agents").exists())

    def test_install_covers_every_command_and_links_for_claude(self) -> None:
        self.ok("skills", "install", "--claude")
        skill = self.skill()
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: unlaw\ndescription: "))
        self.assertIn("ul commands --describe", text)
        records = json.loads(self.ok("commands", "--json").stdout)
        for record in records:
            self.assertTrue((skill / "reference" / f"{record['name']}.md").is_file(), record["name"])
        link = self.home / ".claude" / "skills" / "unlaw"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), "../../.agents/skills/unlaw")
        self.assertEqual(link.resolve(), skill.resolve())
        self.assertIn("ul todo add", (skill / "reference" / "todo.md").read_text(encoding="utf-8"))

    def test_new_and_removed_commands_refresh_the_snapshot(self) -> None:
        self.ok("skills", "install")
        reference = self.skill() / "reference"
        self.ok("create", "command", "hello")
        self.assertTrue((reference / "hello.md").is_file())
        script = self.unlaw / "commands" / "hello" / "main.py"
        (script.parent / "help.txt").write_text("Say hello.\nUsage: ul hello [name]\n", encoding="utf-8")
        self.ok("version")
        self.ok("commands")
        self.assertIn("Usage: ul hello [name]", (reference / "hello.md").read_text(encoding="utf-8"))
        self.assertIn("`hello`", (self.skill() / "SKILL.md").read_text(encoding="utf-8"))
        script.unlink()
        self.ok("commands")
        self.assertFalse((reference / "hello.md").exists())

    def test_aliases_do_not_leak_their_expansion(self) -> None:
        self.ok("config", "set", "aliases.secret", '["tg", "send", "/private/notes.txt"]')
        self.ok("skills", "install")
        everything = "".join(path.read_text(encoding="utf-8") for path in self.skill().rglob("*.md"))
        self.assertIn("secret", everything)
        self.assertNotIn("/private/notes.txt", everything)

    def test_foreign_folders_are_never_overwritten(self) -> None:
        foreign = self.skill()
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("mine\n", encoding="utf-8")
        result = self.ul("skills", "install")
        self.assertEqual(result.returncode, 1)
        self.assertIn("was not created by `ul skills`", result.stderr)
        self.assertEqual((foreign / "SKILL.md").read_text(encoding="utf-8"), "mine\n")
        claude = self.home / ".claude" / "skills" / "unlaw"
        claude.mkdir(parents=True)
        result = self.ul("skills", "install", "--path", str(self.root / "elsewhere"), "--claude")
        self.assertEqual(result.returncode, 1)
        self.assertIn("was not replaced", result.stderr)
        self.assertTrue(claude.is_dir() and not claude.is_symlink())

    def test_project_install_and_remove_keep_added_files(self) -> None:
        project = self.root / "project"
        project.mkdir()
        self.ok("skills", "install", "--project", "--claude", cwd=project)
        skill = project / ".agents" / "skills" / "unlaw"
        self.assertTrue((skill / "SKILL.md").is_file())
        self.assertTrue((project / ".claude" / "skills" / "unlaw").is_symlink())
        self.assertIn(str(skill), self.ok("skills", "list").stdout)
        (skill / "notes.md").write_text("keep\n", encoding="utf-8")
        self.ok("skills", "remove", "--project", cwd=project)
        self.assertFalse((skill / "SKILL.md").exists())
        self.assertFalse((project / ".claude" / "skills" / "unlaw").exists())
        self.assertEqual((skill / "notes.md").read_text(encoding="utf-8"), "keep\n")
        self.assertIn("No skill installed", self.ok("skills", "list").stdout)

    def test_show_prints_skill_and_reference_pages(self) -> None:
        self.assertIn("name: unlaw", self.ok("skills", "show").stdout)
        self.assertIn("# ul zip", self.ok("skills", "show", "zip").stdout)
        self.assertEqual(self.ul("skills", "show", "nope").returncode, 1)
        self.assertFalse((self.home / ".agents").exists())
