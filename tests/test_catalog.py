"""`ul commands search/get`: the command catalog on GitHub, served here from a file:// URL."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from ulbin import CoreTestCase  # noqa: E402

CATALOG = ROOT / "catalog"


class CatalogFilesTests(unittest.TestCase):
    def test_the_committed_catalog_matches_the_seeds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run([sys.executable, "-I", str(ROOT / "rust" / "gen_assets.py"), "--catalog", str(ROOT / "src"), directory], check=True)
            fresh = {str(path.relative_to(directory)): path.read_bytes() for path in Path(directory).rglob("*") if path.is_file()}
        committed = {str(path.relative_to(CATALOG)): path.read_bytes() for path in CATALOG.rglob("*") if path.is_file()}
        self.assertEqual(sorted(committed), sorted(fresh), "run: python3 -I rust/gen_assets.py --catalog src catalog")
        for name, content in fresh.items():
            self.assertEqual(committed[name], content, f"catalog/{name} is stale; regenerate the catalog")
        index = json.loads((CATALOG / "index.json").read_text())
        for entry in index["commands"]:
            code = (CATALOG / entry["name"] / "main.py").read_bytes()
            self.assertEqual(hashlib.sha256(code).hexdigest(), entry["sha256"])


class CatalogCommandTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.env["UNLAW_CATALOG_URL"] = CATALOG.as_uri() + "/"

    def choose(self, *names: str) -> None:
        config = self.unlaw / "config.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        quoted = ", ".join(f'"{name}"' for name in names)
        config.write_text(f"[core]\nfeatures = [{quoted}]\n")

    def test_search_lists_the_catalog_with_installed_marks(self) -> None:
        self.choose("yt")
        self.ok("init")
        listing = self.ok("commands", "search").stdout
        self.assertRegex(listing, r"installed\s+yt\s+Open YouTube")
        self.assertRegex(listing, r"\n\s+music\s+Open Spotify")
        self.assertIn("Download: ul commands get", listing)
        filtered = self.ok("commands", "search", "spotify", "--list").stdout
        self.assertIn("music", filtered)
        self.assertNotIn("yt ", filtered)
        self.assertIn("No command in the catalog matches", self.ok("commands", "search", "zzzz").stdout)
        self.assertIn("ul commands search", self.ok("commands", "search", "--help").stdout)
        self.assertEqual(self.ul("commands", "search", "--bogus").returncode, 2)

    def test_get_downloads_missing_commands_and_never_overwrites(self) -> None:
        self.choose("yt")
        self.ok("init")
        mine = self.unlaw / "commands" / "yt" / "main.py"
        mine.write_text(mine.read_text() + "# mine\n")
        result = self.ok("commands", "get", "music", "yt")
        self.assertIn("Downloaded music", result.stdout)
        self.assertIn("commands/yt already exists; not overwritten", result.stdout)
        self.assertTrue(mine.read_text().endswith("# mine\n"))
        self.assertEqual((self.unlaw / "commands" / "music" / "main.py").read_bytes(), (CATALOG / "music" / "main.py").read_bytes())
        self.assertIn('features = ["yt", "music"]', (self.unlaw / "config.toml").read_text())
        self.ok("init")
        self.assertTrue((self.unlaw / "commands" / "music" / "main.py").exists(), "a downloaded feature stays")
        self.assertIn("installed*", self.ok("commands", "search", "--list").stdout)

    def test_get_explains_built_in_and_unknown_names(self) -> None:
        self.ok("init")
        result = self.ul("commands", "get", "game", "nope")
        self.assertEqual(result.returncode, 2)
        self.assertIn("game is built into ul, not downloaded: ul features add game", result.stderr)
        self.assertIn("nope: not in the catalog", result.stderr)
        self.assertEqual(self.ul("commands", "get").returncode, 2)

    def test_folder_created_during_download_is_not_overwritten(self) -> None:
        self.choose("yt")
        self.ok("init")
        script = self.unlaw / "commands/music/main.py"
        self.tool("curl", f"#!{sys.executable}\nimport pathlib, sys\n"
                  f"catalog = pathlib.Path({str(CATALOG)!r})\n"
                  "if sys.argv[-1].endswith('index.json'):\n"
                  "    sys.stdout.buffer.write((catalog / 'index.json').read_bytes())\n"
                  "else:\n"
                  f"    dest = pathlib.Path({str(script)!r})\n"
                  "    dest.parent.mkdir(parents=True)\n"
                  "    dest.write_text('# mine\\n')\n"
                  "    sys.stdout.buffer.write((catalog / 'music/main.py').read_bytes())\n")
        result = self.ul("commands", "get", "music")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(script.read_text(), "# mine\n")

    def test_checksum_mismatch_writes_nothing(self) -> None:
        bad = self.root / "bad-catalog"
        (bad / "music").mkdir(parents=True)
        (bad / "music" / "main.py").write_text("print('tampered')\n")
        index = {"format": 1, "commands": [{"name": "music", "summary": "x", "sha256": "0" * 64}]}
        (bad / "index.json").write_text(json.dumps(index))
        self.choose("yt")
        self.ok("init")
        result = self.ul("commands", "get", "music", env={"UNLAW_CATALOG_URL": bad.as_uri()})
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not match the catalog checksum", result.stderr)
        self.assertFalse((self.unlaw / "commands" / "music").exists())

    def test_an_unreachable_catalog_is_an_error(self) -> None:
        self.ok("init")
        result = self.ul("commands", "search", env={"UNLAW_CATALOG_URL": (self.root / "missing").as_uri()})
        self.assertEqual(result.returncode, 1)
        self.assertIn("could not fetch", result.stderr)


if __name__ == "__main__":
    unittest.main()
