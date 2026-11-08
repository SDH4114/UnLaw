//! `ul game`: Tetris, Snake, Minesweeper, Space Invaders, Chomp, Dash and Ping Pong in the terminal,
//! playable with keyboard or mouse.
//!
//! Every game is a state machine (input → update → draw) that talks only to
//! the [`Screen`] trait, so it runs on a real terminal and headless in tests.

mod chomp;
mod dash;
mod invaders;
mod mines;
mod pingpong;
mod snake;
mod stream;
mod tetris;
mod terminal;

use std::io::{self, IsTerminal};
use std::path::PathBuf;
use std::os::fd::AsRawFd;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use toml_edit::DocumentMut;

use crate::config::Config;

pub const HELP: &str = "Play a terminal arcade game; no arguments opens the game menu.
Usage: ul game [tetris|snake|minesweeper|invaders|chomp|dash|pingpong] [easy|normal|hard]
       ul game --stream [--size ROWSxCOLS] [game] [difficulty]
Games:
  tetris        7-bag pieces, next/hold, ghost, wall kicks, levels every 10 lines
  snake         eat ● (and bonus ★), grow and speed up; walls kill on normal/hard
  minesweeper   first click is safe; flag mines, click a number to clear around it
  invaders      5x11 formation, shields, UFO, waves; one shot on screen at a time
  chomp         maze chase: eat every pellet, power pellets make the 4 hunters
                edible; a new maze each level
  dash          endless runner: a fox jumps cacti and low birds, ducks under
                middle ones; the world speeds up, day turns to night
  pingpong      old-arcade table tennis, first to 11: 1 player against the bot
                or 2 players on one keyboard (chosen when it starts); where the
                ball meets the paddle sets the angle, every hit speeds it up
Controls (shown in every game): arrows/WASD, Space, P pause, Q or Esc leaves.
Dash: Space/Up/W jump (fixed height), Down/S duck (~0.35 s, key repeat extends it)
or drop fast in the air.
Ping Pong: 1 player W/S or ↑/↓; 2 players: left W/S, right ↑/↓. Holding both
sides at once needs a terminal with the kitty keyboard protocol (Ghostty, kitty,
WezTerm, iTerm2 with CSI u) or the desk page; elsewhere each press moves the
paddle briefly and key repeat keeps it going.
Mouse: click menus; Tetris follows the pointer (left click drops, right rotates);
Snake steers toward a click; Minesweeper left reveals, right flags;
Invaders follow the pointer and click to fire; Chomp steers toward a click;
Dash jumps on a left click; Ping Pong paddles follow the pointer (the nearer
one in a 2-player game).
Difficulty (default: games.difficulty):
  easy     slow start, extra help (Tetris ghost + 3 previews, Snake wraps, 5 lives)
  normal   the classic game
  hard     really hard: Tetris starts at level 12 without ghost/hold, Snake has
           obstacles and doubles growth, Minesweeper is Expert with no safe
           opening, Invaders fire constantly and you have 2 lives, Chomp
           hunters are as fast as you and fright lasts 2 s (none from level 5),
           Dash starts fast with tight gaps, mixed cacti and birds from the start
           (easy: slower, wider gaps, no high birds); Ping Pong: small
           paddles, a fast ball and a bot that aims for steep returns
           (easy: big paddles, a slow ball, a bot that misses often)
Ping Pong records the winning margin against the bot (2-player games and
losses record nothing).
Best scores: storage.root/runtime/arcade.toml, shared by the terminal and
`ul desk` (Games tab); every finished game rereads the file first.
--stream plays without a terminal for `ul desk`: JSON-line input on stdin
(keys, key releases, clicks, hover, resize), one JSON frame per change on stdout; closing
stdin ends the game. --size sets the grid (default 30x100).
Examples: ul game snake hard; ul game --stream --size 40x120 tetris
";

pub const GAMES: [(&str, &str); 7] =
    [("tetris", "Tetris"), ("snake", "Snake"), ("minesweeper", "Minesweeper"), ("invaders", "Space Invaders"), ("chomp", "Chomp"), ("dash", "Dash"), ("pingpong", "Ping Pong")];

/// Seconds per frame of the real-time games.
pub const FRAME: f64 = 1.0 / 30.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Key {
    Up,
    Down,
    Left,
    Right,
    Enter,
    Esc,
    Char(char),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Button {
    Left,
    Right,
    Middle,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Input {
    Key(Key),
    /// A key was let go. Only games that ask for it (`Screen::set_releases`) ever see one.
    Release(Key),
    Click { y: i32, x: i32, button: Button },
    Hover { y: i32, x: i32 },
}

impl Input {
    pub fn char(&self) -> Option<char> {
        match self {
            Input::Key(Key::Char(c)) => Some(c.to_ascii_lowercase()),
            _ => None,
        }
    }

    pub fn is_leave(&self) -> bool {
        matches!(self, Input::Key(Key::Esc)) || self.char() == Some('q')
    }

    pub fn is_pause(&self) -> bool {
        self.char() == Some('p')
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub enum Color {
    #[default]
    Default,
    Red,
    Green,
    Yellow,
    Blue,
    Magenta,
    Cyan,
    White,
    Gray,
    DarkRed,
    DarkYellow,
    DarkBlue,
    DarkCyan,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct Style {
    pub fg: Color,
    pub bg: Color,
    pub bold: bool,
    pub reverse: bool,
    pub dim: bool,
}

impl Style {
    pub const PLAIN: Style = Style { fg: Color::Default, bg: Color::Default, bold: false, reverse: false, dim: false };

    pub const fn fg(color: Color) -> Style {
        Style { fg: color, ..Style::PLAIN }
    }

    pub const fn bold(self) -> Style {
        Style { bold: true, ..self }
    }

    pub const fn reverse(self) -> Style {
        Style { reverse: true, ..self }
    }

    pub const fn dim(self) -> Style {
        Style { dim: true, ..self }
    }

    pub const fn on(self, color: Color) -> Style {
        Style { bg: color, ..self }
    }
}

pub trait Screen {
    /// (height, width) in cells.
    fn size(&self) -> (i32, i32);
    fn clear(&mut self);
    fn put(&mut self, y: i32, x: i32, text: &str, style: Style);
    fn present(&mut self) -> io::Result<()>;
    /// Wait up to `timeout` (`None`: forever); `Ok(None)` when it passes.
    /// Ctrl-C is an `Interrupted` error.
    fn input(&mut self, timeout: Option<Duration>) -> io::Result<Option<Input>>;
    /// Seconds on a monotonic clock.
    fn now(&self) -> f64;

    /// Ask for `Input::Release` events (holding two keys at once, e.g. two players on one
    /// keyboard). Returns whether they will really arrive; screens that cannot tell a release
    /// keep sending presses only.
    fn set_releases(&mut self, _on: bool) -> bool {
        false
    }

    fn frame_box(&mut self, top: i32, left: i32, height: i32, width: i32, style: Style) {
        if height < 2 || width < 2 {
            return;
        }
        let inner = "─".repeat((width - 2) as usize);
        self.put(top, left, &format!("╭{inner}╮"), style);
        self.put(top + height - 1, left, &format!("╰{inner}╯"), style);
        for y in top + 1..top + height - 1 {
            self.put(y, left, "│", style);
            self.put(y, left + width - 1, "│", style);
        }
    }

    /// Fade everything drawn so far (the backdrop of an overlay); nothing where that is impossible.
    fn dim_all(&mut self) {}

    /// Remember the frame drawn so far / bring it back, so an overlay can be redrawn after a
    /// resize without the game. Nothing where the screen cannot do it.
    fn save_frame(&mut self) {}
    fn load_frame(&mut self) {}

    /// Rounded box with `title` set into its top border.
    fn panel(&mut self, top: i32, left: i32, height: i32, width: i32, title: &str, style: Style) {
        self.frame_box(top, left, height, width, style);
        if !title.is_empty() && width > 6 {
            let title: String = title.chars().take((width - 6) as usize).collect();
            self.put(top, left + 2, &format!(" {title} "), style.bold());
        }
    }

    /// One HUD line over a block `width` wide at `left`: the title on the left, `(label, value)`
    /// stats on the right. Stats are listed by importance; the last ones are dropped when the
    /// block is too narrow.
    fn hud(&mut self, y: i32, left: i32, width: i32, title: &str, stats: &[(&str, String)]) {
        let measure = |stats: &[(&str, String)]| -> i32 {
            stats.iter().map(|(label, value)| (label.chars().count() + 1 + value.chars().count()) as i32).sum::<i32>() + 2 * stats.len().saturating_sub(1) as i32
        };
        let title_width = title.chars().count() as i32;
        let mut shown = stats.len();
        while shown > 0 && title_width + 2 + measure(&stats[..shown]) > width {
            shown -= 1;
        }
        self.put(y, left, title, Style::fg(Color::Yellow).bold());
        let mut x = left + width - measure(&stats[..shown]);
        for (label, value) in &stats[..shown] {
            self.put(y, x, label, Style::fg(Color::Gray));
            x += label.chars().count() as i32 + 1;
            self.put(y, x, value, Style::fg(Color::White).bold());
            x += value.chars().count() as i32 + 2;
        }
    }

    fn centered(&mut self, y: i32, text: &str, style: Style) {
        let width = self.size().1;
        self.put(y, ((width - text.chars().count() as i32) / 2).max(0), text, style);
    }

    /// Bottom-line help shown in every screen.
    fn controls(&mut self, text: &str) {
        let height = self.size().0;
        self.centered(height - 1, text, Style::fg(Color::Gray));
    }
}

/// Collect the inputs that arrive before `deadline` (clock seconds).
pub fn inputs_until(screen: &mut dyn Screen, deadline: f64) -> io::Result<Vec<Input>> {
    let mut inputs = Vec::new();
    loop {
        let remaining = deadline - screen.now();
        // Below a tenth of a millisecond the deadline has effectively passed;
        // waiting would only spin (float sums like 3 × 1/30 land just short).
        if remaining < 1e-4 {
            return Ok(inputs);
        }
        match screen.input(Some(Duration::from_secs_f64(remaining)))? {
            Some(input @ Input::Hover { .. }) if matches!(inputs.last(), Some(Input::Hover { .. })) => {
                *inputs.last_mut().expect("checked above") = input;
            }
            Some(input) => inputs.push(input),
            None => return Ok(inputs),
        }
    }
}

/// Fixed cadence for the real-time games. Waiting `FRAME` after every draw would stretch the
/// period to `FRAME` plus the drawing time; this schedules frames on a grid instead and
/// resynchronizes after a stall (a pause, a slow terminal) instead of firing a burst.
pub struct Ticker {
    next: f64,
}

impl Ticker {
    pub fn new(now: f64) -> Ticker {
        Ticker { next: now }
    }

    /// Call right after drawing a frame at `now`: when the frame must end.
    pub fn deadline(&mut self, now: f64) -> f64 {
        let due = self.next + FRAME;
        self.next = if due > now + 1e-4 && due <= now + FRAME + 1e-9 { due } else { now + FRAME };
        self.next
    }

    /// Forget the schedule (after a pause).
    pub fn reset(&mut self, now: f64) {
        self.next = now;
    }
}

/// Top row and left column of a block `height` x `width` cells centered on the screen, leaving
/// the row above it for the HUD (`top - 1`) and the last row for the controls line.
pub fn center_block(size: (i32, i32), height: i32, width: i32) -> (i32, i32) {
    let (rows, columns) = size;
    let spare = (rows - 2 - height).max(0);
    (spare / 2 + 1, ((columns - width) / 2).max(0))
}

/// Does the screen still have `need_width` x `need_height` cells?
pub fn fits(screen: &dyn Screen, need_width: i32, need_height: i32) -> bool {
    let (height, width) = screen.size();
    width >= need_width && height >= need_height
}

fn size_notice(screen: &mut dyn Screen, need_width: i32, need_height: i32) {
    screen.clear();
    let (height, width) = screen.size();
    let lines = [
        (format!("This game needs a {need_width}x{need_height} terminal"), Style::fg(Color::Yellow).bold()),
        (format!("(now {width}x{height}) — enlarge it or press a key"), Style::PLAIN),
    ];
    overlay(screen, &lines);
}

/// Mid-game resize below the board: show why the game stopped and wait for the terminal to
/// grow back (`true`) or for the player to leave (`false`).
pub fn wait_for_room(screen: &mut dyn Screen, need_width: i32, need_height: i32) -> io::Result<bool> {
    while !fits(screen, need_width, need_height) {
        size_notice(screen, need_width, need_height);
        screen.present()?;
        if matches!(screen.input(None)?, Some(input) if input.is_leave()) {
            return Ok(false);
        }
    }
    Ok(true)
}

/// Small xorshift generator; `constant` makes every choice predictable in tests.
pub struct Rng {
    state: u64,
    constant: Option<usize>,
}

impl Rng {
    pub fn from_time() -> Rng {
        let seed = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_nanos() as u64).unwrap_or(1);
        Rng::seeded(seed)
    }

    pub fn seeded(seed: u64) -> Rng {
        Rng { state: seed | 1, constant: None }
    }

    #[cfg(test)]
    pub fn constant(index: usize) -> Rng {
        Rng { state: 1, constant: Some(index) }
    }

    pub fn below(&mut self, bound: usize) -> usize {
        if let Some(index) = self.constant {
            return index % bound.max(1);
        }
        self.state ^= self.state << 13;
        self.state ^= self.state >> 7;
        self.state ^= self.state << 17;
        (self.state % bound.max(1) as u64) as usize
    }

    /// True with probability `chance` (0..=1).
    pub fn chance(&mut self, chance: f64) -> bool {
        (self.below(1_000_000) as f64) < chance * 1_000_000.0
    }

    pub fn shuffle<T>(&mut self, items: &mut [T]) {
        for index in (1..items.len()).rev() {
            items.swap(index, self.below(index + 1));
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Level {
    Easy,
    Normal,
    Hard,
}

impl Level {
    pub fn parse(name: &str) -> Option<Level> {
        Some(match name {
            "easy" => Level::Easy,
            "normal" => Level::Normal,
            "hard" => Level::Hard,
            _ => return None,
        })
    }

    pub fn name(self) -> &'static str {
        match self {
            Level::Easy => "easy",
            Level::Normal => "normal",
            Level::Hard => "hard",
        }
    }

    /// Pick the value for this difficulty.
    pub fn pick<T>(self, easy: T, normal: T, hard: T) -> T {
        match self {
            Level::Easy => easy,
            Level::Normal => normal,
            Level::Hard => hard,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum After {
    Again,
    Leave,
}

/// How a game ended: its score (if it counts) and what the player chose next.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Played {
    pub score: Option<u64>,
    pub after: After,
}

/// Best scores per game and difficulty; Minesweeper keeps the lowest time.
pub struct Scores {
    path: Option<PathBuf>,
    document: DocumentMut,
}

pub fn lower_is_better(game: &str) -> bool {
    game == "minesweeper"
}

pub fn is_better(game: &str, score: u64, best: Option<u64>) -> bool {
    match best {
        None => true,
        Some(best) if lower_is_better(game) => score < best,
        Some(best) => score > best,
    }
}

impl Scores {
    pub fn load(path: Option<PathBuf>) -> Scores {
        let document = path
            .as_ref()
            .and_then(|path| std::fs::read_to_string(path).ok())
            .and_then(|text| text.parse().ok())
            .unwrap_or_default();
        Scores { path, document }
    }

    /// Reread the file: another `ul game` (terminal or desk) may have saved a best.
    pub fn reload(&mut self) {
        let Some(path) = &self.path else { return };
        let Ok(text) = std::fs::read_to_string(path) else { return };
        match text.parse() {
            Ok(document) => self.document = document,
            Err(_) => {
                // Corrupt: keep it for the player under a new name and start fresh, so the next
                // record never overwrites it. Nothing is printed over the game screen.
                let time = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |time| time.as_secs());
                let mut name = path.as_os_str().to_os_string();
                name.push(format!(".corrupt-{time}"));
                let _ = std::fs::rename(path, name);
                self.document = DocumentMut::new();
            }
        }
    }

    pub fn best(&self, game: &str, level: Level) -> Option<u64> {
        self.document.get(game)?.get(level.name())?.as_integer().and_then(|value| u64::try_from(value).ok())
    }

    /// Record a finished game; saves and returns true for a new best.
    pub fn record(&mut self, game: &str, level: Level, score: u64) -> bool {
        // Lock the stable sidecar, not the TOML inode replaced by atomic_write.
        let locked = (|| -> io::Result<Option<std::fs::File>> {
            let Some(path) = &self.path else { return Ok(None) };
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent)?;
            }
            let file = std::fs::OpenOptions::new().write(true).create(true).truncate(false).open(path.with_extension("lock"))?;
            if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX) } != 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(Some(file))
        })();
        let _lock = match locked {
            Ok(lock) => lock,
            Err(error) => {
                eprintln!("unlaw game: could not lock best scores: {error}");
                return false;
            }
        };
        self.reload();
        if !is_better(game, score, self.best(game, level)) {
            return false;
        }
        if self.document.get(game).and_then(|item| item.as_table()).is_none() {
            self.document.insert(game, toml_edit::Item::Table(toml_edit::Table::new()));
        }
        self.document[game][level.name()] = toml_edit::value(score.min(i64::MAX as u64) as i64);
        if let Some(path) = &self.path {
            if let Err(error) = crate::util::atomic_write(path, &self.document.to_string(), ".arcade.") {
                eprintln!("unlaw game: could not save best scores: {error}");
                return false;
            }
        }
        true
    }
}

/// Centered box with `lines` (the first is the title) over the dimmed game, with a drop shadow.
pub fn overlay(screen: &mut dyn Screen, lines: &[(String, Style)]) {
    let (height, width) = screen.size();
    let inner = lines.iter().map(|(text, _)| text.chars().count()).max().unwrap_or(0) as i32 + 6;
    let box_width = inner.min(width).max(10);
    let box_height = lines.len() as i32 + 2;
    let top = ((height - box_height) / 2).max(0);
    let left = ((width - box_width) / 2).max(0);
    screen.dim_all();
    let shadow = Style::fg(Color::Gray).dim();
    for y in top + 1..top + box_height {
        screen.put(y, left + box_width, "▒▒", shadow);
    }
    screen.put(top + box_height, left + 2, &"▒".repeat(box_width as usize), shadow);
    for y in top..top + box_height {
        screen.put(y, left, &" ".repeat(box_width as usize), Style::PLAIN);
    }
    screen.frame_box(top, left, box_height, box_width, Style::fg(Color::Cyan));
    for (index, (text, style)) in lines.iter().enumerate() {
        let x = left + ((box_width - text.chars().count() as i32) / 2).max(1);
        screen.put(top + 1 + index as i32, x, text, *style);
    }
}

/// End-of-game box: Enter/Space/click plays again, Esc/Q leaves. Keys in the
/// first half second are ignored so a held key cannot skip it by accident.
pub fn finish(screen: &mut dyn Screen, title: &str, details: &[String], score: Option<(u64, Option<u64>, &str)>, record: Option<(&mut Scores, Level)>) -> io::Result<After> {
    // Persist before presenting or waiting: closing the page can end either I/O operation.
    if let (Some((score, _, game)), Some((scores, level))) = (score, record) {
        scores.record(game, level, score);
    }
    let mut lines = vec![(title.to_string(), Style::fg(Color::Yellow).bold())];
    lines.extend(details.iter().map(|line| (line.clone(), Style::PLAIN)));
    if let Some((score, best, game)) = score {
        if is_better(game, score, best) {
            lines.push(("★ New best! ★".into(), Style::fg(Color::Green).bold()));
        } else if let Some(best) = best {
            let unit = if lower_is_better(game) { "s" } else { "" };
            lines.push((format!("Best {best}{unit}"), Style::fg(Color::Gray)));
        }
    }
    lines.push((String::new(), Style::PLAIN));
    lines.push(("Enter / click: play again    Esc: leave".into(), Style::fg(Color::Cyan)));
    screen.save_frame();
    overlay(screen, &lines);
    screen.present()?;
    let ready = screen.now() + 0.5;
    loop {
        let Some(input) = screen.input(None)? else {
            // Resized: bring the game picture back and center the box again.
            screen.load_frame();
            overlay(screen, &lines);
            screen.present()?;
            continue;
        };
        if screen.now() < ready {
            continue;
        }
        match input {
            Input::Key(Key::Enter) | Input::Click { .. } => return Ok(After::Again),
            Input::Key(Key::Char(' ')) => return Ok(After::Again),
            other if other.is_leave() || other.char() == Some('m') => return Ok(After::Leave),
            _ => {}
        }
    }
}

/// Paused box; returns `true` if the player chose to leave.
pub fn pause(screen: &mut dyn Screen) -> io::Result<bool> {
    let lines = [
        ("PAUSED".to_string(), Style::fg(Color::Yellow).bold()),
        (String::new(), Style::PLAIN),
        ("P / Enter / click: resume    Esc: leave".to_string(), Style::fg(Color::Cyan)),
    ];
    screen.save_frame();
    overlay(screen, &lines);
    screen.present()?;
    loop {
        match screen.input(None)? {
            None => {
                screen.load_frame();
                overlay(screen, &lines);
                screen.present()?;
            }
            Some(input) if input.is_pause() => return Ok(false),
            Some(Input::Key(Key::Enter) | Input::Click { .. }) => return Ok(false),
            Some(input) if input.is_leave() => return Ok(true),
            _ => {}
        }
    }
}

/// Shown when the terminal is too small for a game: a key leaves; growing the terminal
/// enough starts the game (`Again`).
pub fn too_small(screen: &mut dyn Screen, need_width: i32, need_height: i32) -> io::Result<Played> {
    loop {
        size_notice(screen, need_width, need_height);
        screen.present()?;
        match screen.input(None)? {
            Some(_) => return Ok(Played { score: None, after: After::Leave }),
            None if fits(screen, need_width, need_height) => return Ok(Played { score: None, after: After::Again }),
            None => {}
        }
    }
}

/// One-line description of a game for the menu; unknown names get none.
fn describe(name: &str) -> &'static str {
    match name {
        "tetris" => "7-bag pieces, hold, ghost, wall kicks",
        "snake" => "eat, grow and speed up; bonus stars",
        "minesweeper" => "safe first click, flags, chording",
        "invaders" => "5x11 formation, shields, UFO, waves",
        "chomp" => "maze chase with 4 hunters",
        "pingpong" => "first to 11, vs bot or a friend",
        _ => "",
    }
}

struct Item {
    label: String,
    detail: String,
    note: String,
}

/// First item row of a menu with `count` items: a 3-row banner, a subtitle and a gap above it.
fn menu_first_row(height: i32, count: usize) -> i32 {
    ((height - 1 - (count as i32 + 5)) / 2).max(0) + 5
}

fn banner(screen: &mut dyn Screen, top: i32, title: &str) {
    let (_, width) = screen.size();
    let count = title.chars().count() as i32;
    let box_width = (count + 6).min(width);
    let left = ((width - box_width) / 2).max(0);
    screen.frame_box(top, left, 3, box_width, Style::fg(Color::DarkCyan));
    let colors = [Color::Cyan, Color::Green, Color::Yellow, Color::DarkYellow, Color::Magenta, Color::Red];
    screen.put(top + 1, left + 3, title, Style::fg(Color::Cyan).bold());
    let mut letter = 0;
    for (offset, character) in title.chars().enumerate() {
        if character != ' ' {
            letter += 1;
        }
        let style = Style::fg(colors[letter % colors.len()]).bold();
        screen.put(top + 1, left + 3 + offset as i32, &character.to_string(), style);
    }
}

fn menu(screen: &mut dyn Screen, title: &str, subtitle: &str, items: &[Item], mut selected: usize, footer: &str) -> io::Result<Option<usize>> {
    loop {
        screen.clear();
        let (height, width) = screen.size();
        let first = menu_first_row(height, items.len());
        banner(screen, first - 5, title);
        screen.centered(first - 2, subtitle, Style::fg(Color::Gray));
        let widest = |text: fn(&Item) -> &str| items.iter().map(|item| text(item).chars().count()).max().unwrap_or(0);
        let (label_width, detail_width, note_width) = (widest(|item| &item.label), widest(|item| &item.detail), widest(|item| &item.note));
        // Row: marker, number, label, then the description and best score if the terminal is wide enough.
        let base = 5 + label_width as i32;
        let with_detail = base + 2 + detail_width as i32;
        let with_note = with_detail + 2 + note_width as i32;
        let (show_detail, show_note) = (with_detail < width, with_note < width);
        let row_width = if show_note { with_note } else if show_detail { with_detail } else { base } + 1;
        let left = ((width - row_width) / 2).max(0);
        for (index, item) in items.iter().enumerate() {
            let y = first + index as i32;
            let chosen = index == selected;
            let marker = if chosen { "▸" } else { " " };
            let mut text = format!("{marker} {}  {:<lw$}", index + 1, item.label, lw = label_width);
            if show_detail {
                text.push_str(&format!("  {:<dw$}", item.detail, dw = detail_width));
            }
            if show_note {
                text.push_str(&format!("  {:>nw$}", item.note, nw = note_width));
            }
            text.push(' ');
            if chosen {
                screen.put(y, left, &text, Style::fg(Color::Cyan).bold().reverse());
                continue;
            }
            screen.put(y, left + 2, &(index + 1).to_string(), Style::fg(Color::Gray));
            screen.put(y, left + 5, &item.label, Style::fg(Color::White).bold());
            if show_detail {
                screen.put(y, left + 5 + label_width as i32 + 2, &item.detail, Style::fg(Color::Gray));
            }
            if show_note {
                let x = left + with_detail + 2;
                screen.put(y, x, &format!("{:>nw$}", item.note, nw = note_width), Style::fg(Color::Yellow));
            }
        }
        screen.controls(footer);
        screen.present()?;
        let row_of = |y: i32| (y - first).try_into().ok().filter(|row: &usize| *row < items.len());
        match screen.input(None)? {
            Some(input) if input.is_leave() => return Ok(None),
            Some(Input::Key(Key::Up | Key::Char('k' | 'w'))) => selected = (selected + items.len() - 1) % items.len(),
            Some(Input::Key(Key::Down | Key::Char('j' | 's'))) => selected = (selected + 1) % items.len(),
            Some(Input::Key(Key::Enter | Key::Char(' '))) => return Ok(Some(selected)),
            Some(Input::Key(Key::Char(digit))) if digit.is_ascii_digit() => {
                let index = (digit as usize).wrapping_sub('1' as usize);
                if index < items.len() {
                    return Ok(Some(index));
                }
            }
            Some(Input::Hover { y, .. }) => selected = row_of(y).unwrap_or(selected),
            Some(Input::Click { y, button: Button::Left, .. }) => {
                if let Some(row) = row_of(y) {
                    return Ok(Some(row));
                }
            }
            _ => {}
        }
    }
}

pub fn game_menu(screen: &mut dyn Screen, scores: &Scores, level: Level) -> io::Result<Option<&'static str>> {
    let items: Vec<Item> = GAMES
        .iter()
        .map(|(name, label)| Item {
            label: label.to_string(),
            detail: describe(name).to_string(),
            note: match scores.best(name, level) {
                Some(best) if lower_is_better(name) => format!("best {best}s"),
                Some(best) => format!("best {best}"),
                None => String::new(),
            },
        })
        .collect();
    let subtitle = format!("{} games · best scores for {}", GAMES.len(), level.name());
    let footer = "↑/↓ or mouse select · Enter / click play · 1-9 jump · Q quit";
    Ok(menu(screen, "U N L A W   A R C A D E", &subtitle, &items, 0, footer)?.map(|index| GAMES[index].0))
}

pub fn difficulty_menu(screen: &mut dyn Screen, default: Level) -> io::Result<Option<Level>> {
    let levels = [Level::Easy, Level::Normal, Level::Hard];
    let details = ["slow start, extra help", "the classic game", "really hard"];
    let items: Vec<Item> = levels
        .iter()
        .zip(details)
        .map(|(level, detail)| {
            let name = level.name();
            Item { label: format!("{}{}", name[..1].to_uppercase(), &name[1..]), detail: detail.to_string(), note: if *level == default { "default".into() } else { String::new() } }
        })
        .collect();
    let start = levels.iter().position(|level| *level == default).unwrap_or(1);
    let footer = "↑/↓ or mouse select · Enter / click start · 1-3 jump · Esc back";
    Ok(menu(screen, "S E L E C T   D I F F I C U L T Y", "how hard should it be?", &items, start, footer)?.map(|index| levels[index]))
}

pub fn play_once(screen: &mut dyn Screen, game: &str, level: Level, rng: &mut Rng, best: Option<u64>, scores: Option<&mut Scores>) -> io::Result<Played> {
    match game {
        "tetris" => tetris::play(screen, level, rng, best, scores),
        "snake" => snake::play(screen, level, rng, best, scores),
        "minesweeper" => mines::play(screen, level, rng, best, scores),
        "chomp" => chomp::play(screen, level, rng, best, scores),
        "dash" => dash::play(screen, level, rng, best, scores),
        "pingpong" => pingpong::play(screen, level, rng, best, scores),
        _ => invaders::play(screen, level, rng, best, scores),
    }
}

/// Play `game` until the player leaves, recording best scores.
pub fn play(screen: &mut dyn Screen, game: &str, level: Level, rng: &mut Rng, scores: &mut Scores) -> io::Result<()> {
    loop {
        scores.reload();
        let played = play_once(screen, game, level, rng, scores.best(game, level), Some(scores))?;
        if played.after == After::Leave {
            return Ok(());
        }
    }
}

pub fn arcade(screen: &mut dyn Screen, default: Level, rng: &mut Rng, scores: &mut Scores) -> io::Result<()> {
    loop {
        scores.reload();
        let Some(game) = game_menu(screen, scores, default)? else { return Ok(()) };
        if let Some(level) = difficulty_menu(screen, default)? {
            play(screen, game, level, rng, scores)?;
        }
    }
}

fn usage() -> i32 {
    eprintln!("Usage: ul game [--stream [--size ROWSxCOLS]] [tetris|snake|minesweeper|invaders|chomp|dash|pingpong] [easy|normal|hard]");
    2
}

pub fn run(args: &[String], config: &Config) -> i32 {
    if matches!(args.first().map(String::as_str), Some("-h" | "--help" | "help")) {
        print!("{HELP}");
        return 0;
    }
    let mut stream_size = None;
    let mut rest: Vec<String> = Vec::new();
    let mut flags = args.iter();
    while let Some(arg) = flags.next() {
        match arg.as_str() {
            "--stream" => stream_size = stream_size.or(Some((30, 100))),
            "--size" => match flags.next().and_then(|size| stream::parse_size(size)) {
                Some(size) => stream_size = Some(size),
                None => {
                    eprintln!("unlaw game: --size needs ROWSxCOLS, for example 40x120");
                    return 2;
                }
            },
            _ => rest.push(arg.clone()),
        }
    }
    let args = rest.as_slice();
    let default = config.string("games.difficulty");
    let (game, difficulty) = match args {
        [] => (None, default.as_str()),
        [game] => (Some(game.as_str()), default.as_str()),
        [game, difficulty] => (Some(game.as_str()), difficulty.as_str()),
        _ => return usage(),
    };
    if game.is_some_and(|game| !GAMES.iter().any(|(name, _)| *name == game)) {
        return usage();
    }
    let Some(level) = Level::parse(difficulty) else {
        eprintln!("unlaw game: difficulty must be easy, normal, or hard");
        return 2;
    };
    let mut scores = Scores::load(Some(config.storage_root().join("runtime").join("arcade.toml")));
    let mut rng = Rng::from_time();
    if let Some(size) = stream_size {
        let mut screen = stream::Stream::new(io::BufReader::new(io::stdin()), io::stdout(), size);
        let result = match game {
            Some(game) => play(&mut screen, game, level, &mut rng, &mut scores),
            None => arcade(&mut screen, level, &mut rng, &mut scores),
        };
        // A closed stdin (the desk left) or stdout is the normal way out.
        return match result {
            Ok(()) => 0,
            Err(error) if matches!(error.kind(), io::ErrorKind::Interrupted | io::ErrorKind::BrokenPipe) => 0,
            Err(error) => {
                eprintln!("unlaw game: stream error: {error}");
                1
            }
        };
    }
    if !io::stdout().is_terminal() || !io::stdin().is_terminal() {
        eprintln!("unlaw game: terminal error: stdin and stdout must be a terminal");
        return 1;
    }
    let result = terminal::Terminal::open().and_then(|mut screen| match game {
        Some(game) => play(&mut screen, game, level, &mut rng, &mut scores),
        None => arcade(&mut screen, level, &mut rng, &mut scores),
    });
    match result {
        Ok(()) => 0,
        Err(error) if error.kind() == io::ErrorKind::Interrupted => 130,
        Err(error) => {
            eprintln!("unlaw game: terminal error: {error}");
            1
        }
    }
}

#[cfg(test)]
pub mod testing {
    use super::*;
    use std::collections::VecDeque;

    /// Feeds inputs and records drawing. `None` lets time pass until the
    /// requested timeout; an empty queue answers `q`.
    pub struct Fake {
        pub inputs: VecDeque<Option<Input>>,
        pub size: (i32, i32),
        pub text: Vec<(i32, i32, String, Style)>,
        pub frames: Vec<Vec<(i32, i32, String, Style)>>,
        pub clock: f64,
        /// Whether this fake claims to report key releases.
        pub releases: bool,
        /// Every `set_releases` request, in order.
        pub release_requests: Vec<bool>,
        saved: Vec<(i32, i32, String, Style)>,
        reads: usize,
    }

    impl Fake {
        pub fn new(size: (i32, i32)) -> Fake {
            Fake { inputs: VecDeque::new(), size, text: Vec::new(), frames: Vec::new(), clock: 0.0, releases: false, release_requests: Vec::new(), saved: Vec::new(), reads: 0 }
        }

        pub fn keys(mut self, keys: &[Option<Input>]) -> Fake {
            self.inputs.extend(keys.iter().copied());
            self
        }

        pub fn idle(mut self, frames: usize) -> Fake {
            self.inputs.extend(std::iter::repeat_n(None, frames));
            self
        }

        pub fn drew(&self, needle: &str) -> bool {
            self.frames.iter().flatten().chain(self.text.iter()).any(|(_, _, text, _)| text.contains(needle))
        }
    }

    impl Screen for Fake {
        fn size(&self) -> (i32, i32) {
            self.size
        }
        fn clear(&mut self) {
            self.text.clear();
        }
        fn put(&mut self, y: i32, x: i32, text: &str, style: Style) {
            self.text.push((y, x, text.to_string(), style));
        }
        fn save_frame(&mut self) {
            self.saved = self.text.clone();
        }
        fn load_frame(&mut self) {
            self.text = self.saved.clone();
        }
        fn present(&mut self) -> io::Result<()> {
            self.frames.push(self.text.clone());
            if self.frames.len() > 4000 {
                self.frames.remove(0);
            }
            Ok(())
        }
        fn input(&mut self, timeout: Option<Duration>) -> io::Result<Option<Input>> {
            self.reads += 1;
            assert!(self.reads < 200_000, "game did not finish");
            match self.inputs.pop_front() {
                Some(None) => {
                    self.clock += timeout.map(|t| t.as_secs_f64()).unwrap_or(1.0);
                    Ok(None)
                }
                Some(Some(input)) => {
                    self.clock += 0.6; // also lets end screens accept input
                    Ok(Some(input))
                }
                None => {
                    self.clock += 0.6;
                    Ok(Some(Input::Key(Key::Esc)))
                }
            }
        }
        fn now(&self) -> f64 {
            self.clock
        }
        fn set_releases(&mut self, on: bool) -> bool {
            self.release_requests.push(on);
            on && self.releases
        }
    }

    pub fn key(character: char) -> Option<Input> {
        Some(Input::Key(Key::Char(character)))
    }

    pub fn special(key: Key) -> Option<Input> {
        Some(Input::Key(key))
    }

    pub fn click(y: i32, x: i32, button: Button) -> Option<Input> {
        Some(Input::Click { y, x, button })
    }
}

#[cfg(test)]
mod tests {
    use super::testing::*;
    use super::*;

    #[test]
    fn menus_work_with_keys_numbers_and_mouse() {
        let scores = Scores::load(None);
        let pick = |inputs: &[Option<Input>]| game_menu(&mut Fake::new((40, 120)).keys(inputs), &scores, Level::Normal).unwrap();
        assert_eq!(pick(&[special(Key::Down), key('j'), special(Key::Enter)]), Some("minesweeper"));
        assert_eq!(pick(&[key('k'), special(Key::Enter)]), Some("pingpong"));
        assert_eq!(pick(&[key('6')]), Some("dash"));
        assert_eq!(pick(&[key('7')]), Some("pingpong"));
        assert_eq!(pick(&[key('2')]), Some("snake"));
        assert_eq!(pick(&[key('9'), special(Key::Esc)]), None);
        let first = menu_first_row(40, GAMES.len());
        assert_eq!(pick(&[click(first + 3, 60, Button::Left)]), Some("invaders"));
        assert_eq!(pick(&[Some(Input::Hover { y: first + 1, x: 60 }), special(Key::Enter)]), Some("snake"));
        assert_eq!(pick(&[click(0, 0, Button::Left), key('q')]), None);
        let level = |inputs: &[Option<Input>], default| difficulty_menu(&mut Fake::new((40, 120)).keys(inputs), default).unwrap();
        assert_eq!(level(&[special(Key::Enter)], Level::Hard), Some(Level::Hard));
        assert_eq!(level(&[special(Key::Down), special(Key::Enter)], Level::Hard), Some(Level::Easy));
        assert_eq!(level(&[key('1')], Level::Normal), Some(Level::Easy));
        assert_eq!(level(&[special(Key::Esc)], Level::Easy), None);
    }

    #[test]
    fn scores_keep_the_best_and_persist() {
        let path = std::env::temp_dir().join(format!("unlaw-arcade-{}.toml", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let mut scores = Scores::load(Some(path.clone()));
        assert!(scores.record("snake", Level::Hard, 40));
        assert!(!scores.record("snake", Level::Hard, 30));
        assert!(scores.record("minesweeper", Level::Easy, 90));
        assert!(scores.record("minesweeper", Level::Easy, 60), "lower times are better");
        assert!(!scores.record("minesweeper", Level::Easy, 61));
        let reloaded = Scores::load(Some(path.clone()));
        assert_eq!(reloaded.best("snake", Level::Hard), Some(40));
        assert_eq!(reloaded.best("minesweeper", Level::Easy), Some(60));
        assert_eq!(reloaded.best("tetris", Level::Easy), None);
        std::fs::remove_file(path).unwrap();
        assert_eq!(Scores::load(Some("/nonexistent/x.toml".into())).best("snake", Level::Easy), None);
    }

    #[test]
    fn corrupt_scores_file_is_moved_aside_not_overwritten() {
        let dir = std::env::temp_dir().join(format!("unlaw-arcade-corrupt-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("arcade.toml");
        let mut scores = Scores::load(Some(path.clone()));
        assert!(scores.record("snake", Level::Easy, 5));
        std::fs::write(&path, "snake = [ not toml").unwrap();
        assert!(scores.record("tetris", Level::Easy, 9));
        let aside: Vec<_> = std::fs::read_dir(&dir)
            .unwrap()
            .map(|entry| entry.unwrap().path())
            .filter(|path| path.file_name().unwrap().to_string_lossy().starts_with("arcade.toml.corrupt-"))
            .collect();
        assert_eq!(aside.len(), 1, "the corrupt file is kept under a new name");
        assert_eq!(std::fs::read_to_string(&aside[0]).unwrap(), "snake = [ not toml");
        let saved = Scores::load(Some(path.clone()));
        assert_eq!(saved.best("tetris", Level::Easy), Some(9));
        assert_eq!(saved.best("snake", Level::Easy), None, "started fresh, not from the stale in-memory copy");
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn scores_reread_bests_saved_by_another_game() {
        // The terminal and `ul desk` run separate processes on one arcade.toml.
        let path = std::env::temp_dir().join(format!("unlaw-arcade-shared-{}.toml", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let mut terminal = Scores::load(Some(path.clone()));
        let mut desk = Scores::load(Some(path.clone()));
        assert!(desk.record("tetris", Level::Normal, 900));
        assert_eq!(terminal.best("tetris", Level::Normal), None, "not reread yet");
        terminal.reload();
        assert_eq!(terminal.best("tetris", Level::Normal), Some(900));
        assert!(!terminal.record("tetris", Level::Normal, 500), "a lower score never replaces the desk's best");
        assert!(terminal.record("snake", Level::Easy, 7));
        let saved = Scores::load(Some(path.clone()));
        assert_eq!(saved.best("tetris", Level::Normal), Some(900));
        assert_eq!(saved.best("snake", Level::Easy), Some(7));
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn score_records_wait_for_the_shared_file_lock() {
        use std::os::fd::AsRawFd;
        let path = std::env::temp_dir().join(format!("unlaw-arcade-lock-{}.toml", std::process::id()));
        let lock_path = path.with_extension("lock");
        let lock = std::fs::OpenOptions::new().write(true).create(true).truncate(false).open(&lock_path).unwrap();
        assert_eq!(unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX) }, 0);
        let (started, ready) = std::sync::mpsc::channel();
        let (done, result) = std::sync::mpsc::channel();
        let writer_path = path.clone();
        let writer = std::thread::spawn(move || {
            let mut scores = Scores::load(Some(writer_path));
            started.send(()).unwrap();
            let recorded = scores.record("snake", Level::Normal, 100);
            done.send(recorded).unwrap();
        });
        ready.recv().unwrap();
        let waited = result.recv_timeout(Duration::from_millis(100)).is_err();
        // Publish a competing result while the writer is blocked, as a second process would.
        std::fs::write(&path, "[tetris]\nnormal = 900\n").unwrap();
        drop(lock);
        writer.join().unwrap();
        let recorded = if waited { result.recv().unwrap() } else { false };
        let saved = Scores::load(Some(path.clone()));
        let both = saved.best("snake", Level::Normal) == Some(100) && saved.best("tetris", Level::Normal) == Some(900);
        let _ = std::fs::remove_file(path);
        let _ = std::fs::remove_file(lock_path);
        assert!(waited, "score write ignored the shared file lock");
        assert!(recorded && both, "concurrent bests were not merged after acquiring the lock");
    }

    #[test]
    fn finish_ignores_early_keys_then_offers_again_or_leave() {
        let mut screen = Fake::new((30, 80)).keys(&[special(Key::Enter)]);
        screen.clock = 10.0;
        // The fake advances 0.6s per key, which passes the 0.5s guard.
        assert_eq!(finish(&mut screen, "GAME OVER", &["Score 5".into()], Some((5, Some(9), "snake")), None).unwrap(), After::Again);
        assert!(screen.drew("Best 9"));
        let mut screen = Fake::new((30, 80)).keys(&[key('q')]);
        assert_eq!(finish(&mut screen, "WIN", &[], Some((3, Some(9), "minesweeper")), None).unwrap(), After::Leave);
        assert!(screen.drew("New best"));
    }

    #[test]
    fn pause_resumes_or_leaves() {
        assert!(!pause(&mut Fake::new((30, 80)).keys(&[key('x'), key('p')])).unwrap());
        assert!(pause(&mut Fake::new((30, 80)).keys(&[special(Key::Esc)])).unwrap());
    }

    #[test]
    fn rng_is_bounded_and_shuffles_everything() {
        let mut rng = Rng::seeded(42);
        assert!((0..1000).all(|_| rng.below(7) < 7));
        let mut items: Vec<u8> = (0..20).collect();
        rng.shuffle(&mut items);
        let mut sorted = items.clone();
        sorted.sort();
        assert_eq!(sorted, (0..20).collect::<Vec<_>>());
        assert_eq!(Rng::constant(9).below(4), 1);
        assert!(!Rng::constant(999_999).chance(0.5));
        assert!(Rng::constant(0).chance(0.5));
    }

    #[test]
    fn levels_and_inputs() {
        assert_eq!(Level::parse("hard"), Some(Level::Hard));
        assert_eq!(Level::parse("insane"), None);
        assert_eq!(Level::Normal.pick(1, 2, 3), 2);
        assert!(Input::Key(Key::Char('Q')).is_leave());
        assert!(Input::Key(Key::Esc).is_leave());
        assert!(Input::Key(Key::Char('P')).is_pause());
    }

    #[test]
    fn small_terminals_are_explained() {
        let mut screen = Fake::new((10, 30)).keys(&[key('x')]);
        assert_eq!(too_small(&mut screen, 60, 24).unwrap().after, After::Leave);
        assert!(screen.drew("needs a 60x24 terminal"));
    }

    #[test]
    fn the_ticker_keeps_a_fixed_cadence_whatever_the_drawing_costs() {
        let mut ticker = Ticker::new(10.0);
        // Drawing took 5 ms each time: deadlines stay on the 1/30 s grid instead of drifting.
        let mut deadlines = Vec::new();
        for frame in 1..=3 {
            let drawn_at = 10.0 + (frame - 1) as f64 * FRAME + 0.005;
            deadlines.push(ticker.deadline(drawn_at));
        }
        for (index, deadline) in deadlines.iter().enumerate() {
            assert!((deadline - (10.0 + (index + 1) as f64 * FRAME)).abs() < 1e-9, "{deadlines:?}");
        }
        // A stall (pause, slow terminal) resynchronizes instead of firing a burst of frames.
        assert!((ticker.deadline(20.0) - (20.0 + FRAME)).abs() < 1e-9);
        // Leaving a frame early (Snake's step) does not leave the schedule running ahead.
        assert!((ticker.deadline(20.0 + FRAME / 3.0) - (20.0 + FRAME / 3.0 + FRAME)).abs() < 1e-9);
        ticker.reset(30.0);
        assert!((ticker.deadline(30.001) - (30.0 + FRAME)).abs() < 1e-9);
    }

    #[test]
    fn a_hover_flood_collapses_to_the_last_position() {
        let hover = |y, x| Some(Input::Hover { y, x });
        let mut screen = Fake::new((30, 80)).keys(&[hover(1, 1), hover(2, 2), key('a'), hover(3, 3), hover(4, 4), hover(5, 5)]).idle(1);
        let inputs = inputs_until(&mut screen, 100.0).unwrap();
        assert_eq!(inputs, vec![Input::Hover { y: 2, x: 2 }, Input::Key(Key::Char('a')), Input::Hover { y: 5, x: 5 }]);
    }

    #[test]
    fn blocks_are_centered_with_room_for_the_hud_and_controls() {
        // 40 rows: HUD, 20-row board, controls; the 18 spare rows are split around it.
        assert_eq!(center_block((40, 100), 20, 30), (10, 35));
        // Exactly enough room: HUD on row 0, board from row 1, controls on the last row.
        assert_eq!(center_block((22, 30), 20, 30), (1, 0));
        // Never negative on a terminal that is too small.
        assert_eq!(center_block((5, 10), 20, 30), (1, 0));
    }

    #[test]
    fn the_hud_drops_the_least_important_stats_when_narrow() {
        let stats = [("SCORE", "120".to_string()), ("LEVEL", "3".to_string()), ("BEST", "900".to_string())];
        let mut wide = Fake::new((30, 80));
        wide.hud(0, 0, 60, "SNAKE · easy", &stats);
        assert!(wide.drew("SNAKE · easy") && wide.drew("BEST") && wide.drew("900"));
        // Right aligned to the end of the block.
        let (_, x, text, _) = wide.text.last().unwrap();
        assert_eq!(x + text.chars().count() as i32, 60);
        let mut narrow = Fake::new((30, 80));
        narrow.hud(0, 0, 32, "SNAKE · easy", &stats);
        assert!(narrow.drew("SCORE") && narrow.drew("LEVEL"));
        assert!(!narrow.drew("BEST"), "the last stat goes first");
        let mut tiny = Fake::new((30, 80));
        tiny.hud(0, 0, 10, "SNAKE · easy", &stats);
        assert!(tiny.drew("SNAKE") && !tiny.drew("SCORE"));
    }

    /// A fake screen that also counts `dim_all` calls and can grow on its second read.
    struct Probe {
        fake: Fake,
        dims: usize,
        reads: usize,
        grow: bool,
    }

    impl Screen for Probe {
        fn size(&self) -> (i32, i32) {
            self.fake.size()
        }
        fn clear(&mut self) {
            self.fake.clear()
        }
        fn put(&mut self, y: i32, x: i32, text: &str, style: Style) {
            self.fake.put(y, x, text, style)
        }
        fn dim_all(&mut self) {
            self.dims += 1;
        }
        fn present(&mut self) -> io::Result<()> {
            self.fake.present()
        }
        fn input(&mut self, timeout: Option<Duration>) -> io::Result<Option<Input>> {
            self.reads += 1;
            if self.grow && self.reads == 2 {
                self.fake.size = (40, 120);
                return Ok(None);
            }
            self.fake.input(timeout)
        }
        fn now(&self) -> f64 {
            self.fake.now()
        }
    }

    fn probe(size: (i32, i32), grow: bool) -> Probe {
        Probe { fake: Fake::new(size), dims: 0, reads: 0, grow }
    }

    #[test]
    fn overlays_are_rounded_with_a_shadow_over_a_dimmed_game() {
        let mut screen = probe((20, 60), false);
        overlay(&mut screen, &[("PAUSED".into(), Style::PLAIN)]);
        assert_eq!(screen.dims, 1, "the game behind is dimmed once");
        assert!(screen.fake.drew("╭") && screen.fake.drew("╯") && screen.fake.drew("▒"));
        assert!(!screen.fake.drew("┌"));
    }

    #[test]
    fn a_game_waits_for_the_terminal_to_grow_instead_of_leaving() {
        let mut screen = probe((10, 30), true);
        screen.fake = screen.fake.keys(&[None]);
        assert!(wait_for_room(&mut screen, 60, 24).unwrap());
        assert!(screen.fake.drew("needs a 60x24 terminal"));
        let mut leaving = Fake::new((10, 30)).keys(&[key('q')]);
        assert!(!wait_for_room(&mut leaving, 60, 24).unwrap());
        // Before the game starts, growing the terminal starts it (Again) and a key still leaves.
        let mut screen = probe((10, 30), true);
        screen.fake = screen.fake.keys(&[None]);
        assert_eq!(too_small(&mut screen, 60, 24).unwrap().after, After::Again);
    }

    #[test]
    fn the_menu_lists_descriptions_and_bests_when_it_fits_and_degrades_when_narrow() {
        let mut scores = Scores::load(None);
        scores.document["tetris"] = toml_edit::Item::Table(toml_edit::Table::new());
        scores.document["tetris"]["normal"] = toml_edit::value(1200);
        let mut wide = Fake::new((40, 120)).keys(&[key('q')]);
        game_menu(&mut wide, &scores, Level::Normal).unwrap();
        assert!(wide.drew("A R C A D E") && wide.drew("best 1200") && wide.drew(describe("snake")));
        assert!(wide.drew("best scores for normal"));
        let mut narrow = Fake::new((24, 40)).keys(&[key('q')]);
        game_menu(&mut narrow, &scores, Level::Normal).unwrap();
        assert!(narrow.drew("Tetris") && !narrow.drew(describe("snake")), "descriptions go first on a narrow terminal");
        assert_eq!(describe("a-game-from-the-future"), "");
    }
}
