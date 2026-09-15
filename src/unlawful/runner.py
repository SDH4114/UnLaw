from __future__ import annotations

import shlex
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from .config import user_commands_dir


def _command_scripts(directory: Path) -> dict[str, Path]:
    if not directory.is_dir():
        return {}
    return {
        child.name: child / "main.py"
        for child in directory.iterdir()
        if child.is_dir() and (child / "main.py").is_file() and not child.name.startswith(".")
    }


def discover_commands() -> dict[str, Path]:
    return _command_scripts(user_commands_dir())


def resolve_command(name: str) -> Path | None:
    return discover_commands().get(name)


def command_source(path: Path) -> str:
    try:
        path.relative_to(user_commands_dir())
        return "config"
    except ValueError:
        return "external"


def run_command(
    name: str,
    args: Sequence[str],
    *,
    dry_run: bool = False,
    verbose: bool = False,
    timeout: float | None = None,
) -> int:
    script = resolve_command(name)
    if script is None:
        raise KeyError(name)
    command = [sys.executable, str(script), *args]
    if dry_run:
        print(f"DRY RUN: {shlex.join(command)}")
        return 0
    if verbose:
        print(f"unlaw: running {name} ({command_source(script)}): {shlex.join(command)}", file=sys.stderr)
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            check=False,
            timeout=timeout if timeout and timeout > 0 else None,
        )
    except subprocess.TimeoutExpired:
        print(f"unlaw: Command timed out: {name}", file=sys.stderr)
        return 124
    if verbose:
        print(f"unlaw: finished in {time.perf_counter() - started:.3f}s", file=sys.stderr)
    return completed.returncode
