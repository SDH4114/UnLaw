"""Stand-in for `unlawful.git_hosts` so git command tests never reach a host or the Keychain."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path


class HostError(Exception):
    pass


@dataclass(frozen=True)
class Host:
    name: str
    kind: str
    web: str
    api: str
    ssh_host: str
    keys_page: str


@dataclass(frozen=True)
class Created:
    ssh_url: str
    https_url: str
    web_url: str


HOSTS = {
    "github": Host(
        "github",
        "github",
        "https://github.com",
        "https://api.github.com",
        "github.com",
        "https://github.com/settings/keys",
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
    "gitea": Host("gitea", "gitea", "", "", "", ""),
}


def expand_remote(spec: str) -> str:
    return spec


def is_host_name(spec: str) -> bool:
    return spec in HOSTS


def create_repo(host, name, *, private=True, description="", base_url=None):
    raise AssertionError("tests must patch create_repo")


def token(host):
    return None


def save_token(host, value):
    raise AssertionError("tests must patch save_token")


def web_url(remote):
    return None


def pr_url(remote, branch, base="main"):
    return None


def host_of(remote):
    return None


def ssh_check(ssh_host, timeout=15):
    raise AssertionError("tests must patch ssh_check")


def ensure_ssh_key() -> Path:
    raise AssertionError("tests must patch ensure_ssh_key")


def install() -> None:
    """Register the stub as `unlawful.git_hosts` unless the real module is importable."""
    try:
        import unlawful.git_hosts  # noqa: F401
    except ImportError:
        module = types.ModuleType("unlawful.git_hosts")
        module.__dict__.update(
            {
                name: value
                for name, value in globals().items()
                if not name.startswith("_") and name != "install"
            }
        )
        sys.modules["unlawful.git_hosts"] = module
