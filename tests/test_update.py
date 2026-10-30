from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ulbin import CoreTestCase, binary  # noqa: E402

VERSION = re.search(r'__version__ = "(.+)"', (Path(__file__).resolve().parents[1] / "src/unlawful/__init__.py").read_text()).group(1)

REPOSITORY = "https://github.com/SDH4114/UnLaw.git"


class UpdateTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env["PATH"] = f"{self.bin}:/usr/bin:/bin"
        self.env.pop("CARGO_TARGET_DIR", None)
        self.fake_git("1234567890abcdef1234567890abcdef12345678")
        version = self.ok("--version").stdout.split()
        self.installed_commit = version[2].strip("()") if len(version) > 2 else ""

    def fake_git(self, commit: str | None, *, exit_code: int = 0) -> Path:
        """`git ls-remote` stand-in printing one ref, or nothing."""
        log = self.root / "git.log"
        line = f"{commit}\trefs/heads/main\n" if commit else ""
        self.tool(
            "git",
            f"#!{sys.executable}\nimport pathlib, sys\n"
            f"pathlib.Path({str(log)!r}).write_text('\\n'.join(sys.argv[1:]))\n"
            f"sys.stdout.write({line!r})\nraise SystemExit({exit_code})\n",
        )
        return log

    def fake_cargo(self, *, exit_code: int = 0, version: str = "9.9.9") -> Path:
        """Appends UNLAW_PYTHON and argv (one call per block, ending with `==`), then installs a fake `ul`."""
        log = self.root / "cargo.log"
        self.tool(
            "cargo",
            f"#!{sys.executable}\nimport os, pathlib, sys\n"
            f"open({str(log)!r}, 'a').write('\\n'.join([os.environ.get('UNLAW_PYTHON', ''), *sys.argv[1:], '==']) + '\\n')\n"
            f"pathlib.Path({str(self.root / 'target.log')!r}).write_text(os.environ.get('CARGO_TARGET_DIR', ''))\n"
            f"if {exit_code}: raise SystemExit({exit_code})\n"
            "root = pathlib.Path(sys.argv[sys.argv.index('--root') + 1]) / 'bin'\n"
            "root.mkdir(parents=True, exist_ok=True)\n"
            f"(root / 'ul').write_text('#!/bin/sh\\necho Unlaw {version}\\n')\n"
            "(root / 'ul').chmod(0o755)\n",
        )
        return log

    def fake_curl(self, body: str, *, exit_code: int = 0) -> Path:
        log = self.root / "curl.log"
        self.tool(
            "curl",
            f"#!{sys.executable}\nimport pathlib, sys\n"
            f"pathlib.Path({str(log)!r}).write_text('\\n'.join(sys.argv[1:]))\n"
            f"sys.stdout.write({body!r})\n"
            f"if {exit_code}: sys.stderr.write('404'); raise SystemExit({exit_code})\n",
        )
        return log

    def test_help_and_usage(self) -> None:
        result = self.ok("update", "--help")
        self.assertIn("Usage: ul update", result.stdout)
        self.assertIn("Example", result.stdout)
        for args in (["--branch"], ["--tag", "--check"], ["--branch", "a", "--tag", "b"], ["now"]):
            with self.subTest(args=args):
                result = self.ul("update", *args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("Usage: ul update", result.stderr)

    def test_update_reinstalls_from_github_into_local_bin(self) -> None:
        log = self.fake_cargo()
        result = self.ok("update")
        common = [sys.executable, "install", "--locked", "--force", "--git", REPOSITORY, "--root", str(self.home / ".local")]
        self.assertEqual(
            log.read_text().splitlines(),
            [*common, "--no-default-features", "--features", "lm,agent,game", "unlaw", "==", *common, "ule", "=="],
        )
        self.assertIn("Updated to Unlaw 9.9.9", result.stdout)
        self.assertIn("edited ones are kept", result.stdout)

    def test_up_to_date_is_not_rebuilt_unless_forced(self) -> None:
        if not self.installed_commit:
            self.skipTest("this build has no commit")
        self.fake_git(self.installed_commit + "0" * 33)
        ule = self.home / ".local" / "bin" / "ule"
        ule.parent.mkdir(parents=True)
        ule.write_text("#!/bin/sh\n")
        ule.chmod(0o755)
        log = self.fake_cargo()
        result = self.ok("update")
        self.assertIn("is up to date", result.stdout)
        self.assertFalse(log.exists())
        self.ok("update", "--force")
        self.assertTrue(log.exists())
        # Without ule installed, the same commit is installed to add it.
        log.unlink()
        ule.unlink()
        self.ok("update")
        self.assertTrue(log.exists())

    def test_builds_share_a_cache_folder(self) -> None:
        self.fake_cargo()
        self.ok("update")
        self.assertEqual((self.root / "target.log").read_text(), str(self.home / "Library" / "Caches" / "unlaw" / "cargo-target"))
        self.ok("update", env={"CARGO_TARGET_DIR": str(self.root / "mine")})
        self.assertEqual((self.root / "target.log").read_text(), str(self.root / "mine"))

    def test_branch_tag_and_fork_are_passed_to_cargo(self) -> None:
        log = self.fake_cargo()
        self.ok("update", "--branch", "dev")
        self.assertIn("--branch\ndev\n--root", log.read_text())
        self.ok("update", "--tag", "v3.0.0", env={"UNLAW_UPDATE_REPOSITORY": "https://github.com/me/fork.git"})
        text = log.read_text()
        self.assertIn("--git\nhttps://github.com/me/fork.git\n--tag\nv3.0.0", text)

    def test_binary_in_a_bin_directory_updates_in_place(self) -> None:
        prefix = self.root / "prefix"
        (prefix / "bin").mkdir(parents=True)
        installed = prefix / "bin" / "ul"
        shutil.copy2(binary(), installed)
        log = self.fake_cargo()
        result = self.ul_with(installed, "update")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"--root\n{prefix}\n", log.read_text())

    def ul_with(self, executable: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(executable), *args], env=self.env, capture_output=True, text=True, timeout=60)

    def test_failed_cargo_reports_and_keeps_exit_code(self) -> None:
        self.fake_cargo(exit_code=101)
        result = self.ul("update")
        self.assertEqual(result.returncode, 101)
        self.assertIn("was not changed", result.stderr)

    def test_second_package_failure_reports_partial_update(self) -> None:
        self.fake_cargo()
        cargo = self.bin / "cargo"
        source = cargo.read_text()
        source = source.replace("root = pathlib.Path", "if sys.argv[-1] == 'ule': raise SystemExit(42)\nroot = pathlib.Path")
        cargo.write_text(source)
        result = self.ul("update", "--force")
        self.assertEqual(result.returncode, 42)
        self.assertIn("unlaw was installed", result.stderr)
        self.assertIn("ule", result.stderr)
        self.assertNotIn("was not changed", result.stderr)

    def test_missing_cargo_explains_how_to_install_rust(self) -> None:
        result = self.ul("update")
        self.assertEqual(result.returncode, 1)
        self.assertIn("rustup", result.stderr)

    def test_rustup_cargo_outside_path_is_found(self) -> None:
        cargo_bin = self.home / ".cargo" / "bin"
        cargo_bin.mkdir(parents=True)
        self.fake_cargo()
        shutil.move(self.bin / "cargo", cargo_bin / "cargo")
        result = self.ok("update")
        self.assertIn(str(cargo_bin / "cargo"), result.stdout)

    def test_check_compares_versions_without_installing(self) -> None:
        cargo_log = self.fake_cargo()
        curl_log = self.fake_curl('[package]\nname = "unlaw"\nversion = "9.0.0"\n')
        result = self.ok("update", "--check")
        installed = f"{VERSION} ({self.installed_commit})" if self.installed_commit else VERSION
        self.assertEqual(result.stdout.splitlines()[:2], [f"Installed: {installed}", "Latest:    9.0.0 (1234567, main)"])
        self.assertIn("Update available: a new version", result.stdout)
        self.assertIn("https://raw.githubusercontent.com/SDH4114/UnLaw/main/Cargo.toml", curl_log.read_text())
        self.assertFalse(cargo_log.exists())
        self.fake_curl('[package]\nversion = "1.0.0"\n')
        self.assertIn("/v1/Cargo.toml", (self.ok("update", "--check", "--tag", "v1"), curl_log.read_text())[1])

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_check_compares_commits_when_the_version_is_the_same(self) -> None:
        if not self.installed_commit:
            self.skipTest("this build has no commit")
        self.fake_curl(f'[package]\nversion = "{VERSION}"\n')
        self.fake_git(self.installed_commit + "0" * 33)
        self.assertIn("Up to date.", self.ok("update", "--check").stdout)
        self.fake_git("f" * 40)
        self.assertIn("Update available: newer commits", self.ok("update", "--check").stdout)
        log = self.fake_git(None)
        self.assertIn("commit is unknown", self.ok("update", "--check").stdout)
        self.assertIn("ls-remote\nhttps://github.com/SDH4114/UnLaw.git\nrefs/heads/main", log.read_text())

    def test_check_uses_the_peeled_commit_of_annotated_tags(self) -> None:
        self.fake_curl('[package]\nversion = "3.0.0"\n')
        self.tool(
            "git",
            "#!/bin/sh\nprintf 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\\trefs/tags/v3\\nbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\\trefs/tags/v3^{}\\n'\n",
        )
        self.assertIn("(bbbbbbb, v3)", self.ok("update", "--check", "--tag", "v3").stdout)

    def test_check_failures(self) -> None:
        self.fake_curl("", exit_code=22)
        result = self.ul("update", "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Could not fetch", result.stderr)
        self.fake_curl("not toml at all [")
        self.assertIn("has no package version", self.ul("update", "--check").stderr)
        result = self.ul("update", "--check", env={"UNLAW_UPDATE_REPOSITORY": "https://gitlab.com/me/fork"})
        self.assertEqual(result.returncode, 2)
        (self.bin / "curl").unlink()
        result = self.ul("update", "--check", env={"PATH": str(self.bin)})
        self.assertIn("Could not run curl", result.stderr)

    def test_update_is_a_system_command(self) -> None:
        self.assertEqual(self.ok("which", "update").stdout, "update: system\n")
        self.assertIn("--check:Compare with GitHub", self.ok("_complete", "2", "update").stdout)
        self.assertEqual(self.ul("create", "command", "update").returncode, 2)


if __name__ == "__main__":
    unittest.main()
