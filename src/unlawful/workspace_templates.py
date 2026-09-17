from __future__ import annotations

import json
import os
import re
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .config import ensure_layout, templates_dir

TEMPLATE_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
ALLOWED_APPS = {"zed", "obsidian"}
MANIFEST_FIELDS = {"path", "app", "ai"}


class WorkspaceTemplateError(ValueError):
    """Raised when a saved project template is invalid or unavailable."""


@dataclass(frozen=True)
class WorkspaceTemplate:
    name: str
    path: Path
    app: str
    ai: bool


def validate_workspace_template_name(name: str) -> None:
    if not TEMPLATE_NAME.fullmatch(name):
        raise WorkspaceTemplateError(
            "Invalid template name: use a lowercase letter followed by lowercase "
            "letters, numbers, '-' or '_'."
        )


def workspace_templates_dir() -> Path:
    return templates_dir() / "projects"


def _manifest_path(name: str) -> Path:
    validate_workspace_template_name(name)
    return workspace_templates_dir() / f"{name}.toml"


def _validate_manifest(name: str, data: object) -> WorkspaceTemplate:
    if not isinstance(data, dict):
        raise WorkspaceTemplateError(f"Invalid template {name}: expected a TOML table")
    keys = set(data)
    unknown = keys - MANIFEST_FIELDS
    if unknown:
        raise WorkspaceTemplateError(
            f"Invalid template {name}: unknown fields: {', '.join(sorted(unknown))}"
        )
    if keys != MANIFEST_FIELDS:
        missing = MANIFEST_FIELDS - keys
        raise WorkspaceTemplateError(
            f"Invalid template {name}: missing fields: {', '.join(sorted(missing))}"
        )
    path = data["path"]
    app = data["app"]
    ai = data["ai"]
    if not isinstance(path, str) or not path or not Path(path).is_absolute():
        raise WorkspaceTemplateError(f"Invalid template {name}: path must be absolute")
    if not isinstance(app, str) or app not in ALLOWED_APPS:
        raise WorkspaceTemplateError(
            f"Invalid template {name}: app must be zed or obsidian"
        )
    if not isinstance(ai, bool):
        raise WorkspaceTemplateError(f"Invalid template {name}: ai must be true or false")
    return WorkspaceTemplate(name=name, path=Path(path), app=app, ai=ai)


def load_workspace_template(name: str) -> WorkspaceTemplate:
    path = _manifest_path(name)
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise WorkspaceTemplateError(f"Could not read template {name}: {error}") from error
    return _validate_manifest(name, data)


def discover_workspace_templates() -> dict[str, WorkspaceTemplate]:
    ensure_layout()
    discovered: dict[str, WorkspaceTemplate] = {}
    for manifest in sorted(workspace_templates_dir().glob("*.toml")):
        name = manifest.stem
        validate_workspace_template_name(name)
        discovered[name] = load_workspace_template(name)
    return discovered


def create_workspace_template(
    name: str,
    path: Path,
    app: str,
    ai: bool,
) -> WorkspaceTemplate:
    validate_workspace_template_name(name)
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise WorkspaceTemplateError(f"Project directory does not exist: {resolved}")
    template = _validate_manifest(
        name,
        {"path": str(resolved), "app": app, "ai": ai},
    )
    ensure_layout()
    destination = _manifest_path(name)
    if destination.exists():
        raise WorkspaceTemplateError(f"Template already exists: {name}")
    text = (
        f"path = {json.dumps(str(template.path), ensure_ascii=False)}\n"
        f"app = {json.dumps(template.app)}\n"
        f"ai = {'true' if template.ai else 'false'}\n"
    )
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        if destination.exists():
            raise WorkspaceTemplateError(f"Template already exists: {name}")
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return template
