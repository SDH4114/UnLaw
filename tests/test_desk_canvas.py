"""The Canvas tab of `ul desk`: JSON Canvas files with extra Excalidraw-style elements under "unlaw"."""

from __future__ import annotations

import copy
import http.client
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from unlawful import canvas
from unlawful import desk as desk_module
from unlawful.desk import Desk

TOKEN = "secret"


def sample() -> dict:
    return {
        "nodes": [
            {
                "id": "a",
                "type": "text",
                "text": "Hello",
                "x": 0,
                "y": 0,
                "width": 250,
                "height": 60,
                "color": "3",
                "extra": {"k": [1, 2]},
            },
            {
                "id": "b",
                "type": "file",
                "file": "Note.md",
                "x": 300,
                "y": 0,
                "width": 250,
                "height": 60,
            },
            {
                "id": "c",
                "type": "link",
                "url": "https://example.com",
                "x": 0,
                "y": 100,
                "width": 250,
                "height": 60,
            },
            {
                "id": "d",
                "type": "group",
                "label": "G",
                "x": -50,
                "y": -50,
                "width": 700,
                "height": 400,
            },
        ],
        "edges": [
            {
                "id": "e",
                "fromNode": "a",
                "toNode": "b",
                "label": "to",
                "toEnd": "arrow",
                "other": 1,
            }
        ],
        "topLevelUnknown": {"keep": True},
        "unlaw": {
            "version": 1,
            "elements": [
                {
                    "id": "f1",
                    "type": "freedraw",
                    "x": 1,
                    "y": 2,
                    "width": 10,
                    "height": 10,
                    "points": [[0, 0], [5, 5.5]],
                    "stroke": "#112233",
                    "fill": None,
                    "strokeWidth": 2,
                    "roughness": 1,
                    "seed": 7,
                },
                {
                    "id": "r1",
                    "type": "rectangle",
                    "x": 0,
                    "y": 0,
                    "width": 40,
                    "height": 20,
                    "angle": 0.5,
                    "stroke": "#000000",
                    "fill": "#ffffff",
                    "futureKey": "kept",
                },
                {
                    "id": "t1",
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "width": 40,
                    "height": 20,
                    "text": "hi",
                    "fontSize": 20,
                },
            ],
        },
    }


class ValidationTests(unittest.TestCase):
    def test_valid_document_is_returned_unchanged_with_unknown_keys(self) -> None:
        data = sample()
        self.assertEqual(canvas.validate_canvas(copy.deepcopy(data)), data)

    def test_missing_lists_default_to_empty(self) -> None:
        self.assertEqual(canvas.validate_canvas({}), {"nodes": [], "edges": []})

    def test_new_canvas_is_empty(self) -> None:
        self.assertEqual(canvas.NEW_CANVAS, {"nodes": [], "edges": []})

    def rejects(self, data: object, text: str) -> None:
        with self.assertRaisesRegex(ValueError, text):
            canvas.validate_canvas(data)

    def test_top_level_must_be_object(self) -> None:
        self.rejects([], "object")

    def test_lists_must_be_lists(self) -> None:
        self.rejects({"nodes": {}}, "nodes")
        self.rejects({"edges": 3}, "edges")

    def test_hidden_flags_and_thread_spots(self) -> None:
        data = sample()
        data["nodes"][0]["unlawHidden"] = True
        data["edges"][0]["unlawFrom"] = [0.25, 1]
        data["edges"][0]["unlawTo"] = [0, 0.5]
        data["unlaw"] = {"version": 1, "elements": [
            {"id": "x", "type": "rectangle", "x": 0, "y": 0, "width": 1, "height": 1, "unlawHidden": False}]}
        self.assertEqual(canvas.validate_canvas(copy.deepcopy(data)), data)
        for spot in ([0.5], [0.5, 1.5], [-0.1, 0], ["0", 0], [True, 0], "0,0"):
            bad = sample()
            bad["edges"][0]["unlawTo"] = spot
            self.rejects(bad, "unlawTo")
        bad = sample()
        bad["nodes"][1]["unlawHidden"] = "yes"
        self.rejects(bad, "unlawHidden")
        bad["nodes"][1]["unlawHidden"] = 1
        self.rejects(bad, "unlawHidden")

    def test_node_rules(self) -> None:
        good = sample()["nodes"][0]
        for key, value in (
            ("id", 3),
            ("id", ""),
            ("type", "image"),
            ("x", "1"),
            ("y", True),
            ("width", None),
            ("height", float("nan")),
        ):
            with self.subTest(key=key, value=value):
                self.rejects({"nodes": [{**good, key: value}]}, "node")
        self.rejects({"nodes": ["x"]}, "node")
        self.rejects(
            {"nodes": [{k: v for k, v in good.items() if k != "height"}]}, "height"
        )

    def test_duplicate_node_ids_are_rejected(self) -> None:
        node = sample()["nodes"][0]
        self.rejects({"nodes": [node, dict(node)]}, "duplicate")

    def test_edge_rules(self) -> None:
        for edge in (
            {"id": "e", "fromNode": "a"},
            {"id": 1, "fromNode": "a", "toNode": "b"},
            "x",
        ):
            with self.subTest(edge=edge):
                self.rejects({"edges": [edge]}, "edge")

    def test_unlaw_rules(self) -> None:
        self.rejects({"unlaw": []}, "unlaw")
        self.rejects({"unlaw": {"version": 2, "elements": []}}, "version")
        self.rejects({"unlaw": {"version": 1, "elements": {}}}, "elements")
        self.rejects({"unlaw": {"version": 1, "elements": [], "background": "red"}}, "background")
        data = {"nodes": [], "edges": [], "unlaw": {"version": 1, "elements": [], "background": "#fafafa"}}
        self.assertEqual(canvas.validate_canvas(data), data)

    def test_element_rules(self) -> None:
        good = sample()["unlaw"]["elements"][0]
        bad = (
            ("type", "star"),
            ("id", ""),
            ("x", "1"),
            ("width", True),
            ("angle", "1"),
            ("stroke", "red"),
            ("stroke", "#12345"),
            ("fill", "#GGGGGG"),
            ("fill", 5),
            ("strokeWidth", 0),
            ("strokeWidth", 101),
            ("holes", "x"),
            ("holes", [[[0]]]),
            ("roughness", 3),
            ("roughness", -1),
            ("seed", 1.5),
            ("seed", True),
            ("points", [[0]]),
            ("points", [[0, "1"]]),
            ("points", "x"),
        )
        for key, value in bad:
            with self.subTest(key=key, value=value):
                self.rejects(
                    {"unlaw": {"version": 1, "elements": [{**good, key: value}]}},
                    "element",
                )

    def test_paint_areas_and_wide_strokes(self) -> None:
        paint = {
            "id": "p",
            "type": "paint",
            "x": 0,
            "y": 0,
            "width": 10,
            "height": 10,
            "points": [[0, 0], [10, 0], [10, 10]],
            "holes": [[[2, 2], [3, 2], [3, 3]]],
            "fill": "#30a46c",
            "stroke": "#30a46c",
            "strokeWidth": 100,
        }
        data = {"unlaw": {"version": 1, "elements": [paint]}}
        self.assertEqual(canvas.validate_canvas(data)["unlaw"]["elements"][0], paint)
        self.rejects(
            {"unlaw": {"version": 1, "elements": [{**paint, "points": None}]}},
            "points",
        )
        many = [[0, 0]] * (canvas.MAX_POINTS - 2)
        self.rejects(
            {"unlaw": {"version": 1, "elements": [{**paint, "holes": [many]}]}},
            "points",
        )

    def test_text_element_needs_text_and_font_size_range(self) -> None:
        good = sample()["unlaw"]["elements"][2]
        without = {k: v for k, v in good.items() if k != "text"}
        self.rejects({"unlaw": {"version": 1, "elements": [without]}}, "text")
        for size in (7, 201):
            self.rejects(
                {"unlaw": {"version": 1, "elements": [{**good, "fontSize": size}]}},
                "fontSize",
            )

    def test_line_types_need_points(self) -> None:
        for kind in ("freedraw", "line", "arrow"):
            element = {"id": "p", "type": kind, "x": 0, "y": 0, "width": 1, "height": 1}
            self.rejects({"unlaw": {"version": 1, "elements": [element]}}, "points")

    def test_caps(self) -> None:
        shape = {"type": "rectangle", "x": 0, "y": 0, "width": 1, "height": 1}
        too_many = [{"id": str(i), **shape} for i in range(canvas.MAX_ELEMENTS + 1)]
        self.rejects({"unlaw": {"version": 1, "elements": too_many}}, "elements")
        points = [[i, i] for i in range(canvas.MAX_POINTS // 2 + 1)]
        lines = [
            {
                "id": str(i),
                "type": "line",
                "x": 0,
                "y": 0,
                "width": 1,
                "height": 1,
                "points": points,
            }
            for i in range(2)
        ]
        self.rejects({"unlaw": {"version": 1, "elements": lines}}, "points")
        text = {
            "id": "t",
            "type": "text",
            "x": 0,
            "y": 0,
            "width": 1,
            "height": 1,
            "text": "x" * (canvas.MAX_CANVAS_TEXT + 1),
        }
        self.rejects({"unlaw": {"version": 1, "elements": [text]}}, "text")
        node = {
            "id": "n",
            "type": "text",
            "text": "x" * (canvas.MAX_CANVAS_TEXT + 1),
            "x": 0,
            "y": 0,
            "width": 1,
            "height": 1,
        }
        self.rejects({"nodes": [node]}, "text")


class FileTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_write_uses_tabs_keeps_unicode_and_round_trips(self) -> None:
        path = self.root / "A.canvas"
        data = sample()
        data["nodes"][0]["text"] = "Привет"
        version = canvas.write_canvas(path, data)
        raw = path.read_bytes()
        self.assertIn("Привет".encode(), raw)
        self.assertIn(b'\n\t"nodes": [', raw)
        self.assertEqual(version, canvas.version_of(raw))
        read_version, loaded = canvas.read_canvas(path)
        self.assertEqual(read_version, version)
        self.assertEqual(loaded, data)

    def test_write_keeps_file_mode_and_leaves_no_temporary_files(self) -> None:
        path = self.root / "A.canvas"
        path.write_text("{}", encoding="utf-8")
        path.chmod(0o644)
        canvas.write_canvas(path, canvas.NEW_CANVAS)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        self.assertEqual([item.name for item in self.root.iterdir()], ["A.canvas"])

    def test_invalid_document_is_not_written(self) -> None:
        path = self.root / "A.canvas"
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            canvas.write_canvas(path, {"nodes": [{"id": "x"}]})
        self.assertEqual(path.read_text(), "{}")
        self.assertEqual([item.name for item in self.root.iterdir()], ["A.canvas"])

    def test_read_rejects_broken_json_and_non_utf8(self) -> None:
        path = self.root / "A.canvas"
        path.write_text("{nope", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "JSON"):
            canvas.read_canvas(path)
        path.write_bytes(b"\xff\xfe")
        with self.assertRaises(ValueError):
            canvas.read_canvas(path)

    def test_empty_obsidian_canvas_reads(self) -> None:
        path = self.root / "A.canvas"
        path.write_text("{}", encoding="utf-8")
        self.assertEqual(canvas.read_canvas(path)[1], {"nodes": [], "edges": []})


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        board = self.root / "TODO.md"
        board.write_text("## To do\n\n- [ ] Card\n", encoding="utf-8")
        self.config_home = self.root / "config"
        self.canvas_dir = self.root / "canvases"
        patcher = patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": str(self.config_home), "HOME": str(self.root / "home")},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.desk = Desk(
            board, {"desk": {"canvas_dir": str(self.canvas_dir)}}, self.root / "state"
        )
        server = desk_module.make_server(
            self.desk,
            0,
            TOKEN,
            True,
            arcade=desk_module.Arcade(None, self.root / "scores", "normal"),
            studio=desk_module.Studio(None, {}),
        )
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def stop() -> None:
            server.shutdown()
            server.server_close()
            worker.join(2)

        self.addCleanup(stop)
        self.address = server.server_address

    def request(
        self,
        method: str,
        path: str,
        body: object = None,
        token: str | None = TOKEN,
        raw: bytes | None = None,
    ) -> tuple[int, dict]:
        connection = http.client.HTTPConnection(*self.address, timeout=10)
        try:
            headers = {"X-Desk-Token": token} if token else {}
            payload = (
                raw if raw is not None else (None if body is None else json.dumps(body))
            )
            connection.request(method, path, payload, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def create(self, name: str) -> dict:
        status, data = self.request(
            "POST", "/api/canvases", {"path": name, "create": True}
        )
        self.assertEqual(status, 200, data)
        return data

    def test_endpoints_need_the_token(self) -> None:
        for method, path in (
            ("GET", "/api/canvases"),
            ("GET", "/api/canvas"),
            ("POST", "/api/canvas"),
            ("POST", "/api/canvases"),
        ):
            with self.subTest(path=path, method=method):
                self.assertEqual(
                    self.request(
                        method, path, {} if method == "POST" else None, token=None
                    )[0],
                    403,
                )

    def test_empty_overview(self) -> None:
        status, data = self.request("GET", "/api/canvases")
        self.assertEqual(status, 200)
        self.assertEqual(
            data,
            {"dir": str(self.canvas_dir), "current": None, "items": [], "shelf": {"version": 1, "favorites": [], "groups": []}},
        )

    def test_get_without_current_is_404(self) -> None:
        status, data = self.request("GET", "/api/canvas")
        self.assertEqual(status, 404)
        self.assertTrue(data["missing"])

    def test_create_by_bare_name_makes_the_folder_and_file(self) -> None:
        data = self.create("Plan")
        target = (self.canvas_dir / "Plan.canvas").resolve()
        self.assertEqual(data["path"], str(target))
        self.assertEqual(data["name"], "Plan")
        self.assertEqual(data["canvas"], {"nodes": [], "edges": []})
        self.assertEqual(data["version"], canvas.version_of(target.read_bytes()))
        _, overview = self.request("GET", "/api/canvases")
        self.assertEqual(overview["current"], str(target))
        self.assertEqual(overview["items"], [{"path": str(target), "name": "Plan", "modified": target.stat().st_mtime}])

    def test_create_never_overwrites(self) -> None:
        first = self.create("Plan")
        status, saved = self.request(
            "POST",
            "/api/canvas",
            {"path": first["path"], "version": first["version"], "canvas": sample()},
        )
        self.assertEqual(status, 200, saved)
        again = self.create("Plan")
        self.assertEqual(again["canvas"], sample())

    def test_open_without_create_reports_missing(self) -> None:
        status, data = self.request("POST", "/api/canvases", {"path": "Nope"})
        self.assertEqual(status, 404)
        self.assertTrue(data["missing"])
        status, data = self.request("GET", "/api/canvas?path=Nope")
        self.assertEqual(status, 404)
        self.assertTrue(data["missing"])
        self.assertFalse((self.canvas_dir / "Nope.canvas").exists())

    def test_names_must_be_bare_or_canvas_files(self) -> None:
        for raw in (
            "a/b",
            ".hidden",
            "~x",
            "",
            "a\x01b",
        ):
            with self.subTest(raw=raw):
                status, data = self.request(
                    "POST", "/api/canvases", {"path": raw, "create": True}
                )
                self.assertEqual(status, 400, data)
        self.assertFalse(self.canvas_dir.exists())

    def test_full_path_create_and_get_by_path_sets_current(self) -> None:
        target = self.root / "elsewhere" / "Far.canvas"
        target.parent.mkdir()
        data = self.create(str(target))
        self.assertEqual(data["path"], str(target.resolve()))
        other = self.create("Near")
        self.assertEqual(self.request("GET", "/api/canvas")[1]["name"], "Near")
        status, data = self.request("GET", "/api/canvas?path=" + str(target))
        self.assertEqual((status, data["name"]), (200, "Far"))
        self.assertEqual(
            self.request("GET", "/api/canvas")[1]["path"], str(target.resolve())
        )
        self.assertNotEqual(other["path"], data["path"])

    def test_get_by_bare_name(self) -> None:
        self.create("Plan")
        self.create("Other")
        status, data = self.request("GET", "/api/canvas?path=Plan")
        self.assertEqual((status, data["name"]), (200, "Plan"))

    def test_overview_lists_folder_then_recent_without_duplicates(self) -> None:
        self.create("b")
        self.create("A")
        far = self.root / "far" / "Zed.canvas"
        far.parent.mkdir()
        self.create(str(far))
        _, data = self.request("GET", "/api/canvases")
        names = [item["name"] for item in data["items"]]
        self.assertEqual(names, ["A", "b", "Zed"])
        self.assertEqual(data["current"], str(far.resolve()))
        far.unlink()
        names = [
            item["name"] for item in self.request("GET", "/api/canvases")[1]["items"]
        ]
        self.assertEqual(names, ["A", "b"])

    def test_a_restarted_server_reopens_the_last_canvas(self) -> None:
        self.create("first")
        second = self.create("second")
        again = Desk(self.root / "TODO.md", {"desk": {"canvas_dir": str(self.canvas_dir)}}, self.root / "state")
        self.assertEqual(again.canvases()["current"], second["path"])
        self.assertEqual(again.canvas_open(None)["name"], "second")

    def test_last_board_is_the_newest_recent_one_that_exists(self) -> None:
        gone, kept = self.root / "gone.md", self.root / "kept.md"
        kept.write_text("## A\n", encoding="utf-8")
        state = self.root / "boards-state"
        self.assertIsNone(desk_module.last_board(state))
        state.mkdir()
        (state / "recent.json").write_text(json.dumps([str(gone), str(kept)]), encoding="utf-8")
        self.assertEqual(desk_module.last_board(state), kept)

    def test_recent_canvases_are_capped_at_eight(self) -> None:
        outside = self.root / "out"
        outside.mkdir()
        for index in range(10):
            self.create(str(outside / f"c{index}.canvas"))
        recent = json.loads((self.root / "state" / "recent-canvas.json").read_text())
        self.assertEqual(len(recent), 8)
        self.assertEqual(recent[0], str((outside / "c9.canvas").resolve()))

    def test_save_roundtrip_preserves_unknown_keys_and_returns_new_version(
        self,
    ) -> None:
        opened = self.create("Plan")
        status, saved = self.request(
            "POST",
            "/api/canvas",
            {"path": opened["path"], "version": opened["version"], "canvas": sample()},
        )
        self.assertEqual(status, 200, saved)
        self.assertNotEqual(saved["version"], opened["version"])
        on_disk = json.loads(Path(opened["path"]).read_text(encoding="utf-8"))
        self.assertEqual(on_disk, sample())
        status, again = self.request("GET", "/api/canvas?path=" + opened["path"])
        self.assertEqual(again, saved)

    def test_stale_version_gives_409_with_the_current_canvas(self) -> None:
        opened = self.create("Plan")
        Path(opened["path"]).write_text(
            json.dumps({"nodes": [], "edges": [], "mine": 1}), encoding="utf-8"
        )
        status, data = self.request(
            "POST",
            "/api/canvas",
            {"path": opened["path"], "version": opened["version"], "canvas": sample()},
        )
        self.assertEqual(status, 409)
        self.assertEqual(data["error"], "the canvas changed; reloaded")
        self.assertEqual(data["canvas"]["canvas"]["mine"], 1)
        self.assertEqual(data["canvas"]["path"], opened["path"])
        self.assertEqual(json.loads(Path(opened["path"]).read_text())["mine"], 1)

    def test_invalid_save_is_400_and_keeps_the_file(self) -> None:
        opened = self.create("Plan")
        before = Path(opened["path"]).read_bytes()
        for body in (
            {
                "path": opened["path"],
                "version": opened["version"],
                "canvas": {"nodes": [{"id": "x"}]},
            },
            {"path": opened["path"], "version": opened["version"], "canvas": []},
            {"path": opened["path"], "canvas": sample()},
            {"path": opened["path"], "version": 5, "canvas": sample()},
            {"version": opened["version"], "canvas": sample()},
        ):
            with self.subTest(body=list(body)):
                status, data = self.request("POST", "/api/canvas", body)
                self.assertEqual(status, 400, data)
        self.assertEqual(Path(opened["path"]).read_bytes(), before)

    def test_save_to_a_missing_canvas_is_404(self) -> None:
        status, data = self.request(
            "POST", "/api/canvas", {"path": "Gone", "version": "x", "canvas": sample()}
        )
        self.assertEqual(status, 404)
        self.assertTrue(data["missing"])

    def test_broken_file_on_disk_is_400(self) -> None:
        self.canvas_dir.mkdir()
        (self.canvas_dir / "Bad.canvas").write_text("{nope", encoding="utf-8")
        self.assertEqual(self.request("GET", "/api/canvas?path=Bad")[0], 400)

    def test_big_canvas_posts_are_allowed_but_other_bodies_stay_small(self) -> None:
        opened = self.create("Plan")
        big = sample()
        big["nodes"][0]["text"] = "x" * canvas.MAX_CANVAS_TEXT
        big["nodes"] += [
            {
                "id": f"n{i}",
                "type": "text",
                "text": "y" * 5000,
                "x": 0,
                "y": 0,
                "width": 1,
                "height": 1,
            }
            for i in range(200)
        ]
        body = {"path": opened["path"], "version": opened["version"], "canvas": big}
        self.assertGreater(len(json.dumps(body)), desk_module.MAX_BODY)
        status, data = self.request("POST", "/api/canvas", body)
        self.assertEqual(status, 200, data)
        padded = {"path": "x" * (desk_module.MAX_BODY + 10)}
        status, data = self.request("POST", "/api/canvases", padded)
        self.assertEqual(status, 400)
        self.assertIn("too large", data["error"])
        # Only the header: the server refuses by Content-Length, before reading a body.
        connection = http.client.HTTPConnection(*self.address, timeout=10)
        try:
            connection.putrequest("POST", "/api/canvas")
            connection.putheader("X-Desk-Token", TOKEN)
            connection.putheader("Content-Length", str(16 * 1024 * 1024 + 1))
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            self.assertIn("too large", json.loads(response.read())["error"])
        finally:
            connection.close()

    def test_default_canvas_dir_is_inside_the_config_directory(self) -> None:
        board = self.root / "TODO.md"
        state = Desk(board, {}, self.root / "state2")
        self.assertEqual(state.canvas_dir, self.config_home / "unlaw" / "canvas")


if __name__ == "__main__":
    unittest.main()


class OutdatedServerTests(unittest.TestCase):
    """A desk server from before an update gives its port back, so the page keeps its localStorage."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        script = self.root / "desk.py"
        script.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
        self.process = subprocess.Popen([sys.executable, str(script)])
        self.addCleanup(self.process.wait)
        self.addCleanup(self.process.kill)
        self.script = script
        self.state = self.root / "state"
        self.state.mkdir()
        for _ in range(50):
            started = desk_module._ps(self.process.pid, "lstart")
            if started and "desk.py" in desk_module._ps(self.process.pid, "command"):
                break
            time.sleep(0.05)
        self.started = started

    def record(self, **changes: object) -> None:
        info = {"pid": self.process.pid, "port": 8765, "lstart": self.started, **changes}
        (self.state / "server.json").write_text(json.dumps(info), encoding="utf-8")

    def outdated(self, code_changed: bool) -> int | None:
        stamp = time.time() + (120 if code_changed else -3600)
        os.utime(self.script, (stamp, stamp))
        with patch.object(desk_module, "__file__", str(self.script)):
            return desk_module._outdated_server(self.state, 8765)

    def test_a_server_older_than_its_code_is_outdated(self) -> None:
        self.record()
        self.assertEqual(self.outdated(code_changed=True), self.process.pid)

    def test_a_current_server_keeps_running_beside_a_new_one(self) -> None:
        self.record()
        self.assertIsNone(self.outdated(code_changed=False))

    def test_another_port_start_time_or_program_is_never_touched(self) -> None:
        for changes in ({"port": 9000}, {"lstart": "Mon Jan  1 00:00:00 2001"}, {"pid": os.getpid()}, {"pid": True}):
            self.record(**changes)
            self.assertIsNone(self.outdated(code_changed=True), changes)
        self.record()
        with patch.object(desk_module, "__file__", str(self.root / "other.py")):
            (self.root / "other.py").write_text("", encoding="utf-8")
            self.assertIsNone(desk_module._outdated_server(self.state, 8765))


class CanvasFileActionTests(ServerTests):
    """New canvas-N, renaming from the name field and the macOS open dialog (a fake osascript)."""

    def test_new_takes_the_first_free_number_and_never_overwrites(self) -> None:
        self.canvas_dir.mkdir()
        (self.canvas_dir / "canvas-1.canvas").write_text('{"nodes":[{"id":"k","type":"text","text":"keep","x":0,"y":0,"width":1,"height":1}]}')
        names = []
        for _ in range(2):
            status, data = self.request("POST", "/api/canvas/new", {})
            self.assertEqual(status, 200, data)
            self.assertEqual(data["canvas"], {"nodes": [], "edges": []})
            names.append(data["name"])
        self.assertEqual(names, ["canvas-2", "canvas-3"])
        self.assertIn("keep", (self.canvas_dir / "canvas-1.canvas").read_text())
        _, overview = self.request("GET", "/api/canvases")
        self.assertEqual(overview["current"], str((self.canvas_dir / "canvas-3.canvas").resolve()))

    def test_new_creates_the_folder(self) -> None:
        status, data = self.request("POST", "/api/canvas/new", {})
        self.assertEqual(status, 200, data)
        self.assertEqual(data["path"], str((self.canvas_dir / "canvas-1.canvas").resolve()))

    def test_rename_moves_the_file_and_keeps_contents_and_version(self) -> None:
        made = self.create("canvas-1")
        status, data = self.request("POST", "/api/canvas/rename", {"path": made["path"], "name": "  Ideas.canvas "})
        self.assertEqual(status, 200, data)
        target = (self.canvas_dir / "Ideas.canvas").resolve()
        self.assertEqual((data["path"], data["name"], data["version"]), (str(target), "Ideas", made["version"]))
        self.assertFalse(Path(made["path"]).exists())
        _, overview = self.request("GET", "/api/canvases")
        self.assertEqual(overview["current"], str(target))
        self.assertEqual([item["name"] for item in overview["items"]], ["Ideas"])

    def test_rename_never_overwrites_and_checks_the_name(self) -> None:
        first = self.create("one")
        self.create("two")
        status, data = self.request("POST", "/api/canvas/rename", {"path": first["path"], "name": "two"})
        self.assertEqual(status, 400)
        self.assertIn("already exists", data["error"])
        for bad in ("", "a/b", ".hidden", "~x", "bad\nname", 5):
            with self.subTest(name=bad):
                self.assertEqual(self.request("POST", "/api/canvas/rename", {"path": first["path"], "name": bad})[0], 400)
        self.assertTrue(Path(first["path"]).exists())
        self.assertEqual(self.request("POST", "/api/canvas/rename", {"path": str(self.root / "gone.canvas"), "name": "x"})[0], 404)

    def test_rename_works_on_volumes_without_hard_links(self) -> None:
        import errno

        made = self.create("canvas-1")
        self.create("taken")

        def no_links(*args, **kwargs):
            raise OSError(errno.ENOTSUP, "Operation not supported")

        with patch.object(desk_module.os, "link", no_links):
            status, data = self.request("POST", "/api/canvas/rename", {"path": made["path"], "name": "taken"})
            self.assertEqual(status, 400, data)
            self.assertIn("already exists", data["error"])
            status, data = self.request("POST", "/api/canvas/rename", {"path": made["path"], "name": "Moved"})
        self.assertEqual(status, 200, data)
        self.assertEqual(data["version"], made["version"])
        self.assertFalse(Path(made["path"]).exists())
        self.assertTrue((self.canvas_dir / "Moved.canvas").exists())

    def fake_osascript(self, script: str) -> Path:
        tools = self.root / "bin"
        tools.mkdir(exist_ok=True)
        fake = tools / "osascript"
        fake.write_text("#!/bin/sh\n" + script)
        fake.chmod(0o755)
        return tools

    def test_choose_returns_the_picked_file_and_starts_in_the_canvas_folder(self) -> None:
        self.canvas_dir.mkdir()
        log = self.root / "args"
        tools = self.fake_osascript(f'for a in "$@"; do echo "$a" >> {log}; done\necho /picked/Plan.canvas\n')
        with patch.dict(os.environ, {"PATH": str(tools)}):
            status, data = self.request("POST", "/api/canvas/choose", {})
        self.assertEqual((status, data), (200, {"path": "/picked/Plan.canvas"}))
        args = log.read_text().splitlines()
        self.assertEqual(args[-1], str(self.canvas_dir))
        self.assertIn("choose file", " ".join(args))

    def test_choose_cancel_and_failure(self) -> None:
        tools = self.fake_osascript('echo "execution error: User canceled. (-128)" >&2\nexit 1\n')
        with patch.dict(os.environ, {"PATH": str(tools)}):
            self.assertEqual(self.request("POST", "/api/canvas/choose", {}), (200, {"path": None}))
        tools = self.fake_osascript('echo boom >&2\nexit 1\n')
        with patch.dict(os.environ, {"PATH": str(tools)}):
            status, data = self.request("POST", "/api/canvas/choose", {})
        self.assertEqual(status, 400)
        self.assertIn("boom", data["error"])

    def test_choose_without_osascript_lets_the_page_ask(self) -> None:
        with patch.dict(os.environ, {"PATH": str(self.root / "empty")}):
            self.assertEqual(self.request("POST", "/api/canvas/choose", {}), (200, {"unavailable": True}))


class CanvasFileTests(unittest.TestCase):
    """Files dropped on a canvas: copied into attachments/ next to it, served back as pictures, opened in their app."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        board = self.root / "TODO.md"
        board.write_text("## To do\n", encoding="utf-8")
        patcher = patch.dict(
            os.environ,
            {"XDG_CONFIG_HOME": str(self.root / "config"), "HOME": str(self.root / "home")},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.canvas_dir = self.root / "canvases"
        self.desk = Desk(board, {"desk": {"canvas_dir": str(self.canvas_dir)}}, self.root / "state")
        server = desk_module.make_server(
            self.desk, 0, TOKEN, True,
            arcade=desk_module.Arcade(None, self.root / "scores", "normal"),
            studio=desk_module.Studio(None, {}),
        )
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def stop() -> None:
            server.shutdown()
            server.server_close()
            worker.join(2)

        self.addCleanup(stop)
        self.address = server.server_address
        self.canvas = self.desk.canvas_open("Case", create=True)["path"]

    def call(self, method: str, path: str, payload: bytes | None = None, token: str | None = TOKEN, headers: dict | None = None):
        connection = http.client.HTTPConnection(*self.address, timeout=10)
        try:
            sent = {"X-Desk-Token": token} if token else {}
            connection.request(method, path, payload, {**sent, **(headers or {})})
            response = connection.getresponse()
            return response.status, response.getheader("Content-Type") or "", response.read()
        finally:
            connection.close()

    def upload(self, name: str, data: bytes, canvas: str | None = None, token: str | None = TOKEN):
        query = urllib.parse.urlencode({"path": canvas or self.canvas, "name": name})
        status, _, body = self.call("POST", "/api/canvas/upload?" + query, data, token)
        return status, json.loads(body)

    def media(self, file: str, thumb: bool = False, token: str = TOKEN):
        query = {"t": token, "path": self.canvas, "file": file}
        if thumb:
            query["thumb"] = "1"
        return self.call("GET", "/media/canvas?" + urllib.parse.urlencode(query), token=None)

    def fake_tool(self, name: str, script: str) -> Path:
        tools = self.root / "bin"
        tools.mkdir(exist_ok=True)
        fake = tools / name
        fake.write_text("#!/bin/sh\n" + script)
        fake.chmod(0o755)
        return tools

    def test_upload_copies_the_file_next_to_the_canvas(self) -> None:
        status, data = self.upload("Photo.png", b"\x89PNG data")
        self.assertEqual(status, 200, data)
        self.assertEqual(data, {"file": "attachments/Photo.png", "name": "Photo.png", "size": 9})
        self.assertEqual((self.canvas_dir / "attachments" / "Photo.png").read_bytes(), b"\x89PNG data")

    def test_upload_never_overwrites(self) -> None:
        self.upload("Report.pdf", b"one")
        status, data = self.upload("Report.pdf", b"two")
        self.assertEqual(status, 200, data)
        self.assertEqual(data["file"], "attachments/Report 2.pdf")
        folder = self.canvas_dir / "attachments"
        self.assertEqual((folder / "Report.pdf").read_bytes(), b"one")
        self.assertEqual((folder / "Report 2.pdf").read_bytes(), b"two")

    def test_upload_names_are_cleaned(self) -> None:
        for raw, clean in (
            ("../../evil.txt", "evil.txt"),
            ("..\\x\\y.doc", "y.doc"),
            (".hidden", "hidden"),
            ("a\x00b\nc.md", "abc.md"),
            ("", "file"),
            ("/", "file"),
            ("я" * 300 + ".pdf", "я" * 98 + ".pdf"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(desk_module.attachment_name(raw), clean)
        status, data = self.upload("../../escape.txt", b"x")
        self.assertEqual(status, 200, data)
        self.assertTrue((self.canvas_dir / "attachments" / "escape.txt").is_file())
        self.assertFalse((self.root / "escape.txt").exists())

    def test_upload_needs_the_token_and_an_existing_canvas(self) -> None:
        self.assertEqual(self.upload("a.png", b"x", token=None)[0], 403)
        self.assertEqual(self.upload("a.png", b"x", token="wrong")[0], 403)
        status, data = self.upload("a.png", b"x", canvas=str(self.root / "missing.canvas"))
        self.assertEqual(status, 404, data)
        status, data = self.upload("a.png", b"x", canvas=str(self.root / "TODO.md"))
        self.assertEqual(status, 400, data)
        self.assertFalse((self.root / "attachments").exists())

    def test_upload_size_limit(self) -> None:
        with patch.object(desk_module, "MAX_UPLOAD", 4):
            status, data = self.upload("big.bin", b"12345")
        self.assertEqual(status, 400, data)
        self.assertFalse((self.canvas_dir / "attachments" / "big.bin").exists())

    def test_cut_off_upload_leaves_nothing(self) -> None:
        class Short:
            def read(self, size: int) -> bytes:
                return b""

        with self.assertRaises(ValueError):
            self.desk.canvas_attach(self.canvas, "cut.pdf", Short(), 10)
        self.assertEqual(list((self.canvas_dir / "attachments").iterdir()), [])

    def test_pictures_are_served_with_their_type(self) -> None:
        self.upload("Photo.png", b"\x89PNG data")
        status, kind, body = self.media("attachments/Photo.png")
        self.assertEqual((status, kind, body), (200, "image/png", b"\x89PNG data"))
        self.assertEqual(self.media("attachments/Photo.png", token="wrong")[0], 403)

    def test_media_stays_inside_the_canvas_folder(self) -> None:
        (self.root / "secret.png").write_bytes(b"SECRET-BYTES")
        outside = self.root / "outside.png"
        outside.write_bytes(b"OUTSIDE-BYTES")
        (self.canvas_dir / "link.png").symlink_to(outside)
        for file in ("../secret.png", str(self.root / "secret.png"), "~/secret.png", "link.png", "attachments/none.png"):
            with self.subTest(file=file):
                status, _, body = self.media(file)
                self.assertIn(status, (400, 404, 500))
                self.assertNotIn(b"SECRET-BYTES", body)
                self.assertNotIn(b"OUTSIDE-BYTES", body)

    def test_other_files_get_a_quick_look_thumbnail_once(self) -> None:
        self.upload("Brief.pdf", b"%PDF-1.4")
        log = self.root / "ql.log"
        tools = self.fake_tool(
            "qlmanage",
            f'echo "$@" >> {log}\nfor last; do :; done\nout=""\nwhile [ $# -gt 0 ]; do [ "$1" = -o ] && out="$2"; shift; done\n'
            'printf "PNGTHUMB" > "$out/${last##*/}.png"\n',
        )
        with patch.dict(os.environ, {"PATH": str(tools)}):
            first = self.media("attachments/Brief.pdf")
            second = self.media("attachments/Brief.pdf")
        self.assertEqual(first, (200, "image/png", b"PNGTHUMB"))
        self.assertEqual(second, first)
        self.assertEqual(len(log.read_text().splitlines()), 1, "the thumbnail is cached")
        self.assertIn("-t -s 640", log.read_text())

    def test_no_thumbnail_is_404(self) -> None:
        self.upload("Brief.pdf", b"%PDF-1.4")
        tools = self.fake_tool("qlmanage", "exit 1\n")
        with patch.dict(os.environ, {"PATH": str(tools)}):
            self.assertEqual(self.media("attachments/Brief.pdf")[0], 404)
        with patch.dict(os.environ, {"PATH": str(self.root / "empty")}):
            self.assertEqual(self.media("attachments/Brief.pdf")[0], 404)

    def test_open_file_runs_open_with_the_absolute_path(self) -> None:
        self.upload("Brief.pdf", b"%PDF-1.4")
        log = self.root / "open.log"
        tools = self.fake_tool("open", f'echo "$@" > {log}\n')
        body = json.dumps({"path": self.canvas, "file": "attachments/Brief.pdf"}).encode()
        with patch.dict(os.environ, {"PATH": str(tools)}):
            status, _, data = self.call("POST", "/api/canvas/open-file", body)
            self.assertEqual((status, json.loads(data)), (200, {"ok": True, "revealed": False}))
            self.assertEqual(log.read_text().strip(), str((self.canvas_dir / "attachments" / "Brief.pdf").resolve()))
            refused = json.dumps({"path": self.canvas, "file": "../TODO.md"}).encode()
            status, _, _ = self.call("POST", "/api/canvas/open-file", refused)
        self.assertEqual(status, 404)

    def test_runnable_files_are_only_shown_in_finder(self) -> None:
        log = self.root / "open.log"
        tools = self.fake_tool("open", f'echo "$@" > {log}\n')
        self.upload("run.command", b"#!/bin/sh\necho hi\n")
        program = self.canvas_dir / "attachments" / "program"
        program.write_bytes(b"#!/bin/sh\n")
        program.chmod(0o755)
        for file, shown in (("attachments/run.command", "attachments/run.command"), ("attachments/program", "attachments/program")):
            with self.subTest(file=file), patch.dict(os.environ, {"PATH": str(tools)}):
                status, _, data = self.call("POST", "/api/canvas/open-file", json.dumps({"path": self.canvas, "file": file}).encode())
                self.assertEqual((status, json.loads(data)), (200, {"ok": True, "revealed": True}))
                self.assertEqual(log.read_text().strip(), "-R " + str((self.canvas_dir / shown).resolve()))


class BoardChooseTests(ServerTests):
    def fake_osascript(self, script: str) -> Path:
        tools = self.root / "bin"
        tools.mkdir(exist_ok=True)
        fake = tools / "osascript"
        fake.write_text("#!/bin/sh\n" + script)
        fake.chmod(0o755)
        return tools

    def test_new_board_uses_the_save_dialog_in_the_boards_folder_and_adds_md(self) -> None:
        self.desk.boards_dir.mkdir(parents=True)
        log = self.root / "args"
        tools = self.fake_osascript(f'for a in "$@"; do echo "$a" >> {log}; done\necho /picked/Plan\n')
        with patch.dict(os.environ, {"PATH": str(tools)}):
            status, data = self.request("POST", "/api/boards/choose", {"create": True})
        self.assertEqual((status, data), (200, {"path": "/picked/Plan.md"}))
        args = log.read_text().splitlines()
        self.assertEqual(args[-2:], [str(self.desk.boards_dir), "board.md"])
        self.assertIn("choose file name", " ".join(args))

    def test_open_board_uses_the_open_dialog_and_keeps_md(self) -> None:
        log = self.root / "args"
        tools = self.fake_osascript(f'for a in "$@"; do echo "$a" >> {log}; done\necho /picked/Work.MD\n')
        with patch.dict(os.environ, {"PATH": str(tools)}):
            status, data = self.request("POST", "/api/boards/choose", {})
        self.assertEqual((status, data), (200, {"path": "/picked/Work.MD"}))
        args = log.read_text().splitlines()
        self.assertEqual(args[-1], str(self.root / "home"))  # no boards folder yet
        self.assertNotIn("choose file name", " ".join(args))

    def test_cancel_and_no_osascript(self) -> None:
        tools = self.fake_osascript('echo "execution error: User canceled. (-128)" >&2\nexit 1\n')
        with patch.dict(os.environ, {"PATH": str(tools)}):
            self.assertEqual(self.request("POST", "/api/boards/choose", {"create": True}), (200, {"path": None}))
        with patch.dict(os.environ, {"PATH": str(self.root / "empty")}):
            self.assertEqual(self.request("POST", "/api/boards/choose", {"create": True}), (200, {"unavailable": True}))


class CanvasViewerTests(CanvasFileTests):
    """The page's viewer: files served as themselves (never as a page that runs script), documents as HTML,
    and link previews from public sites only."""

    def raw(self, file: str, extra: dict | None = None):
        query = {"t": TOKEN, "path": self.canvas, "file": file, "raw": "1", **(extra or {})}
        connection = http.client.HTTPConnection(*self.address, timeout=10)
        try:
            connection.request("GET", "/media/canvas?" + urllib.parse.urlencode(query), headers=extra and {"Range": extra.pop("range")} or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_media_plays_with_ranges_and_text_never_becomes_a_page(self) -> None:
        self.upload("clip.mp4", b"0123456789")
        self.upload("evil.html", b"<script>alert(1)</script>")
        self.upload("Report.pdf", b"%PDF-1.4")
        status, headers, body = self.raw("attachments/clip.mp4")
        self.assertEqual((status, headers["Content-Type"], body), (200, "video/mp4", b"0123456789"))
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        connection = http.client.HTTPConnection(*self.address, timeout=10)
        query = urllib.parse.urlencode({"t": TOKEN, "path": self.canvas, "file": "attachments/clip.mp4", "raw": "1"})
        connection.request("GET", "/media/canvas?" + query, headers={"Range": "bytes=2-4"})
        response = connection.getresponse()
        self.assertEqual((response.status, response.read()), (206, b"234"))
        connection.close()
        status, headers, body = self.raw("attachments/evil.html")
        self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        status, headers, _ = self.raw("attachments/Report.pdf")
        self.assertEqual(headers["Content-Type"], "application/pdf")
        self.assertNotIn("Content-Security-Policy", headers, "the browser's PDF viewer refuses sandboxed frames")

    def test_raw_is_only_for_known_kinds(self) -> None:
        self.upload("tool.command", b"#!/bin/sh\n")
        tools = self.fake_tool("qlmanage", 'exit 1\n')
        with patch.dict(os.environ, {"PATH": str(tools)}):
            status, headers, _ = self.raw("attachments/tool.command")
        self.assertEqual(status, 404, "an unknown kind falls back to a Quick Look picture, never the bytes")

    def test_documents_become_a_sandboxed_page(self) -> None:
        self.upload("Report.docx", b"PK fake")
        log = self.root / "textutil.log"
        tools = self.fake_tool("textutil", f'echo "$@" >> {log}\nwhile [ "$1" != "-output" ]; do shift; done\necho "<p>Hello</p>" > "$2"\n')
        with patch.dict(os.environ, {"PATH": str(tools)}):
            status, kind, body = self.media("attachments/Report.docx")[0], None, None
            query = {"t": TOKEN, "path": self.canvas, "file": "attachments/Report.docx", "doc": "1"}
            connection = http.client.HTTPConnection(*self.address, timeout=10)
            connection.request("GET", "/media/canvas?" + urllib.parse.urlencode(query))
            response = connection.getresponse()
            status, headers, body = response.status, dict(response.getheaders()), response.read()
            connection.close()
            self.media("attachments/Report.docx")  # cached: textutil is not run again
        self.assertEqual((status, body.strip()), (200, b"<p>Hello</p>"))
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        self.assertIn("sandbox", headers["Content-Security-Policy"])
        self.assertEqual(len(log.read_text().splitlines()), 1)
        self.upload("notes.txt", b"x")
        query = {"t": TOKEN, "path": self.canvas, "file": "attachments/notes.txt", "doc": "1"}
        connection = http.client.HTTPConnection(*self.address, timeout=10)
        connection.request("GET", "/media/canvas?" + urllib.parse.urlencode(query))
        self.assertEqual(connection.getresponse().status, 400)
        connection.close()

    def test_link_previews_never_reach_private_addresses(self) -> None:
        for host in ("127.0.0.1", "10.1.2.3", "169.254.169.254", "192.168.1.1", "::1", "localhost",
                     "::127.0.0.1", "64:ff9b::7f00:1", "fec0::1", "::ffff:10.0.0.1"):
            with self.assertRaises(ValueError, msg=host):
                canvas._public_address(host, 80)
        status, _, body = self.call("POST", "/api/canvas/link-preview", json.dumps({"path": self.canvas, "url": "http://127.0.0.1:9/"}).encode())
        self.assertEqual(status, 400, body)
        status, _, body = self.call("POST", "/api/canvas/link-preview", json.dumps({"path": self.canvas, "url": "file:///etc/passwd"}).encode())
        self.assertEqual(status, 400, body)

    def test_link_preview_reads_the_page_and_keeps_its_picture(self) -> None:
        import http.server

        picture = b"\x89PNG\r\n fake picture"
        logo = b"\x89PNG\r\n the site's logo"

        class Site(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                return

            def do_GET(self) -> None:
                if self.path == "/old":
                    self.send_response(301)
                    self.send_header("Location", "/page")
                    self.end_headers()
                    return
                if self.path == "/page":
                    body = ('<html><head><meta charset="utf-8"><title>Fallback</title>'
                            '<meta property="og:title" content="Case \u2116 7\x07">'
                            '<meta name="description" content="A short &amp; clear text">'
                            '<meta property="og:image" content="/pic.png">'
                            '<link rel="icon" href="/small.png" sizes="16x16"><link rel="icon" href="/logo.svg">'
                            '<link rel="apple-touch-icon" href="/touch.png"></head></html>').encode()
                    kind = "text/html; charset=utf-8"
                elif self.path == "/touch.png":
                    body, kind = logo, "application/octet-stream"  # a wrong type: the bytes say PNG
                else:
                    body, kind = picture, "image/png"
                self.send_response(200)
                if self.path == "/page":
                    self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'self' https://example.test")
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        site = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Site)
        threading.Thread(target=site.serve_forever, daemon=True).start()
        self.addCleanup(site.server_close)
        self.addCleanup(site.shutdown)
        url = f"http://example.test:{site.server_address[1]}/old"
        with patch.object(canvas, "_public_address", return_value="127.0.0.1"):
            status, _, body = self.call("POST", "/api/canvas/link-preview", json.dumps({"path": self.canvas, "url": url}).encode())
        data = json.loads(body)
        self.assertEqual(status, 200, data)
        self.assertEqual(data["title"], "Case \u2116 7")
        self.assertEqual(data["description"], "A short & clear text")
        self.assertEqual(data["site"], "example.test")
        self.assertTrue(data["image"].startswith("attachments/.previews/") and data["image"].endswith(".png"))
        self.assertEqual((self.canvas_dir / data["image"]).read_bytes(), picture)
        self.assertEqual((self.canvas_dir / data["icon"]).read_bytes(), logo, "the apple-touch-icon is the logo")
        self.assertIs(data["frameable"], False, "frame-ancestors without http: keeps it out of the desk")

    def test_site_logo_falls_back_to_favicon_and_frames_are_read(self) -> None:
        self.assertTrue(canvas.frameable({}))
        self.assertFalse(canvas.frameable({"x-frame-options": "SAMEORIGIN"}))
        self.assertTrue(canvas.frameable({"content-security-policy": "frame-ancestors *"}))
        self.assertFalse(canvas.frameable({"content-security-policy": "img-src *, frame-ancestors 'none'"}))
        self.assertEqual(canvas._best_icon([]), "", "no icon tag: /favicon.ico")
        self.assertEqual(canvas._best_icon([("icon", "/a.svg", ""), ("icon", "/b.png", "16x16"), ("shortcut icon", "/c.png", "48x48")]), "/c.png")
        self.assertEqual(canvas._picture_suffix(b"\x00\x00\x01\x00rest"), ".ico")
        self.assertEqual(canvas._picture_suffix(b"RIFF1234WEBPVP8 "), ".webp")
        self.assertIsNone(canvas._picture_suffix(b"<svg onload=alert(1)>"), "never anything but a picture")


class CanvasManageTests(ServerTests):
    """Deleting canvases to the Trash, importing a dropped .canvas, gallery previews and the remembered dialog folder."""

    fake_osascript = BoardChooseTests.fake_osascript

    def setUp(self) -> None:
        super().setUp()
        (self.root / "home").mkdir(exist_ok=True)

    def test_delete_moves_to_the_trash_and_opens_the_next_recent(self) -> None:
        older = self.create("Older")
        doomed = self.create("Doomed")
        (self.canvas_dir / "attachments").mkdir()
        status, overview = self.request("POST", "/api/canvas/delete", {"path": doomed["path"]})
        self.assertEqual(status, 200, overview)
        self.assertFalse(Path(doomed["path"]).exists())
        self.assertTrue((self.root / "home" / ".Trash" / "Doomed.canvas").is_file())
        self.assertTrue((self.canvas_dir / "attachments").is_dir(), "attachments stay for other canvases")
        self.assertEqual([item["name"] for item in overview["items"]], ["Older"])
        self.assertEqual(overview["current"], older["path"])
        again = self.create("Doomed")
        self.request("POST", "/api/canvas/delete", {"path": again["path"]})
        self.assertTrue((self.root / "home" / ".Trash" / "Doomed 2.canvas").is_file(), "never over a file in the Trash")
        status, data = self.request("POST", "/api/canvas/delete", {"path": doomed["path"]})
        self.assertEqual(status, 404, data)

    def test_favorites_and_groups_follow_renames_and_deletes(self) -> None:
        plan, case = self.create("Plan")["path"], self.create("Case")["path"]
        shelf = {"favorites": [plan, plan], "groups": [{"name": "  Work  stuff ", "paths": [plan, case]}, {"name": "Old", "paths": [case]}]}
        status, overview = self.request("POST", "/api/canvas/shelf", {"shelf": shelf})
        self.assertEqual(status, 200, overview)
        self.assertEqual(overview["shelf"]["favorites"], [plan], "a path is listed once")
        self.assertEqual(overview["shelf"]["groups"], [{"name": "Work stuff", "paths": [plan, case]}, {"name": "Old", "paths": []}], "one group per canvas")
        self.assertTrue(Path(plan).is_file() and Path(case).is_file(), "nothing moves on disk")
        status, renamed = self.request("POST", "/api/canvas/rename", {"path": plan, "name": "Roadmap"})
        self.assertEqual(status, 200, renamed)
        shelf = self.request("GET", "/api/canvases")[1]["shelf"]
        self.assertEqual(shelf["favorites"], [renamed["path"]], "a renamed canvas keeps its star")
        self.assertEqual(shelf["groups"][0]["paths"], [renamed["path"], case])
        self.request("POST", "/api/canvas/delete", {"path": case})
        self.assertEqual(self.request("GET", "/api/canvases")[1]["shelf"]["groups"][0]["paths"], [renamed["path"]])
        for bad in ({"groups": [{"name": "A"}, {"name": "a"}]}, {"groups": [{"name": ""}]}, {"favorites": "x"}, [], {"groups": [{"name": "x" * 81}]}):
            status, data = self.request("POST", "/api/canvas/shelf", {"shelf": bad})
            self.assertEqual(status, 400, (bad, data))
        (self.root / "state" / "canvases.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(self.request("GET", "/api/canvases")[1]["shelf"], {"version": 1, "favorites": [], "groups": []})

    def test_delete_of_a_linked_canvas_trashes_only_the_link(self) -> None:
        real = self.root / "elsewhere" / "Real.canvas"
        real.parent.mkdir()
        real.write_text('{"nodes":[],"edges":[]}', encoding="utf-8")
        self.canvas_dir.mkdir(parents=True, exist_ok=True)
        (self.canvas_dir / "Linked.canvas").symlink_to(real)
        status, _ = self.request("POST", "/api/canvas/delete", {"path": "Linked"})
        self.assertEqual(status, 200)
        self.assertTrue(real.is_file())
        self.assertTrue((self.root / "home" / ".Trash" / "Linked.canvas").is_symlink())

    def test_import_makes_a_new_canvas_under_a_free_name(self) -> None:
        self.create("Plan")
        status, data = self.request("POST", "/api/canvas/import", {"name": "../Plan.canvas", "canvas": sample()})
        self.assertEqual(status, 200, data)
        self.assertEqual(data["name"], "Plan 2")
        self.assertEqual(Path(data["path"]).parent, self.canvas_dir.resolve())
        self.assertEqual(data["canvas"]["nodes"][0]["extra"], {"k": [1, 2]}, "unknown keys come along")
        self.assertEqual(self.request("GET", "/api/canvases")[1]["current"], data["path"])
        status, data = self.request("POST", "/api/canvas/import", {"name": "bad.canvas", "canvas": {"nodes": 3}})
        self.assertEqual(status, 400, data)
        self.assertFalse((self.canvas_dir / "bad.canvas").exists())

    def test_peek_reads_without_switching(self) -> None:
        first = self.create("First")
        self.create("Second")
        status, data = self.request("GET", "/api/canvas/peek?path=" + urllib.parse.quote(first["path"]))
        self.assertEqual((status, data["name"]), (200, "First"))
        self.assertTrue(self.request("GET", "/api/canvases")[1]["current"].endswith("Second.canvas"))
        self.assertEqual(self.request("GET", "/api/canvas/peek?path=nope")[0], 404)

    def test_the_open_dialog_starts_where_it_was_left(self) -> None:
        picked = self.root / "Projects" / "Case.canvas"
        picked.parent.mkdir()
        log = self.root / "args"
        tools = self.fake_osascript(f'for a in "$@"; do echo "$a" >> {log}; done\necho {picked}\n')
        with patch.dict(os.environ, {"PATH": str(tools)}):
            self.request("POST", "/api/canvas/choose", {})
            self.request("POST", "/api/canvas/choose", {})
            self.request("POST", "/api/boards/choose", {})
        starts = [line for line in log.read_text().splitlines() if line.startswith("/")]
        self.assertEqual(starts[0], str(self.root / "home"), "first time: the canvas folder, else HOME")
        self.assertEqual(starts[1], str(picked.parent), "then the folder of the last pick")
        self.assertEqual(starts[2], str(self.root / "home"), "boards remember their own folder")


class SeedNameCollisionTests(unittest.TestCase):
    """Seeds concatenate several modules into one main.py: a top-level name defined twice silently wins for the later file."""

    def test_no_top_level_name_is_defined_in_two_files_of_one_seed(self) -> None:
        import ast

        from unlawful.command_sources import _COMMAND_FILES

        for command, files in _COMMAND_FILES.items():
            owners: dict[str, str] = {}
            for relative in files:
                tree = ast.parse((SRC / "unlawful" / relative).read_text(encoding="utf-8"))
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        names = [node.name]
                    elif isinstance(node, ast.Assign):
                        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
                    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                        names = [node.target.id]
                    else:
                        continue
                    for name in names:
                        if name in {"__all__"}:
                            continue
                        with self.subTest(command=command, name=name):
                            self.assertIn(owners.setdefault(name, relative), {relative}, f"{name} is defined in {owners[name]} and {relative}")
