from __future__ import annotations

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

from .config import ConfigError, load_config, set_config_value, storage_path

USAGE = """Usage: ul tg <message>|send <message-or-file>|photo <file>|video <file>|file <path>|capture
       ul tg setup|status|last|download [directory]

The bot token is stored in macOS Keychain, never in config.toml.
"""


def _settings() -> dict[str, str]:
    return load_config()["telegram"]


def read_token() -> str:
    service = _settings()["keychain_service"]
    result = subprocess.run(
        ["security", "find-generic-password", "-a", "unlaw", "-s", service, "-w"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("Telegram token is not configured; run `ul tg setup`.")
    return result.stdout.strip()


def store_token(token: str) -> None:
    service = _settings()["keychain_service"]
    result = subprocess.run(
        ["security", "add-generic-password", "-a", "unlaw", "-s", service, "-w", token, "-U"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "could not write macOS Keychain").strip())


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
    store_token(token)
    client = TelegramClient(token, _settings()["api_base"])
    result = client.request("getMe", {})
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
    downloaded = 0
    for update in updates:
        message = update.get("message") or update.get("channel_post") or {}
        for filename, file_id in _file_descriptors(message):
            info = client.request("getFile", {"file_id": file_id})["result"]["file_path"]
            target = destination / Path(info).name
            client.download(info, target)
            print(target)
            downloaded += 1
    if not downloaded:
        print("No downloadable files in recent messages.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args == ["setup"]:
            return _setup()
        if not args and sys.stdin.isatty():
            print(USAGE, end="")
            return 2
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
            from .capture import latest_capture

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
