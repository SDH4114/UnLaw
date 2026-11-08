# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Stage, commit and push the current Git project, or run a Git action."""
from __future__ import annotations

COMMAND_HELP = 'Stage, commit and push the current Git project, or run a Git action.\nUsage: ul git [message]\n       ul git push [message] | commit [message] | sync [message]\n       ul git init [--connect SPEC] [--public] [--name NAME]\n       ul git connect SPEC [--public] [--name NAME] [--url BASE] [--force]\n       ul git mirror add SPEC [--name N] | list | remove NAME\n       ul git token HOST | open | pr [--base BRANCH] | undo [--list | COMMIT]\nActions:\n  no arguments / <message>    git add ., commit, then push (prompts "Commit message:" when\n                              missing; with nothing to commit it only pushes)\n  push [message]              Same as above. A branch without an upstream is published on\n                              origin (-u). `ul git status` and `ul git pull` were removed:\n                              use git status / git pull\n  commit [message]            Stage and commit without pushing\n  sync [message]              Pull with rebase, then stage, commit and push\n  init                        Create a repository on branch main (refuses inside one), merge a\n                              .gitignore for the detected project types (pyproject.toml or\n                              requirements.txt = python, Cargo.toml = rust, CMakeLists.txt = cpp,\n                              package.json = node; only missing lines are added, yours are kept\n                              and .env, keys and .DS_Store are always ignored), then make the\n                              first commit "Initial commit"\n  connect SPEC                Set origin and push the current branch with -u\n  mirror add|list|remove      Extra remotes named mirror-*; every push also pushes to them\n  token HOST                  Save an API token (read hidden from the terminal, never from argv)\n  open                        Open the origin page of the current branch in the browser\n  pr                          Push the current branch, then open a pull request (GitHub with\n                              gh when installed, otherwise the host\'s compare page)\n  undo                        Undo the last commit, keeping its changes staged\n  undo --list                 Show the commits of this branch, newest first; (local) marks the\n                              ones not pushed yet\n  undo COMMIT                 Go back to COMMIT (a hash, or its message or a unique part of it):\n                              it stays, every later commit is undone and their changes stay\n                              staged. Refused when any undone commit is already on a remote\n                              branch (use git revert)\nOptions:\n  --connect SPEC     (init) run connect afterwards\n  --public           Create the repository public (default: private)\n  --name NAME        Repository name to create (default: the folder name); for mirror add with a\n                     URL it is the mirror name (remote mirror-NAME)\n  --url BASE         Server for gitea or a self-hosted gitlab, for example https://git.example.com\n  --force            Replace an origin that points somewhere else\n  --base BRANCH      (pr) target branch, default main\n  --allow-secrets    Commit even when secrets or files over 50 MB are staged\n  -h, --help         Show this help\nSPEC is a host name (github, gitlab, codeberg, gitea: creates the repository through its API),\n  a short form (gh:owner/repo, gl:..., cb:...) or a full URL or path. Short forms become SSH URLs.\nSecrets guard: every commit path unstages .env and .env.* (not .env.example), *.pem, *.key,\n  id_rsa*, id_ed25519* (not .pub), *.p12 and files over 50 MB, explains why and stops with exit 1.\n  Fix it with .gitignore, or pass --allow-secrets. Deleting such a file is always allowed.\nMirrors: they exist only as Git remotes named mirror-* in the repository. A failing mirror is\n  reported as a warning and does not fail the push when origin succeeded.\nSSH: for SSH remotes of a known host connect checks the login. When it fails it offers to\n  create ~/.ssh/id_ed25519, prints the public key and opens the host\'s key page; add the key\n  and run the command again.\nTokens: stored in the macOS Keychain, service unlaw.git.<host>. Scopes: gitlab and gitea or\n  codeberg need an access token that can create repositories (gitlab: api; gitea/codeberg:\n  write:repository and write:user). GitHub uses `gh auth login` instead of a token.\nDependencies: git; ssh; gh (optional, for GitHub pull requests); the macOS `open` command.\nExamples: ul git "Fix downloader"\n  ul git init --connect github\n  ul git connect gh:me/project --force\n  ul git mirror add codeberg\n  ul git token gitlab\n  ul git pr --base develop\n  ul git undo --list\n  ul git undo "add parser"\n'

"""Git hosting services: remote shortcuts, repository creation, tokens, SSH keys and web links."""


import json
import os
import re
import shutil
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import NamedTuple


class HostError(Exception):
    """A problem with a git host, worded for the user (no traceback)."""


# NamedTuple, not a dataclass: the seed may be imported from a file outside sys.modules, where
# dataclasses cannot resolve postponed annotations.
class Host(NamedTuple):
    name: str
    kind: str  # "github" | "gitlab" | "gitea"
    web: str
    api: str
    ssh_host: str
    keys_page: str


class Created(NamedTuple):
    ssh_url: str
    https_url: str
    web_url: str


HOSTS: dict[str, Host] = {
    "github": Host(
        "github",
        "github",
        "https://github.com",
        "https://api.github.com",
        "github.com",
        "https://github.com/settings/ssh/new",
    ),
    "gitlab": Host(
        "gitlab",
        "gitlab",
        "https://gitlab.com",
        "https://gitlab.com/api/v4",
        "gitlab.com",
        "https://gitlab.com/-/user_settings/ssh_keys",
    ),
    "codeberg": Host(
        "codeberg",
        "gitea",
        "https://codeberg.org",
        "https://codeberg.org/api/v1",
        "codeberg.org",
        "https://codeberg.org/user/settings/keys",
    ),
    # Self-hosted Gitea/Forgejo: every address comes from base_url.
    "gitea": Host("gitea", "gitea", "", "", "", ""),
}

_SHORT_PREFIXES = {"gh": "github", "gl": "gitlab", "cb": "codeberg"}
_SEGMENT = re.compile(r"[A-Za-z0-9._-]+")
_REPO_NAME = re.compile(r"[A-Za-z0-9._-]{1,100}")
_HOSTNAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?")
_SCP = re.compile(r"^(?:([^@/\s:]+)@)?([^@/\s:]+):(?!//)(.+)$")
_URL_SCHEMES = ("https://", "http://", "ssh://", "git://", "file://")
_API_TIMEOUT = 20
_TOOL_TIMEOUT = 30
_HINTS = {
    "gh": "install it with `brew install gh`, then run `gh auth login`",
    "security": "the macOS `security` tool is needed for the Keychain",
    "ssh": "install the OpenSSH client",
    "ssh-keygen": "install the OpenSSH client",
}


def _hosts_run(
    argv: list[str], timeout: float = _TOOL_TIMEOUT
) -> subprocess.CompletedProcess[str]:
    """Run a program from PATH with an argument list; missing or hung tools become HostError."""
    program = argv[0]
    if shutil.which(program) is None:
        raise HostError(
            f"`{program}` was not found on PATH: {_HINTS.get(program, 'install it')}"
        )
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise HostError(f"`{program}` timed out after {timeout:g}s") from None
    except OSError as error:
        raise HostError(
            f"could not run `{program}`: {error.strerror or error}"
        ) from None


def _hosts_scrub(text: str, *secrets: str) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def _hosts_last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1][:300] if lines else ""


# ---------------------------------------------------------------- remotes


def is_host_name(spec: str) -> bool:
    return spec.lower() in HOSTS


def expand_remote(spec: str) -> str:
    """Expand `gh:user/repo` style shortcuts; URLs and local paths pass through (with ~ expanded)."""
    if (
        not spec
        or spec != spec.strip()
        or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in spec)
    ):
        raise HostError("the remote is empty or contains spaces or control characters")
    if spec.startswith("-"):
        raise HostError(f"the remote cannot start with '-': {spec}")
    if re.match(r"^[A-Za-z0-9_.+-]+::", spec):
        raise HostError("remote helper transports such as `ext::` are not allowed")
    prefix, _, rest = spec.partition(":")
    if prefix.lower() in _SHORT_PREFIXES and not rest.startswith("//"):
        host = HOSTS[_SHORT_PREFIXES[prefix.lower()]]
        path = rest.removesuffix(".git")
        segments = path.split("/")
        if len(segments) < 2 or not all(
            _SEGMENT.fullmatch(s) and s not in (".", "..") for s in segments
        ):
            raise HostError(
                f"use {prefix.lower()}:user/repo (letters, digits, . _ - only), not `{spec}`"
            )
        return f"git@{host.ssh_host}:{path}.git"
    lowered = spec.lower()
    if lowered.startswith(_URL_SCHEMES):
        authority = spec.split("://", 1)[1].split("/", 1)[0]
        if authority.rpartition("@")[2].startswith("-"):
            raise HostError("the host in the remote cannot start with '-'")
        return spec
    if spec.startswith("~"):
        return os.path.expanduser(spec)
    scp = _SCP.match(spec)
    if scp and not spec.startswith(("/", "./", "../")) and scp.group(2).startswith("-"):
        raise HostError("the host in the remote cannot start with '-'")
    return spec


def _hosts_parse(remote: str) -> tuple[str, str, str, int | None] | None:
    """(scheme for the web link, hostname, path without .git, port) or None for local/unknown forms."""
    remote = remote.strip()
    if not remote or remote.startswith(("/", ".", "~", "-")):
        return None
    lowered = remote.lower()
    if lowered.startswith("file://"):
        return None
    if lowered.startswith(("https://", "http://", "ssh://", "git://")):
        try:
            parts = urllib.parse.urlsplit(remote)
            hostname, port = parts.hostname, parts.port
        except ValueError:
            return None
        scheme = parts.scheme.lower()
        path = parts.path
        web_scheme = scheme if scheme in ("http", "https") else "https"
        port = port if scheme in ("http", "https") else None
    else:
        scp = _SCP.match(remote)
        if not scp or not (scp.group(1) or "." in scp.group(2)):
            return None
        hostname, path, web_scheme, port = (
            scp.group(2).lower(),
            scp.group(3),
            "https",
            None,
        )
    path = path.strip("/").removesuffix(".git").strip("/")
    if not hostname or not path:
        return None
    return web_scheme, hostname.lower(), path, port


def web_url(remote: str) -> str | None:
    parsed = _hosts_parse(remote)
    if parsed is None:
        return None
    scheme, hostname, path, port = parsed
    netloc = f"{hostname}:{port}" if port else hostname
    return f"{scheme}://{netloc}/{path}"


def host_of(remote: str) -> Host | None:
    parsed = _hosts_parse(remote)
    if parsed is None:
        return None
    hostname = parsed[1]
    for host in HOSTS.values():
        web_host = urllib.parse.urlsplit(host.web).hostname if host.web else None
        if hostname in (host.ssh_host, web_host) and hostname:
            return host
    return None


def pr_url(remote: str, branch: str, base: str = "main") -> str | None:
    web = web_url(remote)
    host = host_of(remote)
    if web is None or host is None:
        return None
    if host.kind == "gitlab":
        source = urllib.parse.quote(branch, safe="")
        target = urllib.parse.quote(base, safe="")
        return f"{web}/-/merge_requests/new?merge_request[source_branch]={source}&merge_request[target_branch]={target}"
    compare = f"{web}/compare/{urllib.parse.quote(base, safe='/')}...{urllib.parse.quote(branch, safe='/')}"
    return compare + "?expand=1" if host.kind == "github" else compare


# ---------------------------------------------------------------- tokens


def _hosts_lookup(host: str) -> Host:
    found = HOSTS.get(host.lower())
    if found is None:
        raise HostError(f"unknown git host `{host}` (known: {', '.join(HOSTS)})")
    return found


def _hosts_service(host: str) -> str:
    return f"unlaw.git.{_hosts_lookup(host).name}"


def token(host: str) -> str | None:
    result = _hosts_run(
        [
            "security",
            "find-generic-password",
            "-a",
            "unlaw",
            "-s",
            _hosts_service(host),
            "-w",
        ]
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def save_token(host: str, value: str) -> None:
    service = _hosts_service(host)
    value = value.strip()
    if not value or any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise HostError("the token must be one word without spaces")
    # Same call as telegram.py/agent.py. The value is briefly visible in this process's argv (`ps`).
    result = _hosts_run(
        [
            "security",
            "add-generic-password",
            "-a",
            "unlaw",
            "-s",
            service,
            "-w",
            value,
            "-U",
        ]
    )
    if result.returncode != 0:
        detail = _hosts_scrub(_hosts_last_line(result.stderr), value)
        raise HostError(
            f"could not write the macOS Keychain: {detail}"
            if detail
            else "could not write the macOS Keychain"
        )


# ---------------------------------------------------------------- creating repositories


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect could carry the token to another host, so none is followed."""

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def _hosts_api_base(host: Host, base_url: str | None) -> str:
    if base_url:
        base = base_url.rstrip("/")
        parts = urllib.parse.urlsplit(base)
        loopback = parts.hostname in ("127.0.0.1", "localhost", "::1")
        if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
            raise HostError(
                "base_url must start with https:// (plain http only for localhost)"
            )
        if not parts.hostname:
            raise HostError("base_url has no host name")
        return base + ("/api/v4" if host.kind == "gitlab" else "/api/v1")
    if not host.api:
        raise HostError(
            f"`{host.name}` is self-hosted: pass its address as base_url (https://git.example.org)"
        )
    return host.api


def _hosts_post(
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
    secret: str,
    host: str,
) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            **headers,
        },
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=_API_TIMEOUT) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", "replace") if error.fp else ""
        error.close()
        detail = _hosts_scrub(" ".join(raw.split())[:200], secret)
        name = payload.get("name", "")
        if error.code in (401, 403):
            raise HostError(
                f"{host} rejected the token (HTTP {error.code}): create a new one with repo permissions"
            ) from None
        if error.code == 409:
            raise HostError(
                f"a repository named `{name}` already exists on {host}"
            ) from None
        suffix = f": {detail}" if detail else ""
        raise HostError(f"{host} answered HTTP {error.code}{suffix}") from None
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        reason = _hosts_scrub(str(getattr(error, "reason", error)), secret)
        raise HostError(f"could not reach {host}: {reason}") from None
    try:
        data = json.loads(body)
    except ValueError:
        raise HostError(f"{host} returned something that is not JSON") from None
    if not isinstance(data, dict):
        raise HostError(f"{host} returned an unexpected answer")
    return data


def _hosts_fields(data: dict, host: str, *keys: str) -> list[str]:
    values = [data.get(key) for key in keys]
    if not all(isinstance(v, str) and v for v in values):
        raise HostError(f"{host} did not return the new repository's addresses")
    return values  # type: ignore[return-value]


def _hosts_create_github(name: str, private: bool, description: str) -> Created:
    if _hosts_run(["gh", "auth", "status"]).returncode != 0:
        raise HostError("gh is not logged in: run `gh auth login`")
    # An explicit owner: `gh repo view NAME` alone is not documented to mean the logged-in user.
    login = _hosts_run(["gh", "api", "user", "--jq", ".login"]).stdout.strip()
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", login):
        raise HostError("could not read your GitHub login from gh (`gh api user`)")
    name = f"{login}/{name}"
    argv = ["gh", "repo", "create", name, "--private" if private else "--public"]
    if description:
        argv += ["--description", description]
    created = _hosts_run(argv)
    if created.returncode != 0:
        raise HostError(
            f"gh could not create the repository: {_hosts_last_line(created.stderr) or 'unknown error'}"
        )
    view = _hosts_run(["gh", "repo", "view", name, "--json", "sshUrl,url"])
    try:
        data = json.loads(view.stdout)
        ssh_url, url = _hosts_fields(data, "github", "sshUrl", "url")
    except (ValueError, AttributeError):
        raise HostError(
            "gh created the repository but its addresses could not be read"
        ) from None
    return Created(ssh_url=ssh_url, https_url=url + ".git", web_url=url)


def create_repo(
    host: str,
    name: str,
    *,
    private: bool = True,
    description: str = "",
    base_url: str | None = None,
) -> Created:
    info = _hosts_lookup(host)
    if not _REPO_NAME.fullmatch(name) or name in (".", ".."):
        raise HostError(
            "a repository name is 1-100 letters, digits, . _ - and not . or .."
        )
    if info.kind == "github":
        return _hosts_create_github(name, private, description)
    api = _hosts_api_base(info, base_url)
    secret = token(info.name)
    if not secret:
        page = info.keys_page or "the token page of your host"
        raise HostError(
            f"no API token for {info.name}: create one ({page}) with repository write access and save it"
        )
    if info.kind == "gitlab":
        visibility = "private" if private else "public"
        payload: dict[str, object] = {
            "name": name,
            "path": name,
            "visibility": visibility,
        }
        if description:
            payload["description"] = description
        data = _hosts_post(
            f"{api}/projects", {"PRIVATE-TOKEN": secret}, payload, secret, info.name
        )
        fields = _hosts_fields(
            data, info.name, "ssh_url_to_repo", "http_url_to_repo", "web_url"
        )
    else:
        payload = {"name": name, "private": private, "description": description}
        data = _hosts_post(
            f"{api}/user/repos",
            {"Authorization": f"token {secret}"},
            payload,
            secret,
            info.name,
        )
        fields = _hosts_fields(data, info.name, "ssh_url", "clone_url", "html_url")
    return Created(ssh_url=fields[0], https_url=fields[1], web_url=fields[2])


# ---------------------------------------------------------------- SSH


def ssh_check(ssh_host: str, timeout: float = 15) -> tuple[bool, str]:
    if not _HOSTNAME.fullmatch(ssh_host):
        raise HostError(f"not a valid host name: {ssh_host!r}")
    argv = [
        "ssh",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"git@{ssh_host}",
    ]
    try:
        result = _hosts_run(argv, timeout)
    except HostError as error:
        if "timed out" in str(error):
            return False, f"timed out talking to {ssh_host}"
        raise
    output = (result.stdout + "\n" + result.stderr).strip()
    lowered = output.lower()
    if "successfully authenticated" in lowered or "welcome to gitlab" in lowered:
        return True, _hosts_last_line(output)
    if "permission denied" in lowered:
        return (
            False,
            f"{ssh_host} does not know your SSH key: add ~/.ssh/id_ed25519.pub to your account there",
        )
    return False, _hosts_last_line(
        output
    ) or f"ssh to {ssh_host} failed (exit {result.returncode})"


def ensure_ssh_key() -> Path:
    ssh_dir = Path(os.path.expanduser("~")) / ".ssh"
    private = ssh_dir / "id_ed25519"
    public = ssh_dir / "id_ed25519.pub"
    if public.exists():
        return public
    if private.exists():
        raise HostError(
            f"{private} exists without a .pub file: run `ssh-keygen -y -f {private} > {public}`"
        )
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    comment = re.sub(r"[^A-Za-z0-9._-]", "", socket.gethostname()) or "mac"
    result = _hosts_run(
        [
            "ssh-keygen",
            "-t",
            "ed25519",
            "-N",
            "",
            "-f",
            str(private),
            "-C",
            f"unlaw@{comment}",
        ]
    )
    if result.returncode != 0:
        raise HostError(
            f"ssh-keygen failed: {_hosts_last_line(result.stderr) or 'unknown error'}"
        )
    if not public.exists():
        raise HostError("ssh-keygen finished but no public key was written")
    return public

import getpass
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from urllib.parse import quote


USAGE = (
    "Usage: ul git [message|push [message]|commit [message]|sync [message]|init|"
    "connect SPEC|mirror add|list|remove|token HOST|open|pr|undo [--list|COMMIT]]"
)
# Removed actions: still refused, so the word never becomes a commit message by accident.
_GIT_REMOVED = {"status", "pull"}
_GIT_ACTIONS = {
    "push",
    "commit",
    "sync",
    "init",
    "connect",
    "mirror",
    "token",
    "open",
    "pr",
    "undo",
}
_GIT_MAX_BYTES = 50 * 1024 * 1024
_GIT_ALWAYS_IGNORE = [
    ".DS_Store",
    ".env",
    ".env.*",
    "!.env.example",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
]
_GIT_TYPE_IGNORE = {
    "python": [
        "__pycache__/",
        "*.py[cod]",
        ".venv/",
        "venv/",
        ".pytest_cache/",
        ".ruff_cache/",
        ".mypy_cache/",
        "*.egg-info/",
        "build/",
        "dist/",
        ".coverage",
    ],
    "rust": ["target/"],
    "cpp": [
        "build/",
        "cmake-build-*/",
        "CMakeCache.txt",
        "CMakeFiles/",
        "*.o",
        "*.obj",
        "*.a",
        "*.so",
        "*.dylib",
    ],
    "node": ["node_modules/", "dist/", "npm-debug.log*"],
}
_GIT_TYPE_FILES = {
    "python": ("pyproject.toml", "requirements.txt"),
    "rust": ("Cargo.toml",),
    "cpp": ("CMakeLists.txt",),
    "node": ("package.json",),
}
_GIT_REMOTE_SUFFIX = re.compile(r"[A-Za-z0-9._-]+")


class _GitUsage(Exception):
    """A command-line mistake: printed with the usage line, exit code 2."""


def _run_all(commands: list[list[str]]) -> int:
    try:
        for command in commands:
            code = subprocess.run(command, check=False).returncode
            if code:
                return code
    except OSError as error:
        print(f"unlaw git: {error}", file=sys.stderr)
        return 1
    return 0


def _git_fail(message: str) -> int:
    print(f"unlaw git: {message}", file=sys.stderr)
    return 1


def _git_out(*args: str) -> subprocess.CompletedProcess[str]:
    """Run git quietly and return its text output; a missing git becomes exit code 127."""
    command = ["git", *args]
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            errors="surrogateescape",
        )
    except OSError as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def _git_parse(
    args: list[str], *, values: Sequence[str] = (), flags: Sequence[str] = ()
) -> tuple[dict[str, str], list[str]]:
    options: dict[str, str] = {}
    positional: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in values:
            if index + 1 >= len(args):
                raise _GitUsage(f"{arg} needs a value")
            options[arg] = args[index + 1]
            index += 2
            continue
        if arg in flags:
            options[arg] = "1"
        elif arg.startswith("-") and len(arg) > 1:
            raise _GitUsage(f"unknown option {arg}")
        else:
            positional.append(arg)
        index += 1
    return options, positional


def _git_in_worktree() -> bool:
    result = _git_out("rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip() == "true"


def _git_branch() -> str:
    return _git_out("symbolic-ref", "--short", "-q", "HEAD").stdout.strip()


def _git_has_commits() -> bool:
    return _git_out("rev-parse", "--verify", "-q", "HEAD").returncode == 0


def _git_remote_url(name: str) -> str | None:
    """The URL as written in the config (`remote get-url` would apply insteadOf)."""
    result = _git_out("config", "--get", f"remote.{name}.url")
    return result.stdout.strip() or None if result.returncode == 0 else None


def _git_mirrors() -> list[str]:
    return [
        name for name in _git_out("remote").stdout.split() if name.startswith("mirror-")
    ]


def _git_repo_name() -> str:
    root = _git_out("rev-parse", "--show-toplevel").stdout.strip()
    return os.path.basename(root or os.getcwd())


def _git_open_url(url: str) -> int:
    try:
        return subprocess.run(["open", url], check=False).returncode
    except OSError as error:
        return _git_fail(str(error))


def _git_push_all(*, upstream_branch: str | None = None) -> int:
    """Push origin, then every mirror; a failing mirror only warns."""
    if upstream_branch is None and _git_remote_url("origin"):
        # A branch without an upstream would make a plain `git push` fail: publish it on origin.
        branch = _git_branch()
        if branch and _git_out("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode:
            upstream_branch = branch
    command = (
        ["git", "push"]
        if upstream_branch is None
        else ["git", "push", "-u", "origin", upstream_branch]
    )
    code = _run_all([command])
    if code:
        return code
    for mirror in _git_mirrors():
        if subprocess.run(["git", "push", mirror, "HEAD"], check=False).returncode:
            print(
                f"unlaw git: warning: push to {mirror} failed; origin is up to date.",
                file=sys.stderr,
            )
    return 0


def _commit_message(tokens: list[str]) -> str | None:
    if tokens:
        return " ".join(tokens).strip()
    try:
        message = input("Commit message: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nunlaw git: commit cancelled.", file=sys.stderr)
        return None
    if not message:
        print("unlaw git: commit message cannot be empty.", file=sys.stderr)
        return None
    return message


def _has_staged_changes() -> bool | int:
    """True or False, or git's exit code when it cannot tell (not a repository)."""
    try:
        code = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], check=False
        ).returncode
    except OSError as error:
        print(f"unlaw git: {error}", file=sys.stderr)
        return 1
    if code in (0, 1):
        return code == 1
    return code


def _git_secret_reason(path: str, root: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    lower = name.lower()
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return "environment file"
    if lower.endswith((".pem", ".key")):
        return "private key or certificate"
    if lower.endswith(".p12"):
        return "key store"
    if name.startswith(("id_rsa", "id_ed25519")) and not name.endswith(".pub"):
        return "private SSH key"
    try:
        if os.path.getsize(os.path.join(root, path)) > _GIT_MAX_BYTES:
            return f"larger than {_GIT_MAX_BYTES // (1024 * 1024)} MB"
    except OSError:
        return None
    return None


def _git_secrets_guard(allow: bool) -> int:
    """Unstage files that must not be committed; 0 when clear, 1 when something was held back."""
    if allow:
        return 0
    # Deletions are excluded: removing a committed secret must always be possible.
    staged = _git_out("diff", "--cached", "--name-only", "--diff-filter=d", "-z")
    if staged.returncode:
        # Keep git's own exit code (128 outside a repository), as the workflow always did.
        _git_fail(staged.stderr.strip() or "cannot list staged files.")
        return staged.returncode
    paths = [path for path in staged.stdout.split("\0") if path]
    if not paths:
        return 0
    root = _git_out("rev-parse", "--show-toplevel").stdout.strip() or "."
    found = [
        (path, reason) for path in paths if (reason := _git_secret_reason(path, root))
    ]
    if not found:
        return 0
    _git_out("reset", "-q", "--", *[path for path, _ in found])
    lines = [
        "not committing, these staged files look like secrets or are too big (now unstaged):"
    ]
    lines.extend(f"  {path}  ({reason})" for path, reason in found)
    lines.append(
        "Add them to .gitignore (`ul git init` merges a safe one) or rerun with --allow-secrets."
    )
    print("unlaw git: " + "\n".join(lines), file=sys.stderr)
    return 1


def _commit_workflow(
    tokens: list[str], *, push: bool, allow_secrets: bool = False
) -> int:
    code = _run_all([["git", "add", "."]])
    if code:
        return code
    code = _git_secrets_guard(allow_secrets)
    if code:
        return code
    staged = _has_staged_changes()
    if staged is False:
        # Earlier commits may still be unpushed, so a clean tree must not stop the push.
        print("unlaw git: nothing to commit.", file=sys.stderr)
        return _git_push_all() if push else 0
    if staged is not True:
        return staged
    message = _commit_message(tokens)
    if message is None:
        return 2
    code = _run_all([["git", "commit", "-m", message]])
    if code or not push:
        return code
    return _git_push_all()


def _git_commit_args(args: list[str]) -> tuple[list[str], bool]:
    allow = "--allow-secrets" in args
    return [arg for arg in args if arg != "--allow-secrets"], allow


def _git_detect_types() -> list[str]:
    return [
        kind
        for kind, names in _GIT_TYPE_FILES.items()
        if any(os.path.exists(name) for name in names)
    ]


def _git_merge_gitignore(kinds: list[str]) -> None:
    """Append the missing ignore lines; existing lines are never changed or removed."""
    try:
        with open(".gitignore", encoding="utf-8") as handle:
            current = handle.read()
    except FileNotFoundError:
        current = ""
    present = {line.strip() for line in current.splitlines()}
    wanted: list[str] = []
    for line in [
        *(line for kind in kinds for line in _GIT_TYPE_IGNORE[kind]),
        *_GIT_ALWAYS_IGNORE,
    ]:
        if line not in present and line not in wanted:
            wanted.append(line)
    if not wanted:
        return
    prefix = "" if not current or current.endswith("\n") else "\n"
    with open(".gitignore", "a", encoding="utf-8") as handle:
        handle.write(prefix + "\n".join(wanted) + "\n")


def _git_init(args: list[str]) -> int:
    options, positional = _git_parse(
        args,
        values=("--connect", "--name", "--url"),
        flags=("--public", "--allow-secrets"),
    )
    if positional:
        raise _GitUsage("init takes no arguments")
    if _git_in_worktree():
        return _git_fail("already inside a Git work tree; nothing to initialize.")
    created = _git_out("init", "-b", "main")
    if created.returncode:
        # Git before 2.28 has no -b.
        created = _git_out("init")
        if created.returncode == 0:
            created = _git_out("symbolic-ref", "HEAD", "refs/heads/main")
        if created.returncode:
            return _git_fail(created.stderr.strip() or "git init failed.")
    print("Initialized a Git repository on branch main.")
    try:
        _git_merge_gitignore(_git_detect_types())
    except (OSError, UnicodeDecodeError) as error:
        return _git_fail(f"cannot update .gitignore: {error}")
    code = _commit_workflow(
        ["Initial commit"], push=False, allow_secrets="--allow-secrets" in options
    )
    if code or "--connect" not in options:
        return code
    forwarded = [options["--connect"]]
    for name in ("--name", "--url"):
        if name in options:
            forwarded.extend([name, options[name]])
    if "--public" in options:
        forwarded.append("--public")
    return _git_connect(forwarded)


def _git_resolve_remote(spec: str, options: dict[str, str]) -> str:
    """The SSH URL for a host name (creating the repository) or the expanded URL for other specs."""
    if is_host_name(spec):
        name = options.get("--name") or _git_repo_name()
        created = create_repo(
            spec, name, private="--public" not in options, base_url=options.get("--url")
        )
        return created.ssh_url
    return expand_remote(spec)


def _git_ssh_gate(url: str) -> int:
    """For SSH remotes of a known host: 0 when SSH works, otherwise offer an SSH key and return 1."""
    host = host_of(url)
    if host is None or not url.startswith(("git@", "ssh://")):
        return 0
    ok, message = ssh_check(host.ssh_host)
    if ok:
        return 0
    print(f"unlaw git: SSH to {host.ssh_host} failed: {message}", file=sys.stderr)
    try:
        answer = input("Create an SSH key and open the key page? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip().lower() not in {"y", "yes"}:
        return 1
    public = ensure_ssh_key()
    try:
        print(public.read_text(encoding="utf-8").strip())
    except OSError as error:
        print(f"unlaw git: cannot read {public}: {error}", file=sys.stderr)
    if host.keys_page:
        _git_open_url(host.keys_page)
    print("Add the public key above to your account, then run the same command again.")
    return 1


def _git_verify_remote(target: str) -> int:
    result = _git_out("ls-remote", target)
    if result.returncode:
        return _git_fail(
            f"cannot access {target}: {result.stderr.strip() or 'ls-remote failed'}"
        )
    return 0


def _git_connect(args: list[str]) -> int:
    options, positional = _git_parse(
        args, values=("--name", "--url"), flags=("--public", "--force")
    )
    if len(positional) != 1:
        raise _GitUsage("connect needs one SPEC (a host name, gh:owner/repo or a URL)")
    spec = positional[0]
    force = "--force" in options
    if not _git_in_worktree():
        return _git_fail("not a Git repository; run `ul git init` first.")
    existing = _git_remote_url("origin")
    current_host = host_of(existing) if existing else None
    if current_host is not None and is_host_name(spec) and current_host.name == spec.lower() and not force:
        # Already connected to this host (e.g. a rerun after the SSH key step): reuse origin, create nothing.
        url = existing
    elif existing and not force and is_host_name(spec):
        return _git_fail(
            f"origin already points to {existing}; use --force to replace it."
        )
    else:
        url = _git_resolve_remote(spec, options)
    if existing and existing != url and not force:
        return _git_fail(
            f"origin already points to {existing}; use --force to replace it with {url}."
        )
    if existing is None:
        code = _run_all([["git", "remote", "add", "origin", url]])
    elif existing != url:
        code = _run_all([["git", "remote", "set-url", "origin", url]])
    else:
        code = 0
    if code:
        return code
    code = _git_ssh_gate(url)
    if code:
        return code
    code = _git_verify_remote("origin")
    if code or not _git_has_commits():
        return code
    branch = _git_branch()
    if not branch:
        print("unlaw git: detached HEAD; nothing pushed.", file=sys.stderr)
        return 0
    return _git_push_all(upstream_branch=branch)


def _git_mirror(args: list[str]) -> int:
    if not args:
        raise _GitUsage("mirror needs add, list or remove")
    action, rest = args[0], args[1:]
    if action not in {"add", "list", "remove"}:
        raise _GitUsage(f"unknown mirror action {action}")
    if not _git_in_worktree():
        return _git_fail("not a Git repository.")
    if action == "list":
        if rest:
            raise _GitUsage("mirror list takes no arguments")
        mirrors = _git_mirrors()
        if not mirrors:
            print("No mirrors. Add one with: ul git mirror add <host|URL>")
        for name in mirrors:
            print(f"{name}\t{_git_remote_url(name) or ''}")
        return 0
    if action == "remove":
        if len(rest) != 1:
            raise _GitUsage("mirror remove needs a mirror name")
        name = rest[0] if rest[0].startswith("mirror-") else f"mirror-{rest[0]}"
        if name not in _git_mirrors():
            return _git_fail(f"no mirror named {name}; see `ul git mirror list`.")
        return _run_all([["git", "remote", "remove", name]])
    options, positional = _git_parse(
        rest, values=("--name", "--url"), flags=("--public",)
    )
    if len(positional) != 1:
        raise _GitUsage(
            "mirror add needs one SPEC (a host name, gh:owner/repo or a URL)"
        )
    spec = positional[0]
    if is_host_name(spec):
        remote = f"mirror-{spec}"
        if remote in _git_mirrors():
            return _git_fail(f"{remote} already exists; remove it first.")
        url = _git_resolve_remote(spec, options)
    else:
        url = expand_remote(spec)
        host = host_of(url)
        suffix = options.get("--name") or (host.name if host else "")
        if not suffix:
            raise _GitUsage("mirror add needs --name for this URL")
        remote = f"mirror-{suffix}"
        if not _GIT_REMOTE_SUFFIX.fullmatch(suffix):
            raise _GitUsage(
                "the mirror name may use letters, digits, '.', '_' and '-' only"
            )
        if remote in _git_mirrors():
            return _git_fail(f"{remote} already exists; remove it first.")
    code = _git_ssh_gate(url) or _git_verify_remote(url)
    if code:
        return code
    code = _run_all([["git", "remote", "add", remote, url]])
    if not code:
        print(f"Added {remote} -> {url}. `ul git push` now pushes there too.")
    return code


def _git_token(args: list[str]) -> int:
    _, positional = _git_parse(args)
    if len(positional) != 1 or positional[0] not in HOSTS:
        raise _GitUsage(f"token needs a host: {', '.join(HOSTS)}")
    host = positional[0]
    try:
        value = getpass.getpass(f"{host} token (input hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nunlaw git: cancelled.", file=sys.stderr)
        return 2
    if not value:
        print("unlaw git: the token cannot be empty.", file=sys.stderr)
        return 2
    save_token(host, value)
    print(f"Saved the {host} token in the macOS Keychain (service unlaw.git.{host}).")
    return 0


def _git_open(args: list[str]) -> int:
    if args:
        raise _GitUsage("open takes no arguments")
    origin = _git_remote_url("origin")
    if origin is None:
        return _git_fail("no origin remote; run `ul git connect` first.")
    page = web_url(origin)
    if not page:
        return _git_fail(f"cannot work out a web page for {origin}.")
    page = page.rstrip("/")
    branch = _git_branch()
    host = host_of(origin)
    if branch and host is not None:
        page += ("/-/tree/" if host.kind == "gitlab" else "/tree/") + quote(
            branch, safe="/"
        )
    return _git_open_url(page)


def _git_pr(args: list[str]) -> int:
    options, positional = _git_parse(args, values=("--base",))
    if positional:
        raise _GitUsage("pr takes no arguments")
    base = options.get("--base", "main")
    branch = _git_branch()
    if not branch:
        return _git_fail("detached HEAD; check out a branch first.")
    if branch == base:
        return _git_fail(
            f"you are on the base branch {base}; switch to a feature branch first."
        )
    origin = _git_remote_url("origin")
    if origin is None:
        return _git_fail("no origin remote; run `ul git connect` first.")
    code = _git_push_all(upstream_branch=branch)
    if code:
        return code
    host = host_of(origin)
    if host is not None and host.name == "github" and shutil.which("gh"):
        return _run_all([["gh", "pr", "create", "--fill", "--base", base]])
    page = pr_url(origin, branch, base)
    if not page:
        return _git_fail(f"cannot work out a pull request page for {origin}.")
    return _git_open_url(page)


def _git_branch_commits() -> list[tuple[str, str, str]]:
    """(full hash, date, subject) of the current branch, newest first."""
    out = _git_out("log", "--format=%H%x00%ad%x00%s", "--date=short", "HEAD").stdout
    return [tuple(line.split("\0", 2)) for line in out.splitlines() if line.count("\0") == 2]  # type: ignore[misc]


def _git_undo_list() -> int:
    commits = _git_branch_commits()
    if not commits:
        return _git_fail("this branch has no commits yet.")
    local = set(_git_out("rev-list", "HEAD", "--not", "--remotes").stdout.split())
    print(f"Commits on {_git_branch() or 'HEAD'}, newest first; (local) = not pushed, can be undone:")
    for full, date, subject in commits:
        print(f"{full[:7]}  {date}  {subject}{'  (local)' if full in local else ''}")
    print("Go back to one with: ul git undo <hash or part of its message>")
    return 0


def _git_find_commit(text: str) -> str | None:
    """The commit of this branch named by a hash prefix or (part of) its message; None with an explanation."""
    commits = _git_branch_commits()
    if re.fullmatch(r"[0-9a-fA-F]{4,40}", text):
        by_hash = [full for full, _, _ in commits if full.startswith(text.lower())]
        if len(by_hash) == 1:
            return by_hash[0]
    wanted = text.casefold()
    found = [entry for entry in commits if entry[2].casefold() == wanted] or [
        entry for entry in commits if wanted in entry[2].casefold()
    ]
    if len(found) == 1:
        return found[0][0]
    if not found:
        _git_fail(f"no commit in this branch matches `{text}`; see `ul git undo --list`.")
        return None
    lines = "\n".join(f"  {full[:7]}  {subject}" for full, _, subject in found[:10])
    _git_fail(f"several commits match `{text}`; use the hash:\n{lines}")
    return None


def _git_undo(args: list[str]) -> int:
    options, positional = _git_parse(args, flags=("--list",))
    if "--list" in options:
        if positional:
            raise _GitUsage("undo --list takes no commit")
        return _git_undo_list()
    if not _git_has_commits():
        return _git_fail("this branch has no commits yet.")
    if positional:
        # Back to the named commit: it stays, every commit after it is undone.
        target = _git_find_commit(" ".join(positional))
        if target is None:
            return 1
    else:
        parent = _git_out("rev-parse", "--verify", "-q", "HEAD~1")
        if parent.returncode:
            return _git_fail("there is no earlier commit to go back to.")
        target = parent.stdout.strip()
    undone = _git_out("rev-list", f"{target}..HEAD").stdout.split()
    if not undone:
        print("Already at that commit; nothing to undo.")
        return 0
    # The oldest undone commit is in every later one: if a remote has any of them, it has this one.
    if _git_out("branch", "-r", "--contains", undone[-1]).stdout.split():
        return _git_fail(
            "some of these commits are already on a remote branch; undoing them would rewrite shared history.\n"
            f"Use `git revert {'<commit>' if positional else 'HEAD'}` instead."
        )
    subjects = _git_out("log", "--format=%h  %s", f"{target}..HEAD").stdout.rstrip()
    code = _run_all([["git", "reset", "--soft", target]])
    if not code:
        count = len(undone)
        print(f"Undid {count} commit{'s' if count > 1 else ''}:\n{subjects}\nTheir changes are staged.")
    return code


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    action, rest = (args[0], args[1:]) if args else ("", [])
    if action in _GIT_ACTIONS and any(arg in {"-h", "--help"} for arg in rest):
        print(COMMAND_HELP, end="")
        return 0
    if action in _GIT_REMOVED:
        print(f"unlaw git: `ul git {action}` was removed; use `git {action}`.", file=sys.stderr)
        return 2
    try:
        if action in {"push", "commit", "sync"}:
            tokens, allow = _git_commit_args(rest)
            if action == "commit":
                return _commit_workflow(tokens, push=False, allow_secrets=allow)
            if action == "sync":
                code = _run_all([["git", "pull", "--rebase"]])
                return code or _commit_workflow(tokens, push=True, allow_secrets=allow)
            return _commit_workflow(tokens, push=True, allow_secrets=allow)
        handlers = {
            "init": _git_init,
            "connect": _git_connect,
            "mirror": _git_mirror,
            "token": _git_token,
            "open": _git_open,
            "pr": _git_pr,
            "undo": _git_undo,
        }
        if action in handlers:
            return handlers[action](rest)
        tokens, allow = _git_commit_args(args)
        return _commit_workflow(tokens, push=True, allow_secrets=allow)
    except _GitUsage as error:
        print(f"unlaw git: {error}\n{USAGE}", file=sys.stderr)
        return 2
    except HostError as error:
        print(f"unlaw git: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
