"""`ul features`: optional parts of Unlaw, seeding by selection, rebuilds and install.sh."""

from __future__ import annotations

import os
import pty
import select
import subprocess
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from ulbin import CoreTestCase  # noqa: E402

SEEDED = {
    "agent", "capture", "cpp", "git", "gpt", "lofi", "mac", "minecraft", "music", "netflix",
    "obsidian", "py", "rust", "steam", "tg", "todo", "work", "yt", "zed",
}


def chooser_source() -> str:
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    return text[text.index("chooser=$(cat <<'PY'\n") + len("chooser=$(cat <<'PY'\n"):text.index("\nPY\n)")]


class FeatureListTests(unittest.TestCase):
    def test_install_sh_carries_the_feature_list_of_the_package(self) -> None:
        sys.path.insert(0, str(ROOT / "src"))
        from unlawful import features
        from unlawful.config import DEFAULT_COMMAND_NAMES

        namespace: dict[str, object] = {"__name__": "chooser"}
        source = chooser_source().split("\nmode, value = ")[0]
        exec(compile(source, "install.sh", "exec"), namespace)  # noqa: S102 - our own install.sh
        self.assertEqual(namespace["FEATURES"], list(features.FEATURES))
        self.assertEqual(namespace["CORE"], features.CORE)
        self.assertEqual(namespace["REQUIRES"], features.REQUIRES)
        self.assertEqual(namespace["CARGO"], features.CARGO)
        self.assertEqual(len(features.FEATURES), 21)
        self.assertEqual(set(DEFAULT_COMMAND_NAMES), SEEDED)
        self.assertEqual(set(features.NAMES) - set(features.CARGO), SEEDED - {"agent"})

    def run_chooser(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-I", "-c", chooser_source(), *args], capture_output=True, text=True, check=False)

    def test_invalid_installer_choice_keeps_existing_uv_installation(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / "bin"
            tools.mkdir()
            log = root / "uv.log"
            for name, code in {
                "cargo": "#!/bin/sh\nexit 99\n",
                "uv": f"#!/bin/sh\necho \"$*\" >> '{log}'\n[ \"$1\" != tool ] || [ \"$2\" != list ] || echo 'unlaw v3.0.0'\n",
            }.items():
                path = tools / name
                path.write_text(code)
                path.chmod(0o755)
            (tools / "python3.14").symlink_to(sys.executable)
            result = subprocess.run(["/bin/sh", str(ROOT / "install.sh")], capture_output=True, text=True,
                                    env={**os.environ, "HOME": str(root), "XDG_CONFIG_HOME": str(root / "config"),
                                         "PATH": f"{tools}:/usr/bin:/bin", "UNLAW_FEATURES": "invalid-feature"})
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("uninstall", log.read_text() if log.exists() else "")

    def test_invalid_choice_does_not_bootstrap_rust(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / "bin"
            tools.mkdir()
            (tools / "python3.14").symlink_to(sys.executable)
            for name in ("sh", "cat", "sed"):
                (tools / name).symlink_to(f"/bin/{name}" if name != "sed" else "/usr/bin/sed")
            log = root / "curl.log"
            curl = tools / "curl"
            curl.write_text(f"#!/bin/sh\necho called > '{log}'\nexit 22\n")
            curl.chmod(0o755)
            result = subprocess.run(["/bin/sh", str(ROOT / "install.sh")], capture_output=True, text=True,
                                    env={"HOME": str(root), "PATH": str(tools), "UNLAW_FEATURES": "invalid-feature"})
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(log.exists(), "invalid choices must be rejected before installing Rust")

    def test_presets_resolve_requirements_and_cargo_features(self) -> None:
        self.assertEqual(self.run_chooser("--preset", "agent,yt").stdout, "lm agent yt\nlm,agent\n")
        self.assertEqual(self.run_chooser("--preset", "all").stdout, "all\nlm,agent,game\n")
        self.assertEqual(self.run_chooser("--preset", "music").stdout, "music\n\n")
        self.assertEqual(self.run_chooser("--preset", "none").stdout, "none\n\n")
        self.assertEqual(self.run_chooser("--all").stdout, "all\nlm,agent,game\n")
        for bad in ("music nope", " "):
            result = self.run_chooser("--preset", bad)
            self.assertEqual(result.returncode, 2, bad)

    def test_an_existing_config_keeps_its_features(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('[core]\nfeatures = ["game", "yt", "gone"]\n')
            self.assertEqual(self.run_chooser("--config", str(config)).stdout, "yt game\ngame\n")
            config.write_text("[core]\ncolor = true\n")
            self.assertEqual(self.run_chooser("--config", str(config)).stdout, "all\nlm,agent,game\n", "older releases had everything")
            config.write_text("[core]\nfeatures = []\n")
            self.assertEqual(self.run_chooser("--config", str(config)).stdout, "none\n\n")
            config.write_text("not toml [")
            self.assertEqual(self.run_chooser("--config", str(config)).stdout.splitlines()[0], "all")

    def interactive(self, keys: list[bytes]) -> tuple[int, str]:
        pid, master = pty.fork()
        if pid == 0:
            os.execv(sys.executable, [sys.executable, "-I", "-c", chooser_source(), "--choose"])
        output = b""
        for key in keys:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                ready = select.select([master], [], [], 0.2)[0]
                if not ready:
                    break
                output += os.read(master, 65536)
            os.write(master, key)
        while True:
            try:
                ready = select.select([master], [], [], 5)[0]
                if not ready:
                    break
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
        _, status = os.waitpid(pid, 0)
        os.close(master)
        text = output.decode(errors="replace").replace("\r", "")
        return os.waitstatus_to_exitcode(status), text

    @staticmethod
    def result(text: str) -> list[str]:
        """The chooser's two output lines, after it left the alternate screen."""
        return text.split("\x1b[?1049l")[-1].split("\n")[:2]

    def test_checklist_starts_full_and_space_toggles_with_requirements(self) -> None:
        # Space on lm (first) also drops agent; Down Down Space drops tg.
        code, text = self.interactive([b" ", b"\x1b[B", b"\x1b[B", b" ", b"\r"])
        self.assertEqual(code, 0, text)
        self.assertIn("Core (always)", text)
        selection, cargo = self.result(text)
        self.assertEqual(cargo, "game")
        self.assertEqual(selection, "gpt yt music lofi netflix capture todo obsidian work git py rust cpp zed mac steam minecraft game")
        code, _ = self.interactive([b"q"])
        self.assertEqual(code, 1)
        code, text = self.interactive([b"a", b" ", b"\r"])
        self.assertEqual(self.result(text), ["lm", "lm"], "a clears everything, Space picks lm")
        code, text = self.interactive([b"a", b"\r"])
        self.assertEqual(self.result(text), ["none", ""], "nothing chosen: the core only")


class FeatureCommandTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        # Changing compiled features rebuilds ul; never with the real cargo.
        self.cargo_log = self.recording_tool("cargo")

    def choose(self, *names: str) -> None:
        config = self.unlaw / "config.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        quoted = ", ".join(f'"{name}"' for name in names)
        config.write_text(f"[core]\nfeatures = [{quoted}]\n")

    def seeded(self) -> set[str]:
        return {path.parent.name for path in (self.unlaw / "commands").glob("*/main.py")}

    def test_only_chosen_commands_are_seeded(self) -> None:
        self.choose("yt")
        self.ok("init")
        self.assertEqual(self.seeded(), {"yt"})
        result = self.ul("music")
        self.assertEqual(result.returncode, 2)
        self.assertIn("music is not installed. Add it: ul features add music", result.stderr)
        listing = self.ok("features").stdout
        self.assertIn("[x] yt", listing)
        self.assertIn("[ ] music", listing)
        self.assertIn("Core (always installed)", listing)

    def test_default_is_everything(self) -> None:
        self.ok("init")
        self.assertEqual(self.seeded(), SEEDED)
        self.assertIn('features = ["all"]', (self.unlaw / "config.toml").read_text())

    def test_add_and_remove_seed_and_keep_edits(self) -> None:
        self.choose("yt")
        self.ok("init")
        added = self.ok("features", "add", "music", "lofi")
        self.assertIn("Added: music, lofi", added.stdout)
        self.assertIn("Rebuilding ul with: the core only", added.stdout, "this test binary has game, lm and agent")
        self.assertEqual(self.seeded(), {"yt", "music", "lofi"})
        self.assertIn('features = ["yt", "music", "lofi"]', (self.unlaw / "config.toml").read_text())
        script = self.unlaw / "commands" / "yt" / "main.py"
        script.write_text(script.read_text() + "# mine\n")
        removed = self.ok("features", "remove", "yt", "music")
        self.assertIn("Kept commands/yt: you edited it", removed.stdout)
        self.assertEqual(self.seeded(), {"yt", "lofi"})
        self.assertFalse((self.unlaw / "commands" / "music").exists())
        self.ok("init")
        self.assertEqual(self.seeded(), {"yt", "lofi"}, "removed seeds do not come back")

    def test_set_none_keeps_only_the_core(self) -> None:
        self.ok("init")
        result = self.ok("features", "set", "none", "--no-build")
        self.assertIn("Run `ul update` to rebuild ul with: the core only", result.stdout)
        self.assertEqual(self.seeded(), set())
        self.assertIn("features = []", (self.unlaw / "config.toml").read_text())
        self.assertEqual(self.ok("app", "--help").returncode, 0, "the core stays")

    def test_help_neither_bootstraps_nor_requires_valid_config(self) -> None:
        for name in ("features", "commands", "app", "browser"):
            self.ok(name, "--help")
            self.assertFalse(self.unlaw.exists(), name)
        self.choose("yt")
        config = self.unlaw / "config.toml"
        config.write_text("invalid TOML [")
        for name in ("features", "commands", "app", "browser"):
            self.ok(name, "-h")
        self.assertEqual(config.read_text(), "invalid TOML [")
        self.assertFalse((self.unlaw / "commands").exists())

    def test_all_and_none_shortcuts(self) -> None:
        self.choose("yt")
        self.ok("features", "all", "--no-build")
        self.assertEqual(self.seeded(), SEEDED)
        self.ok("features", "none", "--no-build")
        self.assertEqual(self.seeded(), set())

    def test_linked_commands_are_never_migrated_or_removed(self) -> None:
        self.choose("music")
        self.ok("init")
        script = self.unlaw / "commands/music/main.py"
        external = self.root / "external"
        external.mkdir()
        original = script.read_bytes()
        (external / "main.py").write_bytes(original)
        script.unlink()
        script.parent.rmdir()
        script.parent.symlink_to(external, target_is_directory=True)
        self.ok("features", "set", "none", "--no-build")
        self.assertEqual((external / "main.py").read_bytes(), original)
        self.assertTrue(script.parent.is_symlink())

    def test_dangling_seed_link_is_not_followed(self) -> None:
        self.choose("music")
        directory = self.unlaw / "commands/music"
        directory.mkdir(parents=True)
        target = self.root / "missing.py"
        (directory / "main.py").symlink_to(target)
        self.ok("init")
        self.assertFalse(target.exists())

    def test_unknown_names_and_usage(self) -> None:
        self.ok("init")
        for args in (["add", "nope"], ["remove", "zip"], ["add"], ["frobnicate"]):
            with self.subTest(args=args):
                self.assertEqual(self.ul("features", *args).returncode, 2)
        self.assertIn("Usage:", self.ok("features", "--help").stdout)
        self.assertEqual(self.ul("features", "choose").returncode, 1, "choose needs a terminal")
        self.choose("zip")
        self.assertIn("Unknown feature in core.features: zip", self.ul("config", "check").stdout + self.ul("config", "check").stderr)

    def test_compiled_features_rebuild_the_same_commit(self) -> None:
        self.ok("init")
        log = self.cargo_log
        saved = self.ok("features", "remove", "game", "--no-build")
        self.assertIn("Run `ul update` to rebuild ul with: lm, agent", saved.stdout)
        self.assertEqual(self.calls(log), [])
        self.assertIn("still built in until `ul update`", self.ok("features").stdout)
        rebuilt = self.ok("features", "remove", "agent")
        self.assertIn("Rebuilding ul with: lm", rebuilt.stdout)
        unlaw, ule = self.calls(log)
        self.assertEqual(unlaw[-4:], ["--root", str(self.home / ".local"), "--no-default-features", "--features", "lm", "unlaw"][-4:])
        self.assertIn("--features", unlaw)
        self.assertEqual(ule[-1], "ule")
        commit = self.ok("--version").stdout.strip().split("(")[-1].rstrip(")")
        if "Unlaw" not in commit:
            self.assertEqual(unlaw[unlaw.index("--rev") + 1], commit)

    def test_update_builds_only_chosen_cargo_features(self) -> None:
        self.choose("yt", "music")
        log = self.cargo_log
        self.ok("update", "--force")
        unlaw, ule = self.calls(log)
        self.assertEqual(unlaw[-2:], ["--no-default-features", "unlaw"])
        self.assertEqual(ule[-1], "ule")


if __name__ == "__main__":
    unittest.main()
