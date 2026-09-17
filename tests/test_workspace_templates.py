from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class WorkspaceTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {"XDG_CONFIG_HOME": str(self.root / "config")}
        self.project = self.root / "HearMe"
        self.project.mkdir()

    def test_create_load_and_discover_template(self) -> None:
        from unlawful.workspace_templates import (
            create_workspace_template,
            discover_workspace_templates,
            load_workspace_template,
        )

        with patch.dict(os.environ, self.env, clear=False):
            created = create_workspace_template("hearme", self.project, "zed", True)
            loaded = load_workspace_template("hearme")
            discovered = discover_workspace_templates()
        self.assertEqual(created, loaded)
        self.assertEqual(created.path, self.project.resolve())
        self.assertEqual(created.app, "zed")
        self.assertTrue(created.ai)
        self.assertEqual(discovered, {"hearme": created})

    def test_manifest_has_only_expected_fields(self) -> None:
        from unlawful.workspace_templates import (
            create_workspace_template,
            workspace_templates_dir,
        )

        with patch.dict(os.environ, self.env, clear=False):
            create_workspace_template("hearme", self.project, "obsidian", False)
            text = (workspace_templates_dir() / "hearme.toml").read_text(encoding="utf-8")
        self.assertEqual(
            text,
            f'path = "{self.project.resolve()}"\napp = "obsidian"\nai = false\n',
        )

    def test_create_rejects_invalid_name_app_and_missing_path(self) -> None:
        from unlawful.workspace_templates import (
            WorkspaceTemplateError,
            create_workspace_template,
        )

        with patch.dict(os.environ, self.env, clear=False):
            with self.assertRaisesRegex(WorkspaceTemplateError, "name"):
                create_workspace_template("Bad Name", self.project, "zed", True)
            with self.assertRaisesRegex(WorkspaceTemplateError, "app"):
                create_workspace_template("hearme", self.project, "code", True)
            with self.assertRaisesRegex(WorkspaceTemplateError, "directory"):
                create_workspace_template("hearme", self.root / "missing", "zed", True)

    def test_create_never_overwrites_existing_template(self) -> None:
        from unlawful.workspace_templates import (
            WorkspaceTemplateError,
            create_workspace_template,
        )

        with patch.dict(os.environ, self.env, clear=False):
            create_workspace_template("hearme", self.project, "zed", False)
            with self.assertRaisesRegex(WorkspaceTemplateError, "already exists"):
                create_workspace_template("hearme", self.project, "obsidian", True)

    def test_load_rejects_unknown_missing_and_invalid_fields(self) -> None:
        from unlawful.config import ensure_layout
        from unlawful.workspace_templates import (
            WorkspaceTemplateError,
            load_workspace_template,
            workspace_templates_dir,
        )

        cases = (
            ('path = "/tmp"\napp = "zed"\nai = true\nextra = 1\n', "unknown"),
            ('path = "/tmp"\napp = "zed"\n', "fields"),
            ('path = "/tmp"\napp = "code"\nai = true\n', "app"),
            ('path = "/tmp"\napp = "zed"\nai = "yes"\n', "ai"),
            ('not = [valid toml', "Could not read"),
        )
        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
            manifest = workspace_templates_dir() / "demo.toml"
            for text, message in cases:
                with self.subTest(text=text):
                    manifest.write_text(text, encoding="utf-8")
                    with self.assertRaisesRegex(WorkspaceTemplateError, message):
                        load_workspace_template("demo")

    def test_discovery_rejects_invalid_manifest_filename(self) -> None:
        from unlawful.config import ensure_layout
        from unlawful.workspace_templates import (
            WorkspaceTemplateError,
            discover_workspace_templates,
            workspace_templates_dir,
        )

        with patch.dict(os.environ, self.env, clear=False):
            ensure_layout()
            (workspace_templates_dir() / "Bad Name.toml").write_text(
                f'path = "{self.project}"\napp = "zed"\nai = false\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(WorkspaceTemplateError, "name"):
                discover_workspace_templates()


if __name__ == "__main__":
    unittest.main()
