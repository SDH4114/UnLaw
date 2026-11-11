"""Users' own commands, their AGENTS.md/CLAUDE.md and their templates survive every Unlaw maintenance step.

Commands are written by AI agents now, so an update, a reinstall or a feature change
must never touch what they made: files stay byte-identical with the same mtime.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

from ulbin import CoreTestCase, binary

from unlawful.command_sources import command_source

AGENTS_TEXT = "# mine\nRules for this command.\n"
PRESERVED = ("u_py", "u_sh", "u_exec", "u_rust", "u_link")


def snapshot(*roots: Path) -> dict[str, tuple]:
    """Every path under the roots: kind, bytes or link target, mode and mtime."""
    state: dict[str, tuple] = {}
    for root in roots:
        for path in (
            [root, *sorted(root.rglob("*"))]
            if root.exists() or root.is_symlink()
            else []
        ):
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                state[str(path)] = ("link", os.readlink(path))
            elif path.is_dir():
                state[str(path)] = ("dir", info.st_mode)
            else:
                state[str(path)] = (
                    "file",
                    path.read_bytes(),
                    info.st_mode,
                    info.st_mtime_ns,
                )
    return state


class UserWorkSafetyTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env["PATH"] = f"{self.bin}:/usr/bin:/bin"
        self.env.pop("CARGO_TARGET_DIR", None)
        self.ok("init")
        self.cache = self.home / "Library" / "Caches" / "unlaw" / "cargo-target"
        self.cache.mkdir(parents=True)
        self.make_user_work()
        self.guarded = [self.unlaw / "commands" / name for name in PRESERVED] + [
            self.unlaw / "templates" / "commands",
            self.unlaw / "templates" / "projects",
            self.unlaw / "templates" / "python" / "keep.txt",
            self.outside,
        ]
        self.before = snapshot(*self.guarded)

    def make_user_work(self) -> None:
        commands = self.unlaw / "commands"
        self.command("u_py", '"""Mine."""\nprint("py")\n')
        self.command("u_sh", "#!/bin/sh\necho sh\n", "main.sh")
        self.command("u_exec", "#!/bin/sh\necho exec\n", "main", executable=True)
        self.command(
            "u_rust",
            '[package]\nname = "u_rust"\nversion = "0.1.0"\nedition = "2021"\n',
            "Cargo.toml",
        )
        (commands / "u_rust" / "src").mkdir()
        (commands / "u_rust" / "src" / "main.rs").write_text("fn main() {}\n")
        for name in ("u_py", "u_sh", "u_exec", "u_rust"):
            (commands / name / "AGENTS.md").write_text(AGENTS_TEXT)
            (commands / name / "CLAUDE.md").write_text("@AGENTS.md\n")
        (commands / "u_py" / "help.txt").write_text("Mine.\nUsage: ul u_py\n")
        self.outside = self.root / "outside" / "u_link"
        self.outside.mkdir(parents=True)
        (self.outside / "main.py").write_text('"""Linked."""\nprint("link")\n')
        (self.outside / "AGENTS.md").write_text(AGENTS_TEXT)
        (commands / "u_link").symlink_to(self.outside)
        templates = self.unlaw / "templates"
        (templates / "commands" / "main.py").write_text('"""My template."""\n')
        (templates / "commands" / "rust").mkdir()
        (templates / "commands" / "rust" / "Cargo.toml.in").write_text("[package]\n")
        (templates / "projects" / "site.toml").write_text(
            'path = "/tmp/site"\napp = "zed"\nai = false\n'
        )
        (templates / "python" / "keep.txt").write_text("keep")

    def assert_untouched(self) -> None:
        self.assertEqual(snapshot(*self.guarded), self.before)

    def test_init_and_normal_runs(self) -> None:
        self.ok("init")
        self.ok("commands", "--describe")
        self.ok("version")
        self.ok("which", "u_py")
        self.assert_untouched()

    def test_seeds_of_a_new_release_are_upgraded_without_touching_user_work(
        self,
    ) -> None:
        previous = (HERE / "fixtures" / "git-3.10.0.py").read_text()
        script = self.command("git", previous)
        self.ok("init")
        self.assertEqual(script.read_text(), command_source("git"))
        self.assert_untouched()

    def test_features_remove_add_none_and_all(self) -> None:
        self.ok("features", "remove", "yt", "--no-build")
        self.assert_untouched()
        self.ok("features", "add", "yt", "--no-build")
        self.ok("features", "none", "--no-build")
        self.assertFalse((self.unlaw / "commands" / "yt").exists())
        self.assert_untouched()
        self.ok("features", "all", "--no-build")
        self.assertTrue((self.unlaw / "commands" / "yt" / "main.py").is_file())
        self.assert_untouched()

    def test_removing_another_command_and_the_catalog(self) -> None:
        self.ok("remove", "music", "--yes")
        catalog = HERE.parent / "catalog"
        self.ok(
            "commands",
            "get",
            "music",
            env={"UNLAW_CATALOG_URL": catalog.as_uri() + "/"},
        )
        self.assertTrue((self.unlaw / "commands" / "music" / "main.py").is_file())
        self.assert_untouched()

    def test_reinstall(self) -> None:
        log = self.root / "cargo.log"
        self.tool(
            "cargo",
            f"#!{sys.executable}\nimport pathlib, sys\n"
            f"open({str(log)!r}, 'a').write('x\\n')\n"
            "root = pathlib.Path(sys.argv[sys.argv.index('--root') + 1]) / 'bin'\n"
            "root.mkdir(parents=True, exist_ok=True)\n"
            f"(root / 'ul').write_text('#!/bin/sh\\nexec {binary()} \"$@\"\\n')\n"
            "(root / 'ul').chmod(0o755)\n",
        )
        self.ok("reinstall", "--yes")
        self.assertTrue(log.exists())
        self.assert_untouched()

    def test_a_new_default_command_never_replaces_a_user_command_with_its_name(
        self,
    ) -> None:
        # Stands in for a release that adds a seed named like a command the user already made.
        self.ok("features", "remove", "clip", "--no-build")
        self.assertFalse((self.unlaw / "commands" / "clip").exists())
        variants = {
            "main.sh": ("#!/bin/sh\necho mine\n", False),
            "main": ("#!/bin/sh\necho mine\n", True),
            "main.py": ('"""Mine."""\nprint("mine")\n', False),
        }
        for entry, (body, executable) in variants.items():
            with self.subTest(entry=entry):
                script = self.command("clip", body, entry, executable=executable)
                (script.parent / "AGENTS.md").write_text(AGENTS_TEXT)
                mine = snapshot(script.parent)
                self.ok("features", "add", "clip", "--no-build")
                self.ok("init")
                self.assertEqual(snapshot(script.parent), mine)
                self.ok("features", "remove", "clip", "--no-build")
                self.assertEqual(
                    snapshot(script.parent),
                    mine,
                    "an edited or foreign command is kept",
                )
                shutil.rmtree(script.parent)
        self.assert_untouched()

    def test_reinstall_moves_a_user_command_named_like_a_default_into_the_backup(
        self,
    ) -> None:
        self.command("sys", "#!/bin/sh\necho mine\n", "main.sh")
        (self.unlaw / "commands" / "sys" / "main.py").unlink(missing_ok=True)
        self.tool(
            "cargo",
            f"#!{sys.executable}\nimport pathlib, sys\n"
            "root = pathlib.Path(sys.argv[sys.argv.index('--root') + 1]) / 'bin'\n"
            "root.mkdir(parents=True, exist_ok=True)\n"
            f"(root / 'ul').write_text('#!/bin/sh\\nexec {binary()} \"$@\"\\n')\n"
            "(root / 'ul').chmod(0o755)\n",
        )
        self.ok("reinstall", "--yes")
        backups = list((self.unlaw / "backups").iterdir())
        self.assertEqual(
            (backups[0] / "commands" / "sys" / "main.sh").read_text(),
            "#!/bin/sh\necho mine\n",
        )
        self.assertTrue(
            (self.unlaw / "commands" / "sys" / "main.py").is_file(),
            "the default is seeded again",
        )


if __name__ == "__main__":
    unittest.main()
