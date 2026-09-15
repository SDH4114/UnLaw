from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from typing import Any

from .config import ConfigError, load_config


def _server_command(action: str) -> int | None:
    executable = shutil.which("lms")
    if executable is None:
        return None
    return subprocess.run([executable, "server", action], check=False).returncode


def _start_and_retry(operation: Any) -> Any:
    if _server_command("start") != 0:
        raise OSError("LM Studio server could not be started through `lms`")
    time.sleep(0.5)
    return operation()


def _ensure_server(settings: dict[str, object]) -> None:
    url = f"{str(settings['base_url']).rstrip('/')}/models"
    timeout = min(int(settings["timeout"]), 3)
    try:
        json_request(url, None, timeout)
    except (OSError, urllib.error.URLError):
        if _server_command("start") != 0:
            raise OSError("LM Studio server could not be started through `lms`") from None
        time.sleep(0.5)
        json_request(url, None, timeout)


def _local_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("LM Studio URL must point to localhost")
    return base_url.rstrip("/")


def json_request(url: str, payload: dict[str, object] | None, timeout: int) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if data is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _model(base_url: str, configured: str, timeout: int) -> str:
    if configured != "auto":
        return configured
    payload = json_request(f"{base_url}/models", None, timeout)
    models = payload.get("data", [])
    if not models:
        raise RuntimeError("LM Studio has no loaded local model")
    return str(models[0]["id"])


def complete(
    messages: list[dict[str, str]],
    *,
    base_url: str,
    model: str,
    temperature: float,
    timeout: int,
) -> str:
    base_url = _local_base_url(base_url)
    selected = _model(base_url, model, timeout)
    response = json_request(
        f"{base_url}/chat/completions",
        {"model": selected, "messages": messages, "temperature": temperature, "stream": False},
        timeout,
    )
    try:
        return str(response["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("LM Studio returned an invalid chat response") from error


def ask(
    prompt: str,
    *,
    base_url: str,
    model: str,
    system_prompt: str,
    temperature: float,
    timeout: int,
) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    return complete(
        messages,
        base_url=base_url,
        model=model,
        temperature=temperature,
        timeout=timeout,
    )


def _interactive(settings: dict[str, object]) -> int:
    print("Unlaw × LM Studio — local chat. /exit to quit, /clear to reset.")
    messages: list[dict[str, str]] = []
    system_prompt = str(settings["system_prompt"])
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    while True:
        try:
            prompt = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not prompt:
            continue
        if prompt in {"/exit", "/quit"}:
            return 0
        if prompt == "/clear":
            messages = ([{"role": "system", "content": system_prompt}] if system_prompt else [])
            print("Context cleared.")
            continue
        messages.append({"role": "user", "content": prompt})
        answer = complete(
            messages,
            base_url=str(settings["base_url"]),
            model=str(settings["model"]),
            temperature=float(settings["temperature"]),
            timeout=int(settings["timeout"]),
        )
        messages.append({"role": "assistant", "content": answer})
        print(f"lm> {answer}")


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        settings = load_config()["lm"]
        _local_base_url(str(settings["base_url"]))
        if len(args) == 1 and args[0] in {"start", "stop", "status"}:
            result = _server_command(args[0])
            if result is None:
                raise OSError("LM Studio CLI `lms` was not found")
            return result
        if args == ["open"]:
            return subprocess.run(["open", "-a", "LM Studio"], check=False).returncode
        if args == ["models"]:
            payload = json_request(f"{str(settings['base_url']).rstrip('/')}/models", None, int(settings["timeout"]))
            for model in payload.get("data", []):
                print(model.get("id", "unknown"))
            return 0
        if args:
            prompt = " ".join(args)
            operation = lambda: ask(
                    prompt,
                    base_url=str(settings["base_url"]),
                    model=str(settings["model"]),
                    system_prompt=str(settings["system_prompt"]),
                    temperature=float(settings["temperature"]),
                    timeout=int(settings["timeout"]),
                )
            try:
                answer = operation()
            except (OSError, urllib.error.URLError):
                answer = _start_and_retry(operation)
            print(answer)
            return 0
        if not sys.stdin.isatty():
            prompt = sys.stdin.read().strip()
            if prompt:
                return main([prompt])
        _ensure_server(settings)
        return _interactive(settings)
    except (ConfigError, RuntimeError, OSError, ValueError, urllib.error.URLError) as error:
        subprocess.run(["open", "-a", "LM Studio"], check=False)
        print(
            f"unlaw lm: cannot reach the LM Studio local server: {error}. "
            "Load a model and start Local Server in LM Studio.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
