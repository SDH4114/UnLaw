"""`ul doc`: the formats engine behind Unlaw.app's Edit and ule, run as a black box.

sips and qlmanage are fakes on PATH, so no test draws with the real macOS tools.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ulbin import CoreTestCase  # noqa: E402

# Writes a tiny PNG where sips/qlmanage would, and logs its arguments.
FAKE_DRAW = r"""#!/bin/sh
echo "$(basename "$0") $*" >> "$FAKE_LOG"
out=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "--out" ] || [ "$prev" = "-o" ]; then out="$arg"; fi
  prev="$arg"
done
last=""
for arg in "$@"; do last="$arg"; done
if [ "$(basename "$0")" = "qlmanage" ]; then out="$out/$(basename "$last").png"; fi
printf '\211PNG\r\n\032\n' > "$out"
"""


# PDFKit through osascript: a three-page PDF; drawn pages are tiny PNGs, requests are logged.
FAKE_PDFKIT = r"""#!/usr/bin/env python3
import json, os, sys
request = json.loads(sys.argv[-1])
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write("osascript " + json.dumps(request) + "\n")
if request.get("sizes"):
    print(json.dumps({"pages": 3, "sizes": [[612, 792], [792, 612], [612, 792]]}))
else:
    made = []
    for job in request["jobs"]:
        if job["page"] <= 3:
            open(job["out"], "wb").write(b"\x89PNG\r\n")
            made.append(job["page"])
    print(json.dumps({"pages": 3, "made": made}))
"""


class DocTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.files = self.root / "files"
        self.files.mkdir()
        self.log = self.root / "draw.log"
        self.env["FAKE_LOG"] = str(self.log)
        self.tool("sips", FAKE_DRAW)
        self.tool("qlmanage", FAKE_DRAW)

    def doc(self, *args: str, input: str | None = None):
        return self.ul("doc", *args, input=input)

    def info(self, path: Path) -> dict:
        result = self.doc("info", "--json", "--", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_help_has_every_action(self) -> None:
        for flag in ("--help", "-h"):
            text = self.ok("doc", flag).stdout
            for word in ("info", "read", "write", "render", "pages", "--to", "--version", "exit 3"):
                self.assertIn(word, text)

    def test_info_names_the_kind_and_whether_it_is_text(self) -> None:
        cases = {
            "main.rs": (b"fn main() {}\n", "text", True),
            "notes.md": (b"# hi\n", "markdown", True),
            "table.csv": (b"a,b\n1,2\n", "sheet", True),
            "book.xlsx": (b"PK\x03\x04", "sheet", False),
            "letter.docx": (b"PK\x03\x04", "document", False),
            "photo.HEIC": (b"\0\0\0 ftypheic", "image", False),
            "paper.pdf": (b"%PDF-1.7\n", "pdf", False),
            "app.sqlite": (b"SQLite format 3\0", "database", False),
            "README": (b"plain words\n", "text", True),
            "blob": (b"\x00\x01\x02\xff", "binary", False),
        }
        for name, (data, kind, text) in cases.items():
            path = self.files / name
            path.write_bytes(data)
            info = self.info(path)
            self.assertEqual((info["kind"], info["text"]), (kind, text), name)
            self.assertEqual(info["size"], len(data))
            self.assertEqual(len(info["version"]), 16)

    def test_write_needs_the_version_it_was_based_on(self) -> None:
        path = self.files / "a.txt"
        path.write_text("one\n")
        path.chmod(0o640)
        version = self.info(path)["version"]
        refused = self.doc("write", "--", str(path), input="lost\n")
        self.assertEqual(refused.returncode, 2, "no --version: a wrong call")
        saved = self.doc(
            "write", "--version", version, "--json", "--", str(path), input="two\n"
        )
        self.assertEqual(saved.returncode, 0, saved.stderr)
        self.assertEqual(path.read_text(), "two\n")
        self.assertEqual(
            json.loads(saved.stdout)["version"], self.info(path)["version"]
        )
        self.assertEqual(path.stat().st_mode & 0o777, 0o640, "the file's mode is kept")
        # Another program saved meanwhile: the old version is a conflict and nothing changes.
        stale = self.doc(
            "write", "--version", version, "--", str(path), input="three\n"
        )
        self.assertEqual(stale.returncode, 3, stale.stderr)
        self.assertEqual(path.read_text(), "two\n")
        self.assertEqual(
            [entry.name for entry in self.files.iterdir()],
            ["a.txt"],
            "no temporary file is left",
        )

    def test_new_files_never_replace_one(self) -> None:
        path = self.files / "new.md"
        self.assertEqual(
            self.doc(
                "write", "--version", "new", "--", str(path), input="# new\n"
            ).returncode,
            0,
        )
        self.assertEqual(path.read_text(), "# new\n")
        again = self.doc(
            "write", "--version", "new", "--", str(path), input="# other\n"
        )
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(path.read_text(), "# new\n")

    def test_read_prints_text_and_refuses_the_rest(self) -> None:
        path = self.files / "a.py"
        path.write_text("print('hi')\n")
        self.assertEqual(self.doc("read", str(path)).stdout, "print('hi')\n")
        answer = json.loads(self.doc("read", "--json", str(path)).stdout)
        self.assertEqual(answer["text"], "print('hi')\n")
        pdf = self.files / "b.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        refused = self.doc("read", str(pdf))
        self.assertEqual(refused.returncode, 1)
        self.assertIn("not a text file", refused.stderr)
        latin = self.files / "old.txt"
        latin.write_bytes("caf\xe9 au lait\n".encode("latin-1"))
        self.assertIn("not UTF-8", self.doc("read", str(latin)).stderr)

    def test_render_draws_images_with_sips_and_the_rest_with_quick_look(self) -> None:
        image = self.files / "photo.png"
        image.write_bytes(b"\x89PNG\r\n")
        letter = self.files / "letter.docx"
        letter.write_bytes(b"PK\x03\x04")
        first = json.loads(
            self.doc("render", "--width", "300", "--json", "--", str(image)).stdout
        )
        self.assertTrue(Path(first["png"]).is_file())
        self.assertFalse(first["cached"])
        self.assertTrue(
            Path(first["png"]).is_relative_to(self.unlaw / "data" / "doc" / "cache")
        )
        again = json.loads(
            self.doc("render", "--width", "300", "--json", "--", str(image)).stdout
        )
        self.assertTrue(again["cached"], "the same file and width is drawn once")
        quick = json.loads(self.doc("render", "--json", "--", str(letter)).stdout)
        self.assertTrue(Path(quick["png"]).is_file())
        log = self.log.read_text().splitlines()
        self.assertEqual(len(log), 2)
        self.assertTrue(log[0].startswith("sips -s format png --resampleWidth 300"))
        self.assertTrue(log[1].startswith("qlmanage -t -s 1024"))

    def test_pdf_pages_are_read_and_drawn_in_one_run(self) -> None:
        self.tool("osascript", FAKE_PDFKIT)
        book = self.files / "book.pdf"
        book.write_bytes(b"%PDF-1.7\n")
        pages = json.loads(self.doc("pages", "--json", "--", str(book)).stdout)
        self.assertEqual(pages, {"pages": 3, "sizes": [[612, 792], [792, 612], [612, 792]]})
        drawn = json.loads(
            self.doc("render", "--page", "1", "--to", "3", "--width", "200", "--json", "--", str(book)).stdout
        )
        self.assertEqual([item["page"] for item in drawn["pngs"]], [1, 2, 3])
        self.assertTrue(all(Path(item["png"]).is_file() for item in drawn["pngs"]))
        again = json.loads(
            self.doc("render", "--page", "2", "--to", "4", "--width", "200", "--json", "--", str(book)).stdout
        )
        self.assertEqual([item["page"] for item in again["pngs"]], [2, 3], "no page 4")
        requests = [json.loads(line.split(" ", 1)[1]) for line in self.log.read_text().splitlines()]
        self.assertEqual(len(requests), 3, "sizes, pages 1-3, then only page 4 was asked for")
        self.assertEqual([job["page"] for job in requests[2]["jobs"]], [4])
        self.assertEqual(self.doc("render", "--page", "3", "--to", "2", "--", str(book)).returncode, 2)
        note = self.files / "a.txt"
        note.write_text("x\n")
        self.assertEqual(self.doc("pages", "--", str(note)).returncode, 2, "pages is for PDF")
        self.assertEqual(self.doc("render", "--to", "2", "--", str(note)).returncode, 2)

    def test_wrong_calls_are_usage_errors(self) -> None:
        path = self.files / "a.txt"
        path.write_text("x")
        for args in (
            ("nope", str(path)),
            ("info",),
            ("info", str(path), str(path)),
            ("render", "--width", "99999", str(path)),
            ("render", "--width", str(path)),
            ("info", "--bogus", str(path)),
        ):
            result = self.doc(*args)
            self.assertEqual(result.returncode, 2, f"{args}: {result.stderr}")
            self.assertIn("Usage: ul doc", result.stderr)
        missing = self.doc("info", str(self.files / "missing.txt"))
        self.assertEqual(missing.returncode, 1)
        self.assertIn("does not exist", missing.stderr)

    def test_a_file_named_like_an_option_after_the_separator(self) -> None:
        odd = self.files / "--width"
        odd.write_text("odd\n")
        info = json.loads(
            self.ul("doc", "info", "--json", "--", "--width", cwd=self.files).stdout
        )
        self.assertEqual(info["name"], "--width")


if __name__ == "__main__":
    unittest.main()
