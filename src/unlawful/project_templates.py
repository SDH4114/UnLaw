from __future__ import annotations

import os
import shutil
from pathlib import Path

from .config import templates_dir


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
