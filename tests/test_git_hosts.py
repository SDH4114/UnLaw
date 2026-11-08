"""`unlawful.git_hosts` with fake gh, security, ssh and ssh-keygen and local fake GitLab/Gitea APIs."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

# Importing unlawful code must never see the real HOME or config.
with (
    tempfile.TemporaryDirectory() as _import_home,
    mock.patch.dict(
        os.environ,
        {
            "HOME": _import_home,
            "XDG_CONFIG_HOME": _import_home,
            "PATH": "/usr/bin:/bin",
        },
    ),
):
    from unlawful import git_hosts as gh

SECRET = "tok-SECRET-123"


class FakeTools:
    """Executables on a restricted PATH that log their argv and run a small sh body."""

    def __init__(self, root: Path) -> None:
        self.bin = root / "bin"
        self.bin.mkdir()
        self.log = root / "calls.log"

    def add(self, name: str, body: str = "exit 0") -> None:
        script = (
            "#!/bin/sh\n"
            '{ printf "%s\\n" "$(basename "$0")"; for a in "$@"; do printf "%s\\n" "$a"; done;'
            f' printf "@@@@\\n"; }} >> "{self.log}"\n'
            f"{body}\n"
        )
        path = self.bin / name
        path.write_text(script)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def calls(self, name: str | None = None) -> list[list[str]]:
        if not self.log.exists():
            return []
        result = []
        for chunk in self.log.read_text().split("@@@@\n"):
            lines = chunk.split("\n")[:-1]
            if lines and (name is None or lines[0] == name):
                result.append(lines[1:])
        return result


class Api(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, status: int = 201, payload: dict | None = None) -> None:
        super().__init__(("127.0.0.1", 0), self.Handler)
        self.status = status
        self.payload = payload or {}
        self.requests: list[dict] = []
        threading.Thread(
            target=self.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        ).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            self.server.requests.append(
                {
                    "path": self.path,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                    "body": body,
                }
            )
            data = json.dumps(self.server.payload).encode()
            self.send_response(self.server.status)
            if self.server.status in (301, 302, 307):
                self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args: object) -> None:
            pass


class HostTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.tools = FakeTools(self.root)
        patcher = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "PATH": f"{self.tools.bin}:/usr/bin:/bin",
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def api(self, status: int = 201, payload: dict | None = None) -> Api:
        server = Api(status, payload)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def empty_path(self) -> None:
        empty = self.root / "empty"
        empty.mkdir()
        patcher = mock.patch.dict(os.environ, {"PATH": str(empty)})
        patcher.start()
        self.addCleanup(patcher.stop)


class ExpandRemoteTests(unittest.TestCase):
    def test_short_forms(self) -> None:
        self.assertEqual(
            gh.expand_remote("gh:user/repo"), "git@github.com:user/repo.git"
        )
        self.assertEqual(
            gh.expand_remote("gl:user/repo"), "git@gitlab.com:user/repo.git"
        )
        self.assertEqual(
            gh.expand_remote("cb:user/repo"), "git@codeberg.org:user/repo.git"
        )
        self.assertEqual(
            gh.expand_remote("GH:user/repo"), "git@github.com:user/repo.git"
        )

    def test_git_suffix_is_not_doubled_and_gitlab_subgroups_work(self) -> None:
        self.assertEqual(
            gh.expand_remote("gh:user/repo.git"), "git@github.com:user/repo.git"
        )
        self.assertEqual(
            gh.expand_remote("gl:group/sub/repo"), "git@gitlab.com:group/sub/repo.git"
        )

    def test_full_urls_and_scp_forms_are_unchanged(self) -> None:
        for spec in (
            "https://github.com/u/r.git",
            "http://host/u/r",
            "ssh://git@host:2222/u/r.git",
            "git@github.com:u/r.git",
            "git://host/u/r",
            "file:///tmp/repo",
        ):
            self.assertEqual(gh.expand_remote(spec), spec)

    def test_local_paths(self) -> None:
        self.assertEqual(gh.expand_remote("/srv/repo.git"), "/srv/repo.git")
        self.assertEqual(gh.expand_remote("./repo"), "./repo")
        self.assertEqual(gh.expand_remote("../repo"), "../repo")
        with mock.patch.dict(os.environ, {"HOME": "/home/x"}):
            self.assertEqual(gh.expand_remote("~/repos/a"), "/home/x/repos/a")

    def test_rejections(self) -> None:
        for spec in (
            "",
            "   ",
            "a b",
            "gh:u/r\n",
            "gh:u/r\t",
            "gh:u/r\x00",
            "-oProxyCommand=x",
            "--upload-pack=x",
            "ext::sh -c touch% /tmp/x",
            "ext::sh",
            "EXT::sh",
            "fd::3",
            "gh:",
            "gh:user",
            "gh:../x/y",
            "gh:u/..",
            "gh:u/./r",
            "gh:u//r",
            "gh:/u/r",
            "gh:u/r;rm",
            "gh:u/r$(x)",
            "ssh://-oProxyCommand=x/r",
            "git@-host:u/r",
        ):
            with self.subTest(spec=spec), self.assertRaises(gh.HostError):
                gh.expand_remote(spec)

    def test_is_host_name(self) -> None:
        for name in ("github", "GitHub", "gitlab", "codeberg", "gitea"):
            self.assertTrue(gh.is_host_name(name), name)
        for name in ("", "bitbucket", "gh", "github.com"):
            self.assertFalse(gh.is_host_name(name), name)


class UrlTests(unittest.TestCase):
    def test_web_url_shapes(self) -> None:
        for remote, expected in (
            ("git@github.com:u/r.git", "https://github.com/u/r"),
            ("git@github.com:u/r", "https://github.com/u/r"),
            ("ssh://git@host.example:22/u/r.git", "https://host.example/u/r"),
            ("https://host.example/u/r.git", "https://host.example/u/r"),
            ("https://host.example/u/r/", "https://host.example/u/r"),
            ("https://user:pw@host.example/u/r.git", "https://host.example/u/r"),
            ("git@gitlab.com:g/sub/r.git", "https://gitlab.com/g/sub/r"),
            ("http://host.example:3000/u/r.git", "http://host.example:3000/u/r"),
        ):
            with self.subTest(remote=remote):
                self.assertEqual(gh.web_url(remote), expected)

    def test_web_url_none_for_local_and_unknown(self) -> None:
        for remote in (
            "/srv/r.git",
            "./r",
            "../r",
            "file:///tmp/r",
            "",
            "garbage",
            "https://host.example",
        ):
            with self.subTest(remote=remote):
                self.assertIsNone(gh.web_url(remote))

    def test_host_of(self) -> None:
        self.assertEqual(gh.host_of("git@github.com:u/r.git").name, "github")
        self.assertEqual(gh.host_of("https://gitlab.com/u/r").name, "gitlab")
        self.assertEqual(gh.host_of("ssh://git@codeberg.org/u/r.git").name, "codeberg")
        self.assertIsNone(gh.host_of("git@git.example.org:u/r.git"))
        self.assertIsNone(gh.host_of("/srv/r.git"))

    def test_pr_url_per_kind(self) -> None:
        self.assertEqual(
            gh.pr_url("git@github.com:u/r.git", "feat/x y"),
            "https://github.com/u/r/compare/main...feat/x%20y?expand=1",
        )
        self.assertEqual(
            gh.pr_url("git@gitlab.com:u/r.git", "feat/x", "dev"),
            "https://gitlab.com/u/r/-/merge_requests/new"
            "?merge_request[source_branch]=feat%2Fx&merge_request[target_branch]=dev",
        )
        self.assertEqual(
            gh.pr_url("git@codeberg.org:u/r.git", "fix"),
            "https://codeberg.org/u/r/compare/main...fix",
        )

    def test_pr_url_none_without_a_known_host(self) -> None:
        self.assertIsNone(gh.pr_url("git@git.example.org:u/r.git", "x"))
        self.assertIsNone(gh.pr_url("/srv/r.git", "x"))


class CreateRepoGithubTests(HostTestCase):
    def fake_gh(self, create_rc: int = 0, auth_rc: int = 0, login: str = "me") -> None:
        self.tools.add(
            "gh",
            f"""case "$1 $2" in
  "auth status") echo "not logged" >&2; exit {auth_rc};;
  "api user") echo "{login}";;
  "repo create") echo "GraphQL: Name already exists on this account" >&2; exit {create_rc};;
  "repo view") echo '{{"sshUrl":"git@github.com:me/proj.git","url":"https://github.com/me/proj"}}';;
esac
exit 0""",
        )

    def test_private_repo(self) -> None:
        self.fake_gh()
        created = gh.create_repo("github", "proj", description="my thing")
        self.assertEqual(
            created,
            gh.Created(
                ssh_url="git@github.com:me/proj.git",
                https_url="https://github.com/me/proj.git",
                web_url="https://github.com/me/proj",
            ),
        )
        calls = self.tools.calls("gh")
        self.assertEqual(calls[0], ["auth", "status"])
        # The owner is explicit: `gh repo view NAME` alone is not documented to mean the logged-in user.
        self.assertEqual(calls[1], ["api", "user", "--jq", ".login"])
        self.assertEqual(
            calls[2],
            ["repo", "create", "me/proj", "--private", "--description", "my thing"],
        )
        self.assertEqual(calls[3], ["repo", "view", "me/proj", "--json", "sshUrl,url"])

    def test_public_repo_without_description(self) -> None:
        self.fake_gh()
        gh.create_repo("GitHub", "proj", private=False)
        self.assertEqual(
            self.tools.calls("gh")[2], ["repo", "create", "me/proj", "--public"]
        )

    def test_odd_login_is_refused_before_creating(self) -> None:
        self.fake_gh(login="-rf me")
        with self.assertRaises(gh.HostError):
            gh.create_repo("github", "proj")
        self.assertFalse([c for c in self.tools.calls("gh") if c[:2] == ["repo", "create"]])

    def test_gh_missing(self) -> None:
        self.empty_path()
        with self.assertRaises(gh.HostError) as ctx:
            gh.create_repo("github", "proj")
        self.assertIn("gh", str(ctx.exception))
        self.assertIn("brew install gh", str(ctx.exception))

    def test_gh_not_logged_in(self) -> None:
        self.fake_gh(auth_rc=1)
        with self.assertRaises(gh.HostError) as ctx:
            gh.create_repo("github", "proj")
        self.assertIn("gh auth login", str(ctx.exception))
        self.assertEqual(
            len(self.tools.calls("gh")), 1, "nothing is created when not logged in"
        )

    def test_create_failure_reports_gh_message(self) -> None:
        self.fake_gh(create_rc=1)
        with self.assertRaises(gh.HostError) as ctx:
            gh.create_repo("github", "proj")
        self.assertIn("Name already exists", str(ctx.exception))

    def test_bad_view_output(self) -> None:
        self.tools.add(
            "gh", 'case "$1 $2" in "api user") echo me;; "repo view") echo "not json";; esac\nexit 0'
        )
        with self.assertRaises(gh.HostError):
            gh.create_repo("github", "proj")


class CreateRepoApiTests(HostTestCase):
    GITLAB: ClassVar[dict[str, str]] = {
        "ssh_url_to_repo": "git@gitlab.example:me/proj.git",
        "http_url_to_repo": "https://gitlab.example/me/proj.git",
        "web_url": "https://gitlab.example/me/proj",
    }
    GITEA: ClassVar[dict[str, str]] = {
        "ssh_url": "git@codeberg.test:me/proj.git",
        "clone_url": "https://codeberg.test/me/proj.git",
        "html_url": "https://codeberg.test/me/proj",
    }

    def with_token(self, host: str = "gitlab") -> None:
        self.tools.add("security", f'echo "{SECRET}"')

    def test_gitlab_success_sends_token_and_visibility(self) -> None:
        self.with_token()
        server = self.api(201, self.GITLAB)
        created = gh.create_repo(
            "gitlab", "proj", private=True, description="d", base_url=server.url
        )
        self.assertEqual(created.ssh_url, "git@gitlab.example:me/proj.git")
        self.assertEqual(created.https_url, "https://gitlab.example/me/proj.git")
        self.assertEqual(created.web_url, "https://gitlab.example/me/proj")
        request = server.requests[0]
        self.assertEqual(request["path"], "/api/v4/projects")
        self.assertEqual(request["headers"]["private-token"], SECRET)
        self.assertEqual(
            request["body"],
            {
                "name": "proj",
                "path": "proj",
                "visibility": "private",
                "description": "d",
            },
        )
        self.assertEqual(
            self.tools.calls("security")[0],
            ["find-generic-password", "-a", "unlaw", "-s", "unlaw.git.gitlab", "-w"],
        )

    def test_gitlab_public(self) -> None:
        self.with_token()
        server = self.api(201, self.GITLAB)
        gh.create_repo("gitlab", "proj", private=False, base_url=server.url)
        self.assertEqual(server.requests[0]["body"]["visibility"], "public")

    def test_gitea_kinds_send_authorization_and_private_flag(self) -> None:
        for host in ("codeberg", "gitea"):
            with self.subTest(host=host):
                self.with_token()
                server = self.api(201, self.GITEA)
                created = gh.create_repo(
                    host, "proj", private=False, description="d", base_url=server.url
                )
                self.assertEqual(created.ssh_url, "git@codeberg.test:me/proj.git")
                self.assertEqual(created.https_url, "https://codeberg.test/me/proj.git")
                request = server.requests[0]
                self.assertEqual(request["path"], "/api/v1/user/repos")
                self.assertEqual(request["headers"]["authorization"], f"token {SECRET}")
                self.assertEqual(
                    request["body"],
                    {"name": "proj", "private": False, "description": "d"},
                )

    def test_self_hosted_gitea_needs_base_url(self) -> None:
        self.with_token()
        with self.assertRaises(gh.HostError) as ctx:
            gh.create_repo("gitea", "proj")
        self.assertIn("base_url", str(ctx.exception))

    def test_missing_token_points_to_the_keys_page(self) -> None:
        self.tools.add("security", "exit 44")
        server = self.api()
        with self.assertRaises(gh.HostError) as ctx:
            gh.create_repo("gitlab", "proj", base_url=server.url)
        self.assertIn("token", str(ctx.exception))
        self.assertEqual(server.requests, [], "no request without a token")

    def test_http_errors_are_clear_and_never_leak_the_token(self) -> None:
        cases = (
            (401, {"message": "401 Unauthorized"}, "token"),
            (403, {"message": "forbidden"}, "token"),
            (409, {"message": "repository already exists"}, "already"),
            (
                400,
                {"message": {"name": ["has already been taken"]}},
                "already been taken",
            ),
            (500, {"message": "boom"}, "500"),
        )
        for host, payload_key in (("gitlab", None), ("codeberg", None)):
            for status, payload, expected in cases:
                with self.subTest(host=host, status=status):
                    self.with_token()
                    # The server echoes the token back to prove it is scrubbed.
                    payload = {**payload, "echo": SECRET}
                    server = self.api(status, payload)
                    with self.assertRaises(gh.HostError) as ctx:
                        gh.create_repo(host, "proj", base_url=server.url)
                    self.assertIn(expected, str(ctx.exception).lower())
                    self.assertNotIn(SECRET, str(ctx.exception))
                    self.assertIsNone(
                        ctx.exception.__cause__
                        and SECRET in str(ctx.exception.__cause__)
                        or None
                    )

    def test_name_taken_message_is_specific(self) -> None:
        self.with_token()
        server = self.api(409, {"message": "x"})
        with self.assertRaises(gh.HostError) as ctx:
            gh.create_repo("codeberg", "proj", base_url=server.url)
        self.assertIn("proj", str(ctx.exception))
        self.assertIn("already", str(ctx.exception))

    def test_network_error(self) -> None:
        self.with_token()
        with self.assertRaises(gh.HostError) as ctx:
            gh.create_repo("gitlab", "proj", base_url="http://127.0.0.1:1")
        self.assertIn("reach", str(ctx.exception))
        self.assertNotIn(SECRET, str(ctx.exception))

    def test_redirects_are_not_followed_so_the_token_stays_put(self) -> None:
        self.with_token()
        server = self.api(307, {})
        with self.assertRaises(gh.HostError) as ctx:
            gh.create_repo("gitlab", "proj", base_url=server.url)
        self.assertNotIn(SECRET, str(ctx.exception))
        self.assertEqual(len(server.requests), 1)

    def test_incomplete_response(self) -> None:
        self.with_token()
        server = self.api(201, {"unexpected": True})
        with self.assertRaises(gh.HostError):
            gh.create_repo("gitlab", "proj", base_url=server.url)

    def test_plain_http_is_refused_for_non_loopback_hosts(self) -> None:
        self.with_token()
        with self.assertRaises(gh.HostError) as ctx:
            gh.create_repo("gitea", "proj", base_url="http://git.example.org")
        self.assertIn("https", str(ctx.exception))

    def test_trailing_slash_in_base_url(self) -> None:
        self.with_token()
        server = self.api(201, self.GITLAB)
        gh.create_repo("gitlab", "proj", base_url=server.url + "/")
        self.assertEqual(server.requests[0]["path"], "/api/v4/projects")

    def test_repo_name_validation(self) -> None:
        for name in (
            "",
            ".",
            "..",
            "a b",
            "a/b",
            "-x"[:0] or "x" * 101,
            "né",
            "a;b",
            "a\n",
        ):
            with self.subTest(name=name), self.assertRaises(gh.HostError):
                gh.create_repo("github", name)
        self.tools.add("gh", 'if [ "$1 $2" = "api user" ]; then echo me; else echo \'{"sshUrl":"s","url":"https://u"}\'; fi')
        gh.create_repo("github", "A.b_c-1")

    def test_unknown_host(self) -> None:
        with self.assertRaises(gh.HostError):
            gh.create_repo("bitbucket", "proj")


class TokenTests(HostTestCase):
    def test_round_trip(self) -> None:
        store = self.root / "store"
        self.tools.add(
            "security",
            f"""case "$1" in
  add-generic-password) shift; while [ $# -gt 0 ]; do [ "$1" = -w ] && printf %s "$2" > "{store}"; shift; done;;
  find-generic-password) [ -f "{store}" ] && cat "{store}" && echo && exit 0; exit 44;;
esac
exit 0""",
        )
        self.assertIsNone(gh.token("gitlab"))
        gh.save_token("gitlab", SECRET)
        self.assertEqual(gh.token("gitlab"), SECRET)
        add = self.tools.calls("security")[1]
        self.assertEqual(
            add,
            [
                "add-generic-password",
                "-a",
                "unlaw",
                "-s",
                "unlaw.git.gitlab",
                "-w",
                SECRET,
                "-U",
            ],
        )

    def test_host_names_are_validated_and_case_folded(self) -> None:
        self.tools.add("security", f'echo "{SECRET}"')
        self.assertEqual(gh.token("GitLab"), SECRET)
        self.assertEqual(self.tools.calls("security")[0][4], "unlaw.git.gitlab")
        with self.assertRaises(gh.HostError):
            gh.token("evil; rm")
        with self.assertRaises(gh.HostError):
            gh.save_token("nope", SECRET)

    def test_save_rejects_bad_values(self) -> None:
        self.tools.add("security")
        for value in ("", "  ", "a b", "a\nb"):
            with self.subTest(value=value), self.assertRaises(gh.HostError):
                gh.save_token("gitlab", value)
        self.assertEqual(self.tools.calls("security"), [])

    def test_save_failure_never_echoes_the_token(self) -> None:
        self.tools.add("security", f'echo "could not store {SECRET}" >&2; exit 1')
        with self.assertRaises(gh.HostError) as ctx:
            gh.save_token("gitlab", SECRET)
        self.assertNotIn(SECRET, str(ctx.exception))

    def test_security_missing(self) -> None:
        self.empty_path()
        with self.assertRaises(gh.HostError):
            gh.token("gitlab")
        with self.assertRaises(gh.HostError):
            gh.save_token("gitlab", SECRET)


class SshCheckTests(HostTestCase):
    def check(self, body: str) -> tuple[bool, str]:
        self.tools.add("ssh", body)
        return gh.ssh_check("github.com")

    def test_github_success_exits_1(self) -> None:
        ok, message = self.check(
            'echo "Hi me! You\'ve successfully authenticated, but GitHub does not provide shell access." >&2; exit 1'
        )
        self.assertTrue(ok)
        self.assertIn("successfully authenticated", message)
        self.assertEqual(
            self.tools.calls("ssh")[0],
            [
                "-T",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "git@github.com",
            ],
        )

    def test_gitlab_welcome(self) -> None:
        ok, _ = self.check('echo "Welcome to GitLab, @me!"; exit 0')
        self.assertTrue(ok)

    def test_permission_denied_has_a_hint(self) -> None:
        ok, message = self.check(
            'echo "git@github.com: Permission denied (publickey)." >&2; exit 255'
        )
        self.assertFalse(ok)
        self.assertIn("key", message.lower())

    def test_other_failures(self) -> None:
        ok, message = self.check(
            'echo "ssh: Could not resolve hostname github.com" >&2; exit 255'
        )
        self.assertFalse(ok)
        self.assertIn("resolve", message)
        ok, message = self.check("exit 255")
        self.assertFalse(ok)
        self.assertTrue(message)

    def test_timeout(self) -> None:
        self.tools.add("ssh", "sleep 5")
        ok, message = gh.ssh_check("github.com", timeout=0.3)
        self.assertFalse(ok)
        self.assertIn("timed out", message)

    def test_host_validation(self) -> None:
        self.tools.add("ssh")
        for host in ("", "-oProxyCommand=x", "a b", "host;rm", "a@b", "host\n"):
            with self.subTest(host=host), self.assertRaises(gh.HostError):
                gh.ssh_check(host)
        self.assertEqual(self.tools.calls("ssh"), [])

    def test_ssh_missing(self) -> None:
        self.empty_path()
        with self.assertRaises(gh.HostError):
            gh.ssh_check("github.com")


class EnsureSshKeyTests(HostTestCase):
    KEYGEN = """while [ $# -gt 0 ]; do [ "$1" = -f ] && f="$2"; shift; done
echo PRIVATE > "$f"; echo "ssh-ed25519 AAAA unlaw@test" > "$f.pub"; exit 0"""

    def test_creates_once_and_never_overwrites(self) -> None:
        self.tools.add("ssh-keygen", self.KEYGEN)
        pub = gh.ensure_ssh_key()
        self.assertEqual(pub, self.home / ".ssh" / "id_ed25519.pub")
        self.assertTrue(pub.is_file())
        self.assertEqual(stat.S_IMODE((self.home / ".ssh").stat().st_mode), 0o700)
        call = self.tools.calls("ssh-keygen")[0]
        self.assertEqual(call[:4], ["-t", "ed25519", "-N", ""])
        self.assertEqual(call[4:6], ["-f", str(self.home / ".ssh" / "id_ed25519")])
        self.assertEqual(call[6], "-C")
        self.assertTrue(call[7].startswith("unlaw@"))
        pub.write_text("ssh-ed25519 MINE\n")
        self.assertEqual(gh.ensure_ssh_key(), pub)
        self.assertEqual(pub.read_text(), "ssh-ed25519 MINE\n")
        self.assertEqual(len(self.tools.calls("ssh-keygen")), 1)

    def test_private_key_without_pub_is_not_touched(self) -> None:
        self.tools.add("ssh-keygen", self.KEYGEN)
        ssh = self.home / ".ssh"
        ssh.mkdir()
        (ssh / "id_ed25519").write_text("MY PRIVATE")
        with self.assertRaises(gh.HostError) as ctx:
            gh.ensure_ssh_key()
        self.assertIn("ssh-keygen -y", str(ctx.exception))
        self.assertEqual((ssh / "id_ed25519").read_text(), "MY PRIVATE")
        self.assertEqual(self.tools.calls("ssh-keygen"), [])

    def test_keygen_failure_and_missing_output(self) -> None:
        self.tools.add("ssh-keygen", 'echo "boom" >&2; exit 1')
        with self.assertRaises(gh.HostError) as ctx:
            gh.ensure_ssh_key()
        self.assertIn("boom", str(ctx.exception))
        self.tools.add("ssh-keygen", "exit 0")
        with self.assertRaises(gh.HostError):
            gh.ensure_ssh_key()

    def test_keygen_missing(self) -> None:
        self.empty_path()
        with self.assertRaises(gh.HostError):
            gh.ensure_ssh_key()


if __name__ == "__main__":
    unittest.main()
