//! Chess: the board on the left, the players, clocks, captured pieces and the move list on
//! the right. One player against the bot (either color, three strengths) or two players on one
//! keyboard. Optional Fischer clock. The last move, the selected piece, its legal targets and a
//! king in check are shown with square colors.
//!
//! The bot thinks on its own thread with a clone of the board, so the clock, pause and the desk
//! page stay live while it searches; leaving or undoing raises its stop flag.

pub mod board;
mod search;
mod setup;
mod sprites;

use std::io;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{mpsc, Arc};
use std::thread;
use std::time::Duration;

use super::{
    center_block, finish, pause, too_small, wait_for_room, After, Button, Color, Input, Key, Level, Played, Rng, Scores, Screen, Style,
};
use board::{file_of, rank_of, square_at, Board, Kind, Move, Outcome, Piece, Side};

/// Square sizes (columns x rows), largest first: each is roughly square on screen.
const SIZES: [(i32, i32); 3] = [(7, 3), (5, 2), (3, 1)];
const PANEL: i32 = 26;
const GAP: i32 = 2;
/// Width and height of the smallest layout, plus the HUD and controls rows.
pub const MIN_WIDTH: i32 = 2 + 8 * 3 + GAP + PANEL;
pub const MIN_HEIGHT: i32 = 8 + 1 + 2;
/// The bot never answers faster than this (seconds), so its move can be seen arriving.
const BOT_MIN_DELAY: f64 = 0.35;

/// How pieces look: drawn shapes (on 5x2 and larger squares), font glyphs, or letters. `L` cycles.
static STYLE: AtomicUsize = AtomicUsize::new(0);
const STYLES: usize = 3;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    /// The human plays this side against the bot.
    Bot(Side),
    Duel,
}

impl Mode {
    fn bot_side(self) -> Option<Side> {
        match self {
            Mode::Bot(human) => Some(human.other()),
            Mode::Duel => None,
        }
    }
}

/// Fischer clock. It starts after White's first move.
#[derive(Clone, Copy, Debug)]
struct Clock {
    left: [f64; 2],
    increment: f64,
    /// When the side to move started thinking; `None` while stopped.
    since: Option<f64>,
}

impl Clock {
    fn new(base: f64, increment: f64) -> Clock {
        Clock {
            left: [base; 2],
            increment,
            since: None,
        }
    }

    fn remaining(&self, side: Side, turn: Side, now: f64) -> f64 {
        let left = self.left[side.index()];
        match self.since {
            Some(since) if side == turn => left - (now - since),
            _ => left,
        }
    }

    /// `mover` just moved: charge the time, add the increment and start the other clock.
    fn pressed(&mut self, mover: Side, now: f64, first_move: bool) {
        if let Some(since) = self.since {
            self.left[mover.index()] -= now - since;
        }
        if !first_move {
            self.left[mover.index()] += self.increment;
        }
        self.since = Some(now);
    }

    fn stop(&mut self, turn: Side, now: f64) {
        if let Some(since) = self.since.take() {
            self.left[turn.index()] -= now - since;
        }
    }

    fn resume(&mut self, now: f64, started: bool) {
        if started {
            self.since = Some(now);
        }
    }
}

struct Thinking {
    receiver: mpsc::Receiver<Option<Move>>,
    stop: Arc<AtomicBool>,
    started: f64,
}

impl Drop for Thinking {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
    }
}

fn start_bot(board: &Board, level: Level, clock: Option<f64>, seed: u64, now: f64) -> Thinking {
    let (sender, receiver) = mpsc::channel();
    let stop = Arc::new(AtomicBool::new(false));
    let flag = Arc::clone(&stop);
    let board = board.clone();
    thread::spawn(move || {
        let mv = search::choose(&board, level, clock, &mut Rng::seeded(seed), &flag);
        let _ = sender.send(mv);
    });
    Thinking {
        receiver,
        stop,
        started: now,
    }
}

struct Game {
    board: Board,
    sans: Vec<String>,
    mode: Mode,
    level: Level,
    clock: Option<Clock>,
    clock_label: String,
    outcome: Option<Outcome>,
    /// A take-back happened: the game no longer counts for the record.
    undone: bool,
}

impl Game {
    fn new(mode: Mode, level: Level, clock: Option<setup::TimeControl>) -> Game {
        Game {
            board: Board::start(),
            sans: Vec::new(),
            mode,
            level,
            clock: clock.map(|clock| Clock::new(clock.minutes as f64 * 60.0, clock.increment as f64)),
            clock_label: clock.map_or("off".into(), |clock| clock.label()),
            outcome: None,
            undone: false,
        }
    }

    fn human_to_move(&self) -> bool {
        self.mode.bot_side() != Some(self.board.side)
    }

    fn play(&mut self, mv: Move, now: f64) {
        let mover = self.board.side;
        let first = self.board.ply() == 0;
        self.sans.push(self.board.san(mv));
        self.board.make(mv);
        if let Some(clock) = &mut self.clock {
            clock.pressed(mover, now, first);
        }
        self.outcome = self.board.outcome();
        if let (Some(clock), Some(_)) = (&mut self.clock, self.outcome) {
            clock.stop(self.board.side, now);
        }
    }

    /// Take back one ply.
    fn take_back(&mut self) -> bool {
        if self.board.ply() == 0 {
            return false;
        }
        self.board.unmake();
        self.sans.pop();
        self.undone = true;
        true
    }

    fn check_flag(&mut self, now: f64) {
        let Some(clock) = &mut self.clock else { return };
        if self.outcome.is_some() {
            return;
        }
        let turn = self.board.side;
        if clock.remaining(turn, turn, now) <= 0.0 {
            clock.stop(turn, now);
            clock.left[turn.index()] = 0.0;
            self.outcome = Some(if self.board.cannot_mate(turn.other()) {
                Outcome::FlagNoMaterial
            } else {
                Outcome::Flag(turn)
            });
        }
    }

    fn name(&self, side: Side) -> String {
        match self.mode {
            Mode::Bot(human) if human == side => "You".into(),
            Mode::Bot(_) => format!("Bot · {}", self.level.name()),
            Mode::Duel => side.name().into(),
        }
    }
}

#[derive(Default)]
struct View {
    flipped: bool,
    selected: Option<u8>,
    /// Keyboard cursor, shown once a key moved it.
    cursor: u8,
    keyboard: bool,
    /// Waiting for the promotion piece of this move.
    promotion: Option<(u8, u8)>,
    hide_clock: bool,
    /// R was pressed once: the next R resigns.
    resign_armed: bool,
}

#[derive(Clone, Copy)]
struct Layout {
    sw: i32,
    sh: i32,
    top: i32,
    left: i32,
    width: i32,
    panel_left: i32,
}

impl Layout {
    fn fit(size: (i32, i32)) -> Option<Layout> {
        let (rows, columns) = size;
        SIZES.iter().find_map(|&(sw, sh)| {
            let height = 8 * sh + 1;
            let width = 2 + 8 * sw + GAP + PANEL;
            (rows - 2 >= height && columns >= width).then(|| {
                let (top, left) = center_block(size, height, width);
                Layout {
                    sw,
                    sh,
                    top,
                    left,
                    width,
                    panel_left: left + 2 + 8 * sw + GAP,
                }
            })
        })
    }

    fn height(&self) -> i32 {
        8 * self.sh + 1
    }

    /// Screen position (row, column) of a square's top-left corner.
    fn origin(&self, square: u8, flipped: bool) -> (i32, i32) {
        let (row, column) = if flipped {
            (rank_of(square), 7 - file_of(square))
        } else {
            (7 - rank_of(square), file_of(square))
        };
        (self.top + row * self.sh, self.left + 2 + column * self.sw)
    }

    fn square_at(&self, y: i32, x: i32, flipped: bool) -> Option<u8> {
        let (dy, dx) = (y - self.top, x - self.left - 2);
        if dy < 0 || dx < 0 || dy >= 8 * self.sh || dx >= 8 * self.sw {
            return None;
        }
        let (row, column) = (dy / self.sh, dx / self.sw);
        if flipped {
            square_at(7 - column, row)
        } else {
            square_at(column, 7 - row)
        }
    }

    /// The promotion picker: four cells over the middle of the board.
    fn picker(&self) -> (i32, i32) {
        let width = 4 * 4 + 2;
        (
            self.top + 4 * self.sh - 2,
            self.left + 2 + 4 * self.sw - width / 2,
        )
    }
}

const PROMOTIONS: [Kind; 4] = [Kind::Queen, Kind::Rook, Kind::Bishop, Kind::Knight];

fn glyph(piece: Piece) -> &'static str {
    if STYLE.load(Ordering::Relaxed) == 2 {
        return match piece.kind {
            Kind::Pawn => "P",
            Kind::Knight => "N",
            Kind::Bishop => "B",
            Kind::Rook => "R",
            Kind::Queen => "Q",
            Kind::King => "K",
        };
    }
    // Filled glyphs for both colors: outlined ones look inverted on dark themes.
    match piece.kind {
        Kind::Pawn => "♟",
        Kind::Knight => "♞",
        Kind::Bishop => "♝",
        Kind::Rook => "♜",
        Kind::Queen => "♛",
        Kind::King => "♚",
    }
}

fn piece_style(side: Side) -> Style {
    match side {
        Side::White => Style::fg(Color::PieceWhite).bold(),
        Side::Black => Style::fg(Color::PieceBlack).bold(),
    }
}

fn clock_text(seconds: f64) -> String {
    let seconds = seconds.max(0.0);
    if seconds < 10.0 {
        return format!("0:{:04.1}", (seconds * 10.0).floor() / 10.0);
    }
    let whole = seconds.ceil() as u64;
    format!("{}:{:02}", whole / 60, whole % 60)
}

fn draw(
    screen: &mut dyn Screen,
    game: &Game,
    view: &View,
    layout: &Layout,
    targets: &[Move],
    status: &str,
    now: f64,
) {
    screen.clear();
    let mode = match game.mode {
        Mode::Bot(_) => format!("vs bot · {}", game.level.name()),
        Mode::Duel => "2 players".into(),
    };
    screen.hud(
        layout.top - 1,
        layout.left,
        layout.width,
        &format!("CHESS · {mode}"),
        &[("clock", game.clock_label.clone()), ("move", game.board.fullmove.to_string())],
    );
    draw_board(screen, game, view, layout, targets);
    draw_panel(screen, game, view, layout, status, now);
    if view.promotion.is_some() {
        let side = game.board.side;
        let (y, x) = layout.picker();
        screen.frame_box(y - 1, x - 1, 3, 4 * 4 + 4, Style::fg(Color::Cyan));
        screen.put(y, x, &" ".repeat(4 * 4 + 2), Style::PLAIN);
        for (index, kind) in PROMOTIONS.iter().enumerate() {
            let cell = x + 1 + index as i32 * 4;
            let bg = if index % 2 == 0 {
                Color::BoardLight
            } else {
                Color::BoardDark
            };
            screen.put(
                y,
                cell,
                &format!(" {} ", glyph(Piece::new(side, *kind))),
                piece_style(side).on(bg),
            );
        }
    }
    let long = "click or arrows+Enter move · U undo · F flip · L pieces · T clock · R×2 resign · P pause · Esc";
    let short = "U undo · F flip · L pieces · T clock · R×2 resign · P pause";
    let fits = long.chars().count() as i32 <= screen.size().1;
    screen.controls(if fits { long } else { short });
}

fn draw_board(
    screen: &mut dyn Screen,
    game: &Game,
    view: &View,
    layout: &Layout,
    targets: &[Move],
) {
    let board = &game.board;
    let last = board.last_move();
    let check = board.in_check().then(|| board.king(board.side));
    for square in 0..64u8 {
        let light = (file_of(square) + rank_of(square)) % 2 == 1;
        let target = targets.iter().find(|mv| mv.to == square);
        let bg = if check == Some(square) {
            Color::Check
        } else if view.selected == Some(square) {
            Color::Selected
        } else if target.is_some_and(|mv| mv.is_capture()) {
            Color::Target
        } else if last.is_some_and(|mv| mv.from == square || mv.to == square) {
            if light {
                Color::LastLight
            } else {
                Color::LastDark
            }
        } else if light {
            Color::BoardLight
        } else {
            Color::BoardDark
        };
        let (y, x) = layout.origin(square, view.flipped);
        let blank = " ".repeat(layout.sw as usize);
        for row in 0..layout.sh {
            screen.put(y + row, x, &blank, Style::PLAIN.on(bg));
        }
        let (my, mx) = (y + layout.sh / 2, x + layout.sw / 2);
        let shape = board.piece(square).filter(|_| STYLE.load(Ordering::Relaxed) == 0).and_then(|piece| Some((piece, sprites::sprite(piece.kind, layout.sw)?)));
        match board.piece(square) {
            Some(_) if shape.is_some() => {
                let (piece, rows) = shape.expect("checked");
                let width = rows[0].chars().count() as i32;
                for (row, text) in rows.iter().enumerate() {
                    screen.put(y + row as i32, x + (layout.sw - width) / 2, text, piece_style(piece.side).on(bg));
                }
            }
            Some(piece) => screen.put(my, mx, glyph(piece), piece_style(piece.side).on(bg)),
            None if target.is_some() => {
                screen.put(my, mx, "•", Style::fg(Color::PieceBlack).on(bg))
            }
            None => {}
        }
        if view.keyboard && view.cursor == square && game.outcome.is_none() {
            let style = Style::fg(Color::Cyan).bold().on(bg);
            screen.put(my, x, "[", style);
            screen.put(my, x + layout.sw - 1, "]", style);
        }
    }
    let label = Style::fg(Color::Gray);
    for index in 0..8 {
        let rank = if view.flipped { index } else { 7 - index };
        screen.put(
            layout.top + index * layout.sh + layout.sh / 2,
            layout.left,
            &(rank + 1).to_string(),
            label,
        );
        let file = if view.flipped { 7 - index } else { index };
        let letter = ((b'a' + file as u8) as char).to_string();
        screen.put(
            layout.top + 8 * layout.sh,
            layout.left + 2 + index * layout.sw + layout.sw / 2,
            &letter,
            label,
        );
    }
}

fn draw_panel(
    screen: &mut dyn Screen,
    game: &Game,
    view: &View,
    layout: &Layout,
    status: &str,
    now: f64,
) {
    let (top, left, height) = (layout.top, layout.panel_left, layout.height());
    screen.panel(top, left, height, PANEL, "Moves", Style::fg(Color::Gray));
    let inner = PANEL - 4;
    let x = left + 2;
    let (upper, lower) = if view.flipped {
        (Side::White, Side::Black)
    } else {
        (Side::Black, Side::White)
    };
    let turn = game.board.side;
    let over = game.outcome.is_some();
    let player = |screen: &mut dyn Screen, y: i32, side: Side| {
        let active = side == turn && !over;
        let marker = if active { "▶ " } else { "  " };
        let dot = if side == Side::White { "○" } else { "●" };
        let name = format!("{marker}{dot} {}", game.name(side));
        let style = if active {
            Style::fg(Color::White).bold()
        } else {
            Style::fg(Color::Gray)
        };
        screen.put(y, x, &name, style);
        if let (Some(clock), false) = (&game.clock, view.hide_clock) {
            let left = clock.remaining(side, turn, now);
            let text = clock_text(left);
            let style = if left < 10.0 {
                Style::fg(Color::Red).bold()
            } else if active {
                Style::fg(Color::White).bold()
            } else {
                Style::fg(Color::Gray)
            };
            screen.put(y, x + inner - text.chars().count() as i32, &text, style);
        }
    };
    let balance = game.board.material_balance();
    let captured = |screen: &mut dyn Screen, y: i32, side: Side| {
        // The pieces this side took, then its material lead.
        let taken = game.board.captured(side.other());
        let mut text: String = taken
            .iter()
            .map(|kind| glyph(Piece::new(side.other(), *kind)))
            .collect();
        let lead = if side == Side::White {
            balance
        } else {
            -balance
        };
        if lead > 0 {
            text.push_str(&format!(" +{lead}"));
        }
        let text: String = text.chars().take(inner as usize).collect();
        screen.put(y, x + 2, &text, Style::fg(Color::Gray));
    };
    player(screen, top + 1, upper);
    captured(screen, top + 2, upper);
    player(screen, top + height - 2, lower);
    captured(screen, top + height - 3, lower);
    // Status line just above the lower player's captured row, the move list above it.
    let status_y = top + height - 4;
    let status_style = if over || game.board.in_check() {
        Style::fg(Color::Yellow).bold()
    } else {
        Style::fg(Color::Cyan)
    };
    let status: String = status.chars().take(inner as usize).collect();
    screen.put(status_y, x, &status, status_style);
    let first_row = top + 3;
    let rows = (status_y - first_row).max(0) as usize;
    let pairs: Vec<&[String]> = game.sans.chunks(2).collect();
    let skip = pairs.len().saturating_sub(rows);
    let last = game.sans.len().saturating_sub(1);
    for (row, (number, pair)) in pairs.iter().enumerate().skip(skip).enumerate() {
        let y = first_row + row as i32;
        screen.put(y, x, &format!("{:>3}.", number + 1), Style::fg(Color::Gray));
        for (column, san) in pair.iter().enumerate() {
            let index = number * 2 + column;
            let style = if index == last {
                Style::fg(Color::Yellow).bold()
            } else {
                Style::fg(Color::White)
            };
            screen.put(y, x + 5 + column as i32 * 9, san, style);
        }
    }
}

fn status_text(game: &Game, view: &View, thinking: bool) -> String {
    if let Some(outcome) = game.outcome {
        return outcome.describe();
    }
    if view.resign_armed {
        return "Press R again to resign".into();
    }
    if view.promotion.is_some() {
        return "Promote: Q R B N".into();
    }
    if thinking {
        return "Bot is thinking…".into();
    }
    let check = if game.board.in_check() { "Check! " } else { "" };
    match game.mode {
        Mode::Bot(_) => format!("{check}Your move"),
        Mode::Duel => format!("{check}{} to move", game.board.side.name()),
    }
}

fn leave() -> Played {
    Played {
        score: None,
        after: After::Leave,
    }
}

pub fn play(
    screen: &mut dyn Screen,
    level: Level,
    rng: &mut Rng,
    best: Option<u64>,
    scores: Option<&mut Scores>,
) -> io::Result<Played> {
    if Layout::fit(screen.size()).is_none() {
        return too_small(screen, MIN_WIDTH, MIN_HEIGHT);
    }
    let Some(setup::Setup { mode, clock }) = setup::choose(screen, level, rng)? else {
        return Ok(leave());
    };
    let mut game = Game::new(mode, level, clock);
    let mut view = View {
        flipped: mode == Mode::Bot(Side::Black),
        cursor: if mode == Mode::Bot(Side::Black) {
            52
        } else {
            12
        },
        ..View::default()
    };
    let mut thinking: Option<Thinking> = None;
    loop {
        let now = screen.now();
        game.check_flag(now);
        if game.outcome.is_some() {
            thinking = None;
            break;
        }
        // The bot's turn: start thinking, or play the move it found.
        if let Some(bot) = mode.bot_side().filter(|side| *side == game.board.side) {
            match &thinking {
                None => {
                    let left = game.clock.map(|clock| clock.remaining(bot, bot, now));
                    thinking = Some(start_bot(
                        &game.board,
                        level,
                        left,
                        rng.below(1 << 30) as u64,
                        now,
                    ));
                }
                Some(bot_thinking) if now - bot_thinking.started >= BOT_MIN_DELAY => {
                    match bot_thinking.receiver.recv_timeout(Duration::from_millis(1)) {
                        Ok(Some(mv)) => {
                            thinking = None;
                            game.play(mv, screen.now());
                            continue;
                        }
                        Ok(None) | Err(mpsc::RecvTimeoutError::Disconnected) => {
                            // No legal move: the rules already ended the game; nothing to do.
                            thinking = None;
                            game.outcome = game.board.outcome();
                            continue;
                        }
                        Err(mpsc::RecvTimeoutError::Timeout) => {}
                    }
                }
                Some(_) => {}
            }
        }
        let Some(layout) = Layout::fit(screen.size()) else {
            if let Some(clock) = &mut game.clock {
                clock.stop(game.board.side, now);
            }
            if !wait_for_room(screen, MIN_WIDTH, MIN_HEIGHT)? {
                return Ok(leave());
            }
            if let Some(clock) = &mut game.clock {
                clock.resume(screen.now(), game.board.ply() > 0);
            }
            continue;
        };
        let targets: Vec<Move> = match view.selected {
            Some(from) if game.human_to_move() => game
                .board
                .legal_moves()
                .into_iter()
                .filter(|mv| mv.from == from)
                .collect(),
            _ => Vec::new(),
        };
        let status = status_text(&game, &view, thinking.is_some());
        draw(screen, &game, &view, &layout, &targets, &status, now);
        screen.present()?;
        let ticking = thinking.is_some() || game.clock.is_some_and(|clock| clock.since.is_some());
        let timeout =
            ticking.then(|| Duration::from_millis(if thinking.is_some() { 30 } else { 100 }));
        let Some(input) = screen.input(timeout)? else {
            continue;
        };
        let now = screen.now();
        if let Some((from, to)) = view.promotion {
            let picked = match input {
                Input::Key(Key::Enter) => Some(Kind::Queen),
                Input::Key(Key::Char(letter)) => match letter.to_ascii_lowercase() {
                    'q' => Some(Kind::Queen),
                    'r' => Some(Kind::Rook),
                    'b' => Some(Kind::Bishop),
                    'n' => Some(Kind::Knight),
                    _ => None,
                },
                Input::Click {
                    y,
                    x,
                    button: Button::Left,
                } => {
                    let (py, px) = layout.picker();
                    let index = (x - px - 1).div_euclid(4);
                    (y == py && (0..4).contains(&index)).then(|| PROMOTIONS[index as usize])
                }
                _ => None,
            };
            if let Some(kind) = picked {
                view.promotion = None;
                view.selected = None;
                let mv = targets
                    .iter()
                    .find(|mv| mv.from == from && mv.to == to && mv.promotion == Some(kind))
                    .copied();
                if let Some(mv) = mv {
                    game.play(mv, now);
                }
            } else if matches!(input, Input::Key(Key::Esc) | Input::Click { .. }) {
                view.promotion = None;
            }
            continue;
        }
        if !matches!(input, Input::Key(Key::Char('r' | 'R'))) {
            view.resign_armed = false;
        }
        match input {
            Input::Click {
                y,
                x,
                button: Button::Left,
            } => {
                view.keyboard = false;
                if let Some(square) = layout.square_at(y, x, view.flipped) {
                    view.cursor = square;
                    pick(&mut game, &mut view, &targets, square, now);
                }
            }
            Input::Click {
                button: Button::Right,
                ..
            } => view.selected = None,
            Input::Key(key @ (Key::Up | Key::Down | Key::Left | Key::Right)) => {
                if view.keyboard {
                    let (df, dr) = match key {
                        Key::Up => (0, 1),
                        Key::Down => (0, -1),
                        Key::Left => (-1, 0),
                        _ => (1, 0),
                    };
                    let (df, dr) = if view.flipped { (-df, -dr) } else { (df, dr) };
                    let file = (file_of(view.cursor) + df).clamp(0, 7);
                    let rank = (rank_of(view.cursor) + dr).clamp(0, 7);
                    view.cursor = square_at(file, rank).expect("clamped");
                }
                view.keyboard = true;
            }
            Input::Key(Key::Enter | Key::Char(' ')) => {
                if view.keyboard {
                    let cursor = view.cursor;
                    pick(&mut game, &mut view, &targets, cursor, now);
                }
                view.keyboard = true;
            }
            Input::Key(Key::Esc) if view.selected.is_some() => view.selected = None,
            input if input.is_pause() || input.is_leave() => {
                if let Some(clock) = &mut game.clock {
                    clock.stop(game.board.side, now);
                }
                if pause(screen)? {
                    return Ok(leave());
                }
                if let Some(clock) = &mut game.clock {
                    clock.resume(screen.now(), game.board.ply() > 0);
                }
                if let Some(bot_thinking) = &mut thinking {
                    bot_thinking.started = screen.now() - BOT_MIN_DELAY;
                }
            }
            Input::Key(Key::Char(letter)) => match letter.to_ascii_lowercase() {
                'f' => view.flipped = !view.flipped,
                'l' => {
                    STYLE.store((STYLE.load(Ordering::Relaxed) + 1) % STYLES, Ordering::Relaxed);
                }
                't' => view.hide_clock = !view.hide_clock,
                'u' => {
                    view.selected = None;
                    if thinking.take().is_some() {
                        // The bot was answering: take back the human's last move only.
                        game.take_back();
                    } else if game.take_back() && !game.human_to_move() {
                        // That was the bot's reply: take back the human's move too.
                        game.take_back();
                    }
                }
                'r' => {
                    if view.resign_armed {
                        let loser = match game.mode {
                            Mode::Bot(human) => human,
                            Mode::Duel => game.board.side,
                        };
                        game.outcome = Some(Outcome::Resigned(loser));
                        if let Some(clock) = &mut game.clock {
                            clock.stop(game.board.side, now);
                        }
                    }
                    view.resign_armed = !view.resign_armed;
                }
                _ => {}
            },
            _ => {}
        }
    }
    drop(thinking);
    let outcome = game.outcome.expect("the loop ends with an outcome");
    if let Some(layout) = Layout::fit(screen.size()) {
        let status = status_text(&game, &view, false);
        let now = screen.now();
        draw(screen, &game, &view, &layout, &[], &status, now);
    }
    let title = match (game.mode, outcome.winner()) {
        (_, None) => "DRAW".to_string(),
        (Mode::Bot(human), Some(winner)) if human == winner => "YOU WIN".into(),
        (Mode::Bot(_), Some(_)) => "THE BOT WINS".into(),
        (Mode::Duel, Some(winner)) => format!("{} WINS", winner.name().to_uppercase()),
    };
    let moves = game.sans.len().div_ceil(2) as u64;
    let mut details = vec![outcome.describe(), format!("{moves} moves")];
    let human_won = matches!(game.mode, Mode::Bot(human) if outcome.winner() == Some(human));
    // The record is the fewest moves to beat the bot; take-backs and duels never count.
    let score = (human_won && !game.undone).then_some(moves);
    if human_won && game.undone {
        details.push("take-backs used: no record".into());
    }
    let after = finish(
        screen,
        &title,
        &details,
        score.map(|score| (score, best, "chess")),
        scores.map(|scores| (scores, level)),
    )?;
    Ok(Played { score, after })
}

/// A click or Enter on `square`: move the selected piece there, or (re)select a piece.
fn pick(game: &mut Game, view: &mut View, targets: &[Move], square: u8, now: f64) {
    if !game.human_to_move() || game.outcome.is_some() {
        return;
    }
    if let Some(from) = view.selected {
        let matching: Vec<&Move> = targets.iter().filter(|mv| mv.to == square).collect();
        if let Some(mv) = matching.first() {
            if mv.promotion.is_some() {
                view.promotion = Some((from, square));
            } else {
                let mv = **mv;
                view.selected = None;
                game.play(mv, now);
            }
            return;
        }
    }
    view.selected = match game.board.piece(square) {
        Some(piece) if piece.side == game.board.side && view.selected != Some(square) => {
            Some(square)
        }
        _ => None,
    };
}

#[cfg(test)]
mod tests {
    use super::super::testing::*;
    use super::*;

    fn square(name: &str) -> u8 {
        board::parse_square(name).unwrap()
    }

    /// Screen cell of a square's center in the layout for a 30x100 screen, White at the bottom.
    fn at(name: &str) -> Option<Input> {
        let layout = Layout::fit((30, 100)).unwrap();
        let (y, x) = layout.origin(square(name), false);
        click(y + layout.sh / 2, x + layout.sw / 2, Button::Left)
    }

    #[test]
    fn the_layout_picks_the_largest_square_that_fits() {
        assert_eq!(
            Layout::fit((30, 100)).map(|layout| (layout.sw, layout.sh)),
            Some((7, 3))
        );
        assert_eq!(
            Layout::fit((24, 80)).map(|layout| (layout.sw, layout.sh)),
            Some((5, 2))
        );
        assert_eq!(
            Layout::fit((MIN_HEIGHT, MIN_WIDTH)).map(|layout| (layout.sw, layout.sh)),
            Some((3, 1))
        );
        assert!(Layout::fit((MIN_HEIGHT - 1, MIN_WIDTH)).is_none());
        let layout = Layout::fit((24, 80)).unwrap();
        for square in 0..64 {
            for flipped in [false, true] {
                let (y, x) = layout.origin(square, flipped);
                assert_eq!(
                    layout.square_at(y + layout.sh - 1, x + layout.sw - 1, flipped),
                    Some(square)
                );
            }
        }
    }

    #[test]
    fn two_players_move_by_clicks_and_see_the_move_list() {
        let mut screen = Fake::new((30, 100))
            .keys(&[
                key('2'),
                special(Key::Enter),
                at("e2"),
                at("e4"),
                at("e7"),
                at("e5"),
                at("g1"),
                at("f3"),
            ])
            .idle(2);
        let played = play(&mut screen, Level::Normal, &mut Rng::seeded(1), None, None).unwrap();
        assert_eq!(played.after, After::Leave);
        assert!(screen.drew("CHESS"));
        assert!(screen.drew("e4"));
        assert!(screen.drew("e5"));
        assert!(screen.drew("Nf3"));
        assert!(screen.drew("Black to move"));
        // The last move's squares are highlighted.
        let layout = Layout::fit((30, 100)).unwrap();
        let (y, x) = layout.origin(square("f3"), false);
        let last_frame = &screen.frames[screen.frames.len() - 2];
        assert!(last_frame.iter().any(|(row, column, _, style)| *row == y
            && *column == x
            && matches!(style.bg, Color::LastLight | Color::LastDark)));
    }

    #[test]
    fn fools_mate_ends_with_a_win_for_black() {
        let mut screen = Fake::new((30, 100)).keys(&[
            key('2'),
            special(Key::Enter),
            at("f2"),
            at("f3"),
            at("e7"),
            at("e5"),
            at("g2"),
            at("g4"),
            at("d8"),
            at("h4"),
        ]);
        let played = play(&mut screen, Level::Normal, &mut Rng::seeded(1), None, None).unwrap();
        assert_eq!(played.score, None, "duels record nothing");
        assert!(screen.drew("BLACK WINS"));
        assert!(screen.drew("Checkmate"));
    }

    #[test]
    fn the_clock_runs_out() {
        // A 1-minute clock; White moves, then Black waits until the flag falls.
        let mut screen = Fake::new((30, 100))
            .keys(&[key('2'), special(Key::Right), special(Key::Down), key('1'), special(Key::Enter), at("e2"), at("e4")])
            .idle(3000);
        play(&mut screen, Level::Normal, &mut Rng::seeded(1), None, None).unwrap();
        assert!(screen.drew("Black ran out of time"));
        assert!(screen.drew("WHITE WINS"));
    }

    #[test]
    fn promotion_asks_for_the_piece() {
        let mut game = Game::new(Mode::Duel, Level::Normal, None);
        game.board = Board::from_fen("4k3/1P6/8/8/8/8/8/4K3 w - - 0 1").unwrap();
        let mut view = View::default();
        let targets = |game: &mut Game, from: u8| -> Vec<Move> {
            game.board
                .legal_moves()
                .into_iter()
                .filter(|mv| mv.from == from)
                .collect()
        };
        pick(&mut game, &mut view, &[], square("b7"), 0.0);
        assert_eq!(view.selected, Some(square("b7")));
        let moves = targets(&mut game, square("b7"));
        pick(&mut game, &mut view, &moves, square("b8"), 0.0);
        assert_eq!(view.promotion, Some((square("b7"), square("b8"))));
        assert_eq!(
            game.board.ply(),
            0,
            "nothing is played before the piece is chosen"
        );
    }

    #[test]
    fn the_bot_answers_and_undo_takes_back_both_moves() {
        let mut screen = Fake::new((30, 100)).keys(&[key('1'), key('1'), special(Key::Enter), at("e2"), at("e4")]).idle(3000);
        screen.inputs.push_back(key('u'));
        screen.inputs.extend(std::iter::repeat_n(None, 3));
        play(&mut screen, Level::Easy, &mut Rng::seeded(1), None, None).unwrap();
        let has = |frame: &Vec<(i32, i32, String, Style)>, needle: &str| frame.iter().any(|(_, _, text, _)| text.contains(needle));
        let thinking = screen.frames.iter().position(|frame| has(frame, "Bot is thinking")).expect("the bot thought");
        let replied = screen.frames[thinking..].iter().position(|frame| has(frame, "Your move") && has(frame, "e4"));
        assert!(replied.is_some(), "the bot answered and the human is to move");
        // The frame before the pause box: both moves are gone.
        let board = &screen.frames[screen.frames.len() - 2];
        assert!(!has(board, "e4"), "undo took back the human move");
        assert!(!has(board, "  1."), "the move list is empty");
    }

    #[test]
    fn a_small_terminal_is_explained() {
        let mut screen = Fake::new((10, 40)).keys(&[key('q')]);
        let played = play(&mut screen, Level::Normal, &mut Rng::seeded(2), None, None).unwrap();
        assert_eq!(played.after, After::Leave);
    }

    #[test]
    fn clock_text_formats() {
        assert_eq!(clock_text(300.0), "5:00");
        assert_eq!(clock_text(61.2), "1:02");
        assert_eq!(clock_text(9.46), "0:09.4");
        assert_eq!(clock_text(-1.0), "0:00.0");
    }
}
