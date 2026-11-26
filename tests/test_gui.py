"""`ul gui`: Unlaw.app bundle, its login job and the menubar feature, with a fake launchctl.

The bundle goes to UNLAW_GUI_APPS (a temp folder, set by ulbin) and the job to the
temp HOME, so no test touches /Applications or the real launchd.
"""

from __future__ import annotations

import plistlib
import subprocess
import unittest

from tests.ulbin import ROOT, CoreTestCase


def setUpModule() -> None:
    # ul finds ul-app next to itself; build the current one.
    subprocess.run(
        ["cargo", "build", "--quiet", "-p", "unlaw-app"], cwd=ROOT, check=True
    )


class GuiTests(CoreTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.apps = self.root / "Applications"
        self.log = self.root / "launchctl.log"
        self.tool("launchctl", f'#!/bin/sh\necho "$@" >> "{self.log}"\nexit 0\n')

    def bundle(self):
        return self.apps / "Unlaw.app"

    def job(self):
        return self.home / "Library" / "LaunchAgents" / "com.unlaw.gui.plist"

    def calls(self) -> list[str]:
        return (
            self.log.read_text(encoding="utf-8").splitlines()
            if self.log.exists()
            else []
        )

    def test_help_has_no_side_effects(self) -> None:
        for flag in ("--help", "-h"):
            self.assertIn("ul gui install", self.ok("gui", flag).stdout)
        self.assertFalse(self.apps.exists())
        self.assertEqual(self.calls(), [])

    def test_install_builds_the_bundle_and_the_login_job(self) -> None:
        result = self.ok("gui", "install")
        self.assertIn("Installed", result.stdout)
        contents = self.bundle() / "Contents"
        info = plistlib.loads((contents / "Info.plist").read_bytes())
        self.assertEqual(info["CFBundleIdentifier"], "com.unlaw.gui")
        self.assertTrue(info["LSUIElement"])
        self.assertTrue((contents / "MacOS" / "ul-app").is_file())
        self.assertTrue((contents / "Resources" / ".unlaw-gui").is_file())
        job = plistlib.loads(self.job().read_bytes())
        self.assertEqual(job["ProgramArguments"], [str(contents / "MacOS" / "ul-app")])
        self.assertIn("UNLAW_BIN", job["EnvironmentVariables"])
        self.assertEqual(
            job["EnvironmentVariables"]["XDG_CONFIG_HOME"], str(self.config_home)
        )
        self.assertEqual(job["KeepAlive"], {"SuccessfulExit": False})
        verbs = [line.split()[0] for line in self.calls()]
        self.assertEqual(verbs, ["bootout", "bootstrap"])
        # A second install replaces our own bundle.
        self.ok("gui", "install", "--no-start")
        self.assertTrue((contents / "MacOS" / "ul-app").is_file())

    def test_a_foreign_bundle_is_never_replaced_or_deleted(self) -> None:
        foreign = self.bundle() / "Contents"
        foreign.mkdir(parents=True)
        (foreign / "Info.plist").write_text("someone else's\n", encoding="utf-8")
        result = self.ul("gui", "install")
        self.assertEqual(result.returncode, 1)
        self.assertIn("was not made by Unlaw", result.stderr)
        self.ok("gui", "uninstall")
        self.assertEqual(
            (foreign / "Info.plist").read_text(encoding="utf-8"), "someone else's\n"
        )

    def test_uninstall_and_the_feature(self) -> None:
        self.ok("gui", "install")
        self.ok("gui", "uninstall")
        self.assertFalse(self.bundle().exists())
        self.assertFalse(self.job().exists())
        self.assertIn("not installed", self.ok("gui", "uninstall").stdout)
        self.ok("gui", "install")
        # An installed (not development) ul-app goes with the feature, so adding it
        # again builds a current one; the build's own target/debug/ul-app stays.
        installed = self.home / ".local" / "bin" / "ul-app"
        installed.parent.mkdir(parents=True, exist_ok=True)
        installed.write_text("#!/bin/sh\n", encoding="utf-8")
        result = self.ok("features", "remove", "menubar", "--no-build")
        self.assertIn("Removed Unlaw.app", result.stdout)
        self.assertFalse(self.bundle().exists())
        self.assertFalse(installed.exists())
        result = self.ok("features", "add", "menubar")
        self.assertTrue(self.bundle().is_dir(), result.stdout + result.stderr)

    def test_status_and_config(self) -> None:
        result = self.ul("gui", "status")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not installed", result.stdout)
        settings = self.unlaw / "app.toml"
        editor = self.root / "editor.log"
        self.tool("fake-editor", f'#!/bin/sh\necho "$@" >> "{editor}"\n')
        self.ok("config", "set", "core.editor", "fake-editor")
        self.ok("gui", "config")
        self.assertIn('palette = "ctrl+space"', settings.read_text(encoding="utf-8"))
        self.assertIn(str(settings), editor.read_text(encoding="utf-8"))
        settings.write_text("mine = 1\n", encoding="utf-8")
        self.ok("gui", "config")
        self.assertEqual(
            settings.read_text(encoding="utf-8"), "mine = 1\n", "never overwritten"
        )

    def test_checks_find_broken_app_files(self) -> None:
        self.ok("create", "command", "hello")
        sidecar = self.unlaw / "commands" / "hello" / "app.toml"
        sidecar.write_text('icon = "rocket"\n', encoding="utf-8")
        result = self.ul("gui", "check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("rocket", result.stderr)
        # config check is about config.toml: app problems are shown, not a failure.
        checked = self.ul("config", "check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("rocket", checked.stderr)
        sidecar.write_text(
            'icon = "spark"\n[[action]]\nid = "hi"\nlabel = "Say hi"\nargs = ["world"]\n',
            encoding="utf-8",
        )
        self.ok("gui", "check")
        self.ok("config", "check")

    def test_remove_takes_the_app_too(self) -> None:
        self.ok("gui", "install")
        self.tool("cargo", "#!/bin/sh\nexit 0\n")
        self.tool("security", "#!/bin/sh\nexit 44\n")
        result = self.ul("remove", "--yes")
        self.assertIn("Unlaw.app", result.stdout)
        self.assertFalse(self.bundle().exists())
        self.assertFalse(self.job().exists())


if __name__ == "__main__":
    unittest.main()
