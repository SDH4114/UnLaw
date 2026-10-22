//! Minesweeper like the Windows classic: Beginner, Intermediate and Expert
//! boards, a safe first click, flags on right-click, chording on numbers,
//! classic number colors and a timer.

use std::collections::HashSet;
use std::io;

use super::{finish, inputs_until, pause, too_small, After, Button, Color, Input, Key, Level, Played, Rng, Screen, Style};

type Cell = (i32, i32);

#[derive(Debug, PartialEq, Eq)]
pub enum Outcome {
    Nothing,
    Revealed,
    Lost,
    Won,
}

pub struct Mines {
    pub rows: i32,
    pub columns: i32,
    pub mine_count: usize,
    /// Empty until the first reveal, so the first click is always safe.
    pub mines: HashSet<Cell>,
    pub revealed: HashSet<Cell>,
    pub flags: HashSet<Cell>,
    /// Keep the first click's neighbours free too, so it opens an area.
    safe_opening: bool,
    pub exploded: Option<Cell>,
    pub cursor: Cell,
}

impl Mines {
    pub fn new(level: Level) -> Mines {
        let (rows, columns, mine_count, safe_opening) = level.pick((9, 9, 10, true), (16, 16, 40, true), (16, 30, 99, false));
        Mines {
            rows,
            columns,
            mine_count,
            mines: HashSet::new(),
            revealed: HashSet::new(),
            flags: HashSet::new(),
            safe_opening,
            exploded: None,
            cursor: (rows / 2, columns / 2),
        }
    }

    pub fn started(&self) -> bool {
        !self.mines.is_empty()
    }

    pub fn finished(&self) -> bool {
        self.exploded.is_some() || self.won()
    }

    pub fn won(&self) -> bool {
        self.started() && self.revealed.len() == (self.rows * self.columns) as usize - self.mine_count
    }

    pub fn inside(&self, (y, x): Cell) -> bool {
        (0..self.rows).contains(&y) && (0..self.columns).contains(&x)
    }

    pub fn neighbors(&self, (y, x): Cell) -> Vec<Cell> {
        (y - 1..=y + 1)
            .flat_map(|ny| (x - 1..=x + 1).map(move |nx| (ny, nx)))
            .filter(|&cell| cell != (y, x) && self.inside(cell))
            .collect()
    }

    pub fn count(&self, cell: Cell) -> usize {
        self.neighbors(cell).iter().filter(|n| self.mines.contains(n)).count()
    }

    fn place_mines(&mut self, first: Cell, rng: &mut Rng) {
        let mut keep_free: HashSet<Cell> = HashSet::from([first]);
        if self.safe_opening {
            keep_free.extend(self.neighbors(first));
        }
        let mut cells: Vec<Cell> = (0..self.rows)
            .flat_map(|y| (0..self.columns).map(move |x| (y, x)))
            .filter(|cell| !keep_free.contains(cell))
            .collect();
        rng.shuffle(&mut cells);
        self.mines = cells.into_iter().take(self.mine_count).collect();
    }

    pub fn toggle_flag(&mut self, cell: Cell) {
        if self.finished() || !self.inside(cell) || self.revealed.contains(&cell) {
            return;
        }
        if !self.flags.remove(&cell) {
            self.flags.insert(cell);
        }
    }

    pub fn flags_left(&self) -> i64 {
        self.mine_count as i64 - self.flags.len() as i64
    }

    /// Reveal a hidden cell (flood-filling empty areas), or chord a number.
    pub fn open(&mut self, cell: Cell, rng: &mut Rng) -> Outcome {
        if self.finished() || !self.inside(cell) || self.flags.contains(&cell) {
            return Outcome::Nothing;
        }
        if self.revealed.contains(&cell) {
            return self.chord(cell);
        }
        if !self.started() {
            self.place_mines(cell, rng);
        }
        self.flood(cell)
    }

    fn flood(&mut self, start: Cell) -> Outcome {
        if self.mines.contains(&start) {
            self.exploded = Some(start);
            return Outcome::Lost;
        }
        let mut pending = vec![start];
        while let Some(cell) = pending.pop() {
            if self.revealed.contains(&cell) || self.flags.contains(&cell) {
                continue;
            }
            self.revealed.insert(cell);
            if self.count(cell) == 0 {
                pending.extend(self.neighbors(cell));
            }
        }
        if self.won() { Outcome::Won } else { Outcome::Revealed }
    }

    /// When a number has as many flags around it, open its other neighbours.
    pub fn chord(&mut self, cell: Cell) -> Outcome {
        let around = self.neighbors(cell);
        let flagged = around.iter().filter(|n| self.flags.contains(n)).count();
        if self.count(cell) == 0 || flagged != self.count(cell) {
            return Outcome::Nothing;
        }
        let mut result = Outcome::Nothing;
        for neighbor in around {
            if self.revealed.contains(&neighbor) || self.flags.contains(&neighbor) {
                continue;
            }
            match self.flood(neighbor) {
                Outcome::Lost => return Outcome::Lost,
                Outcome::Won => result = Outcome::Won,
                Outcome::Revealed if result == Outcome::Nothing => result = Outcome::Revealed,
                _ => {}
            }
        }
        result
    }

    pub fn move_cursor(&mut self, dy: i32, dx: i32) {
        self.cursor = ((self.cursor.0 + dy).clamp(0, self.rows - 1), (self.cursor.1 + dx).clamp(0, self.columns - 1));
    }
}

fn number_color(count: usize) -> Color {
    match count {
        1 => Color::Blue,
        2 => Color::Green,
        3 => Color::Red,
        4 => Color::DarkBlue,
        5 => Color::DarkRed,
        6 => Color::DarkCyan,
        7 => Color::White,
        _ => Color::Gray,
    }
}

struct Layout {
    top: i32,
    left: i32,
}

impl Layout {
    fn cell_at(&self, y: i32, x: i32) -> Cell {
        (y - self.top - 1, (x - self.left - 1).div_euclid(2))
    }
}

fn draw(screen: &mut dyn Screen, game: &Mines, layout: &Layout, level: Level, seconds: u64, best: Option<u64>) {
    screen.clear();
    let best = best.map(|best| format!(" · Best {best}s")).unwrap_or_default();
    let title = format!("MINESWEEPER · {} · Mines {} · Time {seconds}s{best}", level.name(), game.flags_left());
    screen.centered(0, &title, Style::fg(Color::Yellow).bold());
    screen.frame_box(layout.top, layout.left, game.rows + 2, game.columns * 2 + 2, Style::fg(Color::White));
    let lost = game.exploded.is_some();
    let won = game.won();
    for y in 0..game.rows {
        for x in 0..game.columns {
            let cell = (y, x);
            let mine = game.mines.contains(&cell);
            let flagged = game.flags.contains(&cell);
            let (text, mut style) = if game.exploded == Some(cell) {
                ("✱ ".to_string(), Style::fg(Color::White).bold().on(Color::Red))
            } else if flagged && lost && !mine {
                ("✗ ".to_string(), Style::fg(Color::Red).bold())
            } else if flagged || (won && mine) {
                ("⚑ ".to_string(), Style::fg(Color::Red).bold())
            } else if lost && mine {
                ("✱ ".to_string(), Style::fg(Color::White).bold())
            } else if !game.revealed.contains(&cell) {
                ("■ ".to_string(), Style::fg(Color::Gray))
            } else {
                match game.count(cell) {
                    0 => ("· ".to_string(), Style::fg(Color::Gray).dim()),
                    count => (format!("{count} "), Style::fg(number_color(count)).bold()),
                }
            };
            if cell == game.cursor && !game.finished() {
                style = style.reverse();
            }
            screen.put(layout.top + 1 + y, layout.left + 1 + x * 2, &text, style);
        }
    }
    screen.controls("click / Space open · right-click / F flag · click a number to clear around it · arrows move · P pause · Esc quit");
}

pub fn play(screen: &mut dyn Screen, level: Level, rng: &mut Rng, best: Option<u64>) -> io::Result<Played> {
    let mut game = Mines::new(level);
    let (height, width) = screen.size();
    let (need_width, need_height) = (game.columns * 2 + 4, game.rows + 5);
    if width < need_width || height < need_height {
        return too_small(screen, need_width, need_height);
    }
    let layout = Layout { top: ((height - game.rows - 3) / 2).max(1), left: (width - (game.columns * 2 + 2)) / 2 };
    let mut started_at: Option<f64> = None;
    let elapsed = |screen: &dyn Screen, started_at: Option<f64>| started_at.map(|start| (screen.now() - start) as u64).unwrap_or(0);
    loop {
        let seconds = elapsed(screen, started_at);
        draw(screen, &game, &layout, level, seconds, best);
        screen.present()?;
        let mut outcome = Outcome::Nothing;
        let deadline = screen.now() + 0.25;
        for input in inputs_until(screen, deadline)? {
            let result = match input {
                Input::Key(Key::Up | Key::Char('w' | 'W')) => {
                    game.move_cursor(-1, 0);
                    Outcome::Nothing
                }
                Input::Key(Key::Down | Key::Char('s' | 'S')) => {
                    game.move_cursor(1, 0);
                    Outcome::Nothing
                }
                Input::Key(Key::Left | Key::Char('a' | 'A')) => {
                    game.move_cursor(0, -1);
                    Outcome::Nothing
                }
                Input::Key(Key::Right | Key::Char('d' | 'D')) => {
                    game.move_cursor(0, 1);
                    Outcome::Nothing
                }
                Input::Key(Key::Char('f' | 'F')) => {
                    game.toggle_flag(game.cursor);
                    Outcome::Nothing
                }
                Input::Key(Key::Char(' ') | Key::Enter) => game.open(game.cursor, rng),
                Input::Hover { y, x } => {
                    let cell = layout.cell_at(y, x);
                    if game.inside(cell) {
                        game.cursor = cell;
                    }
                    Outcome::Nothing
                }
                Input::Click { y, x, button } => {
                    let cell = layout.cell_at(y, x);
                    if game.inside(cell) {
                        game.cursor = cell;
                    }
                    match button {
                        Button::Left => game.open(cell, rng),
                        Button::Right => {
                            game.toggle_flag(cell);
                            Outcome::Nothing
                        }
                        Button::Middle => game.chord(cell),
                    }
                }
                input if input.is_pause() => {
                    let paused_at = screen.now();
                    if pause(screen)? {
                        return Ok(Played { score: None, after: After::Leave });
                    }
                    started_at = started_at.map(|start| start + screen.now() - paused_at);
                    Outcome::Nothing
                }
                input if input.is_leave() => return Ok(Played { score: None, after: After::Leave }),
                _ => Outcome::Nothing,
            };
            if started_at.is_none() && game.started() {
                started_at = Some(screen.now());
            }
            if matches!(result, Outcome::Lost | Outcome::Won) {
                outcome = result;
                break;
            }
        }
        if matches!(outcome, Outcome::Lost | Outcome::Won) {
            let seconds = elapsed(screen, started_at).max(1);
            draw(screen, &game, &layout, level, seconds, best);
            let after = if outcome == Outcome::Won {
                finish(screen, "YOU CLEARED THE FIELD!", &[format!("Time {seconds}s")], Some((seconds, best, "minesweeper")))?
            } else {
                finish(screen, "BOOM — GAME OVER", &["You stepped on a mine.".into()], None)?
            };
            let score = (outcome == Outcome::Won).then_some(seconds);
            return Ok(Played { score, after });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::super::testing::*;
    use super::*;

    fn board(mines: &[Cell]) -> Mines {
        let mut game = Mines::new(Level::Easy);
        game.mines = mines.iter().copied().collect();
        game.mine_count = mines.len();
        game
    }

    #[test]
    fn classic_board_sizes() {
        let sizes: Vec<(i32, i32, usize)> =
            [Level::Easy, Level::Normal, Level::Hard].map(Mines::new).iter().map(|g| (g.rows, g.columns, g.mine_count)).collect();
        assert_eq!(sizes, vec![(9, 9, 10), (16, 16, 40), (16, 30, 99)]);
    }

    #[test]
    fn the_first_click_is_safe_and_opens_an_area() {
        for seed in 0..50 {
            let mut game = Mines::new(Level::Normal);
            let outcome = game.open((8, 8), &mut Rng::seeded(seed));
            assert_ne!(outcome, Outcome::Lost);
            assert_eq!(game.mines.len(), 40);
            assert!(game.neighbors((8, 8)).iter().all(|n| !game.mines.contains(n)), "opening is mine free");
            assert!(game.revealed.len() > 1, "an area opened");
        }
        let mut hard = Mines::new(Level::Hard);
        hard.open((0, 0), &mut Rng::seeded(1));
        assert!(!hard.mines.contains(&(0, 0)), "hard keeps only the clicked cell safe");
    }

    #[test]
    fn flood_fill_stops_at_numbers() {
        let mut game = board(&[(8, 8)]);
        assert_eq!(game.open((0, 0), &mut Rng::constant(0)), Outcome::Won);
        assert!(game.revealed.contains(&(7, 7)) && !game.revealed.contains(&(8, 8)));
        let mut game = board(&[(8, 8), (0, 8)]);
        game.open((0, 0), &mut Rng::constant(0));
        assert_eq!(game.count((0, 7)), 1);
        assert!(game.revealed.contains(&(0, 7)), "numbers on the edge are revealed");
    }

    #[test]
    fn flags_block_opening_and_count_down() {
        let mut game = board(&[(4, 4), (0, 0)]);
        game.toggle_flag((0, 0));
        assert_eq!(game.flags_left(), 1);
        assert_eq!(game.open((0, 0), &mut Rng::constant(0)), Outcome::Nothing);
        game.toggle_flag((0, 0));
        assert_eq!(game.flags_left(), 2);
        assert_eq!(game.open((0, 0), &mut Rng::constant(0)), Outcome::Lost);
        assert_eq!(game.exploded, Some((0, 0)));
        game.toggle_flag((1, 1));
        assert!(game.flags.is_empty(), "nothing changes after the game ends");
    }

    #[test]
    fn chording_opens_neighbours_or_explodes_on_a_wrong_flag() {
        let mut game = board(&[(0, 1), (5, 5)]);
        game.revealed.insert((1, 1));
        assert_eq!(game.chord((1, 1)), Outcome::Nothing, "needs a flag first");
        game.flags.insert((0, 1));
        assert!(matches!(game.open((1, 1), &mut Rng::constant(0)), Outcome::Revealed | Outcome::Won));
        assert!(game.revealed.contains(&(0, 0)) && game.revealed.contains(&(2, 2)));
        let mut wrong = board(&[(0, 1), (5, 5)]);
        wrong.revealed.insert((1, 1));
        wrong.flags.insert((0, 0));
        assert_eq!(wrong.chord((1, 1)), Outcome::Lost);
    }

    #[test]
    fn plays_with_the_mouse_until_a_mine_then_shows_the_field() {
        let mut screen = Fake::new((24, 60));
        let layout_top = (24 - 9 - 3) / 2;
        let layout_left = (60 - 20) / 2;
        let at = |row: i32, col: i32| (layout_top + 1 + row, layout_left + 1 + col * 2);
        let (y, x) = at(4, 4);
        let mut inputs = vec![click(y, x, Button::Left)];
        // Right-click flags a corner; then open every cell until something happens.
        let (fy, fx) = at(0, 0);
        inputs.push(click(fy, fx, Button::Right));
        for row in 0..9 {
            for col in 0..9 {
                let (y, x) = at(row, col);
                inputs.push(click(y, x, Button::Left));
            }
        }
        screen = screen.keys(&inputs).keys(&[special(Key::Esc)]);
        // A click on the end screen means "play again".
        let played = play(&mut screen, Level::Easy, &mut Rng::seeded(5), Some(30)).unwrap();
        assert_eq!(played.after, After::Again);
        assert!(screen.drew("BOOM") || screen.drew("CLEARED"));
        assert!(screen.drew("⚑") || screen.drew("✗"));
    }

    #[test]
    fn keyboard_play_pause_and_quit() {
        let mut screen = Fake::new((24, 60)).keys(&[key(' '), special(Key::Up), key('f'), key('p'), key('p'), key('q')]);
        assert_eq!(play(&mut screen, Level::Easy, &mut Rng::seeded(2), None).unwrap().score, None);
        assert!(screen.drew("PAUSED"));
        let mut small = Fake::new((10, 30)).keys(&[key('x')]);
        assert_eq!(play(&mut small, Level::Hard, &mut Rng::seeded(2), None).unwrap().after, After::Leave);
    }
}
