"""Regressions from the Rust arcade and archive review; tools and data are sandboxed."""

from __future__ import annotations

import io
import json
import os
import select
import subprocess
import sys
import tarfile
import time

from ulbin import CoreTestCase, binary


class ReviewGameZipTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env["PATH"] = str(self.bin)

    def test_completed_score_is_saved_before_end_screen_is_dismissed(self) -> None:
        process = subprocess.Popen(
            [str(binary()), "game", "--stream", "tetris", "normal"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=self.env, cwd=self.root,
        )
        self.addCleanup(lambda: process.poll() is None and process.kill())
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(b'{"key":" "}\n' * 24)
        process.stdin.flush()
        deadline = time.monotonic() + 10
        pending = b""
        frame = None
        while time.monotonic() < deadline and frame is None:
            if not select.select([process.stdout], [], [], 0.2)[0]:
                continue
            block = os.read(process.stdout.fileno(), 65536)
            self.assertTrue(block, "game ended before its end screen")
            pending += block
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if b"GAME OVER" in line:
                    frame = json.loads(line)
                    break
        self.assertIsNotNone(frame, "game did not reach its end screen")
        scores = self.unlaw / "data" / "runtime" / "arcade.toml"
        # End-screen dismissal, closing the page or stopping its process must not lose the result.
        saved_before_disconnect = scores.exists()
        process.stdin.close()
        process.wait(timeout=5)
        process.stdout.close()
        assert process.stderr is not None
        process.stderr.close()
        self.assertEqual(process.returncode, 0)
        self.assertTrue(saved_before_disconnect, "finished score was not saved before waiting for input")
        self.assertIn("[tetris]", scores.read_text())

    def test_zstandard_tar_is_detected_by_decompressed_content(self) -> None:
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            entry = tarfile.TarInfo("hello.txt")
            entry.size = 5
            archive.addfile(entry, io.BytesIO(b"hello"))
        fixture = self.root / "fixture.tar"
        fixture.write_bytes(payload.getvalue())
        self.tool("zstd", f"#!{sys.executable}\nimport pathlib, sys\nsys.stdout.buffer.write(pathlib.Path({str(fixture)!r}).read_bytes())\n")
        self.tool("bsdtar", f"#!{sys.executable}\nimport pathlib, sys\npathlib.Path(sys.argv[sys.argv.index('-C') + 1], 'hello.txt').write_text('hello')\n")
        archive = self.root / "renamed.zst"
        archive.write_bytes(b"\x28\xb5\x2f\xfdfixture")
        self.ok("zip", "x", str(archive), "-o", str(self.root / "out"))
        self.assertEqual((self.root / "out" / "hello.txt").read_text(), "hello")

    def test_dash_prefixed_inputs_remain_files_for_native_tools(self) -> None:
        source = self.root / "-notes"
        source.write_text("hello")
        self.tool("zip", f"#!{sys.executable}\nimport pathlib, sys\nif sys.argv[7].startswith('-'): raise SystemExit(16)\npathlib.Path(sys.argv[6]).write_bytes(b'zip')\n")
        self.tool("bsdtar", f"#!{sys.executable}\nimport pathlib, sys\nname = sys.argv[sys.argv.index('-C') + 2]\nif name.startswith('-'): raise SystemExit(1)\npathlib.Path(sys.argv[2]).write_bytes(b'tar')\n")
        for format_name in ("zip", "tar.gz"):
            with self.subTest(format=format_name):
                self.ok("zip", "c", str(source), "-f", format_name)
