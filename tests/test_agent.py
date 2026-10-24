"""`ul agent`: local agent with tools, approvals, schedule and Telegram.

The model and Telegram are local fake servers; nothing reaches the network.
"""

from __future__ import annotations

import datetime as dt
import json
import io
import os
import shutil
import subprocess
import sys
import threading
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
    """A threaded local HTTP server; `route(method, path, body, headers)` returns JSON."""

    def __init__(self, route) -> None:

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def _answer(self, method: str) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                status, payload = route(method, self.path, body, self.headers)
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
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class FakeModel:
    """Answers chat requests from a script and records what it was sent."""

    def __init__(self, script: list[dict]) -> None:
        self.script = list(script)
        self.requests: list[dict] = []
        self.server = FakeServer(self.route)
        self.url = self.server.url

    def route(
        self, method: str, path: str, body: bytes, headers: object
    ) -> tuple[int, dict]:
        if path == "/v1/audio/transcriptions":
            return 200, {"text": "remind me to stretch"}
        request = json.loads(body)
        self.requests.append(request)
        step = self.script.pop(0) if self.script else {"content": "done"}
        message = {"role": "assistant", "content": step.get("content", "")}
        if "tool_calls" in step:
            message["tool_calls"] = step["tool_calls"]
        return 200, {
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}]
        }

    def tool_names(self, index: int = 0) -> set[str]:
        return {
            tool["function"]["name"] for tool in self.requests[index].get("tools", [])
        }

    def tool_results(self) -> list[str]:
        return [
            m["content"]
            for m in self.requests[-1]["messages"]
            if m.get("role") == "tool"
        ]


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

    def model(self, script: list[dict]) -> FakeModel:
        model = FakeModel(script)
        self.addCleanup(model.server.close)
        self.env["UNLAW_AGENT_LM_URL"] = model.url
        return model


class AgentCommandTests(AgentCase):
    def test_help_is_side_effect_free(self) -> None:
        for flag in ("--help", "-h"):
            result = self.ok("agent", flag)
            self.assertIn("ul agent schedule <when> <prompt>", result.stdout)
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
        log = self.ok("agent", "log").stdout
        self.assertIn("declined", log)
        self.assertIn("delete", log)

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

    def test_today_lists_open_tasks_and_todays_jobs(self) -> None:
        self.ok("agent", "schedule", "in 5m", "stretch", "--repeat", "daily")
        self.ok("agent", "schedule", "2099-01-01 09:00", "far away")
        today = self.ok("agent", "today").stdout
        self.assertIn("Write the report", today)
        self.assertIn("due Friday", today)
        self.assertNotIn("Old finished thing", today)
        self.assertNotIn("Done long ago", today)
        self.assertIn("stretch (daily)", today)
        self.assertNotIn("far away", today)
        plan = self.ok("agent", "plan").stdout
        self.assertIn("far away", plan)
        job = plan.split("#")[2].split()[0]
        self.ok("agent", "unschedule", job)
        self.assertNotIn("far away", self.ok("agent", "plan").stdout)
        self.assertEqual(self.ul("agent", "schedule", "yesterday", "x").returncode, 1)

    def test_schedule_tool_and_todo_tools(self) -> None:
        self.model(
            [
                call("schedule", prompt="check mail", when="in 1h"),
                call("todo_add", text="Buy milk"),
                {"content": "ok"},
            ]
        )
        self.ok("agent", "plan things")
        self.assertIn("check mail", self.ok("agent", "plan").stdout)
        self.assertIn("Buy milk", (self.vault / "TODO.md").read_text(encoding="utf-8"))

    def test_start_and_stop_use_launchd(self) -> None:
        log = self.recording_tool("launchctl")
        self.tool("security", "#!/bin/sh\necho TOKEN\n")
        self.ok("config", "set", "telegram.chat_id", '"42"')
        self.ok("agent", "start")
        plist = self.home / "Library" / "LaunchAgents" / "com.unlaw.agent.plist"
        self.assertTrue(plist.exists())
        import plistlib

        loaded = plistlib.loads(plist.read_bytes())
        self.assertEqual(loaded["ProgramArguments"][1:], ["agent", "serve"])
        self.assertTrue(Path(loaded["ProgramArguments"][0]).is_absolute())
        self.assertIn(["bootstrap", f"gui/{os.getuid()}", str(plist)], self.calls(log))
        self.assertIn("running", self.ok("agent", "status").stdout)
        self.ok("agent", "stop")
        self.assertFalse(plist.exists())

    def test_start_needs_telegram(self) -> None:
        self.tool("security", "#!/bin/sh\nexit 44\n")
        result = self.ul("agent", "start")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ul agent setup", result.stderr)


class FakeTelegram:
    def __init__(self, owner: str) -> None:
        self.owner = owner
        self.updates: list[dict] = []
        self.calls: list[tuple[str, dict]] = []
        self.press: str | None = "ok"
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
    def test_setup_connects_telegram_and_saves_the_token_in_env(self) -> None:
        telegram = FakeTelegram("42")
        self.addCleanup(telegram.server.close)
        self.ok("config", "set", "telegram.api_base", telegram.url)
        telegram.updates.append(telegram.message("42", text="hi"))
        self.env["HF_HUB_CACHE"] = str(self.root / "hf")
        answers = "\n".join(["", "123:abc", "", "", "7, 8", "08:30", str(self.files), "n"]) + "\n"
        result = self.ok("agent", "setup", input=answers)
        self.assertIn("No downloaded chat model yet", result.stdout)
        self.assertIn("@unlaw_test_bot", result.stdout)
        env = self.unlaw / ".env"
        self.assertEqual(env.read_text(encoding="utf-8"), "TELEGRAM_BOT_TOKEN=123:abc\n")
        self.assertEqual(env.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("123:abc", (self.unlaw / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(self.ok("config", "get", "telegram.chat_id").stdout.strip(), "42")
        self.assertEqual(json.loads(self.ok("config", "get", "agent.allowed_ids").stdout), ["7", "8"])
        self.assertEqual(self.ok("config", "get", "agent.digest_time").stdout.strip(), "08:30")
        self.assertEqual(json.loads(self.ok("config", "get", "agent.roots").stdout), [str(self.files)])

    def test_setup_without_telegram_only_sets_model_and_folders(self) -> None:
        self.env["HF_HUB_CACHE"] = str(self.root / "hf")
        self.ok("agent", "setup", input="n\n~/work\n")
        self.assertFalse((self.unlaw / ".env").exists())
        self.assertEqual(json.loads(self.ok("config", "get", "agent.roots").stdout), ["~/work"])

    def test_model_choice_by_number(self) -> None:
        from unlawful import agent

        models = [{"id": "Qwen-chat", "type": "text", "runnable": True}, {"id": "Vision-chat", "type": "vision", "runnable": True}]
        saved: list[tuple[str, object]] = []
        config = {"agent": {"model": "auto"}}
        with patch.object(agent, "_chat_models", return_value=models), patch.object(
            agent, "_set", lambda key, value: saved.append((key, value))
        ), patch.object(sys, "stdin", io.StringIO("2\n")):
            agent._choose_model(config)
        self.assertEqual(saved, [("agent.model", "Vision-chat")])

    def test_ula_and_unlawagent_are_ul_agent(self) -> None:
        if shutil.which("cargo") is None:
            self.skipTest("cargo is required")
        subprocess.run(["cargo", "build", "--quiet", "--bin", "ula", "--bin", "unlawagent"], cwd=ROOT, check=True)
        for name in ("ula", "unlawagent"):
            result = subprocess.run(
                [str(ROOT / "target" / "debug" / name), "plan"], env=self.env, capture_output=True, text=True, timeout=60, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "Nothing is scheduled.\n")
