"""Run the actual Desk script with fake DOM, fetch, timers and media in Node.

The harness never starts a server or asks a browser for real media permissions.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node is needed for the Desk JavaScript regressions")
class DeskUITests(unittest.TestCase):
    def run_case(self, name: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "HOME": directory, "XDG_CONFIG_HOME": directory}
            result = subprocess.run(
                [NODE, str(ROOT / "tests" / "test_desk_ui.cjs"), name],
                env=env, capture_output=True, text=True, timeout=15, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_failed_save_can_be_retried(self) -> None:
        self.run_case("failed_save")

    def test_network_failure_does_not_disable_record_button(self) -> None:
        self.run_case("record_network")

    def test_network_failure_does_not_disable_game_input(self) -> None:
        self.run_case("game_network")

    def test_camera_permission_cannot_outlive_studio(self) -> None:
        self.run_case("camera_leave")

    def test_camera_permission_cannot_reacquire_during_recording(self) -> None:
        self.run_case("camera_record")

    def test_microphone_permission_cannot_outlive_studio(self) -> None:
        self.run_case("microphone_leave")

    def test_latest_camera_request_owns_the_only_live_stream(self) -> None:
        self.run_case("camera_concurrent")

    def test_device_lookup_cannot_reopen_camera_after_leaving(self) -> None:
        self.run_case("camera_lookup_leave")

    def test_device_lookup_cannot_reopen_microphone_after_leaving(self) -> None:
        self.run_case("microphone_lookup_leave")

    def test_latest_microphone_request_owns_the_only_live_stream(self) -> None:
        self.run_case("microphone_concurrent")

    def test_microphone_animation_stops_with_its_stream(self) -> None:
        self.run_case("microphone_animation")

    def test_visible_studio_observes_terminal_recordings(self) -> None:
        self.run_case("studio_polling")

    def test_arcade_box_corners_and_tees_connect_the_correct_edges(self) -> None:
        self.run_case("box_edges")
