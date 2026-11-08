from __future__ import annotations

import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from tests import fake_git_hosts

fake_git_hosts.install()

from unlawful.built_in_commands.git import main as cmd

HOST_NAMES = {"github", "gitlab", "codeberg", "gitea"}


class GitCommandCase(unittest.TestCase):
    """Runs the real git against local repositories; host calls are stubbed."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.real_git = shutil.which("git")
        self.assertIsNotNone(self.real_git)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.log = self.tmp / "calls.log"
        for name in ("open", "gh"):
            script = self.bin / name
            script.write_text(
                f'#!/bin/sh\necho "{name} $*" >> "{self.log}"\n', encoding="utf-8"
            )
            script.chmod(0o755)
        (self.tmp / "home").mkdir()
        config = self.tmp / "gitconfig"
        config.write_text(
            "[user]\n\tname = Tester\n\temail = t@example.com\n", encoding="utf-8"
        )
        env = {
            "HOME": str(self.tmp / "home"),
            "XDG_CONFIG_HOME": str(self.tmp / "xdg"),
            "GIT_CONFIG_GLOBAL": str(config),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "PATH": os.pathsep.join(
                [str(self.bin), str(Path(self.real_git).parent), "/bin"]
            ),
        }
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.work = self.tmp / "work" / "proj"
        self.work.mkdir(parents=True)
        previous = os.getcwd()
        os.chdir(self.work)
        self.addCleanup(os.chdir, previous)
        self.stubs: dict[str, MagicMock] = {}
        self.stub_hosts()

    # -- helpers ---------------------------------------------------------
    def stub_hosts(self, **overrides) -> None:
        defaults = {
            "expand_remote": MagicMock(side_effect=lambda spec: spec),
            "is_host_name": MagicMock(side_effect=lambda spec: spec in HOST_NAMES),
            "create_repo": MagicMock(),
            "host_of": MagicMock(return_value=None),
            "web_url": MagicMock(return_value=None),
            "pr_url": MagicMock(return_value=None),
            "ssh_check": MagicMock(return_value=(True, "ok")),
            "ensure_ssh_key": MagicMock(return_value=self.tmp / "key.pub"),
            "prompt_token": MagicMock(),
        }
        defaults.update(overrides)
        for name, mock in defaults.items():
            patcher = patch.object(cmd, name, mock)
            patcher.start()
            self.addCleanup(patcher.stop)
            self.stubs[name] = mock
        patcher = patch.object(cmd, "HOSTS", fake_git_hosts.HOSTS)
        patcher.start()
        self.addCleanup(patcher.stop)

    def git(self, *args: str, cwd: Path | None = None) -> str:
        result = subprocess.run(
            [self.real_git, *args],
            cwd=cwd or self.work,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def ul(self, *args: str, stdin: str = "") -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        sys.stdout.flush()
        sys.stderr.flush()
        saved = [os.dup(1), os.dup(2)]
        null = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(null, 1)
            os.dup2(null, 2)
            with (
                patch("sys.stdin", io.StringIO(stdin)),
                contextlib.redirect_stdout(out),
                contextlib.redirect_stderr(err),
            ):
                code = cmd.main(list(args))
        finally:
            os.dup2(saved[0], 1)
            os.dup2(saved[1], 2)
            for fd in (*saved, null):
                os.close(fd)
        return code, out.getvalue(), err.getvalue()

    def make_repo(self, *, origin: bool = True) -> Path | None:
        self.git("init", "-q", "-b", "main")
        (self.work / "README.md").write_text("hello\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "first")
        if not origin:
            return None
        return self.add_bare("origin", set_upstream=True)

    def add_bare(self, remote: str, *, set_upstream: bool = False) -> Path:
        bare = self.tmp / f"{remote}.git"
        self.git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.tmp)
        self.git("remote", "add", remote, str(bare))
        if set_upstream:
            self.git("push", "-q", "-u", remote, "main")
        return bare

    def subjects(self, bare: Path, branch: str = "main") -> list[str]:
        return self.git("log", "--format=%s", branch, cwd=bare).splitlines()

    def calls(self) -> list[str]:
        return (
            self.log.read_text(encoding="utf-8").splitlines()
            if self.log.exists()
            else []
        )

    def change(self, name: str = "file.txt", text: str = "x\n") -> None:
        (self.work / name).write_text(text, encoding="utf-8")


class CommitWorkflowTests(GitCommandCase):
    def test_default_commits_and_pushes(self) -> None:
        bare = self.make_repo()
        self.change()
        self.assertEqual(self.ul("add feature")[0], 0)
        self.assertEqual(self.subjects(bare)[0], "add feature")

    def test_default_pushes_even_when_auto_push_is_off(self) -> None:
        # Replaces the old mocked test: `ul git <message>` always pushes, git.auto_push does not matter.
        from unlawful.config import ensure_layout, set_config_value

        ensure_layout()
        set_config_value("git.auto_push", False)
        bare = self.make_repo()
        self.change()
        self.assertEqual(self.ul("always push")[0], 0)
        self.assertEqual(self.subjects(bare)[0], "always push")

    def test_deleting_a_tracked_secret_is_allowed(self) -> None:
        bare = self.make_repo()
        self.change(".env", "TOKEN=1\n")
        self.assertEqual(self.ul("commit", "oops", "--allow-secrets")[0], 0)
        (self.work / ".env").unlink()
        code, _, err = self.ul("push", "remove the env file")
        self.assertEqual(code, 0, err)
        self.assertNotIn(".env", self.git("ls-tree", "--name-only", "main", cwd=bare).splitlines())

    def test_push_sets_the_upstream_of_a_new_branch(self) -> None:
        bare = self.make_repo()
        self.git("switch", "-q", "-c", "feat/x")
        self.change()
        code, _, err = self.ul("push", "on a branch")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.subjects(bare, "feat/x")[0], "on a branch")
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "feat/x@{u}"), "origin/feat/x")

    def test_commit_does_not_push(self) -> None:
        bare = self.make_repo()
        self.change()
        self.assertEqual(self.ul("commit", "local", "only")[0], 0)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "local only")
        self.assertEqual(self.subjects(bare), ["first"])

    def test_status_and_pull_were_removed_and_never_commit(self) -> None:
        # Removed at Haos's request; the words must not become commit messages either.
        bare = self.make_repo()
        self.change()
        for words in (["status"], ["pull"], ["status", "x"]):
            with self.subTest(words=words):
                code, _, err = self.ul(*words)
                self.assertEqual(code, 2)
                self.assertIn(f"git {words[0]}", err)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "first")
        self.assertEqual(self.subjects(bare), ["first"])

    def test_push_with_message_commits_and_pushes(self) -> None:
        bare = self.make_repo()
        self.change()
        self.assertEqual(self.ul("push", "with", "words")[0], 0)
        self.assertEqual(self.subjects(bare)[0], "with words")

    def test_push_prompts_for_missing_message(self) -> None:
        bare = self.make_repo()
        self.change()
        self.assertEqual(self.ul("push", stdin="from prompt\n")[0], 0)
        self.assertEqual(self.subjects(bare)[0], "from prompt")

    def test_push_without_message_and_empty_prompt_commits_nothing(self) -> None:
        bare = self.make_repo()
        self.change()
        code, _, err = self.ul("push", stdin="")
        self.assertEqual(code, 2)
        self.assertEqual(self.subjects(bare), ["first"])
        self.assertIn("cancelled", err)

    def test_push_with_nothing_to_commit_only_pushes(self) -> None:
        bare = self.make_repo()
        self.change()
        self.git("add", ".")
        self.git("commit", "-q", "-m", "unpushed")
        code, _, err = self.ul("push")
        self.assertEqual(code, 0)
        self.assertIn("nothing to commit", err)
        self.assertEqual(self.subjects(bare)[0], "unpushed")

    def test_push_reaches_every_mirror(self) -> None:
        bare = self.make_repo()
        first = self.add_bare("mirror-a")
        second = self.add_bare("mirror-b")
        self.change()
        self.assertEqual(self.ul("push", "all places")[0], 0)
        for target in (bare, first, second):
            self.assertEqual(self.subjects(target)[0], "all places")

    def test_failing_mirror_warns_but_succeeds(self) -> None:
        bare = self.make_repo()
        self.git("remote", "add", "mirror-bad", str(self.tmp / "missing.git"))
        good = self.add_bare("mirror-good")
        self.change()
        code, _, err = self.ul("push", "still ok")
        self.assertEqual(code, 0)
        self.assertIn("mirror-bad", err)
        self.assertEqual(self.subjects(bare)[0], "still ok")
        self.assertEqual(self.subjects(good)[0], "still ok")

    def test_failing_origin_fails_and_skips_mirrors(self) -> None:
        self.make_repo()
        self.git("remote", "set-url", "origin", str(self.tmp / "missing.git"))
        mirror = self.add_bare("mirror-a")
        self.change()
        code, _, _ = self.ul("push", "nope")
        self.assertNotEqual(code, 0)
        self.assertFalse((mirror / "refs" / "heads" / "main").exists())

    def test_sync_pulls_with_rebase_then_pushes(self) -> None:
        bare = self.make_repo()
        other = self.tmp / "other"
        self.git("clone", "-q", str(bare), str(other), cwd=self.tmp)
        (other / "theirs.txt").write_text("t\n", encoding="utf-8")
        self.git("add", ".", cwd=other)
        self.git("commit", "-q", "-m", "theirs", cwd=other)
        self.git("push", "-q", cwd=other)
        self.change()
        self.assertEqual(self.ul("sync", "mine")[0], 0)
        self.assertEqual(self.subjects(bare)[:2], ["mine", "theirs"])


class SecretsGuardTests(GitCommandCase):
    NAMES: ClassVar[list[str]] = [
        ".env",
        ".env.local",
        "server.pem",
        "api.key",
        "id_rsa",
        "id_rsa_work",
        "id_ed25519",
        "cert.p12",
    ]

    def test_secret_files_block_every_commit_path(self) -> None:
        bare = self.make_repo()
        for args in (["msg"], ["push", "msg"], ["commit", "msg"], ["sync", "msg"]):
            for name in self.NAMES:
                with self.subTest(args=args[0], name=name):
                    self.change(name, "secret\n")
                    self.change("fine.txt", "ok\n")
                    code, _, err = self.ul(*args)
                    self.assertEqual(code, 1)
                    self.assertIn(name, err)
                    self.assertIn(".gitignore", err)
                    self.assertNotIn(
                        name, self.git("diff", "--cached", "--name-only").splitlines()
                    )
                    self.assertEqual(self.git("log", "-1", "--format=%s"), "first")
                    (self.work / name).unlink()
                    self.git("reset", "-q")
        self.assertEqual(self.subjects(bare), ["first"])

    def test_env_example_and_public_keys_are_allowed(self) -> None:
        self.make_repo()
        self.change(".env.example", "KEY=\n")
        self.change("id_rsa.pub", "ssh-rsa AAA\n")
        self.assertEqual(self.ul("commit", "ok")[0], 0)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "ok")

    def test_secret_in_subdirectory_is_found(self) -> None:
        self.make_repo()
        (self.work / "deploy").mkdir()
        self.change("deploy/.env", "S=1\n")
        self.assertEqual(self.ul("commit", "x")[0], 1)

    def test_allow_secrets_overrides(self) -> None:
        self.make_repo()
        self.change(".env", "S=1\n")
        self.assertEqual(self.ul("commit", "--allow-secrets", "with env")[0], 0)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "with env")
        self.assertIn(".env", self.git("show", "--name-only", "--format=", "HEAD"))

    def test_secret_names_ignore_case_and_cover_more_kinds(self) -> None:
        bare = self.make_repo()
        for name in (".ENV", "ID_RSA", "id_ecdsa", "id_dsa", "cert.PFX", "key.p8", "app.jks", "release.keystore", ".netrc", ".pypirc"):
            with self.subTest(name=name):
                self.change(name, "secret\n")
                code, _, err = self.ul("push", "add " + name)
                self.assertEqual(code, 1)
                self.assertIn(name, err)
                (self.work / name).unlink()
        self.assertEqual(self.subjects(bare), ["first"])

    def test_pathspec_magic_in_a_file_name_only_unstages_that_file(self) -> None:
        self.make_repo()
        self.change("a.txt", "keep me staged\n")
        self.git("add", "a.txt")
        self.change(":(exclude)z.key", "secret\n")
        self.git("add", "--", ":(literal):(exclude)z.key")
        code, _, err = self.ul("commit", "x")
        self.assertEqual(code, 1)
        staged = self.git("diff", "--cached", "--name-only").splitlines()
        self.assertIn("a.txt", staged, err)
        self.assertNotIn(":(exclude)z.key", staged)

    def test_large_files_are_blocked(self) -> None:
        self.make_repo()
        self.change("big.bin", "x" * 11)
        with patch.object(cmd, "_GIT_MAX_BYTES", 10):
            code, _, err = self.ul("commit", "big")
        self.assertEqual(code, 1)
        self.assertIn("big.bin", err)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")


class InitTests(GitCommandCase):
    def test_refuses_inside_a_work_tree(self) -> None:
        self.make_repo(origin=False)
        code, _, err = self.ul("init")
        self.assertEqual(code, 1)
        self.assertIn("already", err)

    def test_creates_repo_with_main_gitignore_and_first_commit(self) -> None:
        self.change("pyproject.toml", "[project]\n")
        self.change("Cargo.toml", "[package]\n")
        self.assertEqual(self.ul("init")[0], 0)
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "main")
        self.assertEqual(self.git("log", "--format=%s"), "Initial commit")
        lines = (self.work / ".gitignore").read_text(encoding="utf-8").splitlines()
        for wanted in (
            "__pycache__/",
            "target/",
            ".DS_Store",
            ".env",
            ".env.*",
            "!.env.example",
            "*.pem",
            "*.key",
        ):
            self.assertIn(wanted, lines)
        self.assertNotIn("node_modules/", lines)
        self.assertIn("pyproject.toml", self.git("ls-files"))

    def test_gitignore_merge_keeps_user_lines_and_adds_only_missing(self) -> None:
        (self.work / ".gitignore").write_text(
            "my-private/\nnode_modules/\n.DS_Store", encoding="utf-8"
        )
        self.change("package.json", "{}\n")
        self.assertEqual(self.ul("init")[0], 0)
        lines = (self.work / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[:3], ["my-private/", "node_modules/", ".DS_Store"])
        self.assertEqual(lines.count("node_modules/"), 1)
        self.assertEqual(lines.count(".DS_Store"), 1)
        self.assertIn(".env", lines)

    def test_detects_cpp_and_requirements(self) -> None:
        self.change("CMakeLists.txt", "project(x)\n")
        self.change("requirements.txt", "requests\n")
        self.assertEqual(self.ul("init")[0], 0)
        lines = (self.work / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("build/", lines)
        self.assertIn("__pycache__/", lines)

    def test_falls_back_for_git_without_initial_branch_switch(self) -> None:
        wrapper = self.bin / "git"
        wrapper.write_text(
            '#!/bin/sh\nif [ "$1" = init ] && [ "$2" = -b ]; then echo "unknown switch" >&2; exit 129; fi\n'
            f'exec "{self.real_git}" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        self.assertEqual(self.ul("init")[0], 0)
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "main")
        self.assertEqual(self.git("log", "--format=%s"), "Initial commit")

    def test_secrets_guard_runs_before_first_commit(self) -> None:
        self.change("cert.p12", "binary\n")
        code, _, err = self.ul("init")
        self.assertEqual(code, 1)
        self.assertIn("cert.p12", err)
        result = subprocess.run(
            [self.real_git, "rev-parse", "--verify", "-q", "HEAD"],
            cwd=self.work,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_connect_creates_repo_and_pushes(self) -> None:
        bare = self.tmp / "created.git"
        self.git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.tmp)
        self.stubs["create_repo"].return_value = fake_git_hosts.Created(
            str(bare), "https://x", "https://x"
        )
        self.assertEqual(self.ul("init", "--connect", "github")[0], 0)
        args, kwargs = self.stubs["create_repo"].call_args
        self.assertEqual(args[:2], ("github", "proj"))
        self.assertTrue(kwargs["private"])
        self.assertEqual(self.git("remote", "get-url", "origin"), str(bare))
        self.assertEqual(self.subjects(bare), ["Initial commit"])

    def test_connect_public_and_name(self) -> None:
        bare = self.tmp / "created.git"
        self.git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.tmp)
        self.stubs["create_repo"].return_value = fake_git_hosts.Created(
            str(bare), "https://x", "https://x"
        )
        self.assertEqual(
            self.ul("init", "--connect", "gitlab", "--public", "--name", "other")[0], 0
        )
        args, kwargs = self.stubs["create_repo"].call_args
        self.assertEqual(args[:2], ("gitlab", "other"))
        self.assertFalse(kwargs["private"])


class InitSymlinkTests(GitCommandCase):
    def test_a_symlinked_gitignore_is_never_written_through(self) -> None:
        target = self.tmp / "home" / "zshrc"
        target.write_text("export A=1\n", encoding="utf-8")
        (self.work / ".gitignore").symlink_to(target)
        code, _, err = self.ul("init")
        self.assertEqual(code, 1)
        self.assertIn(".gitignore", err)
        self.assertEqual(target.read_text(encoding="utf-8"), "export A=1\n")


class ConnectTests(GitCommandCase):
    def created(self, bare: Path) -> None:
        self.stubs["create_repo"].return_value = fake_git_hosts.Created(
            str(bare), "https://x", "https://x"
        )

    def new_bare(self, name: str = "target") -> Path:
        bare = self.tmp / f"{name}.git"
        self.git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.tmp)
        return bare

    def test_needs_a_repository(self) -> None:
        code, _, err = self.ul("connect", "github")
        self.assertEqual(code, 1)
        self.assertIn("ul git init", err)

    def test_host_name_creates_private_repo_sets_origin_and_pushes(self) -> None:
        self.make_repo(origin=False)
        bare = self.new_bare()
        self.created(bare)
        self.assertEqual(self.ul("connect", "github")[0], 0)
        args, kwargs = self.stubs["create_repo"].call_args
        self.assertEqual(args[:2], ("github", "proj"))
        self.assertTrue(kwargs["private"])
        self.assertIsNone(kwargs["base_url"])
        self.assertEqual(self.git("remote", "get-url", "origin"), str(bare))
        self.assertEqual(self.subjects(bare), ["first"])
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "@{u}"), "origin/main")

    def test_options_are_passed_to_create_repo(self) -> None:
        self.make_repo(origin=False)
        self.created(self.new_bare())
        self.assertEqual(
            self.ul(
                "connect",
                "gitea",
                "--public",
                "--name",
                "named",
                "--url",
                "https://git.example",
            )[0],
            0,
        )
        args, kwargs = self.stubs["create_repo"].call_args
        self.assertEqual(args[:2], ("gitea", "named"))
        self.assertFalse(kwargs["private"])
        self.assertEqual(kwargs["base_url"], "https://git.example")

    def test_other_spec_goes_through_expand_remote(self) -> None:
        self.make_repo(origin=False)
        bare = self.new_bare()
        self.stubs["expand_remote"].side_effect = lambda spec: str(bare)
        self.assertEqual(self.ul("connect", "gh:me/proj")[0], 0)
        self.stubs["expand_remote"].assert_called_once_with("gh:me/proj")
        self.stubs["create_repo"].assert_not_called()
        self.assertEqual(self.subjects(bare), ["first"])

    def test_different_origin_is_refused_without_force_and_before_creating(
        self,
    ) -> None:
        self.make_repo()
        code, _, err = self.ul("connect", "github")
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        self.stubs["create_repo"].assert_not_called()

    def test_rerun_on_a_connected_host_reuses_origin(self) -> None:
        # After a failed SSH check the user reruns the same command: nothing is created twice.
        bare = self.make_repo()
        self.stubs["host_of"].side_effect = lambda url: fake_git_hosts.HOSTS["github"] if url == str(bare) else None
        self.stubs["host_of"].return_value = None
        code, _, err = self.ul("connect", "github")
        self.assertEqual(code, 0, err)
        self.stubs["create_repo"].assert_not_called()

    def test_different_origin_is_replaced_with_force(self) -> None:
        self.make_repo()
        bare = self.new_bare()
        self.stubs["expand_remote"].side_effect = lambda spec: str(bare)
        self.assertEqual(self.ul("connect", "somewhere", "--force")[0], 0)
        self.assertEqual(self.git("remote", "get-url", "origin"), str(bare))

    def test_force_shows_the_old_origin(self) -> None:
        old = self.make_repo()
        new = self.tmp / "new.git"
        self.git("init", "-q", "--bare", "-b", "main", str(new), cwd=self.tmp)
        code, out, err = self.ul("connect", str(new), "--force")
        self.assertEqual(code, 0, err)
        self.assertIn(str(old), out + err)

    def test_same_origin_needs_no_force(self) -> None:
        bare = self.make_repo()
        self.assertEqual(self.ul("connect", str(bare))[0], 0)

    def test_unreachable_remote_fails_and_does_not_push(self) -> None:
        self.make_repo(origin=False)
        missing = str(self.tmp / "missing.git")
        self.stubs["expand_remote"].side_effect = lambda spec: missing
        self.assertEqual(self.ul("connect", "x")[0], 1)

    def test_repo_without_commits_only_sets_origin(self) -> None:
        self.git("init", "-q", "-b", "main")
        bare = self.new_bare()
        self.stubs["expand_remote"].side_effect = lambda spec: str(bare)
        self.assertEqual(self.ul("connect", "x")[0], 0)
        self.assertEqual(self.git("remote", "get-url", "origin"), str(bare))
        self.assertEqual(self.git("branch", "--list", cwd=bare), "")

    def test_host_error_is_reported(self) -> None:
        self.make_repo(origin=False)
        self.stubs["create_repo"].side_effect = fake_git_hosts.HostError(
            "no token for github"
        )
        with patch.object(cmd, "HostError", fake_git_hosts.HostError):
            code, _, err = self.ul("connect", "github")
        self.assertEqual(code, 1)
        self.assertIn("no token for github", err)

    def ssh_setup(self, bare: Path) -> str:
        url = "git@github.com:me/proj.git"
        self.git("config", "--global", f"url.{bare}.insteadOf", url)
        self.stubs["expand_remote"].side_effect = lambda spec: url
        self.stubs["host_of"].return_value = fake_git_hosts.HOSTS["github"]
        return url

    def test_ssh_remote_that_works_is_pushed(self) -> None:
        self.make_repo(origin=False)
        bare = self.new_bare()
        url = self.ssh_setup(bare)
        self.assertEqual(self.ul("connect", "gh:me/proj")[0], 0)
        self.stubs["ssh_check"].assert_called_once()
        self.assertEqual(self.stubs["ssh_check"].call_args.args[0], "github.com")
        self.assertEqual(self.git("config", "--get", "remote.origin.url"), url)
        self.assertEqual(self.subjects(bare), ["first"])

    def test_failed_ssh_check_declined_stops(self) -> None:
        self.make_repo(origin=False)
        bare = self.new_bare()
        self.ssh_setup(bare)
        self.stubs["ssh_check"].return_value = (False, "Permission denied (publickey)")
        code, out, err = self.ul("connect", "gh:me/proj", stdin="n\n")
        self.assertEqual(code, 1)
        self.assertIn("Permission denied", out + err)
        self.stubs["ensure_ssh_key"].assert_not_called()
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.git("branch", "--list", cwd=bare), "")

    def test_failed_ssh_check_accepted_creates_key_and_opens_page(self) -> None:
        self.make_repo(origin=False)
        bare = self.new_bare()
        self.ssh_setup(bare)
        pub = self.tmp / "key.pub"
        pub.write_text("ssh-ed25519 AAAA test\n", encoding="utf-8")
        self.stubs["ensure_ssh_key"].return_value = pub
        self.stubs["ssh_check"].return_value = (False, "Permission denied (publickey)")
        code, out, _ = self.ul("connect", "gh:me/proj", stdin="y\n")
        self.assertEqual(code, 1)
        self.stubs["ensure_ssh_key"].assert_called_once()
        self.assertIn("ssh-ed25519 AAAA test", out)
        self.assertEqual(self.calls(), ["open https://github.com/settings/keys"])
        self.assertEqual(self.git("branch", "--list", cwd=bare), "")


class MirrorTests(GitCommandCase):
    def test_add_url_with_name_list_and_remove(self) -> None:
        self.make_repo()
        bare = self.tmp / "m.git"
        self.git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.tmp)
        self.assertEqual(self.ul("mirror", "add", str(bare), "--name", "backup")[0], 0)
        self.assertEqual(self.git("remote", "get-url", "mirror-backup"), str(bare))
        code, out, _ = self.ul("mirror", "list")
        self.assertEqual(code, 0)
        self.assertIn("mirror-backup", out)
        self.assertIn(str(bare), out)
        self.assertNotIn("origin", out)
        self.assertEqual(self.ul("mirror", "remove", "mirror-backup")[0], 0)
        self.assertNotIn("mirror-backup", self.git("remote"))

    def test_add_host_name_creates_repo_and_names_remote_after_host(self) -> None:
        self.make_repo()
        bare = self.tmp / "gl.git"
        self.git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.tmp)
        self.stubs["create_repo"].return_value = fake_git_hosts.Created(
            str(bare), "https://x", "https://x"
        )
        self.assertEqual(self.ul("mirror", "add", "gitlab")[0], 0)
        self.assertEqual(
            self.stubs["create_repo"].call_args.args[:2], ("gitlab", "proj")
        )
        self.assertEqual(self.git("remote", "get-url", "mirror-gitlab"), str(bare))

    def test_a_hostile_api_address_is_never_run_as_an_option(self) -> None:
        # The audit's ls-remote injection: a server answers with an option instead of an address.
        self.make_repo()
        pwn = self.tmp / "PWN"
        self.stubs["create_repo"].return_value = fake_git_hosts.Created(
            f"--upload-pack=touch {pwn};git-upload-pack", "https://x", "https://x"
        )
        code, _, err = self.ul("mirror", "add", "gitlab")
        self.assertEqual(code, 1)
        self.assertFalse(pwn.exists())
        self.assertNotIn("mirror-gitlab", self.git("remote").split())

    def test_add_url_of_known_host_uses_host_name(self) -> None:
        self.make_repo()
        bare = self.tmp / "cb.git"
        self.git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.tmp)
        self.stubs["host_of"].return_value = fake_git_hosts.HOSTS["codeberg"]
        self.stubs["ssh_check"].return_value = (True, "ok")
        self.assertEqual(self.ul("mirror", "add", str(bare))[0], 0)
        self.assertEqual(self.git("remote", "get-url", "mirror-codeberg"), str(bare))

    def test_add_unknown_url_without_name_is_an_error(self) -> None:
        self.make_repo()
        code, _, err = self.ul("mirror", "add", str(self.tmp / "x.git"))
        self.assertEqual(code, 2)
        self.assertIn("--name", err)

    def test_add_existing_mirror_is_refused(self) -> None:
        self.make_repo()
        self.add_bare("mirror-dup")
        bare = self.tmp / "other.git"
        self.git("init", "-q", "--bare", "-b", "main", str(bare), cwd=self.tmp)
        code, _, err = self.ul("mirror", "add", str(bare), "--name", "dup")
        self.assertEqual(code, 1)
        self.assertIn("mirror-dup", err)

    def test_add_unreachable_url_adds_nothing(self) -> None:
        self.make_repo()
        code, _, _ = self.ul(
            "mirror", "add", str(self.tmp / "missing.git"), "--name", "gone"
        )
        self.assertEqual(code, 1)
        self.assertNotIn("mirror-gone", self.git("remote"))

    def test_list_without_mirrors(self) -> None:
        self.make_repo()
        code, out, _ = self.ul("mirror", "list")
        self.assertEqual(code, 0)
        self.assertIn("No mirrors", out)

    def test_remove_refuses_origin_and_unknown_names(self) -> None:
        self.make_repo()
        self.assertEqual(self.ul("mirror", "remove", "origin")[0], 1)
        self.assertIn("origin", self.git("remote"))
        self.assertEqual(self.ul("mirror", "remove", "nothing")[0], 1)

    def test_remove_accepts_name_without_prefix(self) -> None:
        self.make_repo()
        self.add_bare("mirror-short")
        self.assertEqual(self.ul("mirror", "remove", "short")[0], 0)
        self.assertNotIn("mirror-short", self.git("remote"))

    def test_unknown_subcommand_is_usage_error(self) -> None:
        self.make_repo()
        self.assertEqual(self.ul("mirror", "bogus")[0], 2)
        self.assertEqual(self.ul("mirror")[0], 2)


class OutputTests(unittest.TestCase):
    def test_server_text_loses_control_characters(self) -> None:
        self.assertEqual(cmd._git_clean("bad \x1b[2J\x1b]0;t\x07 end\nnext"), "bad [2J]0;t end\nnext")


class TokenTests(GitCommandCase):
    # The token is typed into `security`'s own hidden prompt, so it never passes through argv or Python.
    def test_token_is_asked_by_the_keychain_prompt(self) -> None:
        code, out, err = self.ul("token", "gitlab")
        self.assertEqual(code, 0, err)
        self.stubs["prompt_token"].assert_called_once_with("gitlab", base_url=None)
        self.assertIn("Keychain", out)

    def test_token_for_a_self_hosted_server(self) -> None:
        code, _, err = self.ul("token", "gitea", "--url", "https://git.example.org")
        self.assertEqual(code, 0, err)
        self.stubs["prompt_token"].assert_called_once_with("gitea", base_url="https://git.example.org")

    def test_unknown_host_is_usage_error(self) -> None:
        self.assertEqual(self.ul("token", "bitbucket")[0], 2)
        self.stubs["prompt_token"].assert_not_called()

    def test_host_error_is_reported(self) -> None:
        self.stubs["prompt_token"].side_effect = fake_git_hosts.HostError("Keychain locked")
        with patch.object(cmd, "HostError", fake_git_hosts.HostError):
            code, _, err = self.ul("token", "gitlab")
        self.assertEqual(code, 1)
        self.assertIn("Keychain locked", err)


class OpenAndPrTests(GitCommandCase):
    def github(self) -> None:
        self.stubs["host_of"].return_value = fake_git_hosts.HOSTS["github"]
        self.stubs["web_url"].return_value = "https://github.com/a/b"

    def test_open_uses_branch_tree_page_for_github(self) -> None:
        self.make_repo()
        self.github()
        self.assertEqual(self.ul("open")[0], 0)
        self.assertEqual(self.calls(), ["open https://github.com/a/b/tree/main"])

    def test_open_uses_gitlab_tree_path(self) -> None:
        self.make_repo()
        self.git("checkout", "-q", "-b", "feature/x")
        self.stubs["host_of"].return_value = fake_git_hosts.HOSTS["gitlab"]
        self.stubs["web_url"].return_value = "https://gitlab.com/a/b"
        self.assertEqual(self.ul("open")[0], 0)
        self.assertEqual(self.calls(), ["open https://gitlab.com/a/b/-/tree/feature/x"])

    def test_open_unknown_host_opens_plain_web_url(self) -> None:
        self.make_repo()
        self.stubs["web_url"].return_value = "https://example.org/a/b"
        self.assertEqual(self.ul("open")[0], 0)
        self.assertEqual(self.calls(), ["open https://example.org/a/b"])

    def test_open_without_origin_is_an_error(self) -> None:
        self.make_repo(origin=False)
        self.assertEqual(self.ul("open")[0], 1)
        self.assertEqual(self.calls(), [])

    def test_open_without_web_page_is_an_error(self) -> None:
        self.make_repo()
        self.assertEqual(self.ul("open")[0], 1)
        self.assertEqual(self.calls(), [])

    def feature_branch(self) -> Path:
        bare = self.make_repo()
        self.git("checkout", "-q", "-b", "feature")
        self.change()
        self.git("add", ".")
        self.git("commit", "-q", "-m", "work")
        return bare

    def test_pr_pushes_branch_then_uses_gh_for_github(self) -> None:
        bare = self.feature_branch()
        self.github()
        self.assertEqual(self.ul("pr")[0], 0)
        self.assertEqual(self.subjects(bare, "feature")[0], "work")
        self.assertEqual(
            self.git("rev-parse", "--abbrev-ref", "@{u}"), "origin/feature"
        )
        self.assertEqual(self.calls(), ["gh pr create --fill --base main"])

    def test_pr_passes_base(self) -> None:
        self.feature_branch()
        self.github()
        self.assertEqual(self.ul("pr", "--base", "develop")[0], 0)
        self.assertEqual(self.calls(), ["gh pr create --fill --base develop"])

    def test_pr_without_gh_opens_compare_page(self) -> None:
        self.feature_branch()
        self.github()
        (self.bin / "gh").unlink()
        self.stubs[
            "pr_url"
        ].return_value = "https://github.com/a/b/compare/main...feature"
        self.assertEqual(self.ul("pr")[0], 0)
        self.stubs["pr_url"].assert_called_once()
        self.assertEqual(
            self.calls(), ["open https://github.com/a/b/compare/main...feature"]
        )

    def test_pr_for_other_hosts_opens_page_even_with_gh(self) -> None:
        self.feature_branch()
        self.stubs["host_of"].return_value = fake_git_hosts.HOSTS["gitlab"]
        self.stubs[
            "pr_url"
        ].return_value = "https://gitlab.com/a/b/-/merge_requests/new"
        self.assertEqual(self.ul("pr")[0], 0)
        self.assertEqual(
            self.calls(), ["open https://gitlab.com/a/b/-/merge_requests/new"]
        )

    def test_pr_refuses_on_the_base_branch(self) -> None:
        bare = self.make_repo()
        self.github()
        self.change()
        self.git("add", ".")
        self.git("commit", "-q", "-m", "on main")
        code, _, err = self.ul("pr")
        self.assertEqual(code, 1)
        self.assertIn("main", err)
        self.assertEqual(self.subjects(bare), ["first"])
        self.assertEqual(self.calls(), [])

    def test_pr_without_new_commits_explains_and_pushes_nothing(self) -> None:
        # Haos's case: a new branch with edits but no commit yet; gh only said
        # "could not compute title or body defaults" after a useless push.
        bare = self.make_repo()
        self.github()
        self.git("checkout", "-q", "-b", "feature")
        self.change("main.py", "edited\n")
        code, _, err = self.ul("pr")
        self.assertEqual(code, 1)
        self.assertIn("no commits", err)
        self.assertIn("ul git commit", err)
        self.assertIn("uncommitted", err)
        self.assertNotIn("feature", self.git("branch", "-r"))
        self.assertEqual(self.subjects(bare), ["first"])
        self.assertEqual(self.calls(), [])

    def test_pr_without_any_page_is_an_error(self) -> None:
        self.feature_branch()
        (self.bin / "gh").unlink()
        self.assertEqual(self.ul("pr")[0], 1)


class UndoTests(GitCommandCase):
    def commit(self, subject: str) -> None:
        self.change("file.txt", subject + "\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", subject)

    def test_undo_keeps_changes_staged(self) -> None:
        self.make_repo()
        self.commit("oops")
        code, out, _ = self.ul("undo")
        self.assertEqual(code, 0)
        self.assertIn("oops", out)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "first")
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "file.txt")

    def test_undo_refuses_pushed_commit(self) -> None:
        self.make_repo()
        self.commit("pushed")
        self.git("push", "-q")
        code, _, err = self.ul("undo")
        self.assertEqual(code, 1)
        self.assertIn("git revert HEAD", err)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "pushed")

    def test_undo_without_parent_commit(self) -> None:
        self.make_repo(origin=False)
        code, _, _ = self.ul("undo")
        self.assertEqual(code, 1)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "first")

    def test_undo_works_when_only_older_commits_are_pushed(self) -> None:
        self.make_repo()
        self.commit("pushed")
        self.git("push", "-q")
        self.commit("local")
        self.assertEqual(self.ul("undo")[0], 0)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "pushed")

    def test_undo_of_an_unknown_commit_changes_nothing(self) -> None:
        self.make_repo()
        self.commit("local")
        code, _, err = self.ul("undo", "no such commit")
        self.assertEqual(code, 1)
        self.assertIn("no commit", err)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "local")

    def test_undo_list_shows_the_branch_and_marks_local_commits(self) -> None:
        self.make_repo()
        self.commit("pushed one")
        self.git("push", "-q")
        self.commit("local one")
        code, out, _ = self.ul("undo", "--list")
        self.assertEqual(code, 0)
        lines = [line for line in out.splitlines() if re.match(r"[0-9a-f]{7}  ", line)]
        self.assertEqual([("local one" in l, "pushed one" in l, "first" in l) for l in lines][0], (True, False, False), "newest first")
        self.assertIn(self.git("rev-parse", "--short=7", "HEAD"), out)
        self.assertNotIn("(local)", next(l for l in lines if "pushed one" in l))
        self.assertIn("(local)", next(l for l in lines if "local one" in l))
        self.assertEqual(self.git("log", "-1", "--format=%s"), "local one", "listing changes nothing")

    def test_undo_back_to_a_commit_by_hash(self) -> None:
        self.make_repo()
        self.commit("a")
        target = self.git("rev-parse", "--short", "HEAD")
        self.commit("b")
        self.commit("c")
        code, out, err = self.ul("undo", target)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "a")
        self.assertIn("b", out)
        self.assertIn("c", out)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "file.txt", "the undone changes stay staged")

    def test_undo_back_to_a_commit_by_message(self) -> None:
        self.make_repo()
        self.commit("add parser")
        self.commit("fix typo")
        self.assertEqual(self.ul("undo", "add", "parser")[0], 0)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "add parser")

    def test_undo_with_an_ambiguous_message_lists_candidates(self) -> None:
        self.make_repo()
        self.commit("fix one")
        self.commit("fix two")
        self.commit("last")
        code, _, err = self.ul("undo", "fix")
        self.assertEqual(code, 1)
        self.assertIn("fix one", err)
        self.assertIn("fix two", err)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "last")

    def test_undo_back_past_a_pushed_commit_is_refused(self) -> None:
        self.make_repo()
        self.commit("a")
        target = self.git("rev-parse", "HEAD")
        self.commit("pushed")
        self.git("push", "-q")
        self.commit("local")
        code, _, err = self.ul("undo", target)
        self.assertEqual(code, 1)
        self.assertIn("git revert", err)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "local")

    def test_undo_to_the_current_commit_does_nothing(self) -> None:
        self.make_repo()
        self.commit("only")
        code, out, _ = self.ul("undo", self.git("rev-parse", "HEAD"))
        self.assertEqual(code, 0)
        self.assertIn("nothing to undo", out)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "only")

    def test_undo_refuses_option_like_names(self) -> None:
        self.make_repo()
        self.commit("x")
        self.assertEqual(self.ul("undo", "--hard")[0], 2)
        self.assertEqual(self.git("log", "-1", "--format=%s"), "x")


class HelpTests(GitCommandCase):
    def test_every_action_prints_help_without_side_effects(self) -> None:
        for action in (
            "init",
            "connect",
            "mirror",
            "token",
            "open",
            "pr",
            "undo",
            "push",
            "commit",
            "sync",
        ):
            for flag in ("-h", "--help"):
                with self.subTest(action=action, flag=flag):
                    code, out, _ = self.ul(action, flag)
                    self.assertEqual(code, 0)
                    self.assertIn("Usage: ul git", out)
        self.assertFalse((self.work / ".git").exists())
        self.assertEqual(self.calls(), [])
        self.stubs["create_repo"].assert_not_called()
        self.stubs["prompt_token"].assert_not_called()

    def test_help_documents_every_feature(self) -> None:
        from unlawful.command_help import COMMAND_HELP

        text = COMMAND_HELP["git"]
        for word in (
            "init",
            "connect",
            "mirror",
            "token",
            "open",
            "pr",
            "undo",
            "sync",
            "--connect",
            "--public",
            "--name",
            "--url",
            "--force",
            "--allow-secrets",
            "--base",
            "github",
            "gitlab",
            "codeberg",
            "gitea",
            "Keychain",
            "unlaw.git.",
            "gh auth login",
            "ssh",
            "mirror-",
        ):
            with self.subTest(word=word):
                self.assertIn(word, text)


if __name__ == "__main__":
    unittest.main()
