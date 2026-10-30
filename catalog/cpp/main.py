# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Create a C++ project from the configured templates."""
from __future__ import annotations

COMMAND_HELP = 'Create a C++ project from the configured templates.\nUsage: ul cpp <project-name> [--std 11|14|17|20|23|26] [--git]\nOptions: --std selects the C++ standard; --git initializes Git.\nDefaults: projects.cpp.standard and projects.cpp.initialize_git.\nExample: ul cpp demo --std 23 --git\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'projects': {'cpp': {'standard': 20, 'initialize_git': False}}}


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
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


VALID_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
STANDARDS = {11, 14, 17, 20, 23, 26}
USAGE = "Usage: ul cpp <project-name> [--std 11|14|17|20|23|26] [--git]"


def _parse(args: list[str]) -> tuple[str, int | None, bool] | None:
    if not args or not VALID_NAME.fullmatch(args[0]):
        return None
    standard: int | None = None
    initialize_git = False
    index = 1
    while index < len(args):
        if args[index] == "--git":
            initialize_git = True
            index += 1
        elif args[index] == "--std" and index + 1 < len(args):
            try:
                standard = int(args[index + 1])
            except ValueError:
                return None
            if standard not in STANDARDS:
                return None
            index += 2
        else:
            return None
    return args[0], standard, initialize_git


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    parsed = _parse(args)
    if parsed is None:
        print(USAGE, file=sys.stderr)
        return 2
    name, requested_standard, git_flag = parsed
    try:
        settings = load_config()["projects"]["cpp"]
    except ConfigError as error:
        print(f"unlaw cpp: {error}", file=sys.stderr)
        return 2
    project = Path(name)
    if project.exists():
        print(f"unlaw cpp: Destination already exists: {project}", file=sys.stderr)
        return 1
    standard = requested_standard or settings["standard"]
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.cpp").write_text(
        '#include <iostream>\n\nint main() {\n    std::cout << "Hello from Unlaw\\n";\n    return 0;\n}\n',
        encoding="utf-8",
    )
    (project / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\n"
        f"project({name} LANGUAGES CXX)\n\n"
        f"set(CMAKE_CXX_STANDARD {standard})\n"
        "set(CMAKE_CXX_STANDARD_REQUIRED ON)\n\n"
        f"add_executable({name} src/main.cpp)\n",
        encoding="utf-8",
    )
    (project / ".gitignore").write_text("build/\n.DS_Store\n", encoding="utf-8")
    apply_template(
        "cpp",
        project,
        {"project_name": name, "cpp_standard": str(standard)},
    )
    if git_flag or settings["initialize_git"]:
        try:
            code = subprocess.run(["git", "init", str(project)], check=False).returncode
        except OSError as error:
            print(f"unlaw cpp: {error}", file=sys.stderr)
            return 1
        if code:
            return code
    print(f"Created C++ project: {project} (C++{standard})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
