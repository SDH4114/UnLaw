"""Telegram, LM Studio and macOS Harness against local fake services (no network, no Keychain)."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from unlawful import harness, lmstudio, telegram  # noqa: E402
from unlawful.built_in_commands.app import main as app_command  # noqa: E402
from unlawful.built_in_commands.mac import main as mac_command  # noqa: E402
from unlawful.config import ensure_layout, set_config_value  # noqa: E402


class FakeServer:
    """Serves canned JSON per path and records every request."""

    def __init__(self) -> None:
        self.routes: dict[str, object] = {}
        self.requests: list[dict[str, object]] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def _reply(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                server.requests.append(
                    {"method": self.command, "path": self.path, "type": self.headers.get("Content-Type"), "body": body}
                )
                route = server.routes.get(self.path)
                if route is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                data = route if isinstance(route, bytes) else json.dumps(route).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = _reply

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def form(self, index: int = -1) -> dict[str, str]:
        return dict(urllib.parse.parse_qsl(self.requests[index]["body"].decode()))  # type: ignore[union-attr]


class ServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        environment = patch.dict(
            os.environ,
            {
                "XDG_CONFIG_HOME": str(self.root / "config"),
                "PATH": f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        ensure_layout()
        self.server = FakeServer()
        self.addCleanup(self.server.close)
        self.open_log = self.tool_log("open")

    def tool(self, name: str, body: str) -> Path:
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        path.chmod(0o755)
        return path

    def tool_log(self, name: str, *, exit_code: int = 0, stdout: str = "") -> Path:
        log = self.root / f"{name}.log"
        self.tool(
            name,
            "import sys\n"
            f"open({str(log)!r}, 'a').write('|'.join(sys.argv[1:]) + '\\n')\n"
            f"sys.stdout.write({stdout!r})\n"
            f"raise SystemExit({exit_code})\n",
        )
        return log

    def lines(self, log: Path) -> list[str]:
        return log.read_text().splitlines() if log.exists() else []

    def run_main(self, main, args: list[str], stdin: str | None = None) -> tuple[int, str, str]:
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            if stdin is None:
                code = main(args)
            else:
                with patch.object(sys, "stdin", io.StringIO(stdin)):
                    code = main(args)
        return code, out.getvalue(), err.getvalue()


class TelegramTests(ServiceTestCase):
    TOKEN = "123:secret"

    def setUp(self) -> None:
        super().setUp()
        set_config_value("telegram.api_base", self.server.url)
        set_config_value("telegram.chat_id", "42")
        self.keychain = self.root / "keychain.txt"
        # `security` stand-in: find prints the stored token, add stores it.
        self.tool(
            "security",
            "import sys, pathlib\n"
            f"store = pathlib.Path({str(self.keychain)!r})\n"
            "args = sys.argv[1:]\n"
            "if args[0] == 'add-generic-password':\n"
            "    store.write_text(args[args.index('-w') + 1]); raise SystemExit(0)\n"
            "if store.exists(): print(store.read_text()); raise SystemExit(0)\n"
            "sys.stderr.write('not found'); raise SystemExit(44)\n",
        )
        self.keychain.write_text(self.TOKEN)
        self.api = f"/bot{self.TOKEN}"

    def test_text_message_is_posted_as_a_form(self) -> None:
        self.server.routes[f"{self.api}/sendMessage"] = {"ok": True, "result": {"message_id": 7}}
        code, out, _ = self.run_main(telegram.main, ["send", "hello", "world"])
        self.assertEqual((code, out), (0, "Sent message 7\n"))
        self.assertEqual(self.server.requests[-1]["type"], "application/x-www-form-urlencoded")
        self.assertEqual(self.server.form(), {"chat_id": "42", "text": "hello world"})

    def test_message_from_stdin_and_empty_message(self) -> None:
        self.server.routes[f"{self.api}/sendMessage"] = {"ok": True, "result": {"message_id": 8}}
        self.assertEqual(self.run_main(telegram.main, [], stdin="piped text\n")[0], 0)
        self.assertEqual(self.server.form()["text"], "piped text")
        code, _, error = self.run_main(telegram.main, [], stdin="   ")
        self.assertEqual(code, 1)
        self.assertIn("message cannot be empty", error)

    def test_files_are_uploaded_as_multipart_with_detected_or_forced_type(self) -> None:
        for method in ("sendPhoto", "sendVideo", "sendAudio", "sendDocument"):
            self.server.routes[f"{self.api}/{method}"] = {"ok": True, "result": {"message_id": 1}}
        cases = [
            (["shot.png"], "sendPhoto", 'name="photo"'),
            (["song.mp3"], "sendAudio", 'name="audio"'),
            (["video", "clip.bin"], "sendVideo", 'name="video"'),
            (["file", "shot.png"], "sendDocument", 'name="document"'),
            (["photo", "clip.bin"], "sendPhoto", 'name="photo"'),
        ]
        for args, method, field in cases:
            with self.subTest(args=args):
                path = self.root / args[-1]
                path.write_bytes(b"payload-" + path.name.encode())
                code, out, error = self.run_main(telegram.main, [*args[:-1], str(path)])
                self.assertEqual(code, 0, error)
                request = self.server.requests[-1]
                self.assertTrue(str(request["path"]).endswith(method))
                self.assertTrue(str(request["type"]).startswith("multipart/form-data; boundary=unlaw-"))
                self.assertIn(field.encode(), request["body"])
                self.assertIn(b"payload-" + path.name.encode(), request["body"])
                self.assertIn(f"Sent {path.name}", out)

    def test_missing_file_for_forced_type_is_an_error(self) -> None:
        code, _, error = self.run_main(telegram.main, ["photo", str(self.root / "missing.png")])
        self.assertEqual(code, 1)
        self.assertIn("missing.png", error)

    def test_api_errors_and_unreachable_server(self) -> None:
        self.server.routes[f"{self.api}/sendMessage"] = {"ok": False, "description": "Forbidden: bot was blocked"}
        code, _, error = self.run_main(telegram.main, ["hi"])
        self.assertEqual(code, 1)
        self.assertIn("Forbidden: bot was blocked", error)
        code, _, error = self.run_main(telegram.main, ["status"])
        self.assertEqual(code, 1)
        self.assertIn("HTTP Error 404", error)

    def test_status_last_and_download(self) -> None:
        self.server.routes[f"{self.api}/getMe"] = {"ok": True, "result": {"username": "unlaw_bot"}}
        self.assertEqual(self.run_main(telegram.main, ["status"])[1], "@unlaw_bot  chat=42\n")
        updates = [
            {"message": {"from": {"username": "haos"}, "text": "hi", "document": {"file_id": "D", "file_name": "a.pdf"}}},
            {"channel_post": {"chat": {"title": "News"}, "caption": "pic", "photo": [{"file_id": "small"}, {"file_id": "P"}]}},
            {"message": {"voice": {"file_id": "V"}}},
            {"edited_message": {}},
        ]
        self.server.routes[f"{self.api}/getUpdates"] = {"ok": True, "result": updates}
        self.assertEqual(
            self.run_main(telegram.main, ["last"])[1].splitlines(),
            ["haos: hi", "News: pic", "unknown: [file]", "unknown: [file]"],
        )
        self.server.routes[f"{self.api}/getFile"] = {"ok": True, "result": {"file_path": "documents/file_1.pdf"}}
        self.server.routes[f"/file{self.api}/documents/file_1.pdf"] = b"PDF BYTES"
        target = self.root / "downloads"
        code, out, error = self.run_main(telegram.main, ["download", str(target)])
        self.assertEqual(code, 0, error)
        self.assertEqual(len(out.splitlines()), 3)
        self.assertEqual((target / "file_1.pdf").read_bytes(), b"PDF BYTES")
        self.assertEqual([self.server.form(i)["file_id"] for i, r in enumerate(self.server.requests) if "getFile" in str(r["path"])], ["D", "P", "V"])

    def test_empty_updates(self) -> None:
        self.server.routes[f"{self.api}/getUpdates"] = {"ok": True, "result": []}
        self.assertEqual(self.run_main(telegram.main, ["last"])[1], "No Telegram messages.\n")
        self.assertIn("No downloadable files", self.run_main(telegram.main, ["download"])[1])

    def test_missing_chat_id_is_discovered_and_saved(self) -> None:
        set_config_value("telegram.chat_id", "")
        self.server.routes[f"{self.api}/getUpdates"] = {"ok": True, "result": [{"message": {"chat": {"id": 555}}}]}
        self.server.routes[f"{self.api}/sendMessage"] = {"ok": True, "result": {"message_id": 1}}
        self.assertEqual(self.run_main(telegram.main, ["hello"])[0], 0)
        self.assertEqual(self.server.form()["chat_id"], "555")
        from unlawful.config import load_config

        self.assertEqual(load_config()["telegram"]["chat_id"], "555")

    def test_discovery_without_messages_explains_what_to_do(self) -> None:
        set_config_value("telegram.chat_id", "")
        self.server.routes[f"{self.api}/getUpdates"] = {"ok": True, "result": [{"message": {}}]}
        code, _, error = self.run_main(telegram.main, ["hello"])
        self.assertEqual(code, 1)
        self.assertIn("send a message to the bot first", error)

    def test_missing_token_and_capture(self) -> None:
        self.keychain.unlink()
        code, _, error = self.run_main(telegram.main, ["hello"])
        self.assertEqual(code, 1)
        self.assertIn("ul tg setup", error)
        self.keychain.write_text(self.TOKEN)
        code, _, error = self.run_main(telegram.main, ["capture"])
        self.assertEqual(code, 1)
        self.assertIn("no Unlaw captures found", error)

    def test_setup_stores_token_and_discovers_chat(self) -> None:
        self.keychain.unlink()
        new = "999:new"
        self.server.routes[f"/bot{new}/getMe"] = {"ok": True, "result": {"username": "fresh_bot"}}
        self.server.routes[f"/bot{new}/getUpdates"] = {"ok": True, "result": [{"message": {"chat": {"id": 77}}}]}
        with patch.object(telegram.getpass, "getpass", return_value=f" {new} "), patch("builtins.input", return_value=""):
            code, out, error = self.run_main(telegram.main, ["setup"])
        self.assertEqual(code, 0, error)
        self.assertEqual(out, "Telegram connected: @fresh_bot\n")
        self.assertEqual(self.keychain.read_text(), new)
        from unlawful.config import load_config

        self.assertEqual(load_config()["telegram"]["chat_id"], "77")

    def test_setup_rejects_empty_token_and_keychain_failure(self) -> None:
        with patch.object(telegram.getpass, "getpass", return_value=""):
            code, _, error = self.run_main(telegram.main, ["setup"])
        self.assertEqual(code, 1)
        self.assertIn("token cannot be empty", error)
        self.tool("security", "import sys\nsys.stderr.write('keychain locked')\nraise SystemExit(1)\n")
        with patch.object(telegram.getpass, "getpass", return_value="x"), patch("builtins.input", return_value="1"):
            code, _, error = self.run_main(telegram.main, ["setup"])
        self.assertEqual(code, 1)
        self.assertIn("keychain locked", error)

    def test_no_arguments_on_a_terminal_opens_the_app(self) -> None:
        tty = io.StringIO()
        tty.isatty = lambda: True  # type: ignore[method-assign]
        with patch.object(sys, "stdin", tty):
            self.assertEqual(telegram.main([]), 0)
        self.assertEqual(self.lines(self.open_log), ["-a|Telegram"])


class LMStudioTests(ServiceTestCase):
    def setUp(self) -> None:
        super().setUp()
        set_config_value("lm.base_url", f"{self.server.url}/v1")
        self.server.routes["/v1/models"] = {"data": [{"id": "qwen-local"}, {"id": "other"}]}
        self.server.routes["/v1/chat/completions"] = {"choices": [{"message": {"content": "local answer"}}]}

    def chat_requests(self) -> list[dict[str, object]]:
        return [json.loads(r["body"]) for r in self.server.requests if r["path"] == "/v1/chat/completions"]

    def test_prompt_uses_the_first_loaded_model_and_system_prompt(self) -> None:
        code, out, _ = self.run_main(lmstudio.main, ["explain", "this"])
        self.assertEqual((code, out), (0, "local answer\n"))
        request = self.chat_requests()[-1]
        self.assertEqual(request["model"], "qwen-local")
        self.assertEqual(request["messages"][0]["role"], "system")
        self.assertEqual(request["messages"][-1], {"role": "user", "content": "explain this"})
        self.assertEqual((request["temperature"], request["stream"]), (0.7, False))

    def test_configured_model_and_empty_system_prompt(self) -> None:
        set_config_value("lm.model", "pinned")
        set_config_value("lm.system_prompt", "")
        self.run_main(lmstudio.main, ["hi"])
        request = self.chat_requests()[-1]
        self.assertEqual(request["model"], "pinned")
        self.assertEqual(request["messages"], [{"role": "user", "content": "hi"}])
        self.assertNotIn("/v1/models", [r["path"] for r in self.server.requests])

    def test_prompt_from_stdin(self) -> None:
        code, out, _ = self.run_main(lmstudio.main, [], stdin="from a pipe\n")
        self.assertEqual((code, out), (0, "local answer\n"))
        self.assertEqual(self.chat_requests()[-1]["messages"][-1]["content"], "from a pipe")

    def test_models_lists_loaded_models(self) -> None:
        self.assertEqual(self.run_main(lmstudio.main, ["models"])[1], "qwen-local\nother\n")

    def test_no_loaded_model_and_bad_responses_open_lm_studio(self) -> None:
        self.server.routes["/v1/models"] = {"data": []}
        code, _, error = self.run_main(lmstudio.main, ["hi"])
        self.assertEqual(code, 1)
        self.assertIn("no loaded local model", error)
        self.assertIn("-a|LM Studio", self.lines(self.open_log))
        self.server.routes["/v1/models"] = {"data": [{"id": "m"}]}
        self.server.routes["/v1/chat/completions"] = {"choices": []}
        self.assertIn("invalid chat response", self.run_main(lmstudio.main, ["hi"])[2])

    def test_server_actions_need_lms(self) -> None:
        code, _, error = self.run_main(lmstudio.main, ["status"])
        self.assertEqual(code, 1)
        self.assertIn("`lms` was not found", error)
        log = self.tool_log("lms", exit_code=3)
        self.assertEqual(self.run_main(lmstudio.main, ["stop"])[0], 3)
        self.assertEqual(self.lines(log), ["server|stop"])
        self.assertEqual(self.run_main(lmstudio.main, ["open"])[0], 0)
        self.assertIn("-a|LM Studio", self.lines(self.open_log))

    def test_unreachable_server_is_started_once_then_reported(self) -> None:
        self.server.close()
        log = self.tool_log("lms", exit_code=1)
        code, _, error = self.run_main(lmstudio.main, ["hi"])
        self.assertEqual(code, 1)
        self.assertIn("could not be started through `lms`", error)
        self.assertEqual(self.lines(log), ["server|start"])
        self.server = FakeServer()  # keep cleanup happy

    def test_interactive_chat_keeps_context_and_clear_resets_it(self) -> None:
        tty = io.StringIO()
        tty.isatty = lambda: True  # type: ignore[method-assign]
        answers = iter(["first", "", "second", "/clear", "third", "/exit"])
        with patch.object(sys, "stdin", tty), patch("builtins.input", side_effect=lambda prompt: next(answers)):
            code, out, _ = self.run_main(lmstudio.main, [])
        self.assertEqual(code, 0)
        self.assertEqual(out.count("lm> local answer"), 3)
        self.assertIn("Context cleared.", out)
        first, second, third = self.chat_requests()
        self.assertEqual([m["content"] for m in second["messages"] if m["role"] == "user"], ["first", "second"])
        self.assertEqual([m["content"] for m in third["messages"] if m["role"] == "user"], ["third"])

    def test_interactive_chat_ends_on_eof(self) -> None:
        tty = io.StringIO()
        tty.isatty = lambda: True  # type: ignore[method-assign]
        with patch.object(sys, "stdin", tty), patch("builtins.input", side_effect=EOFError):
            self.assertEqual(self.run_main(lmstudio.main, [])[0], 0)

    def test_only_localhost_urls_are_accepted(self) -> None:
        with self.assertRaisesRegex(ValueError, "localhost"):
            lmstudio._local_base_url("https://api.example.com/v1")
        self.assertEqual(lmstudio._local_base_url("http://[::1]:1234/v1/"), "http://[::1]:1234/v1")


class HarnessTests(ServiceTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.log = self.root / "harness.log"
        self.executable = self.tool(
            "macos-harness",
            "import sys, time\n"
            f"open({str(self.log)!r}, 'a').write(repr((sys.argv[1:], sys.stdin.read() if len(sys.argv) == 1 else '')) + '\\n')\n"
            "if 'slow' in sys.argv: time.sleep(5)\n",
        )

    def calls(self) -> list[tuple[list[str], str]]:
        import ast

        return [ast.literal_eval(line) for line in self.lines(self.log)]

    def test_mac_actions_reach_the_harness(self) -> None:
        self.assertEqual(self.run_main(mac_command.main, ["see", "Zed", "Preview"])[0], 0)
        self.assertEqual(self.run_main(mac_command.main, ["key", "Spotify", "cmd+k"])[0], 0)
        self.assertEqual(self.run_main(mac_command.main, ["type", "Telegram", 'say "hi"'])[0], 0)
        self.assertEqual(self.run_main(mac_command.main, ["click", "Spotify", "10", "20.5"])[0], 0)
        self.assertEqual(
            self.calls(),
            [
                (["see", "Zed Preview"], ""),
                ([], 'mac.key("cmd+k", app="Spotify")\n'),
                ([], 'mac.type("say \\"hi\\"", app="Telegram")\n'),
                ([], 'mac.click(10.0, 20.5, app="Spotify")\n'),
            ],
        )

    def test_invalid_mac_usage(self) -> None:
        for args in ([], ["see"], ["key", "App"], ["click", "App", "x", "1"], ["fly"]):
            with self.subTest(args=args):
                code, out, error = self.run_main(mac_command.main, args)
                self.assertEqual(code, 2)
                self.assertIn("ul mac see <application>", out + error)
        self.assertEqual(self.calls(), [])

    def test_missing_harness_and_timeouts(self) -> None:
        set_config_value("mac.timeout", 1)
        code, _, error = self.run_main(lambda args: harness.see("slow"), [])
        self.assertEqual(code, 124)
        self.assertIn("timed out", error)
        set_config_value("mac.executable", "no-such-harness")
        code, _, error = self.run_main(lambda args: harness.key("App", "a"), [])
        self.assertEqual(code, 1)
        self.assertIn("macOS Harness was not found: no-such-harness", error)
        self.assertEqual(self.run_main(lambda args: harness.see("App"), [])[0], 1)

    def test_program_timeout_and_config_errors(self) -> None:
        self.tool("macos-harness", "import time\ntime.sleep(5)\n")
        set_config_value("mac.timeout", 1)
        code, _, error = self.run_main(lambda args: harness.type_text("App", "x"), [])
        self.assertEqual(code, 124)
        from unlawful.config import config_file

        config_file().write_text('[mac]\ntimeout = "never"\n')
        code, _, error = self.run_main(lambda args: harness.click("App", 1, 2), [])
        self.assertEqual(code, 1)
        self.assertIn("mac.timeout", error)


class AppTests(ServiceTestCase):
    def test_app_opens_named_application(self) -> None:
        self.assertEqual(self.run_main(app_command.main, ["LM", "Studio"])[0], 0)
        self.assertEqual(self.lines(self.open_log), ["-a|LM Studio"])
        code, _, error = self.run_main(app_command.main, [])
        self.assertEqual(code, 2)
        self.assertIn("Usage: ul app", error)
        with patch.object(app_command.subprocess, "run", side_effect=OSError("no open")):
            code, _, error = self.run_main(app_command.main, ["X"])
        self.assertEqual(code, 1)
        self.assertIn("no open", error)


if __name__ == "__main__":
    unittest.main()
