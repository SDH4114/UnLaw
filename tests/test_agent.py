"""`ul agent`: local agent with tools, approvals, schedule and Telegram.

The model and Telegram are local fake servers; nothing reaches the network.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import select
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from tests.ulbin import CoreTestCase, binary

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

KANBAN = """---
kanban-plugin: board
---

## To do

- [ ] Write the report
\tdue Friday
- [x] Old finished thing

## Completed

- [x] Done long ago
"""


def call(name: str, **arguments: object) -> dict:
    return {
        "tool_calls": [
            {
                "id": f"c-{name}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ]
    }


class FakeServer:
    """A threaded local HTTP server.

    `route(method, path, body, headers)` returns (status, payload): a dict is
    sent as JSON, a list of strings as a Server-Sent Events stream.
    """

    def __init__(self, route) -> None:

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def _answer(self, method: str) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                status, payload = route(method, self.path, body, self.headers)
                if isinstance(payload, list):
                    self.send_response(status)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    try:
                        for event in payload:
                            if isinstance(event, float):
                                time.sleep(event)
                                continue
                            self.wfile.write(f"data: {event}\n\n".encode())
                            self.wfile.flush()
                    except OSError:
                        pass
                    self.close_connection = True
                    return
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                self._answer("GET")

            def do_POST(self) -> None:
                self._answer("POST")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class FakeModel:
    """Answers chat requests from a script and records what it was sent.

    A script step is {"content": ...} and/or {"tool_calls": [...]}; "delay"
    (seconds) holds the stream back before the first chunk.
    """

    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)
        self.requests: list[dict] = []
        self.server = FakeServer(self.route)
        self.url = self.server.url

    def route(self, method: str, path: str, body: bytes, headers: object) -> tuple[int, object]:
        if path == "/v1/audio/transcriptions":
            return 200, {"text": "remind me to stretch"}
        request = json.loads(body)
        self.requests.append(request)
        step = self.script.pop(0) if self.script else {"content": "done"}
        content = step.get("content", "")
        if not request.get("stream"):
            message = {"role": "assistant", "content": content}
            if "tool_calls" in step:
                message["tool_calls"] = step["tool_calls"]
            return 200, {"choices": [{"index": 0, "message": message, "finish_reason": "stop"}]}
        chunk = lambda delta, finish=None: json.dumps({"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]})
        events: list[object] = [chunk({"role": "assistant", "content": ""})]
        if step.get("delay"):
            events.append(float(step["delay"]))
        events += [chunk({"content": word}) for word in re.findall(r"\S+\s*", content)]
        last: dict = {}
        if "tool_calls" in step:
            last["tool_calls"] = [{**call, "index": index} for index, call in enumerate(step["tool_calls"])]
        events.append(chunk(last, "tool_calls" if "tool_calls" in step else "stop"))
        events.append(json.dumps({"choices": [], "usage": {"prompt_tokens": 1200, "completion_tokens": 30, "total_tokens": 1230}}))
        events.append("[DONE]")
        return 200, events

    def tool_names(self, index: int = 0) -> set[str]:
        return {tool["function"]["name"] for tool in self.requests[index].get("tools", [])}

    def tool_results(self) -> list[str]:
        return [m["content"] for m in self.requests[-1]["messages"] if m.get("role") == "tool"]

    def last_user(self) -> object:
        return [m for m in self.requests[-1]["messages"] if m.get("role") == "user"][-1]["content"]


class Terminal:
    """`ul agent` on a real pseudo-terminal, so the console sees a TTY."""

    def __init__(self, args: list[str], env: dict, cwd: Path) -> None:
        master, slave = os.openpty()
        self.process = subprocess.Popen(args, stdin=slave, stdout=slave, stderr=slave, env=env, cwd=cwd, start_new_session=True)
        os.close(slave)
        self.master = master
        self.output = ""

    def expect(self, text: str, timeout: float = 30) -> str:
        deadline = time.monotonic() + timeout
        while text not in self.output:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"{text!r} did not appear; output so far:\n{self.output}")
            if select.select([self.master], [], [], min(remaining, 0.2))[0]:
                try:
                    data = os.read(self.master, 4096)
                except OSError:
                    data = b""
                if not data and self.process.poll() is not None:
                    raise AssertionError(f"exited before {text!r}:\n{self.output}")
                self.output += data.decode("utf-8", errors="replace")
        return self.output

    def send(self, keys: str) -> None:
        os.write(self.master, keys.encode())

    def prompt(self, after: str = "") -> None:
        """Wait for the input box drawn after `after` (keys typed while the agent works are dropped)."""
        deadline = time.monotonic() + 30
        quiet_since = time.monotonic()
        while True:
            start = self.output.rfind(after) if after else 0
            if start >= 0 and "@ files" in self.output[start:] and time.monotonic() - quiet_since > 0.3:
                return
            if time.monotonic() > deadline:
                raise AssertionError(f"no input box after {after!r}:\n{self.output}")
            if select.select([self.master], [], [], 0.1)[0]:
                self.output += os.read(self.master, 4096).decode("utf-8", errors="replace")
                quiet_since = time.monotonic()

    def quit(self, after: str = "") -> int:
        self.prompt(after)
        self.send("\x04")
        return self.finish()

    def finish(self) -> int:
        """Wait for exit while draining output: a full pty buffer would block the child."""
        deadline = time.monotonic() + 20
        try:
            while self.process.poll() is None and time.monotonic() < deadline:
                if select.select([self.master], [], [], 0.1)[0]:
                    try:
                        self.output += os.read(self.master, 4096).decode("utf-8", errors="replace")
                    except OSError:
                        break
            return self.process.wait(timeout=5)
        finally:
            if self.process.poll() is None:
                self.process.kill()
            os.close(self.master)


class AgentCase(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.files = self.home / "work"
        self.files.mkdir()
        (self.files / "notes.txt").write_text("alpha\nbeta\n", encoding="utf-8")
        self.vault = self.root / "vault"
        self.vault.mkdir()
        (self.vault / "TODO.md").write_text(KANBAN, encoding="utf-8")
        self.ok("config", "set", "agent.roots", json.dumps([str(self.files)]))
        self.ok("config", "set", "todo.vault_path", str(self.vault))
        # `security` stand-in, so tests never touch the real Keychain.
        self.keychain = self.root / "keychain.txt"
        self.tool(
            "security",
            f"#!{sys.executable}\nimport sys, pathlib\nstore = pathlib.Path({str(self.keychain)!r})\n"
            "args = sys.argv[1:]\n"
            "if args[0] == 'add-generic-password':\n    store.write_text(args[args.index('-w') + 1]); raise SystemExit(0)\n"
            "if store.exists(): print(store.read_text()); raise SystemExit(0)\n"
            "raise SystemExit(44)\n",
        )

    def model(self, script: list[dict]) -> FakeModel:
        model = FakeModel(script)
        self.addCleanup(model.server.close)
        self.env["UNLAW_AGENT_LM_URL"] = model.url
        return model


class AgentCommandTests(AgentCase):
    def test_help_is_side_effect_free(self) -> None:
        for flag in ("--help", "-h"):
            result = self.ok("agent", flag)
            self.assertIn("ula server", result.stdout)
            self.assertIn("-p, --print", result.stdout)
        self.assertFalse((self.unlaw / "data" / "agent").exists())

    def test_reads_files_inside_roots_and_answers(self) -> None:
        model = self.model(
            [
                call("read_file", path=str(self.files / "notes.txt")),
                {"content": "It says alpha and beta."},
            ]
        )
        result = self.ok("agent", "what is in notes?")
        self.assertEqual(result.stdout.strip(), "It says alpha and beta.")
        self.assertIn("alpha", model.tool_results()[0])
        self.assertIn("write_file", model.tool_names())
        system = model.requests[0]["messages"][0]
        self.assertEqual(system["role"], "system")
        self.assertIn(str(self.files), system["content"])

    def test_paths_outside_roots_and_secrets_are_refused(self) -> None:
        secret = self.files / ".ssh"
        secret.mkdir()
        (secret / "id_ed25519").write_text("KEY", encoding="utf-8")
        (self.files / ".env").write_text("TOKEN=1", encoding="utf-8")
        model = self.model(
            [
                call("read_file", path=str(self.home / "outside.txt")),
                call("read_file", path=str(secret / "id_ed25519")),
                call("read_file", path=str(self.files / ".env")),
                call("list_dir", path=str(self.files / ".." / "..")),
                {"content": "no"},
            ]
        )
        self.ok("agent", "steal things")
        results = model.tool_results()
        self.assertIn("outside the allowed folders", results[0])
        self.assertIn("never accessible", results[1])
        self.assertIn("secrets", results[2])
        self.assertIn("outside the allowed folders", results[3])
        self.assertNotIn("KEY", "".join(results))
        self.assertNotIn("TOKEN=1", "".join(results))

    def test_changes_need_approval(self) -> None:
        target = self.files / "new.txt"
        model = self.model(
            [call("write_file", path=str(target), content="hi\n"), {"content": "ok"}]
        )
        result = self.ok("agent", "write it", input="n\n")
        self.assertFalse(target.exists())
        self.assertIn("declined", model.tool_results()[0])
        self.assertIn(f"Create {target}", result.stderr)

        model = self.model(
            [call("write_file", path=str(target), content="hi\n"), {"content": "ok"}]
        )
        self.ok("agent", "write it", input="y\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "hi\n")

        model = self.model(
            [
                call("edit_file", path=str(target), old="hi", new="hello"),
                {"content": "ok"},
            ]
        )
        result = self.ok("agent", "edit", input="y\n")
        self.assertIn("-hi", result.stderr)
        self.assertIn("+hello", result.stderr)
        self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")

    def test_delete_goes_to_the_trash_and_runs_need_approval(self) -> None:
        doomed = self.files / "old.txt"
        doomed.write_text("x", encoding="utf-8")
        self.model([call("delete", path=str(doomed)), {"content": "ok"}])
        self.ok("agent", "delete", input="y\n")
        self.assertFalse(doomed.exists())
        self.assertEqual(
            (self.home / ".Trash" / "old.txt").read_text(encoding="utf-8"), "x"
        )

        marker = self.files / "ran"
        self.model([call("run", command=f"touch {marker}"), {"content": "ok"}])
        self.ok("agent", "run", input="")
        self.assertFalse(marker.exists(), "no answer means no")
        self.model(
            [
                call("run", command=f"touch {marker}", cwd=str(self.files)),
                {"content": "ok"},
            ]
        )
        self.ok("agent", "run", input="yes\n")
        self.assertTrue(marker.exists())
        log = (self.unlaw / "data" / "agent" / "audit.log").read_text(encoding="utf-8")
        self.assertIn('"declined"', log)
        self.assertIn('"delete"', log)

    def test_ul_commands_follow_the_allowlist(self) -> None:
        model = self.model(
            [
                call("ul", args=["config", "set", "agent.roots", '["/"]']),
                call("ul", args=["todo", "--help"]),
                {"content": "ok"},
            ]
        )
        self.ok("agent", "go")
        results = model.tool_results()
        self.assertIn("not in agent.commands", results[0])
        self.assertIn("exit 0", results[1])
        self.assertIn("Obsidian TODO board", results[1])

    def test_today_plan_and_unschedule_through_tools(self) -> None:
        moment = dt.datetime.now()
        if moment.hour == 23 and moment.minute >= 50:
            self.skipTest("'in 5m' would be tomorrow")
        model = self.model(
            [
                call("schedule", prompt="stretch", when="in 5m", repeat="daily"),
                call("schedule", prompt="far away", when="2099-01-01 09:00"),
                call("schedule", prompt="never", when="2020-01-01 09:00"),
                call("today"),
                call("list_schedule"),
                {"content": "ok"},
            ]
        )
        self.ok("agent", "-p", "plan my day")
        scheduled, _far, past, today, plan = model.tool_results()
        self.assertIn("stretch (daily)", scheduled)
        self.assertIn("in the past", past)
        self.assertIn("Write the report", today)
        self.assertIn("due Friday", today)
        self.assertNotIn("Old finished thing", today)
        self.assertNotIn("Done long ago", today)
        self.assertIn("stretch (daily)", today)
        self.assertNotIn("far away", today)
        self.assertIn("far away", plan)
        job = re.search(r"#(\w+)\s+far away", plan).group(1)
        model = self.model([call("unschedule", id=job), call("list_schedule"), {"content": "ok"}])
        self.ok("agent", "-p", "cancel it")
        self.assertNotIn("far away", model.tool_results()[-1])

    def test_todo_tools(self) -> None:
        self.model([call("todo_add", text="Buy milk"), {"content": "ok"}])
        self.ok("agent", "-p", "remember milk")
        self.assertIn("Buy milk", (self.vault / "TODO.md").read_text(encoding="utf-8"))

    def test_print_mode_reads_piped_stdin_and_options(self) -> None:
        model = self.model([{"content": "Reviewed."}])
        result = self.ok("agent", "-m", "Other-Model", input="diff --git a b\n")
        self.assertEqual(result.stdout, "Reviewed.\n")
        self.assertEqual(model.requests[0]["model"], "Other-Model")
        self.assertIn("diff --git", model.last_user())
        self.assertEqual(self.ul("agent", "--bogus").returncode, 1)
        self.assertIn("nothing to do", self.ul("agent", "-p").stderr)

    def test_at_paths_attach_files_but_never_secrets(self) -> None:
        (self.files / ".env").write_text("TOKEN=1", encoding="utf-8")
        model = self.model([{"content": "ok"}])
        self.ok("agent", "-p", "what is in @notes.txt and @.env?", cwd=self.files)
        sent = model.last_user()
        self.assertIn("alpha", sent)
        self.assertIn("was not attached", sent)
        self.assertNotIn("TOKEN=1", sent)

    def test_server_refuses_when_the_background_one_runs(self) -> None:
        self.tool("security", "#!/bin/sh\nexit 44\n")
        result = self.ul("agent", "server")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ula setup", result.stderr)
        plist = self.home / "Library" / "LaunchAgents" / "com.unlaw.agent.plist"
        plist.parent.mkdir(parents=True)
        plist.write_text("x", encoding="utf-8")
        self.recording_tool("launchctl")
        result = self.ul("agent", "server")
        self.assertEqual(result.returncode, 1)
        self.assertIn("already runs in the background", result.stderr)


class FakeTelegram:
    def __init__(self, owner: str) -> None:
        self.owner = owner
        self.updates: list[dict] = []
        self.calls: list[tuple[str, dict]] = []
        self.press: str | None = "ok"
        self.reject_html = False
        self.next_id = 100
        self.server = FakeServer(self.route)
        self.url = self.server.url

    def push(self, **update: object) -> None:
        self.next_id += 1
        self.updates.append({"update_id": self.next_id, **update})

    def message(self, chat: str, **fields: object) -> dict:
        self.next_id += 1
        return {
            "update_id": self.next_id,
            "message": {
                "message_id": self.next_id,
                "chat": {"id": int(chat)},
                "from": {"id": int(chat)},
                **fields,
            },
        }

    def sent(self, method: str = "sendMessage") -> list[dict]:
        return [fields for name, fields in self.calls if name == method]

    def route(
        self, method: str, path: str, body: bytes, headers: object
    ) -> tuple[int, dict]:
        if path.startswith("/file/"):
            return 200, {}
        name = path.rsplit("/", 1)[-1]
        fields = {
            key: values[0]
            for key, values in urllib.parse.parse_qs(body.decode()).items()
        }
        self.calls.append((name, fields))
        if name == "getUpdates":
            offset = int(fields.get("offset", 0))
            if offset == -1:
                return 200, {"ok": True, "result": self.updates[-1:]}
            ready = [update for update in self.updates if update["update_id"] >= offset]
            self.updates = []
            return 200, {"ok": True, "result": ready}
        if name == "sendMessage" and self.reject_html and fields.get("parse_mode") == "HTML":
            return 400, {"ok": False, "description": "Bad Request: can't parse entities: unclosed tag"}
        if name == "getMe":
            return 200, {"ok": True, "result": {"username": "unlaw_test_bot"}}
        if name == "sendMessage" and "reply_markup" in fields and self.press:
            token = json.loads(fields["reply_markup"])["inline_keyboard"][0][0][
                "callback_data"
            ].split(":")[1]
            self.push(
                callback_query={
                    "id": "q",
                    "from": {"id": int(self.owner)},
                    "data": f"{self.press}:{token}",
                }
            )
        return 200, {"ok": True, "result": {"message_id": len(self.calls)}}


class BotTests(AgentCase):
    """The Telegram bot, driven in-process against local fake servers."""

    def setUp(self) -> None:
        super().setUp()
        self.ok("config", "set", "telegram.chat_id", '"42"')
        self.ok("config", "set", "agent.allowed_ids", '["7", "8"]')
        self.ok("config", "set", "agent.users.8", "read")
        self.telegram = FakeTelegram("42")
        self.addCleanup(self.telegram.server.close)
        self.ok("config", "set", "telegram.api_base", self.telegram.url)
        environment = {
            key: value
            for key, value in self.env.items()
            if key.startswith(("XDG", "HOME", "UNLAW", "PATH"))
        }
        environment["UNLAW_BIN"] = str(binary())
        patcher = patch.dict(os.environ, environment)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ok("version")  # bootstrap the layout before importing

    def bot(self, script: list[dict]):
        from unlawful import agent

        fake = self.model(script)
        os.environ["UNLAW_AGENT_LM_URL"] = fake.url
        config = agent.load_config()
        bot = agent.Bot(
            config,
            agent.Telegram("TOKEN", config["telegram"]["api_base"]),
            agent.Model(config),
        )
        bot.poll_timeout = 0
        return bot, fake

    def test_strangers_are_ignored_and_owner_gets_answers(self) -> None:
        bot, model = self.bot([{"content": "hello owner"}])
        bot.handle(self.telegram.message("999", text="hi"))
        self.assertEqual(self.telegram.sent(), [])
        self.assertEqual(model.requests, [])
        bot.handle(self.telegram.message("42", text="hi"))
        self.assertEqual(self.telegram.sent()[-1]["text"], "hello owner")
        self.assertIn("write_file", model.tool_names())

    def test_config_changes_apply_without_restart(self) -> None:
        bot, model = self.bot([{"content": "a"}, {"content": "b"}])
        bot.handle(self.telegram.message("42", text="hi"))
        self.assertEqual(model.requests[0]["model"], "auto")
        self.ok("config", "set", "agent.model", "Big-27B")
        self.ok("config", "set", "agent.allowed_ids", '["9"]')
        bot.handle(self.telegram.message("42", text="again"))
        self.assertEqual(model.requests[1]["model"], "Big-27B")
        bot.handle(self.telegram.message("7", text="hi"))
        self.assertEqual(len(model.requests), 2, "7 was removed from agent.allowed_ids")

    def test_answers_are_sent_as_telegram_html_with_a_plain_fallback(self) -> None:
        bot, _ = self.bot([{"content": "**Done** with `x<1`:\n```py\nprint(1 < 2)\n```"}, {"content": "**again**"}])
        bot.handle(self.telegram.message("42", text="hi"))
        sent = self.telegram.sent()[-1]
        self.assertEqual(sent["parse_mode"], "HTML")
        self.assertEqual(sent["text"], "<b>Done</b> with <code>x&lt;1</code>:\n<pre>print(1 &lt; 2)</pre>")
        self.telegram.reject_html = True
        bot.handle(self.telegram.message("42", text="again"))
        sent = self.telegram.sent()[-1]
        self.assertNotIn("parse_mode", sent)
        self.assertEqual(sent["text"], "**again**")

    def test_control_characters_never_reach_the_screen(self) -> None:
        from unlawful.agent import printable

        self.assertEqual(printable("Icon\r ok\x1b[31m\tx\n"), "Icon? ok?[31m\tx\n")

    def test_levels_limit_tools(self) -> None:
        bot, model = self.bot([{"content": "a"}, {"content": "b"}])
        bot.handle(self.telegram.message("7", text="hi"))
        self.assertNotIn("tools", model.requests[0])
        bot.handle(self.telegram.message("8", text="hi"))
        self.assertIn("read_file", model.tool_names(1))
        self.assertNotIn("write_file", model.tool_names(1))
        bot.handle(self.telegram.message("7", text="/today"))
        self.assertIn("no access", self.telegram.sent()[-1]["text"])

    def test_approval_buttons_go_to_the_owner(self) -> None:
        target = self.files / "from-tg.txt"
        bot, model = self.bot(
            [call("write_file", path=str(target), content="x"), {"content": "written"}]
        )
        bot.handle(self.telegram.message("42", text="write"))
        self.assertEqual(target.read_text(encoding="utf-8"), "x")
        edits = self.telegram.sent("editMessageText")
        self.assertTrue(edits[-1]["text"].startswith("Approved"))

        self.telegram.press = "no"
        other = self.files / "never.txt"
        bot, model = self.bot(
            [call("write_file", path=str(other), content="x"), {"content": "ok"}]
        )
        bot.handle(self.telegram.message("42", text="write"))
        self.assertFalse(other.exists())
        self.assertIn("declined", model.tool_results()[-1])

    def test_messages_during_approval_are_kept(self) -> None:
        target = self.files / "queued.txt"
        bot, _ = self.bot(
            [call("write_file", path=str(target), content="x"), {"content": "done"}]
        )
        self.telegram.updates.append(self.telegram.message("42", text="second message"))
        bot.handle(self.telegram.message("42", text="write"))
        self.assertEqual(
            [update["message"]["text"] for update in bot.backlog], ["second message"]
        )

    def test_due_jobs_run_and_report(self) -> None:
        from unlawful import agent

        bot, _ = self.bot([{"content": "Stretched."}])
        past = agent.now() - dt.timedelta(minutes=1)
        agent.Schedule()._save(
            [
                {
                    "id": "abc123",
                    "prompt": "stretch",
                    "next": past.isoformat(),
                    "repeat": "daily",
                    "by": "terminal",
                }
            ]
        )
        bot.tick()
        texts = [fields["text"] for fields in self.telegram.sent()]
        self.assertEqual(texts, ["Scheduled task #abc123: stretch", "Stretched."])
        self.assertEqual(
            {message["chat_id"] for message in self.telegram.sent()}, {"42"}
        )
        next_run = dt.datetime.fromisoformat(agent.Schedule().jobs()[0]["next"])
        self.assertGreater(next_run, agent.now())
        bot.tick()
        self.assertEqual(len(self.telegram.sent()), 2, "a job runs once per due time")

    def test_voice_messages_are_transcribed(self) -> None:
        from unlawful import agent

        bot, model = self.bot([{"content": "Reminder set."}])
        with patch.object(
            agent.Telegram,
            "download",
            lambda self, file_id, path: (
                path.parent.mkdir(parents=True, exist_ok=True),
                path.write_bytes(b"ogg"),
                path,
            )[2],
        ):
            bot.handle(self.telegram.message("42", voice={"file_id": "v1"}))
        texts = [fields["text"] for fields in self.telegram.sent()]
        self.assertEqual(texts, ["Heard: remind me to stretch", "Reminder set."])
        self.assertEqual(
            model.requests[0]["messages"][-1]["content"], "remind me to stretch"
        )

    def test_backlog_from_before_start_is_skipped(self) -> None:
        bot, model = self.bot([])
        self.telegram.updates.append(self.telegram.message("42", text="old"))
        bot.run(polls=1)
        self.assertEqual(model.requests, [])
        self.assertEqual(self.telegram.sent(), [])


class ScheduleParsingTests(CoreTestCase):
    def test_when_and_repeat(self) -> None:
        from unlawful.agent import parse_repeat, parse_when

        base = dt.datetime(2026, 10, 24, 12, 0)
        self.assertEqual(parse_when("in 30m", base), dt.datetime(2026, 10, 24, 12, 30))
        self.assertEqual(parse_when("18:05", base), dt.datetime(2026, 10, 24, 18, 5))
        self.assertEqual(parse_when("9:00", base), dt.datetime(2026, 10, 25, 9, 0))
        self.assertEqual(
            parse_when("tomorrow 13:00", base), dt.datetime(2026, 10, 25, 13, 0)
        )
        self.assertEqual(
            parse_when("2026-11-01 09:00", base), dt.datetime(2026, 11, 1, 9, 0)
        )
        for bad in ("2020-01-01 09:00", "25:00", "soon", "in 0m"):
            with self.assertRaises(ValueError, msg=bad):
                parse_when(bad, base)
        self.assertEqual(parse_repeat(None), "once")
        self.assertEqual(parse_repeat("every 2h"), "every 120m")
        with self.assertRaises(ValueError):
            parse_repeat("hourly")


class SetupTests(AgentCase):
    def test_setup_saves_the_token_in_the_keychain(self) -> None:
        telegram = FakeTelegram("42")
        self.addCleanup(telegram.server.close)
        self.ok("config", "set", "telegram.api_base", telegram.url)
        telegram.updates.append(telegram.message("42", text="hi"))
        self.env["HF_HUB_CACHE"] = str(self.root / "hf")
        (self.unlaw / ".env").write_text("OTHER=1\nTELEGRAM_BOT_TOKEN=old:token\n", encoding="utf-8")
        answers = "\n".join(["", "123:abc", "", "", "7, 8", "08:30", str(self.files), "n"]) + "\n"
        result = self.ok("agent", "setup", input=answers)
        self.assertIn("No downloaded chat model yet", result.stdout)
        self.assertIn("@unlaw_test_bot", result.stdout)
        self.assertEqual(self.keychain.read_text(encoding="utf-8"), "123:abc")
        self.assertIn("macOS Keychain", result.stdout)
        # The old .env token is dropped so only one token is in use; other lines stay.
        self.assertEqual((self.unlaw / ".env").read_text(encoding="utf-8"), "OTHER=1\n")
        self.assertNotIn("123:abc", (self.unlaw / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(self.ok("config", "get", "telegram.chat_id").stdout.strip(), "42")
        self.assertEqual(json.loads(self.ok("config", "get", "agent.allowed_ids").stdout), ["7", "8"])
        self.assertEqual(self.ok("config", "get", "agent.digest_time").stdout.strip(), "08:30")
        self.assertEqual(json.loads(self.ok("config", "get", "agent.roots").stdout), [str(self.files)])

    def test_setup_turns_background_mode_on_and_off(self) -> None:
        telegram = FakeTelegram("42")
        self.addCleanup(telegram.server.close)
        self.ok("config", "set", "telegram.api_base", telegram.url)
        self.ok("config", "set", "telegram.chat_id", '"42"')
        self.ok("config", "set", "agent.allowed_ids", '["7", "8"]')
        self.env["HF_HUB_CACHE"] = str(self.root / "hf")
        log = self.recording_tool("launchctl")
        # token, owner, ids (add 9, remove 7), digest, folders, background
        answers = "\n".join(["", "123:abc", "", "9, -7", "", "", "y"]) + "\n"
        self.ok("agent", "setup", input=answers)
        self.assertEqual(json.loads(self.ok("config", "get", "agent.allowed_ids").stdout), ["8", "9"])
        plist = self.home / "Library" / "LaunchAgents" / "com.unlaw.agent.plist"
        import plistlib

        loaded = plistlib.loads(plist.read_bytes())
        self.assertEqual(loaded["ProgramArguments"][1:], ["agent", "server"])
        self.assertTrue(Path(loaded["ProgramArguments"][0]).is_absolute())
        self.assertEqual(loaded["EnvironmentVariables"]["UNLAW_AGENT_SERVICE"], "1")
        self.assertIn(["bootstrap", f"gui/{os.getuid()}", str(plist)], self.calls(log))
        # Enter keeps everything, including the saved token; "n" turns background off.
        before = (self.unlaw / "config.toml").read_text(encoding="utf-8")
        self.ok("agent", "setup", input="\n".join(["", "", "", "", "", "", "n"]) + "\n")
        self.assertEqual((self.unlaw / "config.toml").read_text(encoding="utf-8"), before, "nothing changed, nothing written")
        self.assertFalse(plist.exists())
        self.assertIn(["bootout", f"gui/{os.getuid()}/com.unlaw.agent"], self.calls(log))

    def test_token_comes_from_the_keychain_then_env(self) -> None:
        from unlawful import agent

        env = self.unlaw / ".env"
        env.write_text("TELEGRAM_BOT_TOKEN='555:file'\n", encoding="utf-8")
        with patch.dict(os.environ, {"PATH": self.env["PATH"], "XDG_CONFIG_HOME": self.env["XDG_CONFIG_HOME"]}):
            self.assertEqual(agent.stored_token("unlaw.telegram"), "555:file", "no Keychain token: .env is used")
            self.keychain.write_text("777:keychain", encoding="utf-8")
            self.assertEqual(agent.stored_token("unlaw.telegram"), "777:keychain", "the Keychain wins")
            agent.store_token("888:new", "unlaw.telegram")
        self.assertEqual(self.keychain.read_text(encoding="utf-8"), "888:new")
        self.assertFalse(env.exists(), "a .env holding only the token is removed")

    def test_edit_ids(self) -> None:
        from unlawful.agent import edit_ids

        self.assertEqual(edit_ids(["1", "2"], "3"), ["1", "2", "3"])
        self.assertEqual(edit_ids(["1", "2"], "-1, 4 5"), ["2", "4", "5"])
        self.assertEqual(edit_ids(["1", "2"], "-"), [])
        self.assertEqual(edit_ids(["1"], "1"), ["1"])
        with self.assertRaises(ValueError):
            edit_ids([], "@friend")

    def test_setup_without_telegram_only_sets_model_and_folders(self) -> None:
        self.env["HF_HUB_CACHE"] = str(self.root / "hf")
        self.ok("agent", "setup", input="n\n~/work\n")
        self.assertFalse((self.unlaw / ".env").exists())
        self.assertEqual(json.loads(self.ok("config", "get", "agent.roots").stdout), ["~/work"])

    def test_model_choice_by_number_and_tool_check(self) -> None:
        from unlawful import agent

        models = [{"id": "Tiny-2B", "type": "text", "runnable": True}, {"id": "Big-27B", "type": "text", "runnable": True}]
        saved: list[tuple[str, object]] = []
        config = {"agent": {"model": "auto"}}
        probes = iter([False, True])  # the small model answers in text, the big one calls tools
        output = io.StringIO()
        with patch.object(agent, "_chat_models", return_value=models), patch.object(
            agent, "_set", lambda key, value, current=None: saved.append((key, value))
        ), patch.object(agent, "load_config", return_value={"lm": {"port": 1}, "agent": {"model": "auto"}}), patch.object(
            agent.Model, "ensure", lambda self: None
        ), patch.object(agent.Model, "calls_tools", lambda self: next(probes)), patch.object(
            sys, "stdin", io.StringIO("1\n\n2\n")
        ), patch.object(sys, "stdout", output):
            agent._choose_model(config)
        self.assertEqual(saved, [("agent.model", "Tiny-2B"), ("agent.model", "Big-27B")])
        self.assertIn("never calls tools", output.getvalue())
        self.assertIn("It calls tools", output.getvalue())

    def test_ula_and_unlawagent_are_ul_agent(self) -> None:
        if shutil.which("cargo") is None:
            self.skipTest("cargo is required")
        subprocess.run(["cargo", "build", "--quiet", "--bin", "ula", "--bin", "unlawagent"], cwd=ROOT, check=True)
        for name in ("ula", "unlawagent"):
            self.model([{"content": f"hello from {name}"}])
            result = subprocess.run(
                [str(ROOT / "target" / "debug" / name), "-p", "hi"], env=self.env, capture_output=True, text=True, timeout=60, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, f"hello from {name}\n")
        # Regression: setup through `ula` called `$UNLAW_BIN lm list`, which was `ula`
        # itself, so it became an agent task and hung.
        self.env["HF_HUB_CACHE"] = str(self.root / "hf")
        result = subprocess.run(
            [str(ROOT / "target" / "debug" / "ula"), "setup"],
            env=self.env,
            input="n\n~/work\n",
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No downloaded chat model yet", result.stdout)


class ConsoleTests(AgentCase):
    """The interactive console, driven through a pseudo-terminal."""

    def console(self, script: list[dict], *args: str) -> tuple[Terminal, FakeModel]:
        model = self.model(script)
        terminal = Terminal([str(binary()), "agent", *args], {**self.env, "NO_COLOR": "1", "COLUMNS": "100"}, self.files)
        self.addCleanup(lambda: terminal.process.poll() is None and terminal.process.kill())
        terminal.prompt()
        return terminal, model

    def test_streams_answers_and_the_status_line(self) -> None:
        terminal, model = self.console([{"content": "Hi there, I am local."}])
        self.assertIn("ula", terminal.output)
        self.assertIn("Ask anything", terminal.output)
        terminal.send("hello\r")
        terminal.expect("Hi there, I am local.")
        terminal.prompt("Hi there")
        self.assertIn("ctx 1.2k", terminal.output[terminal.output.rfind("Hi there") :])
        self.assertIn("› hello", terminal.output, "the sent message stays in the transcript")
        self.assertTrue(model.requests[0]["stream"])
        self.assertEqual(terminal.quit(), 0)

    def test_slash_opens_a_command_menu(self) -> None:
        terminal, _ = self.console([])
        terminal.send("/")
        terminal.expect("start a new conversation")
        terminal.expect("switch the local model")
        terminal.send("\x1b[B")  # Down: /help -> /new
        time.sleep(0.2)
        terminal.send("\r")
        terminal.expect("New conversation.")
        terminal.prompt("New conversation.")
        terminal.send("/he")
        terminal.expect("commands and keys")
        terminal.send("\r")
        terminal.expect("Ctrl+J new line")
        self.assertEqual(terminal.quit("Ctrl+J new line"), 0)

    def test_at_opens_a_file_menu(self) -> None:
        terminal, model = self.console([{"content": "It says alpha."}])
        terminal.send("@no")
        terminal.expect("notes.txt")
        terminal.send("\t")
        time.sleep(0.2)
        terminal.send("what is inside?\r")
        terminal.expect("It says alpha.")
        self.assertIn("alpha", model.last_user())
        self.assertIn(str(self.files / "notes.txt"), model.last_user())
        self.assertEqual(terminal.quit("It says alpha."), 0)

    def test_history_and_ctrl_c(self) -> None:
        terminal, model = self.console([{"content": "first answer"}, {"content": "second answer"}])
        terminal.send("same question\r")
        terminal.expect("first answer")
        terminal.prompt("first answer")
        terminal.send("\x1b[A")  # Up brings back the last message
        time.sleep(0.2)
        terminal.send("\r")
        terminal.expect("second answer")
        self.assertEqual(model.last_user(), "same question")
        terminal.prompt("second answer")
        terminal.send("draft text")
        time.sleep(0.2)
        terminal.send("\x03")  # clears the input
        time.sleep(0.2)
        terminal.send("\x03")
        terminal.expect("Press Ctrl+C again to quit")
        terminal.send("\x03")
        self.assertEqual(terminal.finish(), 0)
        self.assertEqual(len(model.requests), 2, "the cleared draft was never sent")

    def test_tool_calls_and_approvals(self) -> None:
        first, second = self.files / "one.txt", self.files / "two.txt"
        script = [
            call("list_dir", path=str(self.files)),
            call("write_file", path=str(first), content="1\n"),
            call("write_file", path=str(second), content="2\n"),
            {"content": "Done."},
        ]
        terminal, _ = self.console(script)
        terminal.send("make files\r")
        terminal.expect("● list_dir")
        terminal.expect("notes.txt")
        terminal.expect("don't ask again for write file")
        terminal.send("a")  # yes, and for the rest of the session
        terminal.expect("allowed for this session")
        terminal.expect("Done.")
        self.assertEqual(first.read_text(encoding="utf-8"), "1\n")
        self.assertEqual(second.read_text(encoding="utf-8"), "2\n")
        self.assertEqual(terminal.quit("Done."), 0)

    def test_declining_with_the_picker(self) -> None:
        target = self.files / "never.txt"
        terminal, model = self.console([call("write_file", path=str(target), content="x"), {"content": "Fine."}])
        terminal.send("write\r")
        terminal.expect("No")
        terminal.send("\x1b[C")  # Right: Yes -> always
        time.sleep(0.1)
        terminal.send("\x1b[C")  # Right: always -> No
        time.sleep(0.1)
        terminal.send("\r")
        terminal.expect("Fine.")
        self.assertFalse(target.exists())
        self.assertIn("declined", model.tool_results()[-1])
        self.assertEqual(terminal.quit("Fine."), 0)

    def test_escape_stops_the_answer(self) -> None:
        terminal, model = self.console([{"content": "too late", "delay": 30.0}, {"content": "after"}])
        terminal.send("slow\r")
        terminal.expect("working")
        terminal.send("\x1b")
        terminal.expect("stopped", timeout=10)
        terminal.prompt("stopped")
        terminal.send("next\r")
        terminal.expect("after")
        history = [m["content"] for m in model.requests[-1]["messages"] if m["role"] == "assistant"]
        self.assertIn("[stopped by the user]", history[-1])
        self.assertEqual(terminal.quit("after"), 0)

    def test_shell_output_is_shared_and_continue_resumes(self) -> None:
        terminal, model = self.console([{"content": "noted"}])
        terminal.send("!echo shared-output\r")
        terminal.expect("exit 0")
        terminal.prompt("exit 0")
        terminal.send("what did it print?\r")
        terminal.expect("noted")
        self.assertIn("shared-output", model.last_user())
        terminal.prompt("noted")
        terminal.send("/exit\r")
        self.assertEqual(terminal.finish(), 0)
        terminal, model = self.console([{"content": "still here"}], "-c")
        self.assertIn("continuing", terminal.output)
        terminal.send("again\r")
        terminal.expect("still here")
        self.assertIn("noted", json.dumps(model.requests[0]["messages"]))
        self.assertEqual(terminal.quit("still here"), 0)


class InterfaceTests(CoreTestCase):
    def test_markdown_lines(self) -> None:
        from unlawful.agent_ui import Paint, render_markdown_line

        paint = Paint(True)
        line, code = render_markdown_line("# Title", False, paint)
        self.assertIn("Title", line)
        self.assertNotIn("#", line)
        line, _ = render_markdown_line("- item with `code` and **bold**", False, paint)
        self.assertIn("• item with ", line)
        self.assertNotIn("`", line)
        self.assertNotIn("**", line)
        _, code = render_markdown_line("```python", False, paint)
        self.assertTrue(code)
        line, code = render_markdown_line("x = `not code`", True, paint)
        self.assertIn("`not code`", line, "inside a code block nothing is styled away")
        from unlawful.agent_ui import MarkdownStream

        written: list[str] = []
        stream = MarkdownStream(Paint(False), written.append)
        stream.feed("**plain** text\nmore")
        stream.close()
        self.assertEqual("".join(written), "**plain** text\nmore", "without colors the text passes through as is")

    def test_keyboard_sequences(self) -> None:
        from unlawful.agent_ui import Keyboard

        read, write = os.pipe()
        self.addCleanup(os.close, read)
        os.write(write, "\x1b[A\x1b[1;3Dпривет\x1b\r\x1b[200~a\nb\x1b[201~\r\x03".encode())
        os.close(write)
        keyboard = Keyboard(read)
        events = [keyboard.read(0.1) for _ in range(7)]
        self.assertEqual(
            events,
            [("key", "up"), ("key", "word-left"), ("text", "привет"), ("key", "newline"), ("paste", "a\nb"), ("key", "enter"), ("key", "ctrl-c")],
        )

    def test_wrapping_counts_wide_characters(self) -> None:
        from unlawful.agent_ui import _wrap, cells

        self.assertEqual(cells("abc"), 3)
        self.assertEqual(cells("日本"), 4)
        self.assertEqual(_wrap("abcdef", 4), [(0, 4), (4, 6)])
        self.assertEqual(_wrap("日本語", 4), [(0, 2), (2, 3)])
        self.assertEqual(_wrap("", 4), [(0, 0)])
