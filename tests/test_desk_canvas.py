"""The Canvas tab of `ul desk`: JSON Canvas files with extra Excalidraw-style elements under "unlaw"."""

from __future__ import annotations

import copy
import http.client
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
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
            ("strokeWidth", 21),
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
            "text": "x" * (canvas.MAX_TEXT + 1),
        }
        self.rejects({"unlaw": {"version": 1, "elements": [text]}}, "text")
        node = {
            "id": "n",
            "type": "text",
            "text": "x" * (canvas.MAX_TEXT + 1),
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
            data, {"dir": str(self.canvas_dir), "current": None, "items": []}
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
        self.assertEqual(overview["items"], [{"path": str(target), "name": "Plan"}])

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
        big["nodes"][0]["text"] = "x" * canvas.MAX_TEXT
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
