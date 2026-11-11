"""`ul clip`: clipboard history, run as a black box with fake osascript, pbcopy, pbpaste and launchctl.

Nothing here reaches the real pasteboard, launchd or ~/Library/LaunchAgents: the fakes sit first on a restricted
PATH (a canary test checks that), HOME and XDG_CONFIG_HOME point into a temporary directory.
"""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import stat
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ulbin import CoreTestCase, binary

# The JXA helper of the real watcher is replaced by a script that prints the lines of $FAKE_DIR/feed.jsonl and exits
# with the code in $FAKE_DIR/osascript_exit (default 0). Its argv is logged.
FAKE_OSASCRIPT = """import json, os, sys
d = os.environ["FAKE_DIR"]
open(d + "/osascript.log", "a").write(json.dumps(sys.argv[1:]) + "\\n")
open(d + "/osascript.ppid", "w").write(str(os.getppid()))
feed = d + "/feed.jsonl"
if os.path.exists(feed):
    for line in open(feed):
        sys.stdout.write(line)
        sys.stdout.flush()
code = d + "/osascript_exit"
raise SystemExit(int(open(code).read()) if os.path.exists(code) else 0)
"""

FAKE_PBCOPY = """import os, sys
d = os.environ["FAKE_DIR"]
if os.path.exists(d + "/pbcopy_fail"):
    raise SystemExit(1)
open(d + "/pbcopy.txt", "wb").write(sys.stdin.buffer.read())
"""

FAKE_PBPASTE = """import os
open(os.environ["FAKE_DIR"] + "/pbpaste.called", "w").write("x")
"""

FAKE_LAUNCHCTL = """import json, os, sys
d = os.environ["FAKE_DIR"]
open(d + "/launchctl.log", "a").write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1] == "print":
    raise SystemExit(0 if os.path.exists(d + "/loaded") else 113)
raise SystemExit(1 if os.path.exists(d + "/launchctl_fail") and sys.argv[1] == "bootstrap" else 0)
"""

LABEL = "com.unlaw.clip"
TEXT = "public.utf8-plain-text"


def entry(text: str | None, *types: str, count: int = 1) -> dict:
    """One line of the helper: a pasteboard change with its types."""
    return {"count": count, "types": list(types) or [TEXT], "text": text}


class ClipBase(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.fake = self.root / "fake"
        self.fake.mkdir()
        self.env["FAKE_DIR"] = str(self.fake)
        self.env["PATH"] = f"{self.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"
        for name, body in (
            ("osascript", FAKE_OSASCRIPT),
            ("pbcopy", FAKE_PBCOPY),
            ("pbpaste", FAKE_PBPASTE),
            ("launchctl", FAKE_LAUNCHCTL),
        ):
            self.tool(name, f"#!{sys.executable}\n{body}")
        self.ok("features", "add", "clip", "--no-build")
        self.plist_path = self.home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        self.history_path = self.unlaw / "data" / "clip" / "history.json"

    def read(self, name: str) -> str:
        path = self.fake / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def jlog(self, name: str) -> list[list[str]]:
        return [json.loads(line) for line in self.read(name).splitlines()]

    def feed(self, *items: dict) -> None:
        (self.fake / "feed.jsonl").write_text(
            "".join(json.dumps(item) + "\n" for item in items), encoding="utf-8"
        )

    def watch(self, *items: dict, expect: int = 0) -> None:
        self.feed(*items)
        result = self.ul("clip", "_watch")
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)

    def texts(self) -> list[str]:
        """The stored texts, newest first (read through the command itself)."""
        if not self.history_path.exists():
            return []
        return [
            item["text"]
            for item in json.loads(self.history_path.read_text(encoding="utf-8"))[
                "items"
            ]
        ]

    def fill(self, *texts: str) -> None:
        """Copied in this order: the last one is the newest."""
        self.watch(*(entry(text, count=index) for index, text in enumerate(texts, 1)))


class CanaryTests(ClipBase):
    def test_every_system_tool_resolves_into_the_test_bin_directory(self) -> None:
        for name in ("osascript", "launchctl", "pbcopy", "pbpaste"):
            with self.subTest(tool=name):
                found = shutil.which(name, path=self.env["PATH"])
                self.assertEqual(
                    found,
                    str(self.bin / name),
                    "a real tool would be reachable from the tests",
                )


class HelpTests(ClipBase):
    def test_help_has_no_side_effects(self) -> None:
        for args in (
            ("--help",),
            ("-h",),
            ("help",),
            ("on", "--help"),
            ("off", "-h"),
            ("clear", "--help"),
            ("copy", "1", "--help"),
            ("list", "-h"),
            ("_watch", "--help"),
        ):
            with self.subTest(args=args):
                result = self.ok("clip", *args)
                self.assertIn("Usage: ul clip", result.stdout)
        self.assertFalse(self.plist_path.exists())
        self.assertFalse((self.unlaw / "data" / "clip").exists())
        self.assertEqual(self.jlog("launchctl.log"), [])
        self.assertEqual(self.jlog("osascript.log"), [])
        self.assertEqual(self.read("pbcopy.txt"), "")

    def test_help_is_short_and_mentions_privacy(self) -> None:
        text = self.ok("clip", "--help").stdout
        self.assertLess(len(text.splitlines()), 26)
        for word in (
            "on",
            "off",
            "status",
            "list",
            "search",
            "copy",
            "show",
            "rm",
            "clear",
            "pause",
            "resume",
        ):
            self.assertIn(word, text)
        self.assertIn("password", text.lower())


class WatchTests(ClipBase):
    def test_copies_are_stored_newest_first(self) -> None:
        self.fill("one", "two", "three")
        self.assertEqual(self.texts(), ["three", "two", "one"])

    def test_the_helper_gets_the_interval_and_the_pasteboard_script(self) -> None:
        self.ok("config", "set", "clip.interval", "2.5")
        self.watch(entry("x"))
        (call,) = self.jlog("osascript.log")
        self.assertEqual(call[:3], ["-l", "JavaScript", "-e"])
        self.assertIn("NSPasteboard", call[3])
        self.assertEqual(call[4], "2.5")
        self.assertEqual(
            call[5],
            self.read("osascript.ppid"),
            "the helper is told its parent, so it ends with the watcher",
        )

    def test_recopying_an_older_item_moves_it_to_the_top(self) -> None:
        self.fill("a", "b", "c")
        self.watch(entry("a", count=9))
        self.assertEqual(self.texts(), ["a", "c", "b"])

    def test_empty_and_blank_text_is_skipped(self) -> None:
        self.watch(entry(""), entry("  \n\t "), entry(None), entry("keep", count=4))
        self.assertEqual(self.texts(), ["keep"])

    def test_text_is_stored_as_copied_with_its_whitespace(self) -> None:
        self.watch(entry("  indented\nline two\n"))
        self.assertEqual(self.texts(), ["  indented\nline two\n"])

    def test_the_size_limit_is_100_kb_of_utf8(self) -> None:
        limit = 100 * 1024
        self.watch(
            entry("a" * limit, count=1),
            entry("b" * (limit + 1), count=2),
            entry("é" * (limit // 2 + 1), count=3),
        )
        self.assertEqual(self.texts(), ["a" * limit])

    def test_max_items_keeps_only_the_newest(self) -> None:
        self.ok("config", "set", "clip.max_items", "3")
        self.fill("1", "2", "3", "4", "5")
        self.assertEqual(self.texts(), ["5", "4", "3"])

    def test_concealed_transient_and_generated_items_are_never_stored(self) -> None:
        for marker in (
            "org.nspasteboard.ConcealedType",
            "org.nspasteboard.TransientType",
            "org.nspasteboard.AutoGeneratedType",
        ):
            with self.subTest(marker=marker):
                self.watch(entry("hunter2", TEXT, marker))
                self.assertNotIn(
                    "hunter2",
                    self.history_path.read_text() if self.history_path.exists() else "",
                )
        self.watch(entry("visible", TEXT, "public.html"))
        self.assertEqual(self.texts(), ["visible"])

    def test_files_and_images_are_not_text_items(self) -> None:
        self.watch(
            entry("report.pdf", TEXT, "public.file-url", count=1),
            entry(None, "public.png", count=2),
            entry("only html", "public.html", count=3),
            entry("plain", TEXT, count=4),
        )
        self.assertEqual(self.texts(), ["plain"])

    def test_pause_ignores_changes_and_resume_stores_again(self) -> None:
        self.ok("clip", "pause")
        self.watch(entry("while paused"))
        self.assertEqual(self.texts(), [])
        self.ok("clip", "resume")
        self.watch(entry("after resume"))
        self.assertEqual(self.texts(), ["after resume"])

    def test_garbage_lines_from_the_helper_are_ignored(self) -> None:
        (self.fake / "feed.jsonl").write_text(
            "not json\n[1]\n"
            + json.dumps({"count": 1, "types": TEXT, "text": "x"})
            + "\n"
            + json.dumps(entry("ok"))
            + "\n"
        )
        result = self.ul("clip", "_watch")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.texts(), ["ok"])

    def test_a_failing_helper_ends_the_watcher_with_an_error(self) -> None:
        (self.fake / "osascript_exit").write_text("3")
        result = self.ul("clip", "_watch")
        self.assertEqual(result.returncode, 1)
        self.assertIn("osascript", result.stderr)

    def test_the_watcher_never_reads_the_pasteboard_with_pbpaste(self) -> None:
        self.watch(entry("x"))
        self.assertEqual(self.read("pbpaste.called"), "")

    def test_files_are_private(self) -> None:
        self.watch(entry("secret-ish"))
        self.assertEqual(stat.S_IMODE(self.history_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.history_path.parent.stat().st_mode), 0o700)

    def test_a_damaged_history_is_kept_aside_not_overwritten(self) -> None:
        self.history_path.parent.mkdir(parents=True)
        self.history_path.write_text("{broken")
        result = self.ul("clip", "_watch")
        self.assertEqual(result.returncode, 0)
        self.watch(entry("fresh"))
        self.assertEqual(self.texts(), ["fresh"])
        kept = [
            p
            for p in self.history_path.parent.iterdir()
            if p.name.startswith("history.json.damaged")
        ]
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(), "{broken")


class ListTests(ClipBase):
    def setUp(self) -> None:
        super().setUp()
        self.fill("alpha one", "beta two", "gamma Three", "delta two words")

    def test_list_is_numbered_newest_first(self) -> None:
        lines = self.ok("clip").stdout.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertRegex(lines[0], r"^\s*1\s+.*delta two words")
        self.assertRegex(lines[3], r"^\s*4\s+.*alpha one")
        self.assertEqual(self.ok("clip", "list").stdout, "\n".join(lines) + "\n")

    def test_list_limit(self) -> None:
        lines = self.ok("clip", "list", "2").stdout.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("delta", lines[0])
        self.assertEqual(self.ul("clip", "list", "0").returncode, 2)
        self.assertEqual(self.ul("clip", "list", "x").returncode, 2)

    def test_list_json_has_full_text_and_numbers(self) -> None:
        data = json.loads(self.ok("clip", "list", "2", "--json").stdout)
        self.assertEqual([item["n"] for item in data], [1, 2])
        self.assertEqual(data[0]["text"], "delta two words")
        self.assertIn("time", data[0])
        self.assertEqual(
            json.loads(self.ok("clip", "--json").stdout)[3]["text"], "alpha one"
        )

    def test_an_empty_history(self) -> None:
        self.ok("clip", "clear", "--yes")
        self.assertIn("empty", self.ok("clip").stdout.lower())
        self.assertEqual(json.loads(self.ok("clip", "--json").stdout), [])

    def test_control_characters_are_escaped_in_previews(self) -> None:
        self.fill("line1\nline2\ttab \x1b[31mred\x07 \u202e")
        line = self.ok("clip", "list", "1").stdout
        self.assertNotIn("\x1b", line)
        self.assertNotIn("\x07", line)
        self.assertNotIn("\u202e", line)
        self.assertEqual(line.count("\n"), 1)
        self.assertIn("line1\\nline2\\ttab", line)
        self.assertIn("\\x1b", line)

    def test_long_items_are_cut_in_previews_only(self) -> None:
        self.fill("w" * 500)
        line = self.ok("clip", "list", "1").stdout
        self.assertLess(len(line), 140)
        self.assertEqual(self.ok("clip", "show", "1").stdout, "w" * 500)

    def test_search_needs_every_word_in_any_case_and_keeps_the_numbers(self) -> None:
        lines = self.ok("clip", "search", "TWO", "words").stdout.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^\s*1\s+.*delta")
        both = self.ok("clip", "search", "two").stdout.splitlines()
        self.assertEqual([line.split()[0] for line in both], ["1", "3"])
        self.assertIn(
            "No matches", self.ok("clip", "search", "nothing-like-this").stdout
        )
        self.assertEqual(self.ul("clip", "search").returncode, 2)

    def test_search_json(self) -> None:
        data = json.loads(self.ok("clip", "search", "two", "--json").stdout)
        self.assertEqual(
            [(item["n"], item["text"]) for item in data],
            [(1, "delta two words"), (3, "beta two")],
        )

    def test_show_prints_the_full_text_untouched_when_piped(self) -> None:
        self.fill("a\nb\x1b[0m")
        self.assertEqual(self.ok("clip", "show", "1").stdout, "a\nb\x1b[0m")

    def test_numbers_must_exist(self) -> None:
        for args in (
            ("show", "9"),
            ("rm", "0"),
            ("copy", "-1"),
            ("copy", "x"),
            ("show",),
            ("rm",),
            ("copy",),
        ):
            with self.subTest(args=args):
                result = self.ul("clip", *args)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertTrue(result.stderr)
        self.assertEqual(len(self.texts()), 4)


class ActionTests(ClipBase):
    def setUp(self) -> None:
        super().setUp()
        self.fill("one", "two", "three")

    def test_copy_puts_the_item_on_the_clipboard_and_makes_it_newest(self) -> None:
        self.ok("clip", "copy", "3")
        self.assertEqual(self.read("pbcopy.txt"), "one")
        self.assertEqual(self.texts(), ["one", "three", "two"])

    def test_copy_keeps_multiline_text_and_unicode_exactly(self) -> None:
        self.fill("ünï\n\ncode  \n")
        self.ok("clip", "copy", "1")
        self.assertEqual(self.read("pbcopy.txt"), "ünï\n\ncode  \n")

    def test_a_failing_pbcopy_changes_nothing(self) -> None:
        (self.fake / "pbcopy_fail").write_text("")
        result = self.ul("clip", "copy", "3")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.texts(), ["three", "two", "one"])

    def test_rm_deletes_one_item_and_names_it(self) -> None:
        result = self.ok("clip", "rm", "2")
        self.assertIn("two", result.stdout)
        self.assertEqual(self.texts(), ["three", "one"])

    def test_clear_asks_and_no_keeps_everything(self) -> None:
        for answer in ("n\n", "\n", ""):
            result = self.ul("clip", "clear", input=answer)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Cancelled", result.stdout)
        self.assertEqual(len(self.texts()), 3)

    def test_clear_with_yes_on_stdin_or_the_flag(self) -> None:
        self.ok("clip", "clear", input="y\n")
        self.assertEqual(self.texts(), [])
        self.fill("again")
        self.ok("clip", "clear", "--yes")
        self.assertEqual(self.texts(), [])

    def test_pause_and_resume_report_and_are_idempotent(self) -> None:
        self.assertIn("paused", self.ok("clip", "pause").stdout.lower())
        self.ok("clip", "pause")
        self.assertIn("paused", self.ok("clip", "status").stdout.lower())
        self.assertIn("resumed", self.ok("clip", "resume").stdout.lower())
        self.ok("clip", "resume")
        self.assertNotIn(
            "paused", self.ok("clip", "status").stdout.lower().replace("not paused", "")
        )

    def test_unknown_commands_are_a_usage_error(self) -> None:
        result = self.ul("clip", "frobnicate")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage: ul clip", result.stderr)


class JobTests(ClipBase):
    def plist(self) -> dict:
        return plistlib.loads(self.plist_path.read_bytes())

    def test_on_writes_the_plist_and_loads_it(self) -> None:
        result = self.ok("clip", "on")
        plist = self.plist()
        self.assertEqual(plist["Label"], LABEL)
        self.assertEqual(plist["ProgramArguments"], [str(binary()), "clip", "_watch"])
        self.assertIs(plist["KeepAlive"], True)
        self.assertIs(plist["RunAtLoad"], True)
        self.assertEqual(plist["EnvironmentVariables"]["HOME"], str(self.home))
        self.assertEqual(
            plist["EnvironmentVariables"]["XDG_CONFIG_HOME"], str(self.config_home)
        )
        log = Path(plist["StandardErrorPath"])
        self.assertEqual(log.parent, self.history_path.parent)
        uid = str(os.getuid())
        calls = self.jlog("launchctl.log")
        self.assertEqual([call[0] for call in calls], ["bootout", "bootstrap"])
        self.assertEqual(calls[0][1], f"gui/{uid}/{LABEL}")
        self.assertEqual(calls[1][1:], [f"gui/{uid}", str(self.plist_path)])
        self.assertIn("history", result.stdout.lower())
        self.assertEqual(stat.S_IMODE(self.history_path.parent.stat().st_mode), 0o700)

    def test_on_twice_reloads_without_a_second_file(self) -> None:
        self.ok("clip", "on")
        self.ok("clip", "on")
        self.assertEqual(len(list(self.plist_path.parent.iterdir())), 1)

    def test_a_failing_bootstrap_is_an_error_but_the_plist_stays_for_a_retry(
        self,
    ) -> None:
        (self.fake / "launchctl_fail").write_text("")
        result = self.ul("clip", "on")
        self.assertEqual(result.returncode, 1)
        self.assertIn("launchctl", result.stderr)

    def test_off_removes_the_plist_before_booting_out_and_keeps_the_history(
        self,
    ) -> None:
        self.ok("clip", "on")
        self.fill("kept")
        (self.fake / "launchctl.log").unlink()
        # The plist must already be gone when launchctl runs: launchd would otherwise restart the job from it.
        self.tool(
            "launchctl",
            f"#!{sys.executable}\nimport json, os, sys\n"
            f"open({str(self.fake / 'launchctl.log')!r}, 'a').write(json.dumps([sys.argv[1], os.path.exists({str(self.plist_path)!r})]) + '\\n')\n",
        )
        result = self.ok("clip", "off")
        self.assertFalse(self.plist_path.exists())
        self.assertEqual(self.jlog("launchctl.log"), [["bootout", False]])
        self.assertEqual(self.texts(), ["kept"])
        self.assertIn("clear", result.stdout)

    def test_off_without_a_job_still_boots_out_by_label_and_succeeds(self) -> None:
        result = self.ok("clip", "off")
        self.assertIn("not", result.stdout.lower())

    def test_status_reports_job_pause_and_count(self) -> None:
        text = self.ok("clip", "status").stdout.lower()
        self.assertIn("off", text)
        self.assertIn("0 items", text)
        self.ok("clip", "on")
        (self.fake / "loaded").write_text("")
        self.fill("a", "b")
        text = self.ok("clip", "status").stdout.lower()
        self.assertIn("running", text)
        self.assertIn("2 items", text)
        self.assertEqual(self.jlog("launchctl.log")[-1][0], "print")

    def test_on_needs_osascript(self) -> None:
        (self.bin / "osascript").unlink()
        # /usr/bin has the real one, so only the (now empty) test bin is on PATH.
        result = self.ul("clip", "on", env={"PATH": str(self.bin)})
        self.assertEqual(result.returncode, 1)
        self.assertIn("osascript", result.stderr)
        self.assertFalse(self.plist_path.exists())


if __name__ == "__main__":
    unittest.main()
