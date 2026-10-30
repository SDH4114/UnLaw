# Unlaw command source. Edit freely: this file has no runtime dependency on Unlaw.
"""Open Telegram, or send and download messages/files through your bot."""
from __future__ import annotations

COMMAND_HELP = 'Open Telegram, or send and download messages/files through your bot.\nUsage:\n  ul tg                                  Open Telegram\n  ul tg <message>|send <message-or-file>   Send text or a file\n  ul tg photo|video|file <path>            Send a file with an explicit type\n  ul tg capture                          Send the latest capture\n  ul tg setup                            Configure bot token and chat ID\n  ul tg status                           Check bot configuration\n  ul tg last                             Print recent bot updates\n  ul tg download [directory]              Download files from recent updates\nToken: the macOS Keychain (service telegram.keychain_service); if it has none, a\nTELEGRAM_BOT_TOKEN= line in .env next to config.toml is used. Default downloads:\nstorage.root/telegram/downloads.\nExample: ul tg send "Hello"\n'

import copy
import os
import tomllib
from pathlib import Path


DEFAULT_CONFIG = {'storage': {'root': 'data'},
 'telegram': {'chat_id': '',
              'api_base': 'https://api.telegram.org',
              'keychain_service': 'unlaw.telegram'}}


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

def storage_path(*parts: str) -> Path:
    configured = Path(str(load_config()["storage"]["root"])).expanduser()
    root = configured if configured.is_absolute() else config_dir() / configured
    return root.joinpath(*parts)

import json
import tempfile


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise ConfigError(f"Unsupported configuration value: {value!r}")


def _serialize_table(table: dict, path: tuple[str, ...], lines: list[str]) -> None:
    if path:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append("[" + ".".join(path) + "]")
    for key, value in table.items():
        if not isinstance(value, dict):
            lines.append(f"{key} = {_toml_value(value)}")
    for key, value in table.items():
        if isinstance(value, dict):
            _serialize_table(value, (*path, key), lines)


def set_config_value(dotted: str, value: object) -> None:
    config = load_config()
    parts = dotted.split(".")
    table = config
    for part in parts[:-1]:
        table = table.setdefault(part, {})
        if not isinstance(table, dict):
            raise ConfigError(f"Configuration key is not a table: {part}")
    table[parts[-1]] = value
    lines: list[str] = []
    _serialize_table(config, (), lines)
    root = config_dir()
    root.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, delete=False) as handle:
            handle.write("\n".join(lines).lstrip("\n") + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, root / "config.toml")
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

def latest_capture() -> Path | None:
    candidates = [
        path
        for directory in (
            storage_path("captures", "screenshots"),
            storage_path("captures", "recordings"),
        )
        if directory.is_dir()
        for path in directory.iterdir()
        if path.is_file()
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)

import getpass
import json
import mimetypes
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any


USAGE = """Usage: ul tg                              Open Telegram
       ul tg <message>|send <message-or-file>|photo <file>|video <file>|file <path>|capture
       ul tg setup|status|last|download [directory]

The bot token is stored in the macOS Keychain (a .env next to config.toml also works), never in config.toml.
"""


def _settings() -> dict[str, str]:
    return load_config()["telegram"]


TOKEN_KEY = "TELEGRAM_BOT_TOKEN"


def env_file() -> Path:
    return config_dir() / ".env"


def _env_token() -> str:
    """Optional: a `TELEGRAM_BOT_TOKEN=` line in .env next to config.toml, for those who prefer a file."""
    try:
        lines = env_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        key, _, value = line.partition("=")
        if key.strip() == TOKEN_KEY and value.strip().strip("'\""):
            return value.strip().strip("'\"")
    return ""


def _keychain_token(service: str) -> str:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", "unlaw", "-s", service, "-w"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def stored_token(keychain_service: str) -> str:
    """The macOS Keychain first; .env only when the Keychain has no token."""
    return _keychain_token(keychain_service) or _env_token()


def store_token(token: str, keychain_service: str) -> None:
    """Save to the Keychain and drop a .env copy, so only one token is ever in use."""
    token = token.strip()
    if not token or any(character.isspace() for character in token):
        raise ValueError("the token must be one word without spaces")
    result = subprocess.run(
        ["security", "add-generic-password", "-a", "unlaw", "-s", keychain_service, "-w", token, "-U"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "could not write the macOS Keychain").strip())
    path = env_file()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    kept = [line for line in lines if line.partition("=")[0].strip() != TOKEN_KEY]
    if len(kept) == len(lines):
        return
    if any(line.strip() for line in kept):
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    else:
        path.unlink()


def read_token() -> str:
    token = stored_token(_settings()["keychain_service"])
    if not token:
        raise RuntimeError("Telegram token is not configured; run `ul tg setup`.")
    return token


def classify_file(path: Path) -> tuple[str, str]:
    suffix = path.suffix.casefold()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic"}:
        return "sendPhoto", "photo"
    if suffix in {".mp4", ".mov", ".m4v", ".webm"}:
        return "sendVideo", "video"
    if suffix in {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"}:
        return "sendAudio", "audio"
    return "sendDocument", "document"


def encode_multipart(
    fields: dict[str, str],
    file_field: str,
    filename: str,
    content: bytes,
    *,
    boundary: str | None = None,
) -> tuple[bytes, str]:
    boundary = boundary or f"unlaw-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    safe_name = Path(filename).name.replace('"', "_")
    mime = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{safe_name}"\r\n'.encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


class TelegramClient:
    def __init__(self, token: str, api_base: str, *, timeout: int = 60) -> None:
        self.token = token
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout

    def request(
        self,
        method: str,
        fields: dict[str, str],
        file: tuple[str, Path] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.api_base}/bot{self.token}/{method}"
        headers: dict[str, str] = {}
        if file is None:
            data = urllib.parse.urlencode(fields).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            field, path = file
            data, content_type = encode_multipart(fields, field, path.name, path.read_bytes())
            headers["Content-Type"] = content_type
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description", "Telegram API error"))
        return payload

    def download(self, telegram_path: str, destination: Path) -> Path:
        url = f"{self.api_base}/file/bot{self.token}/{telegram_path}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=self.timeout) as response:
            destination.write_bytes(response.read())
        return destination


def _client() -> tuple[TelegramClient, dict[str, str]]:
    settings = _settings()
    return TelegramClient(read_token(), settings["api_base"]), settings


def discover_chat_id(client: TelegramClient) -> str:
    updates = client.request("getUpdates", {"limit": "20", "timeout": "0"}).get("result", [])
    for update in reversed(updates):
        message = update.get("message") or update.get("channel_post") or {}
        chat_id = message.get("chat", {}).get("id")
        if chat_id is not None:
            return str(chat_id)
    raise RuntimeError("send a message to the bot first, then run `ul tg setup` again")


def _setup() -> int:
    token = getpass.getpass("Telegram bot token: ").strip()
    if not token:
        raise ValueError("token cannot be empty")
    chat_id = input("Default chat ID (leave empty to discover): ").strip()
    client = TelegramClient(token, _settings()["api_base"])
    result = client.request("getMe", {})
    store_token(token, _settings()["keychain_service"])
    chat_id = chat_id or discover_chat_id(client)
    set_config_value("telegram.chat_id", chat_id)
    username = result.get("result", {}).get("username", "unknown")
    print(f"Telegram connected: @{username}")
    return 0


def _send_file(client: TelegramClient, chat_id: str, path: Path, forced: str | None = None) -> int:
    if not path.is_file():
        raise FileNotFoundError(path)
    if forced:
        mapping = {
            "photo": ("sendPhoto", "photo"),
            "video": ("sendVideo", "video"),
            "file": ("sendDocument", "document"),
        }
        method, field = mapping[forced]
    else:
        method, field = classify_file(path)
    response = client.request(method, {"chat_id": chat_id}, (field, path))
    message_id = response.get("result", {}).get("message_id", "?")
    print(f"Sent {path.name} (message {message_id})")
    return 0


def _file_descriptors(message: dict[str, Any]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if message.get("document"):
        item = message["document"]
        result.append((item.get("file_name", "document"), item["file_id"]))
    for field, default in (("video", "video.mp4"), ("audio", "audio.mp3"), ("voice", "voice.ogg")):
        if message.get(field):
            item = message[field]
            result.append((item.get("file_name", default), item["file_id"]))
    if message.get("photo"):
        result.append(("photo.jpg", message["photo"][-1]["file_id"]))
    return result


def _unique(path: Path) -> Path:
    """`name 2.ext`, `name 3.ext`, ... so an existing file is never replaced."""
    candidate, number = path, 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} {number}{path.suffix}")
        number += 1
    return candidate


def _last(client: TelegramClient) -> int:
    updates = client.request("getUpdates", {"limit": "10", "timeout": "0"}).get("result", [])
    if not updates:
        print("No Telegram messages.")
        return 0
    for update in updates:
        message = update.get("message") or update.get("channel_post") or {}
        sender = message.get("from", {}).get("username") or message.get("chat", {}).get("title") or "unknown"
        text = message.get("text") or message.get("caption") or "[file]"
        print(f"{sender}: {text}")
    return 0


def _download(client: TelegramClient, destination: Path) -> int:
    updates = client.request("getUpdates", {"limit": "25", "timeout": "0"}).get("result", [])
    downloaded = skipped = 0
    for update in updates:
        message = update.get("message") or update.get("channel_post") or {}
        for filename, file_id in _file_descriptors(message):
            result = client.request("getFile", {"file_id": file_id})["result"]
            info = result["file_path"]
            # The sender's file name, not Telegram's internal one (file_12.jpg).
            name = Path(filename).name if filename not in {"document", "photo.jpg", "video.mp4", "audio.mp3", "voice.ogg"} else Path(info).name
            target = destination / (name or Path(info).name)
            size = result.get("file_size")
            if target.exists() and size is not None and target.stat().st_size == size:
                skipped += 1
                continue
            target = _unique(target)
            client.download(info, target)
            print(target)
            downloaded += 1
    if skipped:
        print(f"Already downloaded: {skipped} file(s).")
    if not downloaded and not skipped:
        print("No downloadable files in recent messages.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP, end="")
        return 0
    try:
        if args == ["setup"]:
            return _setup()
        if not args and sys.stdin.isatty():
            return subprocess.run(["open", "-a", "Telegram"], check=False).returncode
        client, settings = _client()
        chat_id = settings["chat_id"]
        if args == ["status"]:
            result = client.request("getMe", {})["result"]
            print(f"@{result.get('username', 'unknown')}  chat={chat_id or 'not set'}")
            return 0
        if args == ["last"]:
            return _last(client)
        if args and args[0] == "download" and len(args) <= 2:
            destination = Path(args[1]).expanduser() if len(args) == 2 else storage_path("telegram", "downloads")
            return _download(client, destination)
        if not chat_id:
            chat_id = discover_chat_id(client)
            set_config_value("telegram.chat_id", chat_id)
        if args == ["capture"]:

            latest = latest_capture()
            if latest is None:
                raise FileNotFoundError("no Unlaw captures found")
            return _send_file(client, chat_id, latest)
        if args and args[0] in {"photo", "video", "file"} and len(args) == 2:
            return _send_file(client, chat_id, Path(args[1]).expanduser(), args[0])
        if args and args[0] == "send":
            args = args[1:]
        if len(args) == 1 and Path(args[0]).expanduser().is_file():
            return _send_file(client, chat_id, Path(args[0]).expanduser())
        text = " ".join(args).strip() if args else sys.stdin.read().strip()
        if not text:
            raise ValueError("message cannot be empty")
        response = client.request("sendMessage", {"chat_id": chat_id, "text": text})
        print(f"Sent message {response.get('result', {}).get('message_id', '?')}")
        return 0
    except (ConfigError, FileNotFoundError, RuntimeError, OSError, ValueError, urllib.error.URLError) as error:
        print(f"unlaw tg: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
