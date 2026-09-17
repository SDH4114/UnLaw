from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import tomllib
import urllib.parse
from pathlib import Path
from typing import Any

from .command_sources import command_source, is_replaceable_command_source

DEFAULT_CONFIG: dict[str, Any] = {
    "core": {
        "color": True,
        "verbose": False,
        "command_timeout": 0,
        "show_timing": False,
    },
    "aliases": {},
    "storage": {"root": "data"},
    "git": {"auto_push": True},
    "projects": {
        "python": {"environment": "auto", "initialize_git": False},
        "rust": {"initialize_git": False},
        "cpp": {"standard": 20, "initialize_git": False},
    },
    "mac": {"executable": "macos-harness", "timeout": 30},
    "todo": {
        "vault_path": "~/aiwork/data-obsidian",
        "file": "TODO.md",
        "completed_column": "Completed",
    },
    "capture": {
        "camera_device": "0",
        "audio_device": "0",
        "screen_audio": True,
        "show_clicks": True,
    },
    "games": {"difficulty": "normal"},
    "apps": {
        "spotify": "Spotify",
        "editor": "Zed",
        "spotify_autoplay_delay": 2.0,
        "browser_url": "https://duckduckgo.com/",
        "lofi_url": "https://lofi-engine.vercel.app/",
        "youtube_url": "https://www.youtube.com/",
    },
    "telegram": {
        "chat_id": "",
        "api_base": "https://api.telegram.org",
        "keychain_service": "unlaw.telegram",
    },
    "lm": {
        "base_url": "http://127.0.0.1:1234/v1",
        "model": "auto",
        "system_prompt": "You are a concise and practical local assistant.",
        "temperature": 0.7,
        "timeout": 120,
    },
}

TEMPLATE_NAMES = ("commands", "python", "rust", "cpp", "projects")
DEFAULT_COMMAND_NAMES = (
    "app",
    "browser",
    "capture",
    "cpp",
    "game",
    "git",
    "gpt",
    "lm",
    "lofi",
    "mac",
    "minecraft",
    "music",
    "netflix",
    "obsidian",
    "py",
    "rust",
    "steam",
    "tg",
    "todo",
    "work",
    "yt",
    "zed",
)
STORAGE_SUBDIRECTORIES = (
    ("captures", "screenshots"),
    ("captures", "recordings"),
    ("telegram", "downloads"),
    ("runtime",),
)
BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


class ConfigError(ValueError):
    """Raised when Unlaw's configuration is unreadable or invalid."""


def config_dir() -> Path:
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_home).expanduser() if xdg_home else Path.home() / ".config"
    return base / "unlaw"


def config_file() -> Path:
    return config_dir() / "config.toml"


def user_commands_dir() -> Path:
    return config_dir() / "commands"


def templates_dir() -> Path:
    return config_dir() / "templates"


def storage_path(*parts: str) -> Path:
    configured = Path(str(load_config()["storage"]["root"])).expanduser()
    root = configured if configured.is_absolute() else config_dir() / configured
    return root.joinpath(*parts)


def _seed_default_commands() -> None:
    root = user_commands_dir()
    for name in DEFAULT_COMMAND_NAMES:
        destination = root / name / "main.py"
        if destination.exists() and not is_replaceable_command_source(
            destination.read_text(encoding="utf-8"), name
        ):
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(command_source(name), encoding="utf-8")


def _ensure_storage_layout() -> None:
    configured: object = DEFAULT_CONFIG["storage"]["root"]
    try:
        with config_file().open("rb") as handle:
            user_config = tomllib.load(handle)
        configured = user_config.get("storage", {}).get("root", configured)
    except (AttributeError, OSError, tomllib.TOMLDecodeError):
        pass
    configured_path = Path(configured).expanduser() if isinstance(configured, str) else Path("data")
    root = configured_path if configured_path.is_absolute() else config_dir() / configured_path
    for parts in STORAGE_SUBDIRECTORIES:
        root.joinpath(*parts).mkdir(parents=True, exist_ok=True)


def ensure_layout() -> Path:
    root = config_dir()
    user_commands_dir().mkdir(parents=True, exist_ok=True)
    for name in TEMPLATE_NAMES:
        (templates_dir() / name).mkdir(parents=True, exist_ok=True)
    path = config_file()
    if not path.exists():
        write_config(copy.deepcopy(DEFAULT_CONFIG))
    _seed_default_commands()
    _ensure_storage_layout()
    return root


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _get_from(config: dict[str, Any], dotted: str) -> Any:
    value: Any = config
    for part in dotted.split("."):
        if not part or not isinstance(value, dict) or part not in value:
            raise ConfigError(f"Unknown configuration key: {dotted}")
        value = value[part]
    return value


def _expect(
    config: dict[str, Any],
    dotted: str,
    kind: type | tuple[type, ...],
    *,
    choices: set[Any] | None = None,
) -> None:
    value = _get_from(config, dotted)
    numeric = kind is int or (isinstance(kind, tuple) and int in kind)
    if not isinstance(value, kind) or (numeric and isinstance(value, bool)):
        expected = " or ".join(item.__name__ for item in kind) if isinstance(kind, tuple) else kind.__name__
        raise ConfigError(f"Invalid {dotted}: expected {expected}")
    if choices is not None and value not in choices:
        expected = ", ".join(map(str, sorted(choices)))
        raise ConfigError(f"Invalid {dotted}: expected one of {expected}")


def validate_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    checks = (
        ("core.color", bool, None),
        ("core.verbose", bool, None),
        ("core.command_timeout", int, None),
        ("core.show_timing", bool, None),
        ("storage.root", str, None),
        ("git.auto_push", bool, None),
        ("projects.python.environment", str, {"auto", "uv", "venv", "none"}),
        ("projects.python.initialize_git", bool, None),
        ("projects.rust.initialize_git", bool, None),
        ("projects.cpp.standard", int, {11, 14, 17, 20, 23, 26}),
        ("projects.cpp.initialize_git", bool, None),
        ("mac.executable", str, None),
        ("mac.timeout", int, None),
        ("todo.vault_path", str, None),
        ("todo.file", str, None),
        ("todo.completed_column", str, None),
        ("capture.camera_device", str, None),
        ("capture.audio_device", str, None),
        ("capture.screen_audio", bool, None),
        ("capture.show_clicks", bool, None),
        ("games.difficulty", str, {"easy", "normal", "hard"}),
        ("apps.spotify", str, None),
        ("apps.editor", str, None),
        ("apps.spotify_autoplay_delay", (int, float), None),
        ("apps.browser_url", str, None),
        ("apps.lofi_url", str, None),
        ("apps.youtube_url", str, None),
        ("telegram.chat_id", str, None),
        ("telegram.api_base", str, None),
        ("telegram.keychain_service", str, None),
        ("lm.base_url", str, None),
        ("lm.model", str, None),
        ("lm.system_prompt", str, None),
        ("lm.temperature", (int, float), None),
        ("lm.timeout", int, None),
    )
    for dotted, kind, choices in checks:
        try:
            _expect(config, dotted, kind, choices=choices)
        except ConfigError as error:
            errors.append(str(error))
    for dotted in ("core.command_timeout", "mac.timeout", "lm.timeout"):
        try:
            value = _get_from(config, dotted)
            if isinstance(value, int) and value < 0:
                errors.append(f"Invalid {dotted}: must be zero or greater")
        except ConfigError:
            pass
    try:
        temperature = _get_from(config, "lm.temperature")
        if (
            isinstance(temperature, (int, float))
            and not isinstance(temperature, bool)
            and not 0 <= temperature <= 2
        ):
            errors.append("Invalid lm.temperature: must be between 0 and 2")
    except ConfigError:
        pass
    try:
        parsed = urllib.parse.urlparse(_get_from(config, "lm.base_url"))
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            errors.append("Invalid lm.base_url: LM Studio must use localhost")
    except (ConfigError, TypeError):
        pass
    try:
        delay = _get_from(config, "apps.spotify_autoplay_delay")
        if isinstance(delay, (int, float)) and not isinstance(delay, bool) and delay < 0:
            errors.append("Invalid apps.spotify_autoplay_delay: must be zero or greater")
    except ConfigError:
        pass
    aliases = config.get("aliases")
    if not isinstance(aliases, dict):
        errors.append("Invalid aliases: expected table")
    else:
        for name, tokens in aliases.items():
            if not BARE_KEY.fullmatch(name) or not isinstance(tokens, list) or not tokens or not all(
                isinstance(token, str) and token for token in tokens
            ):
                errors.append(f"Invalid aliases.{name}: expected a non-empty array of strings")
    return errors


def load_config() -> dict[str, Any]:
    ensure_layout()
    try:
        with config_file().open("rb") as handle:
            user_config = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Could not read {config_file()}: {error}") from error
    config = _deep_merge(DEFAULT_CONFIG, user_config)
    errors = validate_config(config)
    if errors:
        raise ConfigError("; ".join(errors))
    return config


def materialize_config() -> bool:
    """Write merged defaults and remove superseded per-feature storage paths."""
    config = load_config()
    config.get("capture", {}).pop("screenshot_dir", None)
    config.get("capture", {}).pop("recording_dir", None)
    config.get("telegram", {}).pop("download_dir", None)
    rendered = serialize_config(config)
    current = config_file().read_text(encoding="utf-8")
    if current == rendered:
        return False
    write_config(config)
    return True


def _toml_key(key: str) -> str:
    return key if BARE_KEY.fullmatch(key) else json.dumps(key, ensure_ascii=False)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise ConfigError(f"Unsupported configuration value: {value!r}")


def _serialize_table(table: dict[str, Any], path: tuple[str, ...], lines: list[str]) -> None:
    scalars = [(key, value) for key, value in table.items() if not isinstance(value, dict)]
    children = [(key, value) for key, value in table.items() if isinstance(value, dict)]
    if path:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append("[" + ".".join(_toml_key(part) for part in path) + "]")
    for key, value in scalars:
        lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    for key, value in children:
        _serialize_table(value, (*path, key), lines)


def serialize_config(config: dict[str, Any]) -> str:
    lines: list[str] = []
    _serialize_table(config, (), lines)
    return "\n".join(lines).lstrip("\n") + "\n"


def write_config(config: dict[str, Any]) -> None:
    errors = validate_config(config)
    if errors:
        raise ConfigError("; ".join(errors))
    root = config_dir()
    root.mkdir(parents=True, exist_ok=True)
    text = serialize_config(config)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=root, prefix=".config.", suffix=".tmp", delete=False
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, config_file())
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def get_config_value(dotted: str) -> Any:
    return _get_from(load_config(), dotted)


def set_config_value(dotted: str, new_value: Any) -> None:
    if not dotted or any(not part for part in dotted.split(".")):
        raise ConfigError(f"Invalid configuration key: {dotted!r}")
    config = load_config()
    parts = dotted.split(".")
    table: dict[str, Any] = config
    for part in parts[:-1]:
        value = table.get(part)
        if value is None:
            value = {}
            table[part] = value
        if not isinstance(value, dict):
            raise ConfigError(f"Configuration key is not a table: {part}")
        table = value
    table[parts[-1]] = new_value
    write_config(config)
