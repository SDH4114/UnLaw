"""Git hosting services: remote shortcuts, repository creation, tokens, SSH keys and web links."""

from __future__ import annotations

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
# A hostile server could stream forever; real answers are a few kilobytes.
_API_MAX_BYTES = 1_000_000
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


def _hosts_clean(text: str) -> str:
    """Drop control characters (ESC sequences, BEL...) so server text cannot drive the terminal."""
    return "".join(ch for ch in text if ch in "\t\n" or (ord(ch) >= 32 and ord(ch) != 127))


def _hosts_last_line(text: str) -> str:
    lines = [line.strip() for line in _hosts_clean(text).splitlines() if line.strip()]
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


def _hosts_service(host: str, base_url: str | None = None) -> str:
    """Keychain service per API server (`unlaw.git.gitlab.com`), so a token only ever goes to the
    server it was saved for: `--url https://elsewhere` finds no token instead of sending gitlab.com's."""
    info = _hosts_lookup(host)
    api = info.api if info.kind == "github" else _hosts_api_base(info, base_url)
    server = (urllib.parse.urlsplit(api).hostname or "").lower()
    if not _HOSTNAME.fullmatch(server):
        raise HostError(f"not a valid server name: {server!r}")
    return f"unlaw.git.{server}"


def token(host: str, base_url: str | None = None) -> str | None:
    result = _hosts_run(
        [
            "security",
            "find-generic-password",
            "-a",
            "unlaw",
            "-s",
            _hosts_service(host, base_url),
            "-w",
        ]
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def save_token(host: str, value: str, base_url: str | None = None) -> None:
    service = _hosts_service(host, base_url)
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



def prompt_token(host: str, base_url: str | None = None) -> None:
    """Save a token typed into `security`'s own hidden prompt (`-w` last, as `man security`
    recommends): the token never appears in argv, where other accounts could see it with `ps`."""
    service = _hosts_service(host, base_url)
    if shutil.which("security") is None:
        raise HostError(f"`security` was not found on PATH: {_HINTS.get('security', 'install it')}")
    # The terminal is inherited on purpose: security asks for the token and its confirmation.
    result = subprocess.run(
        ["security", "add-generic-password", "-a", "unlaw", "-s", service, "-U", "-w"], check=False
    )
    if result.returncode != 0:
        raise HostError("the token was not saved (cancelled, the two entries differ, or the Keychain is locked)")


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
            body = response.read(_API_MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        raw = error.read(_API_MAX_BYTES).decode("utf-8", "replace") if error.fp else ""
        error.close()
        detail = _hosts_scrub(" ".join(_hosts_clean(raw).split())[:200], secret)
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
    if len(body) > _API_MAX_BYTES:
        raise HostError(f"{host} returned an answer that is too large")
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
    secret = token(info.name, base_url)
    if not secret:
        server = _hosts_service(info.name, base_url).removeprefix("unlaw.git.")
        save = f"ul git token {info.name}" + (f" --url {base_url}" if base_url else "")
        raise HostError(
            f"no API token for {server}: create one there with repository write access, then run `{save}`"
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
        # Never accept an unknown host key silently: a first connection could be intercepted.
        "StrictHostKeyChecking=yes",
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
    if "host key verification failed" in lowered:
        return (
            False,
            f"the host key of {ssh_host} is not trusted yet: check its fingerprint on the host's "
            f"documentation page, then run `ssh -T git@{ssh_host}` once and accept it",
        )
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
