"""Play the arcade games headlessly: a fake curses window feeds keys and records drawing."""

from __future__ import annotations

import curses
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from unlawful import games  # noqa: E402

NO_KEY = -1


class FakeScreen:
    """Implements the curses.window calls the games use."""

    def __init__(self, keys: list[int | str], size: tuple[int, int] = (40, 120)) -> None:
        self.keys = [ord(key) if isinstance(key, str) else key for key in keys]
        self.size = size
        self.text: list[str] = []
        self.messages: list[str] = []
        self.timeouts: list[int] = []
        self.reads = 0

    def getch(self) -> int:
        self.reads += 1
        if self.reads > 20000:
            raise AssertionError("game did not finish")
        return self.keys.pop(0) if self.keys else ord("q")

    def getmaxyx(self) -> tuple[int, int]:
        return self.size

    def addstr(self, y: int, x: int, text: str, *attributes: int) -> None:
        self.text.append(text)

    def addch(self, y: int, x: int, char: str, *attributes: int) -> None:
        self.text.append(char)

    def timeout(self, value: int) -> None:
        self.timeouts.append(value)

    def keypad(self, flag: bool) -> None:
        pass

    def erase(self) -> None:
        pass

    def border(self) -> None:
        pass

    def refresh(self) -> None:
        pass

    def titles(self, word: str) -> list[str]:
        return [line for line in self.text if word in line]


class GameTestCase(unittest.TestCase):
    def setUp(self) -> None:
        # curses.curs_set needs initscr; the games already tolerate curses.error.
        patcher = patch.object(games.curses, "curs_set", side_effect=curses.error("headless"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def finished_with(self, screen: FakeScreen, text: str) -> None:
        self.assertTrue(any(text in line for line in screen.text), f"{text!r} not drawn")


class MenuTests(GameTestCase):
    def test_game_menu_moves_wraps_and_selects(self) -> None:
        self.assertEqual(games._menu(FakeScreen([curses.KEY_DOWN, "j", 10])), "minesweeper")
        self.assertEqual(games._menu(FakeScreen(["k", curses.KEY_ENTER])), "invaders")
        self.assertEqual(games._menu(FakeScreen([curses.KEY_UP, curses.KEY_DOWN, 13])), "tetris")
        self.assertEqual(games._menu(FakeScreen(["2"])), "snake")
        self.assertIsNone(games._menu(FakeScreen([27])))
        self.assertIsNone(games._menu(FakeScreen(["x", "q"])))

    def test_difficulty_menu_starts_at_default(self) -> None:
        self.assertEqual(games._difficulty_menu(FakeScreen([10]), "hard"), "hard")
        self.assertEqual(games._difficulty_menu(FakeScreen([curses.KEY_DOWN, 10]), "hard"), "easy")
        self.assertEqual(games._difficulty_menu(FakeScreen(["k", 13]), "normal"), "easy")
        self.assertEqual(games._difficulty_menu(FakeScreen(["j", curses.KEY_UP, curses.KEY_ENTER]), "easy"), "easy")
        self.assertEqual(games._difficulty_menu(FakeScreen(["3"]), "easy"), "hard")
        self.assertIsNone(games._difficulty_menu(FakeScreen(["q"]), "easy"))

    def test_menu_loop_runs_chosen_games_until_quit(self) -> None:
        played: list[tuple[str, str]] = []
        runners = {name: (lambda screen, level, name=name: played.append((name, level))) for name in games.GAME_NAMES}
        with patch.object(games, "_menu", side_effect=["snake", "tetris", None]), patch.object(
            games, "_difficulty_menu", side_effect=["hard", None]
        ), patch.dict(games.GAME_RUNNERS, runners):
            games._choose_and_run(FakeScreen([]), "normal")
        self.assertEqual(played, [("snake", "hard")])

    def test_rules_reject_unknown_names(self) -> None:
        with self.assertRaises(ValueError):
            games.difficulty_rules("pong", "easy")
        with self.assertRaises(ValueError):
            games.difficulty_rules("snake", "insane")
        self.assertEqual(games.playfield_size(1, 1), (0, 0))


class SnakeTests(GameTestCase):
    SIZE = (14, 32)  # playfield 12x30; head starts at (6, 15) moving right, food at (4, 10)

    def test_small_terminal_is_refused(self) -> None:
        screen = FakeScreen([], (10, 60))
        games._snake(screen, "easy")
        self.finished_with(screen, "Terminal must be at least 30x12")

    def test_eating_food_scores_and_turning_back_is_ignored(self) -> None:
        keys = ["a", "w", "w", "a", NO_KEY, NO_KEY, NO_KEY, NO_KEY, NO_KEY, "q"]
        screen = FakeScreen(keys, self.SIZE)
        with patch.object(games.random, "choice", return_value=(0, 0)):
            games._snake(screen, "normal")
        self.assertTrue(screen.titles("score 1"), "food at (4, 10) was not eaten")
        self.assertEqual(screen.timeouts[-1], round(1000 / 11))

    def test_running_into_itself_ends_the_game(self) -> None:
        keys = ["w", "w", "a", NO_KEY, NO_KEY, NO_KEY, NO_KEY, "s", "d", "w"]
        screen = FakeScreen(keys, self.SIZE)
        with patch.object(games.random, "choice", return_value=(0, 0)):
            games._snake(screen, "hard")
        self.finished_with(screen, "Game over · score 1")


class TetrisTests(GameTestCase):
    O_PIECE = games.SHAPES[3]

    def test_rotation_normalises_to_the_origin(self) -> None:
        line = games.SHAPES[0]
        self.assertEqual(games._rotate(line), ((0, 0), (1, 0), (2, 0), (3, 0)))
        self.assertEqual(set(games._rotate(games._rotate(games._rotate(games._rotate(line))))), set(line))
        self.assertEqual(set(games._rotate(self.O_PIECE)), set(self.O_PIECE))

    def test_small_terminal_is_refused(self) -> None:
        screen = FakeScreen([], (20, 60))
        games._tetris(screen, "easy")
        self.finished_with(screen, "Terminal must be at least 22x23")

    def test_full_rows_clear_and_score(self) -> None:
        # Five O pieces side by side fill two rows: 300 points.
        keys = ["a", "a", "a", " ", "a", " ", "d", " ", "d", "d", "d", " ", "d", "d", "d", "d", "d", " ", "q"]
        screen = FakeScreen(keys)
        with patch.object(games.random, "choice", return_value=self.O_PIECE):
            games._tetris(screen, "normal")
        self.assertTrue(screen.titles("score 300"), "two rows were not cleared")

    def test_stacking_to_the_top_is_game_over(self) -> None:
        screen = FakeScreen([" "] * 12)
        with patch.object(games.random, "choice", return_value=self.O_PIECE):
            games._tetris(screen, "hard")
        self.finished_with(screen, "Game over · score 0")

    def test_moves_rotation_soft_drop_and_gravity(self) -> None:
        line = games.SHAPES[0]
        keys = [curses.KEY_LEFT, curses.KEY_RIGHT, "w", curses.KEY_DOWN, "s"] + [NO_KEY] * 3 + ["q"]
        screen = FakeScreen(keys)
        clock = iter(range(0, 1000))
        with patch.object(games.random, "choice", return_value=line), patch.object(
            games.time, "monotonic", side_effect=lambda: float(next(clock))
        ):
            games._tetris(screen, "easy")
        self.assertTrue(screen.titles("Tetris · easy"))

    def test_blocked_rotation_and_walls_are_respected(self) -> None:
        line = games.SHAPES[0]
        keys = ["a"] * 6 + ["d"] * 12 + ["w", "q"]
        screen = FakeScreen(keys)
        with patch.object(games.random, "choice", return_value=line):
            games._tetris(screen, "normal")
        self.assertTrue(screen.titles("score 0"))


class MinesweeperTests(GameTestCase):
    # Easy: 9x9 with 10 mines — the bottom row plus one more.
    MINES = [(8, x) for x in range(9)] + [(7, 8)]

    def play(self, keys: list[int | str], size: tuple[int, int] = (24, 40)) -> FakeScreen:
        screen = FakeScreen(keys, size)
        with patch.object(games.random, "sample", return_value=self.MINES):
            games._minesweeper(screen, "easy")
        return screen

    def test_flood_reveal_clears_the_field(self) -> None:
        self.finished_with(self.play([" "]), "You cleared the field!")

    def test_stepping_on_a_mine_ends_the_game(self) -> None:
        screen = self.play(["s"] * 9 + [10])
        self.finished_with(screen, "Boom — game over")

    def test_flags_block_reveal_and_toggle(self) -> None:
        screen = self.play(["f", " ", "f", "f", "q"])
        self.assertIn("⚑", screen.text)
        self.assertFalse(any("cleared" in line for line in screen.text))

    def test_cursor_stays_on_the_board(self) -> None:
        keys = ["w", "a", curses.KEY_UP, curses.KEY_LEFT] + ["d"] * 12 + [curses.KEY_RIGHT, curses.KEY_DOWN, "q"]
        screen = self.play(keys)
        self.assertTrue(screen.titles("10 mines"))

    def test_small_terminal_is_refused(self) -> None:
        self.finished_with(self.play([], (10, 60)), "Easy needs at least 22x13")


class InvadersTests(GameTestCase):
    def test_small_terminal_is_refused(self) -> None:
        screen = FakeScreen([], (10, 60))
        games._invaders(screen, "easy")
        self.finished_with(screen, "Terminal must be at least 40x14")

    def test_enemies_reaching_the_player_end_the_game(self) -> None:
        screen = FakeScreen([NO_KEY] * 5000, (16, 42))
        games._invaders(screen, "hard")
        self.finished_with(screen, "Game over")

    def test_shooting_hits_invaders_above_the_player(self) -> None:
        # Width 50 puts the player at x=25, under the column of invaders at x=25.
        calm = {**games.RULES, "invaders": {"easy": {"speed": 1, "move_every": 1000, "fire_every": 1000}}}
        screen = FakeScreen([" "] + [NO_KEY] * 15 + [" "] + [NO_KEY] * 15, (16, 52))
        with patch.object(games, "RULES", calm):
            games._invaders(screen, "easy")
        self.assertTrue(screen.titles("score 10"))
        self.assertTrue(screen.titles("score 20"))

    def test_player_moves_within_bounds_and_enemy_bullets_hit(self) -> None:
        keys = ["a"] * 30 + ["d"] * 40 + [curses.KEY_LEFT, curses.KEY_RIGHT] + [NO_KEY] * 4000
        screen = FakeScreen(keys, (16, 42))
        with patch.object(games.random, "choice", side_effect=lambda enemies: max(enemies)):
            games._invaders(screen, "normal")
        self.finished_with(screen, "Game over")


class EntryPointTests(GameTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        environment = patch.dict(os.environ, {"XDG_CONFIG_HOME": self.temp.name})
        environment.start()
        self.addCleanup(environment.stop)

    def run_main(self, args: list[str]) -> tuple[int, str, str]:
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = games.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_arguments_are_validated(self) -> None:
        self.assertEqual(self.run_main(["pong"])[0], 2)
        self.assertEqual(self.run_main(["snake", "easy", "extra"])[0], 2)
        code, _, error = self.run_main(["snake", "insane"])
        self.assertEqual(code, 2)
        self.assertIn("easy, normal, or hard", error)

    def test_configured_difficulty_is_the_default(self) -> None:
        from unlawful.config import ensure_layout, set_config_value

        ensure_layout()
        set_config_value("games.difficulty", "hard")
        with patch.object(games, "run_game", return_value=0) as run:
            self.assertEqual(self.run_main(["tetris"])[0], 0)
        run.assert_called_once_with("tetris", "hard")

    def test_invalid_config_is_reported(self) -> None:
        from unlawful.config import config_file, ensure_layout

        ensure_layout()
        config_file().write_text('[games]\ndifficulty = "insane"\n')
        code, _, error = self.run_main(["snake"])
        self.assertEqual(code, 2)
        self.assertIn("games.difficulty", error)

    def test_terminal_errors_are_reported(self) -> None:
        with patch.object(games.curses, "wrapper", side_effect=curses.error("no tty")):
            self.assertEqual(games.run_game("snake", "easy"), 1)
            code, _, error = self.run_main([])
        self.assertEqual(code, 1)
        self.assertIn("terminal error: no tty", error)

    def test_wrapper_runs_the_menu_and_named_games(self) -> None:
        calls: list[str] = []
        with patch.object(games.curses, "wrapper", side_effect=lambda function: calls.append("wrapped") or function(FakeScreen([]))):
            with patch.object(games, "_choose_and_run") as choose:
                self.assertEqual(self.run_main([])[0], 0)
            choose.assert_called_once()
            with patch.dict(games.GAME_RUNNERS, {"snake": lambda screen, level: calls.append(level)}):
                self.assertEqual(games.run_game("snake", "easy"), 0)
        self.assertEqual(calls, ["wrapped", "wrapped", "easy"])


if __name__ == "__main__":
    unittest.main()
