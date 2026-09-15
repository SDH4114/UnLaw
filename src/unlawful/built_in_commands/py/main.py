from __future__ import annotations

import re
import shutil
import subprocess
import sys
import venv
from collections.abc import Sequence
from pathlib import Path

from unlawful.config import ConfigError, load_config
from unlawful.project_templates import apply_template

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
    parsed = _parse(list(sys.argv[1:] if argv is None else argv))
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
