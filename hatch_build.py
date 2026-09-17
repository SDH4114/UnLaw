"""Hatch build hook that prepares Unlaw's user-owned command sources."""

from __future__ import annotations

import sys
from pathlib import Path


def bootstrap_user_layout() -> Path:
    source_root = Path(__file__).parent / "src"
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    from unlawful.config import ensure_layout

    return ensure_layout()


try:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
except ImportError:  # Allows the hook to be unit-tested without Hatchling installed.
    class BuildHookInterface:  # type: ignore[no-redef]
        pass


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict[str, object]) -> None:
        bootstrap_user_layout()
