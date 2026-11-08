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

    def test_canvas_rough_strokes_are_seeded_and_deterministic(self) -> None:
        self.run_case("canvas_prng_and_rough")

    def test_canvas_view_transforms_zoom_at_the_cursor(self) -> None:
        self.run_case("canvas_view_transforms")

    def test_canvas_hit_testing_picks_the_right_item(self) -> None:
        self.run_case("canvas_hit_testing")

    def test_canvas_resize_keeps_a_minimum_and_scales_points(self) -> None:
        self.run_case("canvas_resize")

    def test_canvas_wraps_text_and_validates_colors(self) -> None:
        self.run_case("canvas_text_wrap_and_ink")

    def test_canvas_shapes_and_style_changes(self) -> None:
        self.run_case("canvas_shapes_and_styles")

    def test_canvas_grouping_moving_deleting_and_pasting(self) -> None:
        self.run_case("canvas_structure_edits")

    def test_canvas_history_undoes_redoes_and_is_capped(self) -> None:
        self.run_case("canvas_history")

    def test_canvas_save_keeps_unknown_keys(self) -> None:
        self.run_case("canvas_save_keeps_unknown_keys")

    def test_canvas_conflict_reloads_the_servers_version(self) -> None:
        self.run_case("canvas_save_conflict_reloads")

    def test_canvas_never_saves_a_half_finished_drag(self) -> None:
        self.run_case("canvas_save_waits_for_drag")

    def test_canvas_poll_reloads_only_when_idle(self) -> None:
        self.run_case("canvas_poll")

    def test_canvas_and_board_shortcuts_do_not_clash(self) -> None:
        self.run_case("canvas_keys_stay_in_their_view")

    def test_canvas_pointer_flows_create_move_connect_and_erase(self) -> None:
        self.run_case("canvas_interaction_flow")
