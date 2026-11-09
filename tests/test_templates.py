"""Templates v2: `ul template save|edit|show|rm` and launching, with a fake
osascript (no real windows are read or moved) and a recording `open`."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ulbin import CoreTestCase  # noqa: E402

FAKE_OSASCRIPT = """#!{python}
import json, os, sys
root = {root!r}
request = sys.stdin.read()
with open(os.path.join(root, "osascript.args"), "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
with open(os.path.join(root, "osascript.requests"), "a") as log:
    log.write(request.strip() + "\\n")
with open(os.path.join(root, "osascript.reply")) as handle:
    reply = json.load(handle)
if reply.get("exit"):
    sys.stderr.write(reply.get("stderr", "boom") + "\\n")
    raise SystemExit(reply["exit"])
request = json.loads(request)
if request["mode"] == "snapshot":
    print(json.dumps(reply["snapshot"]))
else:
    failing = reply.get("fail", {{}})
    results = []
    for window in request["plan"]["windows"][: reply.get("answer_only", 99)]:
        note = failing.get(str(window["index"]))
        results.append({{"index": window["index"], "ok": note is None, "notes": [note] if note else [],
                        "state": {{"id": "win-%d" % window["index"], "pid": 7}} if window["kind"] != "app" else None}})
    print(json.dumps({{"trusted": reply.get("trusted", True), "results": results}}))
"""

SCREENS = [
    {"frame": [0, 0, 1800, 1169], "visible": [0, 39, 1725, 1130]},
    {"frame": [-2560, -711, 2560, 1440], "visible": [-2560, -711, 2560, 1440]},
]


class TemplateTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project = self.root / "home" / "giti" / "app"
        (self.project / "src").mkdir(parents=True)
        self.tool(
            "osascript",
            FAKE_OSASCRIPT.format(python=sys.executable, root=str(self.root)),
        )
        self.open_log = self.recording_tool("open")
        self.reply({})

    # ------------------------------------------------------------ helpers

    def reply(self, reply: dict) -> None:
        (self.root / "osascript.reply").write_text(json.dumps(reply))

    def requests(self) -> list[dict]:
        path = self.root / "osascript.requests"
        return (
            [json.loads(line) for line in path.read_text().splitlines()]
            if path.exists()
            else []
        )

    def manifest(self, name: str) -> Path:
        return self.unlaw / "templates" / "projects" / f"{name}.toml"

    def write(self, name: str, text: str) -> None:
        self.manifest(name).parent.mkdir(parents=True, exist_ok=True)
        self.manifest(name).write_text(text)

    def snapshot(self, *, browser_tabs: bool) -> dict:
        browser_window = {
            "title": "Docs",
            "frame": [-2560, -711, 2560, 1440],
            "document": None,
        }
        if browser_tabs:
            browser_window["urls"] = [
                "https://docs.rs/",
                "https://github.com/x",
                "file:///etc/hosts",
            ]
        return {
            "trusted": True,
            "screens": SCREENS,
            "browser": {
                "name": "Helium",
                "bundle": "net.imput.helium",
                "scriptable": browser_tabs,
            },
            "apps": [
                {
                    "name": "Zed",
                    "bundle": "dev.zed.Zed",
                    "windows": [
                        {
                            "title": "app",
                            "frame": [0, 39, 862.5, 1130],
                            "document": str(self.project),
                        }
                    ],
                },
                {
                    "name": "Ghostty",
                    "bundle": "com.mitchellh.ghostty",
                    "windows": [
                        {
                            "title": "zsh",
                            "frame": [862.5, 39, 862.5, 1130],
                            "document": None,
                            "tabs": [
                                [str(self.project), str(self.project / "src")],
                                [str(self.project)],
                            ],
                        }
                    ],
                },
                {
                    "name": "Helium",
                    "bundle": "net.imput.helium",
                    "browser": True,
                    "windows": [browser_window],
                },
                {
                    "name": "Telegram",
                    "bundle": "com.tdesktop.Telegram",
                    "windows": [
                        {
                            "title": "Telegram",
                            "frame": [100, 100, 400, 600],
                            "document": None,
                        }
                    ],
                },
            ],
        }

    V2 = """version = 2
path = "~/giti/app"
focus = false

[[window]]
app = "Zed"
open = "src"
frame = "left"

[[window]]
app = "Ghostty"
frame = "right"
screen = 2

[[window.tab]]
panes = [
  { run = "claude" },
  { dir = "src", split = "down" },
]

[[window]]
app = "browser"
urls = ["https://docs.rs"]
"""

    # ------------------------------------------------------------ save

    def test_save_snapshots_then_keeps_only_the_chosen_windows(self) -> None:
        self.reply({"snapshot": self.snapshot(browser_tabs=True)})
        answers = (
            "\n".join(
                [
                    "1 2 3",  # Zed, Ghostty, browser; not Telegram
                    "c",  # Ghostty tab 1, pane 1: claude
                    "",  # tab 1, pane 2: shell
                    "npm run dev",  # tab 2: a command
                    "1 2",  # the two http(s) sites (file:// is never offered)
                    "",  # project folder = current directory
                    "y",  # focus mode
                    "",  # save
                ]
            )
            + "\n"
        )
        result = self.ok("template", "save", "env", input=answers, cwd=self.project)
        self.assertIn("Saved template 'env'", result.stdout)
        self.assertIn(
            "[x] Ghostty", result.stdout
        )  # the terminal in this folder is pre-marked
        self.assertIn("[ ] Zed", result.stdout)
        self.assertEqual(self.requests(), [{"mode": "snapshot"}])
        text = self.manifest("env").read_text()
        self.assertIn('path = "~/giti/app"', text)
        self.assertIn("focus = true", text)
        self.assertIn('app = "Zed"\nopen = "~/giti/app"\nframe = "left"', text)
        self.assertIn('{ dir = "~/giti/app", run = "claude" }', text)
        self.assertIn('{ dir = "~/giti/app/src", split = "right" }', text)
        self.assertIn('{ dir = "~/giti/app", run = "npm run dev" }', text)
        self.assertIn(
            'app = "browser"\nframe = "full"\nscreen = 2\nurls = [\n  "https://docs.rs/",\n  "https://github.com/x",\n]',
            text,
        )
        self.assertNotIn("Telegram", text)
        self.assertNotIn("file://", text)
        # What it saved is a valid template.
        self.assertIn(
            "env  ~/giti/app  focus on", self.ok("template", "show", "env").stdout
        )

    def test_save_asks_for_links_when_the_browser_hides_its_tabs(self) -> None:
        self.reply({"snapshot": self.snapshot(browser_tabs=False)})
        answers = "3\nftp://x https://a.example\nhttps://a.example https://b.example\n\nn\ny\n"
        result = self.ok("template", "save", "web", input=answers, cwd=self.project)
        self.assertIn("does not share its tabs", result.stdout)
        self.assertIn("Not an http(s) link: ftp://x", result.stderr)
        self.assertIn(
            'urls = [\n  "https://a.example",\n  "https://b.example",\n]',
            self.manifest("web").read_text(),
        )

    def test_save_refuses_without_accessibility_and_writes_nothing(self) -> None:
        self.reply(
            {
                "snapshot": {
                    "trusted": False,
                    "screens": SCREENS,
                    "browser": None,
                    "apps": [],
                }
            }
        )
        result = self.ul("template", "save", "env", cwd=self.project)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Accessibility", result.stderr)
        self.assertFalse(self.manifest("env").exists())

    def test_save_reports_osascript_errors(self) -> None:
        self.reply(
            {
                "exit": 1,
                "stderr": "execution error: Not authorized to send Apple events (-1743)",
            }
        )
        result = self.ul("template", "save", "env", cwd=self.project)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Privacy & Security > Automation", result.stderr)

    def test_save_cancelled_at_the_end_or_on_eof_writes_nothing(self) -> None:
        self.reply({"snapshot": self.snapshot(browser_tabs=True)})
        result = self.ul(
            "template", "save", "env", input="none\n\nn\nn\n", cwd=self.project
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("(no windows: only changes the folder)", result.stdout)
        result = self.ul("template", "save", "env", input="1\n", cwd=self.project)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Cancelled", result.stderr)
        self.assertFalse(self.manifest("env").exists())

    def test_save_rejects_bad_numbers_and_folders_then_reprompts(self) -> None:
        self.reply({"snapshot": self.snapshot(browser_tabs=True)})
        result = self.ok(
            "template", "save", "env", input="9\nnone\n/nope\n\n\n\n", cwd=self.project
        )
        self.assertIn("Not a number from 1 to 4: 9", result.stderr)
        self.assertIn("Not a folder: /nope", result.stderr)

    def test_save_replaces_an_existing_template_only_with_force_or_yes(self) -> None:
        self.write("env", self.V2)
        self.reply({"snapshot": self.snapshot(browser_tabs=True)})
        self.assertEqual(
            self.ul(
                "template", "save", "env", input="\n", cwd=self.project
            ).returncode,
            1,
        )
        self.assertEqual(self.requests(), [])
        self.ok(
            "template",
            "save",
            "env",
            "--force",
            input="none\n\n\n\n",
            cwd=self.project,
        )
        self.assertNotIn("[[window]]", self.manifest("env").read_text())

    def test_save_never_prints_or_stores_escape_sequences_from_other_apps(self) -> None:
        snapshot = self.snapshot(browser_tabs=True)
        snapshot["apps"].append(
            {"name": "Preview", "bundle": "com.apple.Preview", "windows": [
                {"title": "x\u001b]52;c;Y3VybA==\u0007", "frame": [0, 39, 400, 400],
                 "document": "/tmp/a\u001b[2Kb.pdf"}]}
        )
        self.reply({"snapshot": snapshot})
        result = self.ok("template", "save", "env", input="5\n\nn\n\n", cwd=self.project)
        self.assertNotIn("\u001b", result.stdout + result.stderr)
        self.assertIn("\\u{1b}]52;c;Y3VybA==\\u{7}", result.stdout)
        text = self.manifest("env").read_text()
        self.assertIn('app = "Preview"', text)
        self.assertNotIn("open =", text)  # the file name with ESC is dropped

    def test_template_files_with_control_characters_are_refused(self) -> None:
        self.write("env", self.V2.replace('run = "claude"', 'run = "curl x | sh; : \\u001b[2K"'))
        result = self.ul("template", "show", "env")
        self.assertEqual(result.returncode, 1)
        self.assertIn("run must not contain control characters", result.stderr)
        self.assertNotIn("\u001b", result.stdout + result.stderr)

    def test_a_template_named_like_a_command_never_shadows_it(self) -> None:
        self.ok("config", "set", "aliases.short", '["version"]')
        for name in ("git", "doctor", "game", "short"):
            with self.subTest(name=name):
                self.write(name, self.V2)
                self.assertEqual(self.ul("_template-path", name).returncode, 3)

    # ------------------------------------------------------------ launch

    def test_launch_opens_apps_then_places_everything_in_one_script_run(self) -> None:
        self.write("env", self.V2)
        result = self.ok("_template-launch", "env", "--focus")
        self.assertEqual(
            self.calls(self.open_log), [["-a", "Zed", str(self.project / "src")]]
        )
        [request] = self.requests()
        plan = request["plan"]
        self.assertEqual((request["mode"], plan["focus"]), ("apply", True))
        zed, ghostty, browser = plan["windows"]
        self.assertEqual(
            (zed["kind"], zed["frame"], zed["open"]),
            ("app", [0.0, 0.0, 0.5, 1.0], str(self.project / "src")),
        )
        self.assertEqual(
            (ghostty["kind"], ghostty["screen"], ghostty.get("state")),
            ("terminal", 2, None),
        )
        self.assertEqual(
            ghostty["tabs"],
            [
                [
                    {"dir": str(self.project), "run": "claude", "split": None},
                    {"dir": str(self.project / "src"), "run": None, "split": "down"},
                ]
            ],
        )
        self.assertEqual(
            (browser["kind"], browser["urls"], browser["frame"]),
            ("browser", ["https://docs.rs"], None),
        )
        self.assertEqual(result.stdout, "✓ Zed\n✓ Ghostty\n✓ browser\n")
        # Commands and links reach osascript on stdin, never in its argv.
        args = (self.root / "osascript.args").read_text()
        self.assertNotIn("claude", args.replace("Unlaw templates", ""))
        self.assertNotIn("docs.rs", args)

    def test_second_launch_reuses_the_windows_it_opened_until_the_template_changes(self) -> None:
        self.write("env", self.V2)
        self.ok("_template-launch", "env")
        state_file = self.unlaw / "data" / "runtime" / "templates.json"
        state = json.loads(state_file.read_text())["env"]
        self.assertEqual(sorted(state), ["1", "2"])
        self.assertEqual((state["1"]["id"], state["1"]["pid"]), ("win-1", 7))
        self.ok("_template-launch", "env", "--no-focus")
        second = self.requests()[-1]["plan"]
        self.assertEqual(
            [window.get("state") for window in second["windows"]],
            [None, {"id": "win-1", "pid": 7}, {"id": "win-2", "pid": 7}],
        )
        self.assertFalse(second["focus"])
        # After an edit the Ghostty window asks for other panes: a new window, not the old one.
        self.write("env", self.V2.replace('run = "claude"', 'run = "codex"'))
        self.ok("_template-launch", "env")
        third = self.requests()[-1]["plan"]
        self.assertEqual([window.get("state") for window in third["windows"]], [None, None, {"id": "win-2", "pid": 7}])
        # rm forgets the windows too.
        self.ok("template", "rm", "env", "--yes")
        self.assertNotIn("env", json.loads(state_file.read_text()))

    def test_windows_the_script_does_not_answer_for_are_failures(self) -> None:
        self.write("env", self.V2)
        self.reply({"answer_only": 1})
        result = self.ul("_template-launch", "env")
        self.assertEqual(result.returncode, 1)
        self.assertIn("✓ Zed", result.stdout)
        self.assertIn("! Ghostty  no answer from osascript", result.stderr)

    def test_a_window_parked_off_screen_saves_a_loadable_frame(self) -> None:
        snapshot = self.snapshot(browser_tabs=True)
        snapshot["apps"] = [{"name": "Notes", "bundle": "com.apple.Notes", "windows": [
            {"title": "n", "frame": [5000, 3000, 400, 400], "document": None}]}]
        self.reply({"snapshot": snapshot})
        self.ok("template", "save", "env", input="1\n\n\n\n", cwd=self.project)
        self.assertIn("Notes", self.ok("template", "show", "env").stdout)

    def test_focus_from_the_file_and_no_focus_flag(self) -> None:
        self.write("env", self.V2.replace("focus = false", "focus = true"))
        self.ok("_template-launch", "env")
        self.assertTrue(self.requests()[-1]["plan"]["focus"])
        self.ok("_template-launch", "env", "--no-focus")
        self.assertFalse(self.requests()[-1]["plan"]["focus"])

    def test_plain_apps_without_frames_never_run_osascript(self) -> None:
        self.write(
            "plain",
            'version = 2\npath = "~/giti/app"\n[[window]]\napp = "Obsidian"\n[[window]]\napp = "Zed"\nopen = "."\n',
        )
        self.ok("_template-launch", "plain")
        self.assertEqual(
            self.calls(self.open_log),
            [["-a", "Obsidian"], ["-a", "Zed", str(self.project)]],
        )
        self.assertEqual(self.requests(), [])

    def test_one_failing_window_does_not_stop_the_others(self) -> None:
        self.write("env", self.V2)
        self.reply({"fail": {"1": "window did not appear in 10 s"}, "trusted": True})
        result = self.ul("_template-launch", "env")
        self.assertEqual(result.returncode, 1)
        self.assertIn("✓ Zed", result.stdout)
        self.assertIn("✓ browser", result.stdout)
        self.assertIn("! Ghostty  window did not appear in 10 s", result.stderr)

    def test_a_failing_osascript_marks_only_scripted_windows(self) -> None:
        self.write("env", self.V2.replace('frame = "left"\n', ""))
        self.reply({"exit": 1, "stderr": "boom"})
        result = self.ul("_template-launch", "env")
        self.assertEqual(result.returncode, 1)
        self.assertIn("✓ Zed", result.stdout)
        self.assertIn("! Ghostty  osascript failed: boom", result.stderr)

    def test_without_accessibility_windows_open_but_are_not_placed(self) -> None:
        self.write("env", self.V2)
        self.reply({"trusted": False})
        result = self.ul("_template-launch", "env")
        self.assertIn("not placed", result.stderr)
        self.assertIn("Accessibility", result.stderr)

    def test_missing_folders_stop_before_anything_opens(self) -> None:
        self.write("env", self.V2.replace('dir = "src"', 'dir = "gone"'))
        result = self.ul("_template-launch", "env")
        self.assertEqual(result.returncode, 1)
        self.assertIn("window 2, tab 1: folder does not exist", result.stderr)
        self.assertEqual((self.calls(self.open_log), self.requests()), ([], []))

    def test_dry_run_shows_the_plan_and_changes_nothing(self) -> None:
        self.write("env", self.V2)
        for args in (
            ("_template-launch", "env", "--dry-run", "--focus"),
            ("env", "--dry-run", "--focus"),
        ):
            with self.subTest(args=args):
                result = self.ok(*args)
                self.assertIn("env  ~/giti/app  focus on", result.stdout)
                self.assertIn("1  Zed      left             opens src", result.stdout)
                self.assertIn(
                    "2  Ghostty  right, screen 2  tab 1: claude | shell (down)",
                    result.stdout,
                )
                self.assertIn("3  browser  as is            docs.rs", result.stdout)
        self.assertEqual((self.calls(self.open_log), self.requests()), ([], []))

    def test_launch_rejects_unknown_flags(self) -> None:
        self.write("env", self.V2)
        self.assertEqual(self.ul("_template-launch", "env", "--fast").returncode, 2)
        result = self.ul("env", "--fast")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage: ul env [--focus|--no-focus] [--dry-run]", result.stderr)

    def test_invalid_files_name_the_problem(self) -> None:
        self.write("env", self.V2.replace('frame = "left"', 'frame = "middle"'))
        result = self.ul("_template-launch", "env")
        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "Invalid template env: window 1: frame must be one of full, left",
            result.stderr,
        )

    # ------------------------------------------------------------ edit, show, rm, list, help

    def editor(self, body: str) -> None:
        script = self.tool("fake-editor", f"#!/bin/sh\n{body}\n")
        self.ok("config", "set", "core.editor", str(script))

    def test_edit_creates_a_valid_starter_and_validates_after_saving(self) -> None:
        self.editor('echo "$1" > "$(dirname "$0")/edited"')
        result = self.ok("template", "edit", "fresh", cwd=self.project)
        self.assertIn("projects/fresh.toml from a starter", result.stdout)
        self.assertIn("1  Zed      left   opens ~/giti/app", result.stdout)
        self.assertIn('run = "claude"', self.manifest("fresh").read_text())
        self.assertEqual(
            (self.bin / "edited").read_text().strip(), str(self.manifest("fresh"))
        )
        self.editor('echo "version = 9" > "$1"')
        result = self.ul("template", "edit", "fresh")
        self.assertEqual(result.returncode, 1)
        self.assertIn("version must be 2", result.stderr)
        self.assertIn("ul template edit fresh", result.stderr)

    def test_edit_refuses_names_of_commands(self) -> None:
        self.editor("exit 0")
        result = self.ul("template", "edit", "doctor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("already in use", result.stderr)
        self.assertFalse(self.manifest("doctor").exists())

    def test_show_rm_and_list(self) -> None:
        self.write("env", self.V2)
        self.save_template("old", self.project, "obsidian", True)
        self.assertIn("(old format: re-save", self.ok("template", "show", "old").stdout)
        self.assertEqual(
            self.ok("templates").stdout,
            "env  ~/giti/app  Zed, Ghostty, browser\nold  ~/giti/app  Obsidian, ChatGPT\n",
        )
        self.assertEqual(
            self.ok("template", "list").stdout, self.ok("templates").stdout
        )
        result = self.ul("template", "rm", "env", input="n\n")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.manifest("env").exists())
        self.ok("template", "rm", "env", input="y\n")
        self.assertFalse(self.manifest("env").exists())
        self.ok("template", "rm", "old", "--yes")
        self.assertEqual(self.ul("template", "rm", "old", "--yes").returncode, 1)
        self.assertEqual(self.ul("template", "show", "missing").returncode, 1)

    def test_help_and_usage(self) -> None:
        for args in (("template", "--help"), ("help", "template")):
            text = self.ok(*args).stdout
            self.assertIn("ul template save [name] [--force]", text)
            self.assertIn("[[window.tab]]", text)
        self.assertIn("template", self.ok("--help").stdout)
        self.assertEqual(self.ul("template").returncode, 2)
        self.assertEqual(self.ul("template", "frobnicate").returncode, 2)
        self.assertEqual(self.ul("template", "show").returncode, 2)
        self.write("env", self.V2)
        text = self.ok("env", "--help").stdout
        self.assertIn("Usage: ul env [--focus|--no-focus] [--dry-run]", text)
        self.assertIn("2  Ghostty", text)
        self.assertEqual(self.requests(), [])

    def test_completion_offers_subcommands_and_names(self) -> None:
        self.write("env", self.V2)
        self.assertIn(
            "save:Save the open windows as a template",
            self.ok("_complete", "2", "template").stdout,
        )
        self.assertIn(
            "env:template", self.ok("_complete", "3", "template", "show").stdout
        )


if __name__ == "__main__":
    unittest.main()
