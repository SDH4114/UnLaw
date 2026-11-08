from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from unlawful.desk import Conflict, Desk, Pomodoro, desk_settings, stats
from unlawful.kanban import KanbanBoard, card, complete_task, quick_text, reopen_task, write_board

BOARD = """---

kanban-plugin: board

---

Some note above the columns.

## To do

- [ ] Write #work report @{2026-10-29}
\twith a detail line
- [ ] Call [[Mom|mom]] #home

## Doing

- [ ] Fix the bike

## Completed

- [x] Old one  [completion:: 2026-10-28]

%% kanban:settings
```
{"kanban-plugin":"board","lane-width":300}
```
%%
"""
TODAY = date(2026, 10, 30)


class KanbanTests(unittest.TestCase):
    def test_untouched_board_renders_back_unchanged(self) -> None:
        self.assertEqual(KanbanBoard.parse(BOARD).render(), BOARD)

    def test_cards_expose_tags_due_dates_links_and_completion(self) -> None:
        board = KanbanBoard.parse(BOARD)
        first = card(board.sections[0].tasks[0])
        self.assertEqual(first["tags"], ["work"])
        self.assertEqual(first["due"], "2026-10-29")
        self.assertEqual(first["details"], ["with a detail line"])
        self.assertEqual(card(board.sections[0].tasks[1])["links"], ["Mom"])
        old = card(board.sections[2].tasks[0])
        self.assertTrue(old["checked"])
        self.assertEqual(old["completed"], "2026-10-28")

    def test_quick_dates_become_obsidian_due_dates(self) -> None:
        self.assertEqual(quick_text("a @today", TODAY), "a @{2026-10-30}")
        self.assertEqual(quick_text("b @завтра #x", TODAY), "b @{2026-10-31} #x")
        self.assertEqual(quick_text("c @+3", TODAY), "c @{2026-11-02}")
        self.assertEqual(quick_text("d @2026-12-01", TODAY), "d @{2026-12-01}")
        self.assertEqual(
            quick_text("mail me@example.com @someone", TODAY),
            "mail me@example.com @someone",
        )
        self.assertEqual(quick_text("kept @{2026-01-01}", TODAY), "kept @{2026-01-01}")

    def test_complete_then_reopen_restores_the_line(self) -> None:
        task = ["- [ ] Task #a"]
        self.assertEqual(complete_task(task, TODAY), "Task #a")
        self.assertEqual(task[0], "- [x] Task #a  [completion:: 2026-10-30]")
        reopen_task(task)
        self.assertEqual(task[0], "- [ ] Task #a")


ARCHIVE_BOARD = """---

kanban-plugin: board

---

## To do

- [ ] Live card

***

## Archive

- [x] Old card

%% kanban:settings
```
{"kanban-plugin":"board"}
```
%%
"""


class KanbanFileFormatTests(unittest.TestCase):
    def test_obsidian_archive_footer_is_kept_and_not_numbered(self) -> None:
        board = KanbanBoard.parse(ARCHIVE_BOARD)
        self.assertEqual([section.name for section in board.sections], ["To do"])
        self.assertEqual([number for number, _, _ in board.numbered_tasks()], [1])
        self.assertEqual(board.sections[0].tasks, [["- [ ] Live card"]])
        self.assertEqual(board.render(), ARCHIVE_BOARD)

    def test_crlf_files_keep_crlf_and_odd_separators_stay_inside_lines(self) -> None:
        text = BOARD.replace("Call [[Mom|mom]]", "Call\x0c[[Mom|mom]]\x85now").replace("\n", "\r\n")
        board = KanbanBoard.parse(text)
        self.assertEqual(board.sections[0].tasks[1], ["- [ ] Call\x0c[[Mom|mom]]\x85now #home"])
        self.assertEqual(board.render(), text)

    def test_write_board_keeps_the_file_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TODO.md"
            path.write_text(BOARD, encoding="utf-8")
            path.chmod(0o644)
            write_board(path, KanbanBoard.parse(BOARD))
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)


class DeskTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "TODO.md"
        self.path.write_text(BOARD, encoding="utf-8")
        self.now = [1_000_000.0]
        config = {
            "todo": {"completed_column": "Completed"},
            "desk": {"pomodoro": {"work": 25, "cycles": 2}},
        }
        self.desk = Desk(
            self.path, config, self.root / "state", clock=lambda: self.now[0]
        )
        self.desk.today = lambda: TODAY

    def change(self, **request: object) -> dict:
        return self.desk.change(
            {"version": self.desk.board_json()["version"], **request}
        )

    def line(self, column: int, index: int) -> str:
        return self.desk.board_json()["columns"][column]["cards"][index]["line"]

    def test_add_move_done_reopen_and_delete_keep_the_rest_of_the_file(self) -> None:
        self.change(op="add", column=1, text="Plan trip @tomorrow #travel")
        self.assertIn("- [ ] Plan trip @{2026-10-31} #travel", self.path.read_text())
        self.change(
            op="move", column=0, index=0, line=self.line(0, 0), to_column=1, to_index=0
        )
        doing = self.desk.board_json()["columns"][1]["cards"]
        self.assertEqual(
            doing[0]["title"], "Write #work report @{2026-10-29}"
        )
        self.assertEqual(doing[0]["details"], ["with a detail line"])
        self.change(op="done", column=1, index=0, line=self.line(1, 0))
        done = self.desk.board_json()["columns"][2]["cards"]
        self.assertEqual(done[-1]["completed"], "2026-10-30")
        self.change(op="reopen", column=2, index=1, line=self.line(2, 1))
        self.assertEqual(
            self.desk.board_json()["columns"][0]["cards"][-1]["title"],
            "Write #work report @{2026-10-29}",
        )
        self.change(op="delete", column=0, index=0, line=self.line(0, 0))
        text = self.path.read_text()
        self.assertNotIn("Call [[Mom|mom]]", text)
        self.assertIn("Some note above the columns.", text)
        self.assertTrue(
            text.endswith('{"kanban-plugin":"board","lane-width":300}\n```\n%%\n')
        )

    def test_stale_version_or_changed_card_is_a_conflict(self) -> None:
        version = self.desk.board_json()["version"]
        self.path.write_text(
            BOARD.replace("Fix the bike", "Fix the car"), encoding="utf-8"
        )
        with self.assertRaises(Conflict):
            self.desk.change(
                {"version": version, "op": "add", "column": 0, "text": "x"}
            )
        with self.assertRaises(Conflict):
            self.change(op="delete", column=1, index=0, line="- [ ] Fix the bike")
        self.assertIn("Fix the car", self.path.read_text())

    def test_bad_requests_are_rejected_without_writing(self) -> None:
        before = self.path.read_text()
        for request in (
            {"op": "add", "column": 9, "text": "x"},
            {"op": "add", "column": 0, "text": "   "},
            {"op": "add", "column": True, "text": "x"},
            {
                "op": "move",
                "column": 0,
                "index": 0,
                "line": self.line(0, 0),
                "to_column": 7,
            },
            {"op": "column", "name": "to do"},
            {"op": "explode"},
        ):
            with self.subTest(request=request), self.assertRaises(ValueError):
                self.change(**request)
        self.assertEqual(self.path.read_text(), before)

    def test_switching_boards_creates_from_template_and_remembers_recent(self) -> None:
        other = self.root / "Project.md"
        with self.assertRaises(FileNotFoundError):
            self.desk.switch(str(other), create=False)
        board = self.desk.switch(str(other), create=True)
        self.assertEqual(
            [column["name"] for column in board["columns"]], ["To do", "Doing", "Done"]
        )
        self.assertTrue(board["columns"][1]["doing"])
        self.assertEqual(self.desk.recent(), [str(other.resolve())])
        with self.assertRaises(ValueError):
            self.desk.switch(str(self.root / "notes.txt"), create=True)


class PomodoroTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.now = [1_000_000.0]
        settings = desk_settings(
            {
                "desk": {
                    "pomodoro": {
                        "work": 25,
                        "short_break": 5,
                        "long_break": 15,
                        "cycles": 2,
                    }
                }
            }
        )
        self.timer = Pomodoro(Path(temporary.name), settings, clock=lambda: self.now[0])

    def test_cycles_breaks_pause_and_log(self) -> None:
        self.timer.act("start", card_title="Write report")
        self.now[0] += 10 * 60
        paused = self.timer.act("pause")
        self.assertTrue(paused["paused"])
        self.now[0] += 60 * 60
        self.assertIsNone(self.timer.tick())
        self.assertEqual(self.timer.act("resume")["remaining"], 15 * 60)
        self.now[0] += 15 * 60
        self.assertEqual(
            self.timer.tick(),
            {"ended": "work", "next": "short", "card": "Write report"},
        )
        self.assertEqual(self.timer.status()["remaining"], 5 * 60)
        self.now[0] += 5 * 60
        self.assertEqual(self.timer.tick()["next"], "idle")
        self.timer.act("start")
        self.now[0] += 25 * 60
        self.assertEqual(
            self.timer.tick()["next"], "long", "every second focus ends in a long break"
        )
        entries = self.timer.entries()
        self.assertEqual([entry["minutes"] for entry in entries], [25.0, 25.0])
        self.assertEqual(entries[0]["card"], "Write report")

    def test_stats_count_focus_done_tasks_and_streak(self) -> None:
        entries = [
            {"end": "2026-10-30T10:00:00+04:00", "minutes": 25, "card": "A"},
            {"end": "2026-10-29T10:00:00+04:00", "minutes": 50, "card": "B"},
            {"end": "broken"},
        ]
        result = stats(KanbanBoard.parse(BOARD), entries, TODAY)
        self.assertEqual(
            result["today"],
            {"date": "2026-10-30", "pomodoros": 1, "minutes": 25.0, "done": 0},
        )
        self.assertEqual(result["week"][-3]["done"], 1)
        self.assertEqual(result["streak"], 3)
        self.assertEqual(result["cards"][0], {"card": "B", "minutes": 50.0})

    def test_bad_settings_fall_back_to_defaults(self) -> None:
        settings = desk_settings(
            {"desk": {"port": "x", "pomodoro": {"work": -1, "cycles": True}}}
        )
        self.assertEqual(
            (settings["port"], settings["work"], settings["cycles"]), (8765, 25, 4)
        )


class DeskServerTests(unittest.TestCase):
    """The seeded command as a real process: auth, sync with `ul todo`, the timer CLI."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        (self.vault / "TODO.md").write_text(BOARD, encoding="utf-8")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        for tool in ("osascript", "open"):
            fake = bin_dir / tool
            fake.write_text(
                f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{self.root}/{tool}.log"\n',
                encoding="utf-8",
            )
            fake.chmod(0o755)
        self.env = {
            "HOME": str(self.root / "home"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin",
        }
        from unlawful.config import ensure_layout, set_config_value

        with patch.dict(os.environ, self.env):
            commands = ensure_layout() / "commands"
            set_config_value("todo.vault_path", str(self.vault))
        self.desk = commands / "desk" / "main.py"
        self.todo = commands / "todo" / "main.py"

    def run_seed(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def start(self) -> tuple[int, str]:
        process = subprocess.Popen(
            [sys.executable, str(self.desk), "--port", "0", "--no-open"],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def stop() -> None:
            process.terminate()
            process.wait(timeout=10)
            process.stdout.close()
            process.stderr.close()

        self.addCleanup(stop)
        line = process.stdout.readline()
        if not line.startswith("Desk: http://127.0.0.1:"):
            process.terminate()
            self.fail(line + process.stderr.read())
        address, token = line.split()[1].split("/?token=")
        return int(address.rsplit(":", 1)[1]), token

    def request(
        self,
        port: int,
        method: str,
        path: str,
        body: object = None,
        headers: dict | None = None,
    ):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.request(
                method, path, None if body is None else json.dumps(body), headers or {}
            )
            response = connection.getresponse()
            data = response.read()
            return response.status, json.loads(
                data
            ) if data and "json" in response.getheader("Content-Type", "") else data
        finally:
            connection.close()

    def test_help_needs_no_config(self) -> None:
        result = subprocess.run(
            [sys.executable, str(self.desk), "--help"],
            env={**self.env, "XDG_CONFIG_HOME": str(self.root / "missing")},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ul desk pomodoro", result.stdout)

    def test_server_guards_host_and_token_and_syncs_with_todo(self) -> None:
        port, token = self.start()
        auth = {"X-Desk-Token": token}
        self.assertEqual(self.request(port, "GET", "/")[0], 403)
        self.assertEqual(self.request(port, "GET", f"/?token={token}")[0], 200)
        self.assertEqual(self.request(port, "GET", "/api/board")[0], 403)
        self.assertEqual(
            self.request(
                port, "GET", "/api/board", headers={**auth, "Host": "evil.example"}
            )[0],
            403,
        )
        status, board = self.request(port, "GET", "/api/board", headers=auth)
        self.assertEqual(status, 200)
        self.assertEqual(
            self.request(
                port,
                "GET",
                "/api/board",
                headers={**auth, "If-None-Match": board["version"]},
            )[0],
            304,
        )

        status, board = self.request(
            port,
            "POST",
            "/api/board",
            {
                "op": "add",
                "version": board["version"],
                "column": 1,
                "text": "From the page",
            },
            auth,
        )
        self.assertEqual(status, 200)
        listed = self.run_seed(self.todo)
        self.assertIn("From the page", listed.stdout)

        added = self.run_seed(self.todo, "add", "From the terminal")
        self.assertEqual(added.returncode, 0, added.stderr)
        status, conflict = self.request(
            port,
            "POST",
            "/api/board",
            {"op": "add", "version": board["version"], "column": 0, "text": "Late"},
            auth,
        )
        self.assertEqual(status, 409)
        titles = [item["title"] for item in conflict["board"]["columns"][0]["cards"]]
        self.assertIn("From the terminal", titles)
        self.assertNotIn("Late", (self.vault / "TODO.md").read_text())

    def test_request_targets_must_be_origin_form_so_the_token_cannot_be_bypassed(self) -> None:
        port, token = self.start()
        auth = {"X-Desk-Token": token}
        for target in (f"http://127.0.0.1:{port}/api/board", "api/board"):
            for headers in ({}, auth):
                self.assertEqual(self.request(port, "GET", target, headers=headers)[0], 400, (target, headers))
        self.assertEqual(self.request(port, "GET", "/api/board", headers=auth)[0], 200)

    def test_todo_keeps_crlf_line_endings(self) -> None:
        board = self.vault / "TODO.md"
        board.write_bytes(BOARD.replace("\n", "\r\n").encode())
        added = self.run_seed(self.todo, "add", "From the terminal")
        self.assertEqual(added.returncode, 0, added.stderr)
        data = board.read_bytes()
        self.assertIn(b"From the terminal\r\n", data)
        self.assertNotIn(b"\r\r", data)
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))

    def test_pomodoro_from_the_terminal_is_the_page_timer(self) -> None:
        port, token = self.start()
        started = self.run_seed(
            self.desk, "pomodoro", "start", "0.01", "--card", "Deep work"
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn("Focus: 00:01 running · Deep work", started.stdout)
        status, timer = self.request(
            port, "GET", "/api/pomodoro", headers={"X-Desk-Token": token}
        )
        self.assertEqual((status, timer["card"]), (200, "Deep work"))
        deadline = time.time() + 10
        while time.time() < deadline and not (self.root / "osascript.log").exists():
            time.sleep(0.2)
        self.assertIn("Focus finished", (self.root / "osascript.log").read_text())
        self.assertEqual(
            self.request(port, "GET", "/api/pomodoro", headers={"X-Desk-Token": token})[
                1
            ]["phase"],
            "short",
        )
        report = self.run_seed(self.desk, "stats")
        self.assertIn("Today: 1 focus session(s)", report.stdout)
        self.assertEqual(self.run_seed(self.desk, "pomodoro", "stop").returncode, 0)

    def test_wrong_arguments_and_missing_board(self) -> None:
        self.assertEqual(self.run_seed(self.desk, "--port", "x").returncode, 2)
        missing = self.run_seed(self.desk, str(self.root / "none.md"), "--no-open")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("ul desk new", missing.stderr)
        created = self.run_seed(self.desk, "new", str(self.root / "Plan.md"))
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertIn("## Doing", (self.root / "Plan.md").read_text())
        self.assertEqual(
            self.run_seed(self.desk, "new", str(self.root / "Plan.md")).returncode,
            2,
            "never overwrites",
        )


if __name__ == "__main__":
    unittest.main()


class DeskGameTests(unittest.TestCase):
    """The Games tab: `ul game --stream` relayed by the desk, records shared with the terminal."""

    setUp = DeskServerTests.setUp
    start = DeskServerTests.start
    request = DeskServerTests.request

    def use_ul(self) -> None:
        from tests import ulbin

        self.env["UNLAW_BIN"] = str(ulbin.binary())

    def call(self, port: int, token: str, path: str, body: object = None):
        return self.request(port, "POST" if body is not None else "GET", path, body, {"X-Desk-Token": token})

    def open_stream(self, port: int, token: str, session: str):
        """A raw socket so closing it really drops the connection."""
        body = json.dumps({"session": session}).encode()
        sock = socket.create_connection(("127.0.0.1", port), timeout=20)
        self.addCleanup(sock.close)
        sock.sendall(
            (
                f"POST /api/game/stream HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
                f"X-Desk-Token: {token}\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode()
            + body
        )
        reader = sock.makefile("rb")
        self.addCleanup(reader.close)
        status = reader.readline()
        self.assertIn(b" 200 ", status)
        while reader.readline().strip():
            pass
        return sock, reader

    @staticmethod
    def screen(frame: dict) -> str:
        return "\n".join("".join(run[0] for run in line) for line in frame["lines"])

    def frames(self, reader, until, seconds: float = 30.0):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            line = reader.readline()
            if not line:
                return None
            if line.strip():
                message = json.loads(line)
                if until(message):
                    return message
        self.fail("no matching frame in time")

    def test_games_report_the_shared_records(self) -> None:
        self.use_ul()
        runtime = self.root / "config" / "unlaw" / "data" / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "arcade.toml").write_text("[snake]\nnormal = 12\n[minesweeper]\neasy = 40\n", encoding="utf-8")
        port, token = self.start()
        status, data = self.call(port, token, "/api/games")
        self.assertEqual(status, 200)
        self.assertTrue(data["available"])
        games = {game["name"]: game for game in data["games"]}
        self.assertEqual(list(games), ["tetris", "snake", "minesweeper", "invaders", "chomp", "dash", "pingpong"])
        self.assertEqual(games["snake"]["best"], {"normal": 12})
        self.assertEqual(games["minesweeper"]["best"], {"easy": 40})
        self.assertTrue(games["minesweeper"]["lower"])
        self.assertEqual(self.request(port, "GET", "/api/games")[0], 403)

    def test_a_game_streams_frames_takes_input_and_ends_with_esc(self) -> None:
        self.use_ul()
        port, token = self.start()
        for bad in (
            {"game": "rm -rf /", "rows": 30, "cols": 90},
            {"game": "snake", "level": "insane", "rows": 30, "cols": 90},
            {"level": "hard", "rows": 30, "cols": 90},
            {"game": "snake", "rows": "30", "cols": 90},
        ):
            self.assertEqual(self.call(port, token, "/api/game/start", bad)[0], 400, bad)
        status, data = self.call(port, token, "/api/game/start", {"game": "snake", "level": "easy", "rows": 5, "cols": 999})
        self.assertEqual(status, 200)
        session = data["session"]
        _, reader = self.open_stream(port, token, session)
        first = self.frames(reader, lambda frame: "lines" in frame)
        self.assertEqual((first["rows"], first["cols"]), (24, 200), "size is clamped")
        self.assertIn("SNAKE · easy", self.screen(first))
        status, _ = self.call(port, token, "/api/game/stream", {"session": session})
        self.assertEqual(status, 410, "one reader per game")
        events = [{"key": "up"}, {"release": "up"}, {"hover": {"y": 1, "x": 2}}, {"click": {"y": 3, "x": 4, "button": "right"}}, {"resize": {"rows": 30, "cols": 90}}]
        self.assertEqual(self.call(port, token, "/api/game/input", {"session": session, "events": events})[0], 200)
        for bad in ([{"key": "\u0003"}], [{"release": "ab"}], [{"key": "up", "x": 1}, {"click": {"y": -1, "x": 0}}], "up", [{"run": "ls"}]):
            self.assertEqual(self.call(port, token, "/api/game/input", {"session": session, "events": bad})[0], 400, bad)
        self.assertEqual(self.call(port, token, "/api/game/input", {"session": "nope", "events": []})[0], 410)
        resized = self.frames(reader, lambda frame: frame.get("cols") == 90)
        self.assertEqual(resized["rows"], 30)
        self.call(port, token, "/api/game/input", {"session": session, "events": [{"key": "p"}]})
        self.frames(reader, lambda frame: "PAUSED" in self.screen(frame) if "lines" in frame else False)
        self.call(port, token, "/api/game/input", {"session": session, "events": [{"key": "esc"}]})
        self.frames(reader, lambda frame: frame.get("end") is True)
        self.assertEqual(self.call(port, token, "/api/game/input", {"session": session, "events": [{"key": "up"}]})[0], 410)

    def test_a_record_made_in_the_desk_lands_in_arcade_toml(self) -> None:
        self.use_ul()
        port, token = self.start()
        # Normal Snake dies at the wall when nobody steers.
        session = self.call(port, token, "/api/game/start", {"game": "snake", "level": "normal", "rows": 24, "cols": 72})[1]["session"]
        _, reader = self.open_stream(port, token, session)
        self.frames(reader, lambda frame: "lines" in frame and "GAME OVER" in self.screen(frame), seconds=60)
        time.sleep(0.7)  # the end box ignores keys for half a second
        self.call(port, token, "/api/game/input", {"session": session, "events": [{"key": "esc"}]})
        self.frames(reader, lambda frame: frame.get("end") is True)
        saved = self.root / "config" / "unlaw" / "data" / "runtime" / "arcade.toml"
        self.assertIn("[snake]", saved.read_text(encoding="utf-8"))
        games = {game["name"]: game for game in self.call(port, token, "/api/games")[1]["games"]}
        self.assertIn("normal", games["snake"]["best"])

    def test_closing_the_page_or_stop_ends_the_game_process(self) -> None:
        self.use_ul()
        port, token = self.start()
        session = self.call(port, token, "/api/game/start", {"rows": 30, "cols": 90})[1]["session"]
        sock, reader = self.open_stream(port, token, session)
        self.assertIn("A R C A D E", self.screen(self.frames(reader, lambda frame: "lines" in frame)))
        reader.close()
        sock.close()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.call(port, token, "/api/game/input", {"session": session, "events": []})[0] == 410:
                break
            time.sleep(0.3)
        else:
            self.fail("the game outlived its page")
        session = self.call(port, token, "/api/game/start", {"game": "tetris", "level": "hard", "rows": 30, "cols": 90})[1]["session"]
        self.assertEqual(self.call(port, token, "/api/game/stop", {"session": session})[0], 200)
        self.assertEqual(self.call(port, token, "/api/game/input", {"session": session, "events": []})[0], 410)

    def test_without_the_game_feature_the_tab_says_so(self) -> None:
        fake = self.root / "bin" / "ul"
        fake.write_text("#!/bin/sh\necho 'Unknown command: game' >&2\nexit 2\n", encoding="utf-8")
        fake.chmod(0o755)
        self.env["UNLAW_BIN"] = str(fake)
        port, token = self.start()
        self.assertFalse(self.call(port, token, "/api/games")[1]["available"])
        status, data = self.call(port, token, "/api/game/start", {"game": "snake", "rows": 30, "cols": 90})
        self.assertEqual(status, 400)
        self.assertIn("feature", data["error"])

    def test_ul_game_stream_runs_without_a_terminal(self) -> None:
        from tests import ulbin

        result = subprocess.run(
            [str(ulbin.binary()), "game", "--stream", "--size", "30x90"],
            input='{"key":"down"}\nnot json\n{"key":"q"}\n',
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        frames = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertGreaterEqual(len(frames), 2, "the menu moved after Down")
        self.assertIn("A R C A D E", self.screen(frames[0]))
        bad = subprocess.run([str(ulbin.binary()), "game", "--stream", "--size", "big"], env=self.env, capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("ROWSxCOLS", bad.stderr)


class DeskStudioTests(unittest.TestCase):
    """The Studio tab drives the real `ul capture` (fake screencapture/ffmpeg on PATH)."""

    setUp = DeskServerTests.setUp
    start = DeskServerTests.start
    request = DeskServerTests.request
    call = DeskGameTests.call

    def media(self) -> None:
        from tests import ulbin
        from tests.test_command_paths import (
            FAKE_DISPLAYS,
            FAKE_FFMPEG,
            FAKE_FFPROBE,
            FAKE_SCREENCAPTURE,
            FAKE_SIPS,
        )

        bin_dir = self.root / "bin"
        for name, body in (
            ("screencapture", FAKE_SCREENCAPTURE),
            ("ffmpeg", FAKE_FFMPEG),
            ("ffprobe", FAKE_FFPROBE),
            ("sips", FAKE_SIPS),
            ("system_profiler", FAKE_DISPLAYS),
        ):
            tool = bin_dir / name
            tool.write_text(f"#!{sys.executable}\nimport sys\n{body}", encoding="utf-8")
            tool.chmod(0o755)
        self.env["UNLAW_BIN"] = str(ulbin.binary())
        self.env["UNLAW_PYTHON"] = sys.executable
        self.captures = self.root / "config" / "unlaw" / "data" / "captures"
        (self.root / "home").mkdir(exist_ok=True)

    def wait_saved(self, port: int, token: str) -> dict:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status = self.call(port, token, "/api/studio/status")[1]
            if not status["active"] and status.get("saving_done"):
                return status["saving_done"]
            time.sleep(0.2)
        self.fail("the recording was not saved")

    def raw(self, port: int, path: str, headers: dict | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
        try:
            connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_record_pause_stop_and_play_from_the_library(self) -> None:
        self.media()
        port, token = self.start()
        overview = self.call(port, token, "/api/studio")[1]
        self.assertTrue(overview["available"])
        self.assertEqual(overview["settings"]["audio_device"], "default")
        self.assertFalse(self.call(port, token, "/api/studio/status")[1]["active"])
        devices = self.call(port, token, "/api/studio/devices")[1]
        self.assertEqual(devices["cameras"], ["FaceTime HD Camera"])
        for bad in (
            {"mode": "hologram"},
            {"mode": "audio", "mic": "--rm"},
            {"mode": "screen", "display": 0},
            {"mode": "screen", "format": "exe"},
        ):
            self.assertEqual(self.call(port, token, "/api/studio/record", bad)[0], 400, bad)
        status, data = self.call(port, token, "/api/studio/record", {"mode": "audio", "mic": "Studio"})
        self.assertEqual(status, 400)
        self.assertIn("no microphone named", data["error"])
        status, data = self.call(port, token, "/api/studio/record", {"mode": "screen-camera", "display": 2, "system_audio": False, "clicks": False, "format": "mp4"})
        self.assertEqual(status, 200, data)
        self.assertEqual((data["phase"], data["camera"]), ("recording", True))
        self.assertEqual(self.call(port, token, "/api/studio/record", {"mode": "audio"})[0], 400, "one recording at a time")
        self.assertTrue(self.call(port, token, "/api/studio/pause", {})[1]["paused"])
        self.assertFalse(self.call(port, token, "/api/studio/resume", {})[1]["paused"])
        self.assertEqual(self.call(port, token, "/api/studio/stop", {})[1], {"saving": True})
        saved = Path(self.wait_saved(port, token)["saved"])
        self.assertEqual(saved.suffix, ".mp4")
        self.assertTrue(saved.is_file())
        library = self.call(port, token, "/api/studio/library")[1]
        self.assertEqual([item["name"] for item in library], [saved.name])
        status, headers, body = self.raw(port, f"/media/file?t={token}&name={saved.name}", {"Range": "bytes=2-5"})
        self.assertEqual((status, headers["Content-Range"], headers["Content-Type"]), (206, f"bytes 2-5/{saved.stat().st_size}", "video/mp4"))
        self.assertEqual(body, saved.read_bytes()[2:6])
        self.assertEqual(self.raw(port, f"/media/file?t={token}&name={saved.name}", {"Range": "bytes=999-"})[0], 416)
        self.assertEqual(self.raw(port, f"/media/file?name={saved.name}")[0], 403, "media needs the token")
        self.assertEqual(self.raw(port, f"/media/file?t={token}&name=..%2F..%2Fconfig.toml")[0], 404)
        self.assertEqual(self.raw(port, f"/media/file?t={token}&name=.parts")[0], 404)
        wave = self.call(port, token, f"/api/studio/wave?name={saved.name}&bars=20")[1]
        self.assertEqual(len(wave["peaks"]), 20)
        self.assertTrue(all(0 <= value <= 1 for value in wave["peaks"]))
        self.assertEqual(self.call(port, token, f"/api/studio/wave?name={saved.name}&bars=5")[0], 400)
        self.assertEqual(self.call(port, token, "/api/studio/wave?name=..%2Fx.mov")[0], 404)

    def test_trim_rejects_non_finite_seconds(self) -> None:
        self.media()
        port, token = self.start()
        (self.captures / "recordings").mkdir(parents=True, exist_ok=True)
        (self.captures / "recordings" / "talk.mov").write_bytes(b"video")
        for value in (float("nan"), float("inf")):
            status, data = self.call(port, token, "/api/studio/action", {"action": "trim", "name": "talk.mov", "from": value})
            self.assertEqual(status, 400, value)
            self.assertEqual(data["error"], "from must be seconds", value)

    def test_screenshots_thumbnails_edits_and_trash(self) -> None:
        self.media()
        port, token = self.start()
        shot = self.call(port, token, "/api/studio/shot", {"kind": "screen", "display": 2, "delay": 0})[1]
        image = Path(shot["saved"])
        self.assertEqual(image.parent, self.captures / "screenshots")
        self.assertEqual(self.call(port, token, "/api/studio/shot", {"kind": "area", "clipboard": True})[1]["clipboard"], True)
        self.assertEqual(self.call(port, token, "/api/studio/shot", {"kind": "selfie"})[0], 400)
        status, headers, body = self.raw(port, f"/media/thumb?t={token}&name={image.name}")
        self.assertEqual((status, headers["Content-Type"], body), (200, "image/jpeg", b"jpg"))
        video = self.captures / "recordings" / "talk.mov"
        video.write_bytes(b"video")
        trimmed = self.call(port, token, "/api/studio/action", {"action": "trim", "name": "talk.mov", "from": 1.5, "to": 3})[1]
        self.assertTrue(trimmed["saved"].endswith("talk trim.mov"))
        self.assertTrue(self.call(port, token, "/api/studio/action", {"action": "convert", "name": "talk.mov", "to": "gif"})[1]["saved"].endswith("talk.gif"))
        for bad in (
            {"action": "rm", "name": "talk.mov"},
            {"action": "trim", "name": "talk.mov"},
            {"action": "convert", "name": "talk.mov", "to": "exe"},
        ):
            self.assertEqual(self.call(port, token, "/api/studio/action", bad)[0], 400, bad)
        self.assertEqual(self.call(port, token, "/api/studio/action", {"action": "delete", "name": "../TODO.md"})[0], 404)
        result = self.call(port, token, "/api/studio/action", {"action": "delete", "name": image.name})
        self.assertEqual(result[0], 200, result)
        trashed = result[1]["trashed"]
        self.assertEqual(Path(trashed).parent, self.root / "home" / ".Trash")
        self.assertFalse(image.exists())

    def test_without_the_capture_command_the_tab_says_so(self) -> None:
        fake = self.root / "bin" / "ul"
        fake.write_text("#!/bin/sh\necho 'Unknown command: capture' >&2\nexit 2\n", encoding="utf-8")
        fake.chmod(0o755)
        self.env["UNLAW_BIN"] = str(fake)
        port, token = self.start()
        self.assertFalse(self.call(port, token, "/api/studio")[1]["available"])
        status, data = self.call(port, token, "/api/studio/record", {"mode": "audio"})
        self.assertEqual(status, 400)
        self.assertIn("not installed", data["error"])


class DeskFailureTests(unittest.TestCase):
    """Failure paths stay local and never invoke the user's tools or data."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {
            "HOME": str(self.root / "home"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "PATH": str(self.root / "bin"),
        })
        environment.start()
        self.addCleanup(environment.stop)

    def test_parallel_feature_probes_do_not_report_missing_commands(self) -> None:
        import threading
        from types import SimpleNamespace

        from unlawful import desk

        for relay, help_text in (
            (desk.Studio("/fake-ul", {}), "record [screen"),
            (desk.Arcade("/fake-ul", self.root / "scores", "normal"), "--stream"),
        ):
            with self.subTest(relay=type(relay).__name__):
                entered, release = threading.Event(), threading.Event()
                answers = []

                def probe(*args, entered=entered, release=release, help_text=help_text, **kwargs):
                    entered.set()
                    release.wait(2)
                    return SimpleNamespace(returncode=0, stdout=help_text)

                with patch.object(desk.subprocess, "run", side_effect=probe) as run:
                    second_started, second_done = threading.Event(), threading.Event()

                    def check_second(relay=relay, answers=answers, second_started=second_started, second_done=second_done):
                        second_started.set()
                        answers.append(relay.available())
                        second_done.set()

                    first = threading.Thread(target=lambda relay=relay, answers=answers: answers.append(relay.available()))
                    second = threading.Thread(target=check_second)
                    first.start()
                    self.assertTrue(entered.wait(1))
                    second.start()
                    self.assertTrue(second_started.wait(1))
                    finished_early = second_done.wait(0.05)
                    release.set()
                    first.join(2)
                    second.join(2)
                self.assertFalse(finished_early, "the second request must wait for the first probe")
                self.assertEqual(answers, [True, True])
                self.assertEqual(run.call_count, 1)

    def test_stalled_game_input_has_a_deadline_and_can_be_stopped(self) -> None:
        import signal
        import threading

        from unlawful import desk

        fake = self.root / "ul"
        fake.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(30)\n")
        fake.chmod(0o755)
        arcade = desk.Arcade(str(fake), self.root / "scores", "normal")
        arcade._available = True
        session = arcade.start("snake", "normal", 30, 90)
        process = arcade.process
        ended = threading.Event()

        def feed():
            try:
                for _ in range(1000):
                    arcade.send(session, [{"key": "up"}] * 64)
            except LookupError:
                ended.set()

        sender = threading.Thread(target=feed, daemon=True)
        sender.start()
        try:
            self.assertTrue(ended.wait(3), "a full game pipe must not hold the relay lock forever")
            arcade.stop()
            sender.join(1)
            self.assertIsNotNone(process.poll())
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            sender.join(2)
            arcade.stop()

    def test_studio_timeout_stops_helper_descendants(self) -> None:
        import signal

        from unlawful import desk

        pid_file = self.root / "child.pid"
        child = self.root / "child.py"
        child.write_text(f"import os, time\nopen({str(pid_file)!r}, 'w').write(str(os.getpid()))\ntime.sleep(30)\n")
        fake = self.root / "ul"
        fake.write_text(f"#!{sys.executable}\nimport subprocess, time\nsubprocess.Popen([{sys.executable!r}, {str(child)!r}])\ntime.sleep(30)\n")
        fake.chmod(0o755)
        studio = desk.Studio(str(fake), {})
        studio._available = True
        try:
            with self.assertRaises(desk.StudioError):
                studio.run("preview", timeout=1)
            self.assertTrue(pid_file.exists(), "the fake helper must have started")
            pid = int(pid_file.read_text())
            for _ in range(100):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.01)
            else:
                self.fail("a capture helper outlived the request timeout")
        finally:
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_missing_capture_binary_finishes_the_background_save_with_an_error(self) -> None:
        import threading

        from unlawful import desk

        studio = desk.Studio(str(self.root / "missing-ul"), {})
        studio._available = True
        with patch.object(threading, "excepthook"):
            studio.stop()
            studio.saving.join(2)
        self.assertIsInstance(studio.last, dict)
        self.assertIn("error", studio.last)

    def test_partial_or_corrupt_pomodoro_state_recovers_to_idle(self) -> None:
        timer = Pomodoro(self.root / "timer", desk_settings({}))
        timer.directory.mkdir()
        for state in (
            {"phase": "work"},
            {"phase": "unknown"},
            {"phase": []},
            {"phase": "work", "ends_at": "tomorrow"},
            {"phase": "work", "ends_at": float("nan")},
            {"cycle": "one"},
            {"length": 10 ** 400},
        ):
            with self.subTest(state=state):
                timer.state_file.write_text(json.dumps(state))
                self.assertIsNone(timer.tick())
                self.assertEqual(timer.status()["phase"], "idle")
                self.assertEqual(timer.act("start")["phase"], "work")

    def test_non_ascii_tokens_are_forbidden(self) -> None:
        import threading

        from unlawful import desk

        board = self.root / "TODO.md"
        board.write_text(BOARD)
        state = Desk(board, {}, self.root / "desk")
        server = desk.make_server(
            state, 0, "secret", True,
            arcade=desk.Arcade(None, self.root / "scores", "normal"),
            studio=desk.Studio(None, {}),
        )
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            connection = http.client.HTTPConnection(*server.server_address, timeout=2)
            try:
                connection.request("GET", "/?token=%D1%8F")
                response = connection.getresponse()
                self.assertEqual(response.status, 403)
                response.read()
            finally:
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)
