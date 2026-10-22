//! Tetris close to the modern guideline: 7-bag randomizer, next queue, hold,
//! ghost piece, rotation with wall kicks, lock delay, levels every 10 lines,
//! guideline gravity, combos and back-to-back Tetris bonuses.

use std::collections::VecDeque;
use std::io;

use super::{finish, inputs_until, pause, too_small, After, Button, Color, Input, Key, Level, Played, Rng, Screen, Style, FRAME};

pub const WIDTH: i32 = 10;
pub const VISIBLE: i32 = 20;
/// Spawn rows above the visible field.
pub const HIDDEN: i32 = 2;
pub const ROWS: i32 = VISIBLE + HIDDEN;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    I,
    O,
    T,
    S,
    Z,
    J,
    L,
}

pub const KINDS: [Kind; 7] = [Kind::I, Kind::O, Kind::T, Kind::S, Kind::Z, Kind::J, Kind::L];

impl Kind {
    /// Bounding box size and the cells of rotation 0.
    fn shape(self) -> (i32, [(i32, i32); 4]) {
        match self {
            Kind::I => (4, [(1, 0), (1, 1), (1, 2), (1, 3)]),
            Kind::O => (2, [(0, 0), (0, 1), (1, 0), (1, 1)]),
            Kind::T => (3, [(0, 1), (1, 0), (1, 1), (1, 2)]),
            Kind::S => (3, [(0, 1), (0, 2), (1, 0), (1, 1)]),
            Kind::Z => (3, [(0, 0), (0, 1), (1, 1), (1, 2)]),
            Kind::J => (3, [(0, 0), (1, 0), (1, 1), (1, 2)]),
            Kind::L => (3, [(0, 2), (1, 0), (1, 1), (1, 2)]),
        }
    }

    pub fn color(self) -> Color {
        match self {
            Kind::I => Color::Cyan,
            Kind::O => Color::Yellow,
            Kind::T => Color::Magenta,
            Kind::S => Color::Green,
            Kind::Z => Color::Red,
            Kind::J => Color::Blue,
            Kind::L => Color::DarkYellow,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Piece {
    pub kind: Kind,
    pub rotation: u8,
    pub row: i32,
    pub col: i32,
}

impl Piece {
    pub fn spawn(kind: Kind) -> Piece {
        let col = if kind == Kind::O { 4 } else { 3 };
        Piece { kind, rotation: 0, row: if kind == Kind::I { -1 } else { 0 }, col }
    }

    pub fn cells(&self) -> [(i32, i32); 4] {
        let (size, cells) = self.kind.shape();
        cells.map(|(mut r, mut c)| {
            for _ in 0..self.rotation {
                (r, c) = (c, size - 1 - r);
            }
            (self.row + r, self.col + c)
        })
    }

    fn rotated(&self, clockwise: bool) -> Piece {
        Piece { rotation: (self.rotation + if clockwise { 1 } else { 3 }) % 4, ..*self }
    }

    fn shifted(&self, rows: i32, cols: i32) -> Piece {
        Piece { row: self.row + rows, col: self.col + cols, ..*self }
    }
}

/// Kicks tried, in order, when a rotation does not fit in place.
const KICKS: [(i32, i32); 8] = [(0, 0), (0, -1), (0, 1), (-1, 0), (0, -2), (0, 2), (-1, -1), (-1, 1)];
const MAX_LOCK_RESETS: u32 = 15;

pub struct Rules {
    pub start_level: u32,
    pub gravity_scale: f64,
    pub lock_delay: f64,
    pub ghost: bool,
    pub hold: bool,
    pub previews: usize,
    /// Seconds between rising garbage rows (hard only).
    pub garbage_every: Option<f64>,
}

pub fn rules(level: Level) -> Rules {
    match level {
        Level::Easy => Rules { start_level: 1, gravity_scale: 1.6, lock_delay: 1.0, ghost: true, hold: true, previews: 3, garbage_every: None },
        Level::Normal => Rules { start_level: 1, gravity_scale: 1.0, lock_delay: 0.5, ghost: true, hold: true, previews: 3, garbage_every: None },
        Level::Hard => Rules {
            start_level: 12,
            gravity_scale: 1.0,
            lock_delay: 0.3,
            ghost: false,
            hold: false,
            previews: 1,
            garbage_every: Some(20.0),
        },
    }
}

/// Guideline gravity: seconds per row at `level`.
pub fn gravity(level: u32) -> f64 {
    let level = level.clamp(1, 20) as f64;
    (0.8 - (level - 1.0) * 0.007).powf(level - 1.0)
}

pub struct Tetris {
    pub board: Vec<[Option<Kind>; WIDTH as usize]>,
    pub piece: Piece,
    pub queue: VecDeque<Kind>,
    pub held: Option<Kind>,
    can_hold: bool,
    pub score: u64,
    pub lines: u32,
    combo: i32,
    back_to_back: bool,
    lock_timer: f64,
    lock_resets: u32,
    fall_timer: f64,
    garbage_timer: f64,
    pub over: bool,
    pub rules: Rules,
    /// Text of the last clear, e.g. "TETRIS" or "2 COMBO", for a moment.
    pub banner: Option<(String, f64)>,
}

impl Tetris {
    pub fn new(level: Level, rng: &mut Rng) -> Tetris {
        let mut tetris = Tetris {
            board: vec![[None; WIDTH as usize]; ROWS as usize],
            piece: Piece::spawn(Kind::T),
            queue: VecDeque::new(),
            held: None,
            can_hold: true,
            score: 0,
            lines: 0,
            combo: -1,
            back_to_back: false,
            lock_timer: 0.0,
            lock_resets: 0,
            fall_timer: 0.0,
            garbage_timer: 0.0,
            over: false,
            rules: rules(level),
            banner: None,
        };
        let first = tetris.next_kind(rng);
        tetris.piece = Piece::spawn(first);
        tetris
    }

    pub fn level(&self) -> u32 {
        self.rules.start_level + self.lines / 10
    }

    fn next_kind(&mut self, rng: &mut Rng) -> Kind {
        while self.queue.len() <= 7 {
            let mut bag = KINDS;
            rng.shuffle(&mut bag);
            self.queue.extend(bag);
        }
        self.queue.pop_front().unwrap()
    }

    pub fn fits(&self, piece: &Piece) -> bool {
        piece.cells().iter().all(|&(row, col)| {
            (0..WIDTH).contains(&col) && row < ROWS && (row < 0 || self.board[row as usize][col as usize].is_none())
        })
    }

    fn grounded(&self) -> bool {
        !self.fits(&self.piece.shifted(1, 0))
    }

    fn after_player_move(&mut self) {
        if self.grounded() && self.lock_resets < MAX_LOCK_RESETS {
            self.lock_timer = 0.0;
            self.lock_resets += 1;
        }
    }

    pub fn shift(&mut self, cols: i32) -> bool {
        let moved = self.piece.shifted(0, cols);
        if self.over || !self.fits(&moved) {
            return false;
        }
        self.piece = moved;
        self.after_player_move();
        true
    }

    pub fn rotate(&mut self, clockwise: bool) -> bool {
        if self.over || self.piece.kind == Kind::O {
            return false;
        }
        let turned = self.piece.rotated(clockwise);
        let Some(kicked) = KICKS.iter().map(|&(rows, cols)| turned.shifted(rows, cols)).find(|piece| self.fits(piece)) else {
            return false;
        };
        self.piece = kicked;
        self.after_player_move();
        true
    }

    pub fn soft_drop(&mut self) -> bool {
        let moved = self.piece.shifted(1, 0);
        if self.over || !self.fits(&moved) {
            return false;
        }
        self.piece = moved;
        self.score += 1;
        self.fall_timer = 0.0;
        true
    }

    pub fn ghost(&self) -> Piece {
        let mut ghost = self.piece;
        while self.fits(&ghost.shifted(1, 0)) {
            ghost = ghost.shifted(1, 0);
        }
        ghost
    }

    pub fn hard_drop(&mut self, rng: &mut Rng) {
        if self.over {
            return;
        }
        let ghost = self.ghost();
        self.score += 2 * (ghost.row - self.piece.row) as u64;
        self.piece = ghost;
        self.lock(rng);
    }

    pub fn hold(&mut self, rng: &mut Rng) -> bool {
        if self.over || !self.rules.hold || !self.can_hold {
            return false;
        }
        let current = self.piece.kind;
        let next = match self.held.replace(current) {
            Some(kind) => kind,
            None => self.next_kind(rng),
        };
        self.start_piece(next);
        self.can_hold = false;
        true
    }

    fn start_piece(&mut self, kind: Kind) {
        self.piece = Piece::spawn(kind);
        self.lock_timer = 0.0;
        self.lock_resets = 0;
        self.fall_timer = 0.0;
        if !self.fits(&self.piece) {
            self.over = true;
        }
    }

    fn lock(&mut self, rng: &mut Rng) {
        let cells = self.piece.cells();
        for &(row, col) in &cells {
            if row >= 0 {
                self.board[row as usize][col as usize] = Some(self.piece.kind);
            }
        }
        if cells.iter().all(|&(row, _)| row < HIDDEN) {
            self.over = true; // locked entirely above the field
            return;
        }
        let kept: Vec<_> = self.board.iter().copied().filter(|row| row.iter().any(Option::is_none)).collect();
        let cleared = ROWS as usize - kept.len();
        let mut board = vec![[None; WIDTH as usize]; cleared];
        board.extend(kept);
        self.board = board;
        self.score_clear(cleared as u32);
        let next = self.next_kind(rng);
        self.start_piece(next);
        self.can_hold = true;
    }

    fn score_clear(&mut self, cleared: u32) {
        let level = self.level() as u64;
        if cleared == 0 {
            self.combo = -1;
            return;
        }
        self.combo += 1;
        let mut points = [0, 100, 300, 500, 800][cleared as usize] * level;
        let tetris = cleared == 4;
        let mut banner = ["", "SINGLE", "DOUBLE", "TRIPLE", "TETRIS"][cleared as usize].to_string();
        if tetris && self.back_to_back {
            points = points * 3 / 2;
            banner = "BACK-TO-BACK TETRIS".into();
        }
        self.back_to_back = tetris;
        if self.combo > 0 {
            points += 50 * self.combo as u64 * level;
            banner.push_str(&format!(" · {} COMBO", self.combo));
        }
        self.score += points;
        self.lines += cleared;
        self.banner = Some((banner, 1.5));
    }

    /// Push a garbage row with one hole up from the bottom (hard mode).
    pub fn add_garbage(&mut self, rng: &mut Rng) {
        if self.board[0].iter().any(Option::is_some) {
            self.over = true;
            return;
        }
        self.board.remove(0);
        let hole = rng.below(WIDTH as usize);
        let mut row = [Some(Kind::J); WIDTH as usize];
        row[hole] = None;
        self.board.push(row);
        if !self.fits(&self.piece) {
            self.piece = self.piece.shifted(-1, 0);
            if !self.fits(&self.piece) {
                self.over = true;
            }
        }
    }

    /// Advance time: gravity, lock delay and garbage.
    pub fn update(&mut self, seconds: f64, rng: &mut Rng) {
        if self.over {
            return;
        }
        if let Some((text, left)) = self.banner.take() {
            if left > seconds {
                self.banner = Some((text, left - seconds));
            }
        }
        if let Some(every) = self.rules.garbage_every {
            self.garbage_timer += seconds;
            if self.garbage_timer >= every {
                self.garbage_timer -= every;
                self.add_garbage(rng);
                if self.over {
                    return;
                }
            }
        }
        if self.grounded() {
            self.lock_timer += seconds;
            if self.lock_timer >= self.rules.lock_delay {
                self.lock(rng);
            }
            return;
        }
        self.lock_timer = 0.0;
        self.fall_timer += seconds;
        let interval = gravity(self.level()) * self.rules.gravity_scale;
        while self.fall_timer >= interval {
            self.fall_timer -= interval;
            let moved = self.piece.shifted(1, 0);
            if !self.fits(&moved) {
                self.fall_timer = 0.0;
                break;
            }
            self.piece = moved;
        }
    }

    /// Move toward the column under the mouse pointer.
    pub fn follow(&mut self, target_col: i32) {
        for _ in 0..WIDTH {
            let center = self.piece.cells().iter().map(|(_, col)| *col).sum::<i32>().div_euclid(4);
            let step = (target_col - center).signum();
            if step == 0 || !self.shift(step) {
                break;
            }
        }
    }
}

struct Layout {
    top: i32,
    board_left: i32,
    left_panel: i32,
    right_panel: i32,
}

fn draw_mini(screen: &mut dyn Screen, y: i32, x: i32, kind: Kind, style_dim: bool) {
    let piece = Piece { kind, rotation: 0, row: 0, col: 0 };
    let style = if style_dim { Style::fg(kind.color()).dim() } else { Style::fg(kind.color()) };
    for (row, col) in piece.cells() {
        let row = if kind == Kind::I { row - 1 } else { row };
        screen.put(y + row, x + col * 2, "██", style);
    }
}

fn draw(screen: &mut dyn Screen, game: &Tetris, layout: &Layout, level: Level, best: Option<u64>) {
    screen.clear();
    screen.centered(0, &format!("TETRIS · {}", level.name()), Style::fg(Color::Yellow).bold());
    let (top, left) = (layout.top, layout.board_left);
    screen.frame_box(top, left, VISIBLE + 2, WIDTH * 2 + 2, Style::fg(Color::White));
    for row in HIDDEN..ROWS {
        for col in 0..WIDTH {
            let (y, x) = (top + 1 + row - HIDDEN, left + 1 + col * 2);
            match game.board[row as usize][col as usize] {
                Some(kind) => screen.put(y, x, "██", Style::fg(kind.color())),
                None => screen.put(y, x, " .", Style::fg(Color::Gray).dim()),
            }
        }
    }
    let visible = |row: i32| row >= HIDDEN;
    if game.rules.ghost && !game.over {
        for (row, col) in game.ghost().cells() {
            if visible(row) {
                screen.put(top + 1 + row - HIDDEN, left + 1 + col * 2, "░░", Style::fg(game.piece.kind.color()).dim());
            }
        }
    }
    for (row, col) in game.piece.cells() {
        if visible(row) {
            screen.put(top + 1 + row - HIDDEN, left + 1 + col * 2, "██", Style::fg(game.piece.kind.color()).bold());
        }
    }
    let panel = layout.left_panel;
    let label = Style::fg(Color::Gray);
    let value = Style::fg(Color::White).bold();
    if game.rules.hold {
        screen.put(top, panel, "HOLD", label);
        if let Some(kind) = game.held {
            draw_mini(screen, top + 2, panel, kind, !game.can_hold);
        }
    }
    let stats = [
        ("SCORE", game.score.to_string()),
        ("LEVEL", game.level().to_string()),
        ("LINES", game.lines.to_string()),
        ("BEST", best.map(|best| best.to_string()).unwrap_or_else(|| "—".into())),
    ];
    for (index, (name, text)) in stats.iter().enumerate() {
        let y = top + 6 + index as i32 * 3;
        screen.put(y, panel, name, label);
        screen.put(y + 1, panel, text, value);
    }
    screen.put(top, layout.right_panel, "NEXT", label);
    for (index, kind) in game.queue.iter().take(game.rules.previews).enumerate() {
        draw_mini(screen, top + 2 + index as i32 * 3, layout.right_panel, *kind, false);
    }
    if let Some((text, _)) = &game.banner {
        screen.centered(top + VISIBLE + 2, text, Style::fg(Color::Yellow).bold());
    }
    let hold = if game.rules.hold { "C hold · " } else { "" };
    screen.controls(&format!("←→ move · ↑/X rotate · Z back · ↓ soft · Space drop · {hold}P pause · mouse: move, click drop, right-click rotate"));
}

pub fn play(screen: &mut dyn Screen, level: Level, rng: &mut Rng, best: Option<u64>) -> io::Result<Played> {
    let (height, width) = screen.size();
    let total = 12 + WIDTH * 2 + 2 + 2 + 12;
    if height < VISIBLE + 5 || width < total {
        return too_small(screen, total, VISIBLE + 5);
    }
    let board_left = (width - (WIDTH * 2 + 2)) / 2;
    let layout = Layout { top: 1, board_left, left_panel: board_left - 13, right_panel: board_left + WIDTH * 2 + 4 };
    let mut game = Tetris::new(level, rng);
    let mut last = screen.now();
    loop {
        draw(screen, &game, &layout, level, best);
        screen.present()?;
        let deadline = screen.now() + FRAME;
        for input in inputs_until(screen, deadline)? {
            match input {
                Input::Key(Key::Left | Key::Char('a' | 'A')) => {
                    game.shift(-1);
                }
                Input::Key(Key::Right | Key::Char('d' | 'D')) => {
                    game.shift(1);
                }
                Input::Key(Key::Up | Key::Char('x' | 'X' | 'w' | 'W')) => {
                    game.rotate(true);
                }
                Input::Key(Key::Char('z' | 'Z')) => {
                    game.rotate(false);
                }
                Input::Key(Key::Down | Key::Char('s' | 'S')) => {
                    game.soft_drop();
                }
                Input::Key(Key::Char(' ')) | Input::Click { button: Button::Left, .. } => game.hard_drop(rng),
                Input::Click { button: Button::Right, .. } => {
                    game.rotate(true);
                }
                Input::Key(Key::Char('c' | 'C')) => {
                    game.hold(rng);
                }
                Input::Hover { x, .. } => {
                    if (layout.board_left..layout.board_left + WIDTH * 2 + 2).contains(&x) {
                        game.follow((x - layout.board_left - 1).div_euclid(2));
                    }
                }
                input if input.is_pause() => {
                    if pause(screen)? {
                        return Ok(Played { score: None, after: After::Leave });
                    }
                    last = screen.now();
                }
                input if input.is_leave() => return Ok(Played { score: None, after: After::Leave }),
                _ => {}
            }
        }
        let now = screen.now();
        game.update((now - last).min(0.25), rng);
        last = now;
        if game.over {
            draw(screen, &game, &layout, level, best);
            let details = [format!("Score {} · Level {} · Lines {}", game.score, game.level(), game.lines)];
            let after = finish(screen, "GAME OVER", &details, Some((game.score, best, "tetris")))?;
            return Ok(Played { score: Some(game.score), after });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::super::testing::*;
    use super::*;

    fn game(level: Level) -> Tetris {
        Tetris::new(level, &mut Rng::constant(0))
    }

    fn fill_row(game: &mut Tetris, row: i32, hole: Option<i32>) {
        for col in 0..WIDTH {
            game.board[row as usize][col as usize] = (Some(col) != hole).then_some(Kind::J);
        }
    }

    #[test]
    fn the_bag_deals_every_piece_once_per_seven() {
        let mut rng = Rng::seeded(3);
        let mut tetris = Tetris::new(Level::Normal, &mut rng);
        let mut seen = vec![tetris.piece.kind];
        for _ in 0..6 {
            seen.push(tetris.next_kind(&mut rng));
        }
        for kind in KINDS {
            assert_eq!(seen.iter().filter(|k| **k == kind).count(), 1, "{kind:?}");
        }
        assert!(tetris.queue.len() >= 7, "previews are always available");
    }

    #[test]
    fn rotation_cycles_and_kicks_off_walls() {
        let mut piece = Piece::spawn(Kind::T);
        let start = piece.cells();
        for _ in 0..4 {
            piece = piece.rotated(true);
        }
        assert_eq!(piece.cells(), start);
        assert_eq!(Piece::spawn(Kind::T).rotated(true).rotated(false), Piece::spawn(Kind::T));
        let mut tetris = game(Level::Normal);
        tetris.piece = Piece { kind: Kind::I, rotation: 1, row: 5, col: -2 }; // vertical, hugging the left wall
        assert!(tetris.fits(&tetris.piece));
        assert!(tetris.rotate(true), "kicked right to fit");
        assert!(tetris.piece.cells().iter().all(|(_, col)| *col >= 0));
        tetris.piece = Piece::spawn(Kind::O);
        assert!(!tetris.rotate(true), "O does not rotate");
    }

    #[test]
    fn walls_and_floor_stop_pieces() {
        let mut tetris = game(Level::Normal);
        while tetris.shift(-1) {}
        assert_eq!(tetris.piece.cells().iter().map(|(_, c)| *c).min(), Some(0));
        while tetris.shift(1) {}
        assert_eq!(tetris.piece.cells().iter().map(|(_, c)| *c).max(), Some(WIDTH - 1));
        let mut drops = 0;
        while tetris.soft_drop() {
            drops += 1;
        }
        assert_eq!(tetris.score, drops, "soft drop scores 1 per row");
        assert!(!tetris.soft_drop());
    }

    #[test]
    fn hard_drop_locks_scores_and_spawns_the_next_piece() {
        let mut tetris = game(Level::Normal);
        let mut rng = Rng::constant(0);
        let distance = (tetris.ghost().row - tetris.piece.row) as u64;
        let next = tetris.queue[0];
        tetris.hard_drop(&mut rng);
        assert_eq!(tetris.score, distance * 2);
        assert_eq!(tetris.piece.kind, next);
        assert_eq!(tetris.board.iter().flatten().filter(|cell| cell.is_some()).count(), 4);
    }

    #[test]
    fn clears_score_by_level_with_combo_and_back_to_back() {
        let mut tetris = game(Level::Normal);
        let mut rng = Rng::constant(0);
        for row in ROWS - 4..ROWS {
            fill_row(&mut tetris, row, Some(0));
        }
        tetris.piece = Piece { kind: Kind::I, rotation: 1, row: 0, col: -2 }; // vertical I in column 0
        tetris.hard_drop(&mut rng);
        assert_eq!(tetris.lines, 4);
        let first = tetris.score;
        assert!(first >= 800);
        assert_eq!(tetris.banner.as_ref().unwrap().0, "TETRIS");
        for row in ROWS - 4..ROWS {
            fill_row(&mut tetris, row, Some(0));
        }
        tetris.piece = Piece { kind: Kind::I, rotation: 1, row: 0, col: -2 };
        let before = tetris.score;
        tetris.hard_drop(&mut rng);
        let gained = tetris.score - before;
        assert!(gained >= 1200 + 50, "back-to-back 1.5x plus a 1 combo, got {gained}");
        assert!(tetris.banner.as_ref().unwrap().0.contains("BACK-TO-BACK"));
        assert!(tetris.banner.as_ref().unwrap().0.contains("COMBO"));
    }

    #[test]
    fn levels_rise_every_ten_lines_and_gravity_speeds_up() {
        let mut tetris = game(Level::Normal);
        assert_eq!(tetris.level(), 1);
        tetris.lines = 25;
        assert_eq!(tetris.level(), 3);
        assert!((gravity(1) - 1.0).abs() < 1e-9);
        assert!(gravity(5) < gravity(4) && gravity(12) < 0.05);
        assert_eq!(game(Level::Hard).level(), 12);
    }

    #[test]
    fn gravity_and_lock_delay() {
        let mut tetris = game(Level::Normal);
        let mut rng = Rng::constant(0);
        let row = tetris.piece.row;
        tetris.update(1.05, &mut rng);
        assert_eq!(tetris.piece.row, row + 1, "one row per second at level 1");
        for _ in 0..40 {
            tetris.update(1.0, &mut rng);
        }
        assert!(tetris.board.iter().flatten().any(Option::is_some), "the piece locked after resting");
        let mut resting = game(Level::Normal);
        while resting.soft_drop() {}
        resting.update(0.3, &mut rng);
        assert!(resting.shift(-1), "moving while grounded resets the lock timer");
        resting.update(0.3, &mut rng);
        assert!(resting.board.iter().flatten().all(Option::is_none), "still not locked");
        resting.update(0.3, &mut rng);
        assert!(resting.board.iter().flatten().any(Option::is_some));
    }

    #[test]
    fn hold_swaps_once_per_piece_and_is_off_on_hard() {
        let mut tetris = game(Level::Normal);
        let mut rng = Rng::constant(0);
        let first = tetris.piece.kind;
        assert!(tetris.hold(&mut rng));
        assert_eq!(tetris.held, Some(first));
        assert!(!tetris.hold(&mut rng), "only once until the piece locks");
        tetris.hard_drop(&mut rng);
        let current = tetris.piece.kind;
        assert!(tetris.hold(&mut rng));
        assert_eq!(tetris.piece.kind, first);
        assert_eq!(tetris.held, Some(current));
        assert!(!game(Level::Hard).hold(&mut rng));
        assert!(!game(Level::Hard).rules.ghost);
    }

    #[test]
    fn topping_out_and_garbage_end_the_game() {
        let mut tetris = game(Level::Normal);
        let mut rng = Rng::constant(0);
        for row in 0..ROWS {
            fill_row(&mut tetris, row, Some((row % 9) + 1));
        }
        tetris.start_piece(Kind::O);
        assert!(tetris.over);
        let mut hard = game(Level::Hard);
        hard.update(20.0, &mut rng);
        assert!(hard.board[(ROWS - 1) as usize].iter().filter(|c| c.is_some()).count() == 9, "a garbage row with one hole");
        fill_row(&mut hard, 0, Some(3));
        hard.add_garbage(&mut rng);
        assert!(hard.over);
    }

    #[test]
    fn mouse_follow_moves_toward_the_pointer() {
        let mut tetris = game(Level::Normal);
        tetris.follow(9);
        assert_eq!(tetris.piece.cells().iter().map(|(_, c)| *c).max(), Some(WIDTH - 1));
        tetris.follow(0);
        assert_eq!(tetris.piece.cells().iter().map(|(_, c)| *c).min(), Some(0));
    }

    #[test]
    fn plays_on_a_screen_until_topping_out() {
        let mut inputs = vec![special(Key::Left), key('x'), key('z'), special(Key::Down), key('c'), click(5, 60, Button::Right)];
        inputs.extend(std::iter::repeat_n(key(' '), 80));
        let mut screen = Fake::new((30, 100)).keys(&inputs).keys(&[special(Key::Esc)]);
        // Space on the end screen means "play again".
        let played = play(&mut screen, Level::Normal, &mut Rng::constant(0), None).unwrap();
        assert_eq!(played.after, After::Again);
        assert!(played.score.unwrap() > 0);
        assert!(screen.drew("GAME OVER"));
        assert!(screen.drew("HOLD"));
        let mut small = Fake::new((20, 40)).keys(&[key('x')]);
        assert_eq!(play(&mut small, Level::Easy, &mut Rng::constant(0), None).unwrap().score, None);
    }
}
