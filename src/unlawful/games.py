from __future__ import annotations

import curses
import random
import sys
import time
from collections import deque
from collections.abc import Callable, Sequence

from .config import ConfigError, load_config

GAME_NAMES = ("tetris", "snake", "minesweeper", "invaders")
GAME_LABELS = {
    "tetris": "Tetris",
    "snake": "Snake",
    "minesweeper": "Minesweeper",
    "invaders": "Space Invaders",
}
DIFFICULTIES = ("easy", "normal", "hard")
DIFFICULTY_LABELS = {"easy": "Easy", "normal": "Normal", "hard": "Hard"}
RULES: dict[str, dict[str, dict[str, int | float]]] = {
    "snake": {
        "easy": {"speed": 7},
        "normal": {"speed": 11},
        "hard": {"speed": 16},
    },
    "tetris": {
        "easy": {"speed": 1, "drop": 0.75},
        "normal": {"speed": 2, "drop": 0.5},
        "hard": {"speed": 3, "drop": 0.28},
    },
    "minesweeper": {
        "easy": {"rows": 9, "columns": 9, "mines": 10},
        "normal": {"rows": 12, "columns": 16, "mines": 32},
        "hard": {"rows": 16, "columns": 30, "mines": 99},
    },
    "invaders": {
        "easy": {"speed": 1, "move_every": 11, "fire_every": 20},
        "normal": {"speed": 2, "move_every": 8, "fire_every": 14},
        "hard": {"speed": 3, "move_every": 5, "fire_every": 8},
    },
}


def difficulty_rules(game: str, difficulty: str) -> dict[str, int | float]:
    if game not in RULES or difficulty not in DIFFICULTIES:
        raise ValueError(f"Unknown game or difficulty: {game} {difficulty}")
    return RULES[game][difficulty]


def playfield_size(terminal_height: int, terminal_width: int) -> tuple[int, int]:
    return max(0, terminal_height - 2), max(0, terminal_width - 2)


def _screen(stdscr: curses.window, *, timeout: int = -1) -> None:
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    stdscr.keypad(True)
    stdscr.timeout(timeout)


def _message(stdscr: curses.window, text: str) -> None:
    stdscr.timeout(-1)
    stdscr.erase()
    stdscr.border()
    height, width = stdscr.getmaxyx()
    stdscr.addstr(max(0, height // 2), max(0, (width - len(text)) // 2), text[: max(1, width - 1)])
    stdscr.addstr(max(0, height // 2 + 2), max(0, (width - 24) // 2), "Press any key to return")
    stdscr.refresh()
    stdscr.getch()


def _menu(stdscr: curses.window) -> str | None:
    _screen(stdscr)
    selected = 0
    while True:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        stdscr.border()
        title = "UNLAW ARCADE"
        stdscr.addstr(max(0, height // 2 - 5), max(0, (width - len(title)) // 2), title, curses.A_BOLD)
        for index, name in enumerate(GAME_NAMES):
            label = f"{index + 1}. {GAME_LABELS[name]}"
            attribute = curses.A_REVERSE if index == selected else curses.A_NORMAL
            stdscr.addstr(height // 2 - 2 + index, max(0, (width - len(label)) // 2), label, attribute)
        stdscr.addstr(height // 2 + 4, max(0, (width - 32) // 2), "↑/↓ select · Enter play · q quit")
        key = stdscr.getch()
        if key in {ord("q"), 27}:
            return None
        if key in {curses.KEY_UP, ord("k")}:
            selected = (selected - 1) % len(GAME_NAMES)
        elif key in {curses.KEY_DOWN, ord("j")}:
            selected = (selected + 1) % len(GAME_NAMES)
        elif ord("1") <= key <= ord("4"):
            return GAME_NAMES[key - ord("1")]
        elif key in {10, 13, curses.KEY_ENTER}:
            return GAME_NAMES[selected]


def _difficulty_menu(stdscr: curses.window, default: str) -> str | None:
    selected = DIFFICULTIES.index(default)
    while True:
        stdscr.erase()
        stdscr.border()
        height, width = stdscr.getmaxyx()
        title = "SELECT DIFFICULTY"
        stdscr.addstr(max(1, height // 2 - 3), max(1, (width - len(title)) // 2), title, curses.A_BOLD)
        for index, name in enumerate(DIFFICULTIES):
            label = f"{index + 1}. {DIFFICULTY_LABELS[name]}"
            attribute = curses.A_REVERSE if index == selected else curses.A_NORMAL
            stdscr.addstr(height // 2 + index, max(1, (width - len(label)) // 2), label, attribute)
        key = stdscr.getch()
        if key in {ord("q"), 27}:
            return None
        if key in {curses.KEY_UP, ord("k")}:
            selected = (selected - 1) % len(DIFFICULTIES)
        elif key in {curses.KEY_DOWN, ord("j")}:
            selected = (selected + 1) % len(DIFFICULTIES)
        elif ord("1") <= key <= ord("3"):
            return DIFFICULTIES[key - ord("1")]
        elif key in {10, 13, curses.KEY_ENTER}:
            return DIFFICULTIES[selected]


def _snake(stdscr: curses.window, difficulty: str) -> None:
    rules = difficulty_rules("snake", difficulty)
    _screen(stdscr, timeout=round(1000 / int(rules["speed"])))
    terminal_height, terminal_width = stdscr.getmaxyx()
    height, width = playfield_size(terminal_height, terminal_width)
    if height < 12 or width < 30:
        _message(stdscr, "Terminal must be at least 30x12")
        return
    snake = deque([(height // 2, width // 2 - offset) for offset in range(4)])
    direction = (0, 1)
    food = (height // 3, width // 3)
    score = 0
    while True:
        stdscr.erase()
        stdscr.border()
        stdscr.addstr(0, 2, f" Snake · {difficulty} · score {score} · q quit ")
        stdscr.addch(food[0] + 1, food[1] + 1, "●")
        for index, (y, x) in enumerate(snake):
            stdscr.addch(y + 1, x + 1, "@" if index == 0 else "o")
        key = stdscr.getch()
        choices = {
            curses.KEY_UP: (-1, 0), ord("w"): (-1, 0),
            curses.KEY_DOWN: (1, 0), ord("s"): (1, 0),
            curses.KEY_LEFT: (0, -1), ord("a"): (0, -1),
            curses.KEY_RIGHT: (0, 1), ord("d"): (0, 1),
        }
        if key == ord("q"):
            return
        candidate = choices.get(key)
        if candidate and candidate != (-direction[0], -direction[1]):
            direction = candidate
        head = ((snake[0][0] + direction[0]) % height, (snake[0][1] + direction[1]) % width)
        if head in snake:
            _message(stdscr, f"Game over · score {score}")
            return
        snake.appendleft(head)
        if head == food:
            score += 1
            empty = [(y, x) for y in range(height) for x in range(width) if (y, x) not in snake]
            if not empty:
                _message(stdscr, f"You win · score {score}")
                return
            food = random.choice(empty)
        else:
            snake.pop()


SHAPES = (
    ((0, 0), (0, 1), (0, 2), (0, 3)),
    ((0, 0), (1, 0), (1, 1), (1, 2)),
    ((0, 2), (1, 0), (1, 1), (1, 2)),
    ((0, 0), (0, 1), (1, 0), (1, 1)),
    ((0, 1), (0, 2), (1, 0), (1, 1)),
    ((0, 1), (1, 0), (1, 1), (1, 2)),
    ((0, 0), (0, 1), (1, 1), (1, 2)),
)


def _rotate(shape: tuple[tuple[int, int], ...]) -> tuple[tuple[int, int], ...]:
    rotated = [(x, -y) for y, x in shape]
    min_y = min(y for y, _ in rotated)
    min_x = min(x for _, x in rotated)
    return tuple((y - min_y, x - min_x) for y, x in rotated)


def _tetris(stdscr: curses.window, difficulty: str) -> None:
    rules = difficulty_rules("tetris", difficulty)
    _screen(stdscr, timeout=max(35, round(float(rules["drop"]) * 140)))
    rows, columns = 20, 10
    board = [[False] * columns for _ in range(rows)]
    score = 0
    shape = random.choice(SHAPES)
    y, x = 0, 3
    last_drop = time.monotonic()

    def valid(test_shape: tuple[tuple[int, int], ...], test_y: int, test_x: int) -> bool:
        return all(
            0 <= test_x + dx < columns
            and 0 <= test_y + dy < rows
            and not board[test_y + dy][test_x + dx]
            for dy, dx in test_shape
        )

    while True:
        stdscr.erase()
        terminal_height, terminal_width = stdscr.getmaxyx()
        if terminal_height < rows + 4 or terminal_width < columns * 2 + 4:
            _message(stdscr, "Terminal must be at least 22x23")
            return
        stdscr.border()
        stdscr.addstr(0, 2, f" Tetris · {difficulty} · score {score} · arrows/space · q ")
        offset_y = max(1, (terminal_height - (rows + 2)) // 2)
        offset_x = max(1, (terminal_width - (columns * 2 + 2)) // 2)
        stdscr.addstr(offset_y, offset_x, "┌" + "─" * (columns * 2) + "┐")
        cells = {(y + dy, x + dx) for dy, dx in shape}
        for row in range(rows):
            stdscr.addstr(offset_y + row + 1, offset_x, "│")
            for column in range(columns):
                stdscr.addstr(
                    offset_y + row + 1,
                    offset_x + 1 + column * 2,
                    "██" if board[row][column] or (row, column) in cells else "  ",
                )
            stdscr.addstr(offset_y + row + 1, offset_x + 1 + columns * 2, "│")
        stdscr.addstr(offset_y + rows + 1, offset_x, "└" + "─" * (columns * 2) + "┘")
        key = stdscr.getch()
        if key == ord("q"):
            return
        if key in {curses.KEY_LEFT, ord("a")} and valid(shape, y, x - 1):
            x -= 1
        elif key in {curses.KEY_RIGHT, ord("d")} and valid(shape, y, x + 1):
            x += 1
        elif key in {curses.KEY_UP, ord("w")}:
            rotated = _rotate(shape)
            if valid(rotated, y, x):
                shape = rotated
        elif key == ord(" "):
            while valid(shape, y + 1, x):
                y += 1
            last_drop = 0
        elif key in {curses.KEY_DOWN, ord("s")} and valid(shape, y + 1, x):
            y += 1
        now = time.monotonic()
        if now - last_drop < max(0.08, float(rules["drop"]) - score / 7000):
            continue
        last_drop = now
        if valid(shape, y + 1, x):
            y += 1
            continue
        for dy, dx in shape:
            board[y + dy][x + dx] = True
        kept = [row for row in board if not all(row)]
        cleared = rows - len(kept)
        board = [[False] * columns for _ in range(cleared)] + kept
        score += (0, 100, 300, 500, 800)[cleared]
        shape, y, x = random.choice(SHAPES), 0, 3
        if not valid(shape, y, x):
            _message(stdscr, f"Game over · score {score}")
            return


def _minesweeper(stdscr: curses.window, difficulty: str) -> None:
    _screen(stdscr)
    rules = difficulty_rules("minesweeper", difficulty)
    rows, columns, mine_count = int(rules["rows"]), int(rules["columns"]), int(rules["mines"])
    mines = set(random.sample([(y, x) for y in range(rows) for x in range(columns)], mine_count))
    revealed: set[tuple[int, int]] = set()
    flags: set[tuple[int, int]] = set()
    cursor = [0, 0]

    def neighbors(cell: tuple[int, int]) -> set[tuple[int, int]]:
        y, x = cell
        return {
            (ny, nx)
            for ny in range(max(0, y - 1), min(rows, y + 2))
            for nx in range(max(0, x - 1), min(columns, x + 2))
            if (ny, nx) != cell
        }

    def reveal(cell: tuple[int, int]) -> None:
        pending = [cell]
        while pending:
            current = pending.pop()
            if current in revealed or current in flags:
                continue
            revealed.add(current)
            if not (neighbors(current) & mines):
                pending.extend(neighbors(current) - mines - revealed)

    while True:
        stdscr.erase()
        terminal_height, terminal_width = stdscr.getmaxyx()
        if terminal_height < rows + 4 or terminal_width < columns * 2 + 4:
            _message(stdscr, f"{difficulty.title()} needs at least {columns * 2 + 4}x{rows + 4}")
            return
        stdscr.border()
        stdscr.addstr(0, 2, f" Minesweeper · {difficulty} · {mine_count} mines · space/f/q ")
        offset_y = max(2, (terminal_height - rows) // 2)
        offset_x = max(1, (terminal_width - columns * 2) // 2)
        for y in range(rows):
            for x in range(columns):
                cell = (y, x)
                if cell in flags:
                    char = "⚑"
                elif cell not in revealed:
                    char = "■"
                elif cell in mines:
                    char = "*"
                else:
                    count = len(neighbors(cell) & mines)
                    char = str(count) if count else "·"
                attribute = curses.A_REVERSE if [y, x] == cursor else curses.A_NORMAL
                stdscr.addstr(offset_y + y, offset_x + x * 2, char, attribute)
        key = stdscr.getch()
        if key == ord("q"):
            return
        if key in {curses.KEY_UP, ord("w")}:
            cursor[0] = max(0, cursor[0] - 1)
        elif key in {curses.KEY_DOWN, ord("s")}:
            cursor[0] = min(rows - 1, cursor[0] + 1)
        elif key in {curses.KEY_LEFT, ord("a")}:
            cursor[1] = max(0, cursor[1] - 1)
        elif key in {curses.KEY_RIGHT, ord("d")}:
            cursor[1] = min(columns - 1, cursor[1] + 1)
        elif key == ord("f"):
            cell = tuple(cursor)
            flags.discard(cell) if cell in flags else flags.add(cell)
        elif key in {ord(" "), 10, 13}:
            cell = tuple(cursor)
            reveal(cell)
            if cell in mines:
                revealed |= mines
                _message(stdscr, "Boom — game over")
                return
        if len(revealed - mines) == rows * columns - len(mines):
            _message(stdscr, "You cleared the field!")
            return


def _invaders(stdscr: curses.window, difficulty: str) -> None:
    rules = difficulty_rules("invaders", difficulty)
    _screen(stdscr, timeout=max(30, round(90 / int(rules["speed"]))))
    terminal_height, terminal_width = stdscr.getmaxyx()
    height, width = playfield_size(terminal_height, terminal_width)
    if height < 14 or width < 40:
        _message(stdscr, "Terminal must be at least 40x14")
        return
    player = width // 2
    enemy_rows = 2 if difficulty == "easy" else 3 if difficulty == "normal" else 4
    enemies = {(2 + row * 2, x) for row in range(enemy_rows) for x in range(5, width - 3, 5)}
    bullets: set[tuple[int, int]] = set()
    enemy_bullets: set[tuple[int, int]] = set()
    direction = 1
    tick = score = 0
    while True:
        stdscr.erase()
        stdscr.border()
        stdscr.addstr(0, 2, f" Space Invaders · {difficulty} · score {score} · ←/→ · space · q ")
        stdscr.addstr(height, player, "▲")
        for y, x in enemies:
            stdscr.addstr(y, x, "▼")
        for y, x in bullets:
            stdscr.addstr(y, x, "│")
        for y, x in enemy_bullets:
            stdscr.addstr(y, x, "·")
        key = stdscr.getch()
        if key == ord("q"):
            return
        if key in {curses.KEY_LEFT, ord("a")}:
            player = max(1, player - 2)
        elif key in {curses.KEY_RIGHT, ord("d")}:
            player = min(width - 2, player + 2)
        elif key == ord(" "):
            bullets.add((height - 1, player))
        bullets = {(y - 1, x) for y, x in bullets if y > 1}
        enemy_bullets = {(y + 1, x) for y, x in enemy_bullets if y < height}
        hits = {enemy for enemy in enemies if enemy in bullets}
        enemies -= hits
        bullets -= hits
        score += len(hits) * 10
        if any(y >= height and x == player for y, x in enemy_bullets):
            _message(stdscr, f"Game over · score {score}")
            return
        if not enemies:
            _message(stdscr, f"You win · score {score}")
            return
        tick += 1
        if tick % int(rules["move_every"]) == 0:
            edge = any(x + direction <= 0 or x + direction >= width for _, x in enemies)
            if edge:
                direction *= -1
                enemies = {(y + 1, x) for y, x in enemies}
            else:
                enemies = {(y, x + direction) for y, x in enemies}
        if tick % int(rules["fire_every"]) == 0 and enemies:
            y, x = random.choice(tuple(enemies))
            enemy_bullets.add((y + 1, x))
        if any(y >= height - 1 for y, _ in enemies):
            _message(stdscr, f"Game over · score {score}")
            return


GAME_RUNNERS: dict[str, Callable[[curses.window, str], None]] = {
    "tetris": _tetris,
    "snake": _snake,
    "minesweeper": _minesweeper,
    "invaders": _invaders,
}


def run_game(name: str, difficulty: str) -> int:
    try:
        curses.wrapper(lambda screen: GAME_RUNNERS[name](screen, difficulty))
        return 0
    except curses.error as error:
        print(f"unlaw game: terminal error: {error}", file=sys.stderr)
        return 1


def _choose_and_run(stdscr: curses.window, default_difficulty: str) -> None:
    while True:
        name = _menu(stdscr)
        if name is None:
            return
        difficulty = _difficulty_menu(stdscr, default_difficulty)
        if difficulty is not None:
            GAME_RUNNERS[name](stdscr, difficulty)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["-h"], ["--help"], ["help"]):
        print("Usage: ul game [tetris|snake|minesweeper|invaders] [easy|normal|hard]")
        return 0
    try:
        default_difficulty = str(load_config()["games"]["difficulty"])
    except ConfigError as error:
        print(f"unlaw game: {error}", file=sys.stderr)
        return 2
    if not args:
        try:
            curses.wrapper(lambda screen: _choose_and_run(screen, default_difficulty))
            return 0
        except curses.error as error:
            print(f"unlaw game: terminal error: {error}", file=sys.stderr)
            return 1
    if len(args) not in {1, 2} or args[0] not in GAME_NAMES:
        print("Usage: ul game [tetris|snake|minesweeper|invaders] [easy|normal|hard]", file=sys.stderr)
        return 2
    difficulty = args[1] if len(args) == 2 else default_difficulty
    if difficulty not in DIFFICULTIES:
        print("unlaw game: difficulty must be easy, normal, or hard", file=sys.stderr)
        return 2
    return run_game(args[0], difficulty)


if __name__ == "__main__":
    raise SystemExit(main())
