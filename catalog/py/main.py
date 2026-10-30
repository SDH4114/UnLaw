# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Create a Python project from the configured templates."""
from __future__ import annotations

COMMAND_HELP = 'Create a Python project from the configured templates.\nUsage: ul py <project-name> [--uv|--venv|--no-venv] [--git]\nOptions: --uv uses uv; --venv uses Python venv; --no-venv skips environment creation.\n--git initializes Git. Defaults come from projects.python.\nExample: ul py demo --venv --git\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'projects': {'python': {'environment': 'auto', 'initialize_git': False}}}


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
import venv
from collections.abc import Sequence
from pathlib import Path


VALID_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
USAGE = "Usage: ul py <project-name> [--uv|--venv|--no-venv] [--git]"


def _parse(args: list[str]) -> tuple[str, str | None, bool] | None:
    if not args or not VALID_NAME.fullmatch(args[0]):
        return None
    mode: str | None = None
    initialize_git = False
    for flag in args[1:]:
        if flag in {"--uv", "--venv", "--no-venv"}:
            requested = {"--uv": "uv", "--venv": "venv", "--no-venv": "none"}[flag]
            if mode is not None and mode != requested:
                return None
            mode = requested
        elif flag == "--git":
            initialize_git = True
        else:
            return None
    return args[0], mode, initialize_git


def _run(command: list[str]) -> int:
    try:
        return subprocess.run(command, check=False).returncode
    except OSError as error:
        print(f"unlaw py: {error}", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    parsed = _parse(args)
    if parsed is None:
        print(USAGE, file=sys.stderr)
        return 2
    name, requested_mode, git_flag = parsed
    try:
        settings = load_config()["projects"]["python"]
    except ConfigError as error:
        print(f"unlaw py: {error}", file=sys.stderr)
        return 2
    project = Path(name)
    if project.exists():
        print(f"unlaw py: Destination already exists: {project}", file=sys.stderr)
        return 1

    mode = requested_mode or settings["environment"]
    if mode == "auto":
        mode = "uv" if shutil.which("uv") else "venv"
    uv = shutil.which("uv") if mode == "uv" else None
    if mode == "uv" and uv is None:
        print("unlaw py: uv is not installed or not on PATH.", file=sys.stderr)
        return 1
    project.mkdir()
    (project / "main.py").write_text(
        'def main() -> None:\n    print("Hello from Unlaw")\n\n\nif __name__ == "__main__":\n    main()\n',
        encoding="utf-8",
    )
    (project / ".gitignore").write_text(".venv/\n__pycache__/\n*.py[cod]\n", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n',
        encoding="utf-8",
    )
    apply_template("python", project, {"project_name": name})

    if mode == "uv":
        assert uv is not None
        code = _run([uv, "venv", str(project / ".venv")])
        if code:
            return code
    elif mode == "venv":
        try:
            venv.EnvBuilder(with_pip=True).create(project / ".venv")
        except (OSError, subprocess.SubprocessError) as error:
            print(f"unlaw py: Virtual environment failed: {error}", file=sys.stderr)
            return 1
    if git_flag or settings["initialize_git"]:
        code = _run(["git", "init", str(project)])
        if code:
            return code
    print(f"Created Python project: {project} (environment: {mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
