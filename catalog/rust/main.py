# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Create a Rust project using Cargo and the configured templates."""
from __future__ import annotations

COMMAND_HELP = 'Create a Rust project using Cargo and the configured templates.\nUsage: ul rust <project-name> [--bin|--lib] [--git]\nOptions: --bin creates an executable (default); --lib creates a library.\n--git initializes Git; default comes from projects.rust.initialize_git.\nExample: ul rust demo --lib --git\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'projects': {'rust': {'initialize_git': False}}}


class ConfigError(ValueError):
    pass


def config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return base / "unlaw"


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        result[key] = (
            _deep_merge(result[key], value)
            if isinstance(value, dict) and isinstance(result.get(key), dict)
            else copy.deepcopy(value)
        )
    return result


def load_config() -> dict:
    path = config_dir() / "config.toml"
    try:
        with path.open("rb") as handle:
            configured = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Could not read {path}: {error}") from error
    return _deep_merge(DEFAULT_CONFIG, configured)

def templates_dir() -> Path:
    return config_dir() / "templates"

import os
import shutil
from pathlib import Path



def _render(text: str, variables: dict[str, str]) -> str:
    for name, value in variables.items():
        text = text.replace("{{" + name + "}}", value)
    return text


def apply_template(name: str, destination: Path, variables: dict[str, str]) -> int:
    source = templates_dir() / name
    if not source.is_dir():
        return 0
    copied = 0
    for item in sorted(source.rglob("*")):
        relative = Path(*(_render(part, variables) for part in item.relative_to(source).parts))
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        data = item.read_bytes()
        try:
            target.write_text(_render(data.decode("utf-8"), variables), encoding="utf-8")
            os.chmod(target, item.stat().st_mode)
        except UnicodeDecodeError:
            shutil.copy2(item, target)
        copied += 1
    return copied

import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


VALID_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
USAGE = "Usage: ul rust <project-name> [--bin|--lib] [--git]"


def _parse(args: list[str]) -> tuple[str, str, bool] | None:
    if not args or not VALID_NAME.fullmatch(args[0]):
        return None
    kind: str | None = None
    initialize_git = False
    for flag in args[1:]:
        if flag in {"--bin", "--lib"}:
            if kind is not None and flag != kind:
                return None
            kind = flag
        elif flag == "--git":
            initialize_git = True
        else:
            return None
    return args[0], kind or "--bin", initialize_git


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    parsed = _parse(args)
    if parsed is None:
        print(USAGE, file=sys.stderr)
        return 2
    name, kind, git_flag = parsed
    cargo = shutil.which("cargo")
    if cargo is None:
        print("unlaw rust: Cargo is not installed or not on PATH.", file=sys.stderr)
        return 1
    try:
        initialize_git = git_flag or load_config()["projects"]["rust"]["initialize_git"]
    except ConfigError as error:
        print(f"unlaw rust: {error}", file=sys.stderr)
        return 2
    command = [cargo, "new", name, kind]
    if not initialize_git:
        command.extend(["--vcs", "none"])
    try:
        code = subprocess.run(command, check=False).returncode
    except OSError as error:
        print(f"unlaw rust: {error}", file=sys.stderr)
        return 1
    if code:
        return code
    apply_template("rust", Path(name), {"project_name": name})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
