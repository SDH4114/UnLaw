from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from .command_sources import command_source, is_replaceable_command_source
from .features import NAMES as OPTIONAL_FEATURES
from .features import resolve as resolve_features

DEFAULT_CONFIG: dict[str, Any] = {
    "core": {
        "color": True,
        "verbose": False,
        "command_timeout": 0,
        "show_timing": False,
        "python": "auto",
        "editor": "auto",
        "features": ["all"],
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
    "zip": {"format": "zip", "level": "max", "keep_junk": False},
    "yt": {"podcast_dir": "~/Library/Mobile Documents/com~apple~CloudDocs/Podcasts"},
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
        "model": "auto",
        "embedding_model": "auto",
        "stt_model": "auto",
        "tts_model": "auto",
        "image_model": "auto",
        "video_model": "auto",
        "music_model": "auto",
        "port": 1234,
        "idle_minutes": 10,
        "system_prompt": "You are a concise and practical local assistant.",
        "temperature": 0.7,
        "max_tokens": 4096,
    },
    "agent": {
        "model": "auto",
        "roots": ["~"],
        "allowed_ids": [],
        "commands": ["todo", "capture", "music", "yt", "zip", "tg"],
        "max_steps": 12,
        "confirm_timeout": 300,
        "digest_time": "",
        "system_prompt": "",
        "users": {},
    },
}

TEMPLATE_NAMES = ("commands", "python", "rust", "cpp", "projects")
DEFAULT_COMMAND_NAMES = (
    "agent",
    "capture",
    "cpp",
    "git",
    "gpt",
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
TELEGRAM_ID = re.compile(r"^-?[0-9]+$")
CLOCK = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
AGENT_LEVELS = ("chat", "read", "full")


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


def _configured_selection() -> list[str] | None:
    """The chosen features, or None when config.toml cannot be read or is invalid."""
    try:
        with config_file().open("rb") as handle:
            config = _deep_merge(DEFAULT_CONFIG, tomllib.load(handle))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return None if validate_config(config) else selected_features(config)


def _seed_default_commands() -> None:
    """Seed chosen features and remove untouched seeds of the others; mirrors rust/src/layout.rs."""
    root = user_commands_dir()
    selection = _configured_selection()
    for name in DEFAULT_COMMAND_NAMES:
        destination = root / name / "main.py"
        if destination.parent.is_symlink() or destination.is_symlink():
            continue
        try:
            existing = destination.read_text(encoding="utf-8")
        except FileNotFoundError:
            existing = None
        except (OSError, UnicodeError):
            continue
        if selection is not None and name not in selection:
            if existing is not None and is_replaceable_command_source(existing, name):
                destination.unlink()
                (destination.parent / ".DS_Store").unlink(missing_ok=True)
                shutil.rmtree(destination.parent / "__pycache__", ignore_errors=True)
                try:
                    destination.parent.rmdir()
                except OSError:
                    pass
            continue
        if selection is None and not destination.parent.exists():
            continue
        if existing is not None:
            if not is_replaceable_command_source(existing, name):
                continue
        elif any((destination.parent / entry).exists() for entry in ("main.sh", "main.js", "Cargo.toml", "main")):
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


def _feature_errors(features: Any) -> list[str]:
    """Rules for core.features; mirrored in rust/src/features.rs (`config_errors`)."""
    message = "Invalid core.features: expected an array of feature names"
    if not isinstance(features, list) or not all(isinstance(item, str) for item in features):
        return [message]
    return [f"Unknown feature in core.features: {name}" for name in features if name != "all" and name not in OPTIONAL_FEATURES]


def selected_features(config: dict[str, Any]) -> list[str]:
    """`core.features` with "all" expanded and requirements added, like the Rust core."""
    names = config.get("core", {}).get("features", ["all"])
    return resolve_features(names if isinstance(names, list) else ["all"])


def _agent_errors(agent: Any) -> list[str]:
    """Rules for list and table keys of [agent]; mirrored in rust/src/config.rs."""
    if not isinstance(agent, dict):
        return ["Invalid agent: expected table"]
    errors: list[str] = []

    def strings(key: str, message: str, valid: Any = lambda item: isinstance(item, str) and bool(item)) -> None:
        items = agent.get(key)
        if not isinstance(items, list) or not all(valid(item) for item in items):
            errors.append(f"Invalid agent.{key}: {message}")

    def telegram_id(item: Any) -> bool:
        if isinstance(item, bool):
            return False
        return isinstance(item, int) or (isinstance(item, str) and bool(TELEGRAM_ID.fullmatch(item)))

    strings("roots", "expected an array of non-empty strings")
    strings("allowed_ids", "expected an array of Telegram ids", telegram_id)
    strings("commands", "expected an array of command names")
    steps = agent.get("max_steps")
    if isinstance(steps, int) and not isinstance(steps, bool) and not 1 <= steps <= 100:
        errors.append("Invalid agent.max_steps: must be between 1 and 100")
    timeout = agent.get("confirm_timeout")
    if isinstance(timeout, int) and not isinstance(timeout, bool) and timeout < 1:
        errors.append("Invalid agent.confirm_timeout: must be greater than zero")
    digest = agent.get("digest_time")
    if isinstance(digest, str) and digest and not CLOCK.fullmatch(digest):
        errors.append("Invalid agent.digest_time: expected HH:MM or an empty string")
    users = agent.get("users")
    if not isinstance(users, dict):
        errors.append("Invalid agent.users: expected table")
    else:
        for user, level in users.items():
            if not TELEGRAM_ID.fullmatch(user) or level not in AGENT_LEVELS:
                errors.append(f'Invalid agent.users.{user}: expected "chat", "read" or "full"')
    return errors


def validate_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    checks = (
        ("core.color", bool, None),
        ("core.verbose", bool, None),
        ("core.command_timeout", int, None),
        ("core.show_timing", bool, None),
        ("core.python", str, None),
        ("core.editor", str, None),
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
        ("zip.format", str, {"zip", "7z", "rar", "tar.zst", "tar.xz", "tar.gz"}),
        ("zip.keep_junk", bool, None),
        ("yt.podcast_dir", str, None),
        ("apps.spotify", str, None),
        ("apps.editor", str, None),
        ("apps.spotify_autoplay_delay", (int, float), None),
        ("apps.browser_url", str, None),
        ("apps.lofi_url", str, None),
        ("apps.youtube_url", str, None),
        ("telegram.chat_id", str, None),
        ("telegram.api_base", str, None),
        ("telegram.keychain_service", str, None),
        ("lm.model", str, None),
        ("lm.embedding_model", str, None),
        ("lm.stt_model", str, None),
        ("lm.tts_model", str, None),
        ("lm.image_model", str, None),
        ("lm.video_model", str, None),
        ("lm.music_model", str, None),
        ("lm.port", int, None),
        ("lm.idle_minutes", int, None),
        ("lm.system_prompt", str, None),
        ("lm.temperature", (int, float), None),
        ("lm.max_tokens", int, None),
        ("agent.model", str, None),
        ("agent.max_steps", int, None),
        ("agent.confirm_timeout", int, None),
        ("agent.digest_time", str, None),
        ("agent.system_prompt", str, None),
    )
    for dotted, kind, choices in checks:
        try:
            _expect(config, dotted, kind, choices=choices)
        except ConfigError as error:
            errors.append(str(error))
    for dotted in ("core.command_timeout", "mac.timeout", "lm.idle_minutes"):
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
        port = _get_from(config, "lm.port")
        if isinstance(port, int) and not isinstance(port, bool) and not 1 <= port <= 65535:
            errors.append("Invalid lm.port: must be between 1 and 65535")
    except ConfigError:
        pass
    try:
        tokens = _get_from(config, "lm.max_tokens")
        if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens < 1:
            errors.append("Invalid lm.max_tokens: must be greater than zero")
    except ConfigError:
        pass
    try:
        delay = _get_from(config, "apps.spotify_autoplay_delay")
        if isinstance(delay, (int, float)) and not isinstance(delay, bool) and delay < 0:
            errors.append("Invalid apps.spotify_autoplay_delay: must be zero or greater")
    except ConfigError:
        pass
    try:
        level = _get_from(config, "zip.level")
        names = {"store", "fastest", "fast", "normal", "max", "ultra"}
        if not (
            (isinstance(level, int) and not isinstance(level, bool) and 0 <= level <= 9)
            or (isinstance(level, str) and level in names)
        ):
            errors.append("Invalid zip.level: expected 0-9 or store, fastest, fast, normal, max, ultra")
    except ConfigError as error:
        errors.append(str(error))
    core = config.get("core")
    errors.extend(_feature_errors(core.get("features") if isinstance(core, dict) else None))
    errors.extend(_agent_errors(config.get("agent")))
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
    config.get("lm", {}).pop("base_url", None)
    config.get("lm", {}).pop("timeout", None)
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
