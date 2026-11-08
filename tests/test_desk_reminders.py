"""The Apple Reminders layer and the boards folder of `ul desk`, without touching the real Reminders."""

from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from unlawful.desk import Conflict, Desk, board_file  # noqa: E402
from unlawful.reminders import (
    REMINDERS,
    Reminders,
    RemindersError,
    boards_folder,
    split_due,
)  # noqa: E402

TODAY = date(2026, 11, 8)


class FakeReminders(Reminders):
    """EventKit replaced by a dict; `call` sees exactly the requests the real script would get."""

    def __init__(self) -> None:
        super().__init__(clock=lambda: 0.0)
        self.lists = [
            {"id": "L1", "title": "Reminders"},
            {"id": "L2", "title": "Projects"},
        ]
        self.items = {
            "R1": {
                "title": "Buy milk",
                "list": "L1",
                "due": "2026-11-09",
                "notes": "2 liters\n\nfresh",
                "created": 1,
            },
            "R2": {
                "title": "Ship  desk\nlayer",
                "list": "L2",
                "due": None,
                "notes": "",
                "created": 2,
            },
            "R3": {
                "title": "Call mom",
                "list": "L1",
                "due": None,
                "notes": "",
                "created": 3,
            },
        }
        self.requests: list[dict] = []

    def call(self, request: dict) -> dict:
        op = request["op"]
        if op != "list":
            self.requests.append(request)
        if op == "list":
            return {
                "lists": self.lists,
                "items": [{"id": key, **value} for key, value in self.items.items()],
            }
        if op == "add":
            key = f"R{len(self.items) + 10}"
            self.items[key] = {
                "title": request["title"],
                "list": request["list"],
                "due": request["due"],
                "notes": "",
                "created": 99,
            }
            return {"id": key}
        if op == "new_list":
            self.lists.append(
                {"id": f"L{len(self.lists) + 1}", "title": request["title"]}
            )
            return {}
        if request["id"] not in self.items:
            raise RemindersError("the reminder no longer exists")
        if op == "edit":
            self.items[request["id"]].update(title=request["title"], due=request["due"])
        elif op == "move":
            self.items[request["id"]]["list"] = request["list"]
        elif op in {"done", "delete"}:
            del self.items[request["id"]]
        return {}


class SplitDueTests(unittest.TestCase):
    def test_takes_the_date_out_of_the_title(self) -> None:
        self.assertEqual(
            split_due("Buy milk @{2026-11-09}"), ("Buy milk", "2026-11-09")
        )
        self.assertEqual(split_due("Plain"), ("Plain", None))
        self.assertEqual(
            split_due("a @{2026-01-02} b @{2026-03-04}"), ("a b", "2026-01-02")
        )

    def test_a_lone_date_is_not_a_title(self) -> None:
        with self.assertRaises(ValueError):
            split_due("@{2026-11-09}")


class ReminderLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        board = self.root / "TODO.md"
        board.write_text("## To do\n\n- [ ] File card\n", encoding="utf-8")
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config")}):
            self.desk = Desk(board, {"todo": {}}, self.root / "state", layer=REMINDERS)
        self.fake = FakeReminders()
        self.desk.reminders = self.fake
        self.desk.today = lambda: TODAY

    def change(self, **request: object) -> dict:
        return self.desk.change(
            {"version": self.desk.board_json()["version"], **request}
        )

    def test_lists_are_columns_and_open_reminders_are_cards(self) -> None:
        board = self.desk.board_json()
        self.assertEqual(board["layer"], "reminders")
        self.assertEqual(board["path"], REMINDERS)
        self.assertIsNone(board["done_column"])
        self.assertEqual(
            [column["name"] for column in board["columns"]], ["Reminders", "Projects"]
        )
        first = board["columns"][0]["cards"][0]
        self.assertEqual(first["title"], "Buy milk @{2026-11-09}")
        self.assertEqual(first["due"], "2026-11-09")
        self.assertEqual(first["details"], ["2 liters", "fresh"])
        self.assertEqual(board["columns"][1]["cards"][0]["title"], "Ship desk layer")

    def test_the_file_board_is_left_alone(self) -> None:
        before = self.desk.path.read_bytes()
        self.change(op="add", column=0, text="New one")
        self.assertEqual(self.desk.path.read_bytes(), before)

    def test_add_sets_the_due_date_from_quick_text(self) -> None:
        self.change(op="add", column=1, text="Write tests @tomorrow")
        self.assertEqual(
            self.fake.requests[-1],
            {"op": "add", "list": "L2", "title": "Write tests", "due": "2026-11-09"},
        )
        self.assertIn(
            "Write tests @{2026-11-09}",
            [card["title"] for card in self.desk.board_json()["columns"][1]["cards"]],
        )

    def test_edit_move_done_delete_reach_the_right_reminder(self) -> None:
        line = self.desk.board_json()["columns"][0]["cards"][1]["line"]
        self.change(op="edit", column=0, index=1, line=line, text="Call mom today")
        self.assertEqual(
            self.fake.requests[-1],
            {"op": "edit", "id": "R3", "title": "Call mom today", "due": None},
        )
        line = self.desk.board_json()["columns"][0]["cards"][1]["line"]
        self.change(op="move", column=0, index=1, line=line, to_column=1, to_index=0)
        self.assertEqual(
            self.fake.requests[-1], {"op": "move", "id": "R3", "list": "L2"}
        )
        line = self.desk.board_json()["columns"][0]["cards"][0]["line"]
        self.change(op="done", column=0, index=0, line=line)
        self.assertEqual(self.fake.requests[-1], {"op": "done", "id": "R1"})
        line = self.desk.board_json()["columns"][1]["cards"][0]["line"]
        self.change(op="delete", column=1, index=0, line=line)
        self.assertEqual(self.fake.requests[-1], {"op": "delete", "id": "R2"})

    def test_reordering_inside_a_list_changes_nothing(self) -> None:
        line = self.desk.board_json()["columns"][0]["cards"][1]["line"]
        self.change(op="move", column=0, index=1, line=line, to_column=0, to_index=0)
        self.assertEqual(self.fake.requests, [])

    def test_new_column_is_a_new_list_and_duplicates_are_refused(self) -> None:
        self.change(op="column", name="Errands")
        self.assertEqual(self.fake.requests[-1], {"op": "new_list", "title": "Errands"})
        with self.assertRaises(ValueError):
            self.change(op="column", name="projects")

    def test_a_stale_version_or_a_changed_card_is_a_conflict(self) -> None:
        version = self.desk.board_json()["version"]
        self.fake.items["R9"] = {
            "title": "From the phone",
            "list": "L1",
            "due": None,
            "notes": "",
            "created": 9,
        }
        with self.assertRaises(Conflict):
            self.desk.change(
                {"version": version, "op": "add", "column": 0, "text": "x"}
            )
        with self.assertRaises(Conflict):
            self.change(op="done", column=0, index=0, line="- [ ] Something else")
        self.assertEqual(self.fake.requests, [])

    def test_reopen_is_refused(self) -> None:
        line = self.desk.board_json()["columns"][0]["cards"][0]["line"]
        with self.assertRaises(ValueError):
            self.change(op="reopen", column=0, index=0, line=line)

    def test_switching_back_to_a_file_board(self) -> None:
        board = self.desk.switch(str(self.desk.path), create=False)
        self.assertEqual(board["layer"], "file")
        self.assertEqual(board["columns"][0]["cards"][0]["title"], "File card")
        self.assertEqual(self.desk.current, str(self.desk.path))


class BoardsFolderTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_relative_folder_is_inside_the_config_directory(self) -> None:
        self.assertEqual(boards_folder("boards", self.root), self.root / "boards")
        self.assertEqual(boards_folder("", self.root), self.root / "boards")
        self.assertEqual(boards_folder("/abs/place", self.root), Path("/abs/place"))
        self.assertEqual(boards_folder("~/b", self.root), Path.home() / "b")

    def test_a_bare_name_creates_the_folder_and_the_board(self) -> None:
        folder = self.root / "deep" / "boards"
        path = board_file("Work", create=True, boards_dir=folder)
        self.assertEqual(path, (folder / "Work.md").resolve())
        self.assertIn("## To do", path.read_text(encoding="utf-8"))
        self.assertEqual(board_file("Work", boards_dir=folder), path)

    def test_paths_and_md_names_keep_their_old_meaning(self) -> None:
        folder = self.root / "boards"
        with self.assertRaises(FileNotFoundError):
            board_file("Missing", boards_dir=folder)
        with self.assertRaises(ValueError):
            board_file(str(self.root / "notes.txt"), create=True, boards_dir=folder)
        explicit = board_file(
            str(self.root / "Here.md"), create=True, boards_dir=folder
        )
        self.assertEqual(explicit.parent, self.root.resolve())
        self.assertFalse(folder.exists())


FAKE_OSASCRIPT = r"""#!{python}
import json, sys
args = sys.argv[1:]
request = json.loads(args[-1])
with open({log!r}, "a") as log:
    log.write(json.dumps(request) + "\n")
if request["op"] == "list":
    print(json.dumps({{"lists": [{{"id": "L1", "title": "Inbox"}}], "items": [{{"id": "R1", "title": "From Reminders", "list": "L1", "due": None, "notes": "", "created": 1}}]}}))
elif request["op"] == "add":
    print(json.dumps({{"id": "R2"}}))
else:
    print("{{}}")
"""


@unittest.skipUnless(sys.platform == "darwin", "the Reminders layer is macOS only")
class SeedReminderTests(unittest.TestCase):
    """The seeded desk command as a process, with a fake osascript in front of EventKit."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        self.log = self.root / "osascript.log"
        fake = bin_dir / "osascript"
        fake.write_text(
            FAKE_OSASCRIPT.format(python=sys.executable, log=str(self.log)),
            encoding="utf-8",
        )
        fake.chmod(0o755)
        (bin_dir / "open").write_text("#!/bin/sh\n", encoding="utf-8")
        (bin_dir / "open").chmod(0o755)
        self.env = {
            "HOME": str(self.root / "home"),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "PATH": f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin",
        }
        from unlawful.config import ensure_layout, set_config_value

        with patch.dict(os.environ, self.env):
            self.desk = ensure_layout() / "commands" / "desk" / "main.py"
            set_config_value("todo.vault_path", str(self.root / "no-vault"))

    def run_seed(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(self.desk), *args],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def test_new_board_by_name_goes_to_the_boards_folder(self) -> None:
        result = self.run_seed("new", "Work")
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.root / "config" / "unlaw" / "boards" / "Work.md"
        self.assertTrue(target.is_file())
        self.assertEqual(
            self.run_seed("path", "Work").stdout.strip(), str(target.resolve())
        )
        self.assertEqual(self.run_seed("new", "Work").returncode, 2)

    def test_configured_boards_folder(self) -> None:
        from unlawful.config import set_config_value

        with patch.dict(os.environ, self.env):
            set_config_value("desk.boards_dir", str(self.root / "elsewhere"))
        self.assertEqual(self.run_seed("new", "Ideas").returncode, 0)
        self.assertTrue((self.root / "elsewhere" / "Ideas.md").is_file())

    def test_reminders_layer_serves_lists_and_writes_through_osascript(self) -> None:
        process = subprocess.Popen(
            [sys.executable, str(self.desk), "--reminders", "--port", "0", "--no-open"],
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
        port = int(address.rsplit(":", 1)[1])

        def request(method: str, path: str, body: object = None) -> tuple[int, dict]:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            try:
                connection.request(
                    method,
                    path,
                    None if body is None else json.dumps(body),
                    {"X-Desk-Token": token},
                )
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()

        status, board = request("GET", "/api/board")
        self.assertEqual(status, 200)
        self.assertEqual(board["layer"], "reminders")
        self.assertEqual(board["columns"][0]["name"], "Inbox")
        self.assertEqual(board["columns"][0]["cards"][0]["title"], "From Reminders")
        status, boards = request("GET", "/api/boards")
        self.assertTrue(boards["reminders"])
        self.assertEqual(boards["current"], REMINDERS)
        self.assertEqual(
            boards["boards_dir"], str(self.root / "config" / "unlaw" / "boards")
        )
        status, _ = request(
            "POST",
            "/api/board",
            {
                "version": board["version"],
                "op": "add",
                "column": 0,
                "text": "Milk @{2026-11-09}",
            },
        )
        self.assertEqual(status, 200)
        writes = [json.loads(item) for item in self.log.read_text().splitlines()]
        self.assertIn(
            {"op": "add", "list": "L1", "title": "Milk", "due": "2026-11-09"}, writes
        )
        status, created = request(
            "POST", "/api/boards", {"path": "Fresh", "create": True}
        )
        self.assertEqual(status, 200, created)
        self.assertEqual(created["layer"], "file")
        self.assertTrue(
            (self.root / "config" / "unlaw" / "boards" / "Fresh.md").is_file()
        )
        status, boards = request("GET", "/api/boards")
        self.assertIn(
            str((self.root / "config" / "unlaw" / "boards" / "Fresh.md").resolve()),
            boards["boards"],
        )


if __name__ == "__main__":
    unittest.main()
