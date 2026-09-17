from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .config import (
    DEFAULT_CONFIG,
    ConfigError,
    config_dir,
    config_file,
    ensure_layout,
    load_config,
    materialize_config,
    storage_path,
    templates_dir,
    user_commands_dir,
)
from .runner import command_source, discover_commands, resolve_command
from .shell_integration import install_zsh_integration
from .workspace_templates import (
    WorkspaceTemplateError,
    create_workspace_template,
    discover_workspace_templates,
    validate_workspace_template_name,
)

SYSTEM_COMMAND_NAMES = {
    "commands",
    "completion",
    "config",
    "create",
    "doctor",
    "init",
    "list",
    "templates",
    "version",
    "which",
}
COMMAND_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")


def _command_records() -> list[dict[str, object]]:
    discovered = discover_commands()
    aliases = load_config()["aliases"]
    records_by_name: dict[str, dict[str, object]] = {}
    for name in sorted(SYSTEM_COMMAND_NAMES | discovered.keys()):
        path = discovered.get(name)
        records_by_name[name] = {
            "name": name,
            "source": command_source(path) if path else "system",
            "path": str(path) if path else None,
        }
    for name, expansion in aliases.items():
        if name not in SYSTEM_COMMAND_NAMES:
            records_by_name[name] = {
                "name": name,
                "source": "alias",
                "path": None,
                "expansion": expansion,
            }
    return [records_by_name[name] for name in sorted(records_by_name)]


def list_commands(argv: Sequence[str] = ()) -> int:
    args = list(argv)
    if args not in ([], ["--verbose"], ["--json"]):
        print("Usage: ul commands [--verbose|--json]", file=sys.stderr)
        return 2
    try:
        records = _command_records()
    except ConfigError as error:
        print(f"unlaw commands: {error}", file=sys.stderr)
        return 2
    if args == ["--json"]:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    elif args == ["--verbose"]:
        for record in records:
            suffix = f"  {record['path']}" if record["path"] else ""
            print(f"{record['name']:<16} {record['source']}{suffix}")
    else:
        for record in records:
            print(record["name"])
    return 0


def list_templates(argv: Sequence[str] = ()) -> int:
    if argv:
        print("Usage: ul templates", file=sys.stderr)
        return 2
    try:
        names = sorted(discover_workspace_templates())
    except WorkspaceTemplateError as error:
        print(f"unlaw templates: {error}", file=sys.stderr)
        return 2
    for name in names:
        print(name)
    return 0


def list_all(argv: Sequence[str] = ()) -> int:
    if argv:
        print("Usage: ul list", file=sys.stderr)
        return 2
    try:
        templates = sorted(discover_workspace_templates())
        commands = [str(record["name"]) for record in _command_records()]
    except (ConfigError, WorkspaceTemplateError) as error:
        print(f"unlaw list: {error}", file=sys.stderr)
        return 2
    print("Templates")
    for name in templates:
        print(name)
    print("\nCommands")
    for name in commands:
        print(name)
    return 0


def init_command(argv: Sequence[str] = ()) -> int:
    if argv:
        print("Usage: ul init", file=sys.stderr)
        return 2
    root = ensure_layout()
    print(f"Unlaw configuration: {root}")
    print(f"Commands: {user_commands_dir()}")
    print(f"Templates: {templates_dir()}")
    print(f"Storage: {storage_path()}")
    return 0


def which_command(argv: Sequence[str]) -> int:
    if len(argv) != 1:
        print("Usage: ul which <command>", file=sys.stderr)
        return 2
    name = argv[0]
    if name in SYSTEM_COMMAND_NAMES:
        print(f"{name}: system")
        return 0
    try:
        alias = load_config()["aliases"].get(name)
    except ConfigError as error:
        print(f"unlaw which: {error}", file=sys.stderr)
        return 2
    if alias:
        print(f"{name}: alias -> {shlex.join(alias)}")
        return 0
    path = resolve_command(name)
    if path is None:
        print(f"unlaw: Unknown command: {name}", file=sys.stderr)
        return 1
    print(f"{name}: {command_source(path)} {path}")
    return 0


def version_command(argv: Sequence[str] = ()) -> int:
    if argv:
        print("Usage: ul version", file=sys.stderr)
        return 2
    print(f"Unlaw {__version__}")
    return 0


def completion_command(argv: Sequence[str]) -> int:
    if list(argv) != ["zsh"]:
        print("Usage: ul completion zsh", file=sys.stderr)
        return 2
    print("""#compdef ul unlaw
_unlaw() {
  local -a commands
  commands=( ${(f)\"$( { ul commands; ul templates; } 2>/dev/null )\"} )
  if (( CURRENT == 2 )); then
    _describe 'unlaw command' commands
  else
    _files
  fi
}
compdef _unlaw ul unlaw
""", end="")
    return 0


def _create_user_command(args: list[str]) -> int:
    if len(args) != 1:
        print("Usage: ul create command <name>", file=sys.stderr)
        return 2
    name = args[0]
    if not COMMAND_NAME.fullmatch(name) or name in SYSTEM_COMMAND_NAMES:
        print(
            "unlaw: Command names must start with a lowercase letter and contain only "
            "lowercase letters, numbers, '-' or '_'.",
            file=sys.stderr,
        )
        return 2

    destination = user_commands_dir() / name / "main.py"
    if destination.exists():
        print(f"unlaw: Command already exists: {destination}", file=sys.stderr)
        return 1

    user_template = templates_dir() / "commands" / "main.py"
    template = (
        user_template
        if user_template.is_file()
        else Path(__file__).with_name("templates") / "command_main.py"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Created command '{name}': {destination}")
    print(f"Run it with: ul {name}")
    return 0


class _PromptCancelled(Exception):
    pass


def _prompt_value(prompt: str, allowed: set[str], error: str) -> str:
    while True:
        try:
            value = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt) as cause:
            raise _PromptCancelled from cause
        if value in allowed:
            return value
        print(error, file=sys.stderr)


def _create_project_template(args: list[str]) -> int:
    if len(args) > 1:
        print("Usage: ul create template [name]", file=sys.stderr)
        return 2
    try:
        name = args[0] if args else input("Name of template > ").strip()
    except (EOFError, KeyboardInterrupt):
        print("unlaw create template: Cancelled.", file=sys.stderr)
        return 1
    try:
        validate_workspace_template_name(name)
        ensure_layout()
        aliases = load_config()["aliases"]
        commands = discover_commands()
        templates = discover_workspace_templates()
        if name in SYSTEM_COMMAND_NAMES or name in commands or name in aliases or name in templates:
            print(f"unlaw create template: Name already in use: {name}", file=sys.stderr)
            return 1
        app = _prompt_value(
            "Open with (zed/obsidian) > ",
            {"zed", "obsidian"},
            "Please enter zed or obsidian.",
        )
        ai = _prompt_value(
            "Add AI? (y/n) > ",
            {"y", "n"},
            "Please enter y or n.",
        ) == "y"
        template = create_workspace_template(name, Path.cwd(), app, ai)
    except _PromptCancelled:
        print("unlaw create template: Cancelled.", file=sys.stderr)
        return 1
    except (ConfigError, WorkspaceTemplateError, OSError) as error:
        print(f"unlaw create template: {error}", file=sys.stderr)
        return 2
    print(f"Created template '{name}' for {template.path}")
    print(f"Run it with: ul {name}")
    return 0


def create_command(argv: Sequence[str]) -> int:
    args = list(argv)
    if args and args[0] == "command":
        return _create_user_command(args[1:])
    if args and args[0] == "template":
        return _create_project_template(args[1:])
    print("Usage: ul create command <name> | ul create template [name]", file=sys.stderr)
    return 2


def _harness_permissions(executable: str | None = None) -> tuple[bool, str]:
    executable = executable or shutil.which("macos-harness")
    if executable is None:
        return False, "not installed"
    try:
        result = subprocess.run(
            [executable, "doctor"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False, "permission check timed out"
    except OSError as error:
        return False, str(error)
    detail = (result.stdout or result.stderr).strip().splitlines()
    return result.returncode == 0, detail[-1] if detail else "no details"


def _user_bin_precedes_system() -> bool:
    entries = [Path(item).expanduser() for item in os.environ.get("PATH", "").split(os.pathsep) if item]
    user_bin = Path.home() / ".local" / "bin"
    try:
        user_position = entries.index(user_bin)
    except ValueError:
        return False
    try:
        system_position = entries.index(Path("/usr/bin"))
    except ValueError:
        return True
    return user_position < system_position


def _fix_shell_path() -> bool:
    """Add Unlaw's uv launcher directory once, preserving the user's zsh config."""
    line = 'export PATH="$HOME/.local/bin:$PATH"'
    zshrc = Path.home() / ".zshrc"
    existing = zshrc.read_text(encoding="utf-8") if zshrc.exists() else ""
    if line in existing:
        return False
    zshrc.parent.mkdir(parents=True, exist_ok=True)
    separator = "" if not existing or existing.endswith("\n") else "\n"
    with zshrc.open("a", encoding="utf-8") as handle:
        handle.write(f"{separator}\n# Unlaw CLI (managed by `unlaw doctor --fix`)\n{line}\n")
    return True


def _lm_studio_server(base_url: str) -> tuple[bool, str]:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 1234
        with socket.create_connection((host, port), timeout=0.15):
            return True, f"listening at {host}:{port}"
    except OSError as error:
        return False, f"not listening: {error}"


def _apply_doctor_fixes() -> list[str]:
    changes: list[str] = []
    ensure_layout()
    if _fix_shell_path():
        changes.append("Added ~/.local/bin before system commands in ~/.zshrc")
    if install_zsh_integration():
        changes.append("Installed current-shell integration in ~/.zshrc")
    if materialize_config():
        changes.append("Added current defaults and removed deprecated storage settings in config.toml")
    for parts in (
        ("captures", "screenshots"),
        ("captures", "recordings"),
        ("telegram", "downloads"),
        ("runtime",),
    ):
        path = storage_path(*parts)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            changes.append(f"Created {path}")
    legacy_log = config_file().with_name("recording.log")
    new_log = storage_path("runtime", "recording.log")
    if legacy_log.is_file() and not new_log.exists():
        shutil.move(legacy_log, new_log)
        changes.append(f"Moved {legacy_log} to {new_log}")
    return changes


def _doctor_records() -> list[dict[str, object]]:
    root = ensure_layout()
    try:
        config = load_config()
        config_ok = True
        config_detail = str(config_file())
    except ConfigError as error:
        config = DEFAULT_CONFIG
        config_ok = False
        config_detail = str(error)
    storage_root = storage_path() if config_ok else config_dir() / str(DEFAULT_CONFIG["storage"]["root"])
    harness_name = str(config["mac"]["executable"])
    harness_path = shutil.which(harness_name)
    permissions, permission_detail = _harness_permissions(harness_path) if harness_path else (False, "not installed")
    todo_file = Path(config["todo"]["vault_path"]).expanduser() / config["todo"]["file"]
    lm_server, lm_detail = _lm_studio_server(config["lm"]["base_url"])

    def tool(name: str, executable: str, detail: str, *, required: bool = False) -> dict[str, object]:
        path = shutil.which(executable)
        return {
            "name": name,
            "available": path is not None,
            "required": required,
            "detail": path or detail,
        }

    return [
        {"name": "Unlaw", "available": True, "required": True, "detail": f"version {__version__}"},
        {"name": "Layout", "available": root.is_dir(), "required": True, "detail": str(root)},
        {"name": "Configuration", "available": config_ok, "required": True, "detail": config_detail},
        {
            "name": "Storage",
            "available": storage_root.is_dir(),
            "required": False,
            "detail": str(storage_root),
        },
        tool("Python", "python3", sys.version.split()[0], required=True),
        tool("uv", "uv", "optional; Python falls back to venv"),
        tool("Git", "git", "needed by Git workflows and --git"),
        tool("Cargo", "cargo", "needed by `ul rust`"),
        tool("CMake", "cmake", "needed to build generated C++ projects"),
        tool("screencapture", "screencapture", "built into macOS"),
        tool("ffmpeg", "ffmpeg", "needed for camera and audio recording"),
        tool("Zed", "zed", "needed by `ul work`"),
        tool("macOS Keychain", "security", "needed to store the Telegram token"),
        {
            "name": "Unlaw PATH",
            "available": _user_bin_precedes_system(),
            "required": False,
            "detail": "~/.local/bin must precede /usr/bin because macOS also ships `ul`",
        },
        {
            "name": "Obsidian TODO",
            "available": todo_file.is_file(),
            "required": False,
            "detail": str(todo_file),
        },
        {
            "name": "Spotify",
            "available": Path("/Applications/Spotify.app").exists(),
            "required": False,
            "detail": "/Applications/Spotify.app",
        },
        {
            "name": "macOS Harness",
            "available": harness_path is not None,
            "required": False,
            "detail": harness_path or "optional backend",
        },
        {
            "name": "macOS permissions",
            "available": permissions,
            "required": False,
            "detail": permission_detail,
        },
        {
            "name": "LM Studio",
            "available": Path("/Applications/LM Studio.app").exists(),
            "required": False,
            "detail": "/Applications/LM Studio.app",
        },
        {
            "name": "LM Studio local server",
            "available": lm_server,
            "required": False,
            "detail": lm_detail,
        },
    ]


def doctor(argv: Sequence[str] = ()) -> int:
    args = list(argv)
    if args not in ([], ["--verbose"], ["--json"], ["--fix"]):
        print("Usage: ul doctor [--verbose|--json|--fix]", file=sys.stderr)
        return 2
    try:
        if args == ["--fix"]:
            changes = _apply_doctor_fixes()
            if changes:
                for change in changes:
                    print(f"FIXED  {change}")
                print("Restart the shell or run: exec zsh")
            else:
                print("No automatic fixes were needed.")
        records = _doctor_records()
    except (ConfigError, OSError) as error:
        print(f"unlaw doctor: {error}", file=sys.stderr)
        return 1
    if args == ["--json"]:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        verbose = args in (["--verbose"], ["--fix"])
        for record in records:
            marker = "✓" if record["available"] else "○"
            suffix = f"  {record['detail']}" if verbose else ""
            print(f"{record['name']!s:<20} {marker}{suffix}")
    return 1 if any(record["required"] and not record["available"] for record in records) else 0
