"""Run the actual Desk script with fake DOM, fetch, timers and media in Node.

The harness never starts a server or asks a browser for real media permissions.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node is needed for the Desk JavaScript regressions")
class DeskUITests(unittest.TestCase):
    def run_case(self, name: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "HOME": directory, "XDG_CONFIG_HOME": directory, "PYTHON": sys.executable}
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

    def test_board_dialogs(self) -> None:
        self.run_case("board_dialogs")

    def test_delete_board_asks_first(self) -> None:
        self.run_case("delete_board_asks_first")

    def test_columns_move_by_dragging_the_heading(self) -> None:
        self.run_case("columns_move_by_dragging_the_heading")

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

    def test_studio_record_tab_renders_every_panel(self) -> None:
        self.run_case("studio_record_tab_renders")

    def test_project_clock_maps_segments_and_scenes(self) -> None:
        self.run_case("project_clock_maps_segments")

    def test_export_dialog_prefill(self) -> None:
        self.run_case("export_dialog_prefill")

    def test_export_progress_polls_until_done(self) -> None:
        self.run_case("export_progress_polls_until_done")

    def test_studio_panels_move_resize_and_audio_records_alone(self) -> None:
        self.run_case("studio_layout_and_audio")

    def test_edit_model(self) -> None:
        self.run_case("edit_model")

    def test_edit_tab_keys_and_page(self) -> None:
        self.run_case("edit_tab_keys_and_page")

    def test_studio_survives_failures_and_double_clicks(self) -> None:
        self.run_case("studio_failures_and_double_clicks")

    def test_studio_audio_recording_draws_a_voice_memos_wave(self) -> None:
        self.run_case("studio_voice_wave")

    def test_studio_scenes_and_sources_edit_like_obs(self) -> None:
        self.run_case("studio_obs_editing")

    def test_studio_first_preview_replaces_the_placeholder(self) -> None:
        self.run_case("studio_first_preview_shows_the_screen")

    def test_studio_projects_tab_and_project_page(self) -> None:
        self.run_case("studio_projects_tab_renders")

    def test_studio_shapes_snap_resize_and_focus(self) -> None:
        self.run_case("studio_shape_math")

    def test_studio_shapes_match_the_export(self) -> None:
        self.run_case("studio_shape_parity")

    def test_studio_keys_poll_delays_and_countdown_steps(self) -> None:
        self.run_case("studio_keys_and_polling")

    def test_studio_countdown_records_once_and_can_be_cancelled(self) -> None:
        self.run_case("studio_countdown_then_record")

    def test_studio_setup_save_is_debounced(self) -> None:
        self.run_case("studio_setup_save_is_debounced")

    def test_studio_permission_banner_names_the_app(self) -> None:
        self.run_case("studio_permission_banner")

    def test_rec_pill_shows_recordings_started_elsewhere(self) -> None:
        self.run_case("rec_pill_shows_terminal_recordings")

    def test_camera_preview_stays_while_recording(self) -> None:
        self.run_case("camera_record")

    def test_arcade_box_corners_and_tees_connect_the_correct_edges(self) -> None:
        self.run_case("box_edges")

    def test_boards_menu_is_one_flat_list(self) -> None:
        self.run_case("boards_menu_is_one_flat_list")

    def test_favicon_follows_the_page_theme(self) -> None:
        self.run_case("favicon_follows_the_page_theme")

    def test_canvas_fill_tool(self) -> None:
        self.run_case("canvas_fill_tool")

    def test_canvas_photoshop_keys_new_rename_and_open(self) -> None:
        self.run_case("canvas_keys_and_files")

    def test_canvas_fill_floods_the_clicked_color(self) -> None:
        self.run_case("canvas_flood_fill")

    def test_canvas_partial_eraser_cuts_lines(self) -> None:
        self.run_case("canvas_partial_eraser")

    def test_canvas_tool_menus_and_width_slider(self) -> None:
        self.run_case("canvas_tool_menus_and_width")

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

    def test_canvas_detective_board_pins_and_thread(self) -> None:
        self.run_case("canvas_detective_board")

    def test_canvas_files_are_uploaded_and_pinned(self) -> None:
        self.run_case("canvas_files_are_added_and_pinned")

    def test_canvas_pointer_flows_create_move_connect_and_erase(self) -> None:
        self.run_case("canvas_interaction_flow")


class DeskLogoTests(unittest.TestCase):
    def test_page_uses_the_logo_files(self) -> None:
        import re
        import sys
        from urllib.parse import unquote

        sys.path.insert(0, str(ROOT / "src"))
        try:
            from unlawful.desk_ui import PAGE
        finally:
            sys.path.pop(0)
        light = (ROOT / "assets" / "logo.svg").read_text().strip()
        dark = (ROOT / "assets" / "logo-dark.svg").read_text().strip()
        header = PAGE.split('<span class="brand">', 1)[1].split("Desk</span>", 1)[0]
        self.assertEqual(
            header,
            light.replace("<svg ", '<svg class="mark light" aria-hidden="true" ', 1)
            + dark.replace("<svg ", '<svg class="mark dark" aria-hidden="true" ', 1),
        )
        link = re.search(r'<link rel="icon" id="favicon" href="([^"]*)" data-light="([^"]*)" data-dark="([^"]*)">', PAGE)
        self.assertIsNotNone(link)
        href, icon_light, icon_dark = link.groups()
        self.assertEqual(href, icon_light, "the light icon is the default before the script runs")
        self.assertEqual(unquote(icon_light.removeprefix("data:image/svg+xml,")), light)
        self.assertEqual(unquote(icon_dark.removeprefix("data:image/svg+xml,")), dark)
