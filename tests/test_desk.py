from __future__ import annotations

import http.client
import json
import os
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
from unlawful.kanban import KanbanBoard, card, complete_task, quick_text, reopen_task

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
