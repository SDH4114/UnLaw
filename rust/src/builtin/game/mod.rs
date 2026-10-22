//! `ul game`: Tetris, Snake, Minesweeper and Space Invaders in the terminal,
//! playable with keyboard or mouse.
//!
//! Every game is a state machine (input → update → draw) that talks only to
//! the [`Screen`] trait, so it runs on a real terminal and headless in tests.

mod invaders;
mod mines;
mod snake;
mod tetris;
mod terminal;

use std::io::{self, IsTerminal};
use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use toml_edit::DocumentMut;

use crate::config::Config;

pub const HELP: &str = "Play a terminal arcade game; no arguments opens the game menu.
Usage: ul game [tetris|snake|minesweeper|invaders] [easy|normal|hard]
Games:
  tetris        7-bag pieces, next/hold, ghost, wall kicks, levels every 10 lines
  snake         eat ● (and bonus ★), grow and speed up; walls kill on normal/hard
  minesweeper   first click is safe; flag mines, click a number to clear around it
  invaders      5x11 formation, shields, UFO, waves; one shot on screen at a time
Controls (shown in every game): arrows/WASD, Space, P pause, Q or Esc leaves.
Mouse: click menus; Tetris follows the pointer (left click drops, right rotates);
Snake steers toward a click; Minesweeper left reveals, right flags;
Invaders follow the pointer and click to fire.
Difficulty (default: games.difficulty):
  easy     slow start, extra help (Tetris ghost + 3 previews, Snake wraps, 5 lives)
  normal   the classic game
  hard     really hard: Tetris starts at level 12 without ghost/hold, Snake has
           obstacles and doubles growth, Minesweeper is Expert with no safe
           opening, Invaders fire constantly and you have 2 lives
Best scores: storage.root/runtime/arcade.toml.
Example: ul game snake hard
";

pub const GAMES: [(&str, &str); 4] =
    [("tetris", "Tetris"), ("snake", "Snake"), ("minesweeper", "Minesweeper"), ("invaders", "Space Invaders")];

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

    fn frame_box(&mut self, top: i32, left: i32, height: i32, width: i32, style: Style) {
        if height < 2 || width < 2 {
            return;
        }
        let inner = "─".repeat((width - 2) as usize);
        self.put(top, left, &format!("┌{inner}┐"), style);
        self.put(top + height - 1, left, &format!("└{inner}┘"), style);
        for y in top + 1..top + height - 1 {
            self.put(y, left, "│", style);
            self.put(y, left + width - 1, "│", style);
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
            Some(input) => inputs.push(input),
            None => return Ok(inputs),
        }
    }
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

    pub fn best(&self, game: &str, level: Level) -> Option<u64> {
        self.document.get(game)?.get(level.name())?.as_integer().and_then(|value| u64::try_from(value).ok())
    }

    /// Record a finished game; saves and returns true for a new best.
    pub fn record(&mut self, game: &str, level: Level, score: u64) -> bool {
        if !is_better(game, score, self.best(game, level)) {
            return false;
        }
        if self.document.get(game).and_then(|item| item.as_table()).is_none() {
            self.document.insert(game, toml_edit::Item::Table(toml_edit::Table::new()));
        }
        self.document[game][level.name()] = toml_edit::value(score.min(i64::MAX as u64) as i64);
        if let Some(path) = &self.path {
            let _ = crate::util::atomic_write(path, &self.document.to_string(), ".arcade.");
        }
        true
    }
}

/// Darken the screen behind a centered box with `lines`; the first is the title.
pub fn overlay(screen: &mut dyn Screen, lines: &[(String, Style)]) {
    let (height, width) = screen.size();
    let inner = lines.iter().map(|(text, _)| text.chars().count()).max().unwrap_or(0) as i32 + 4;
    let box_width = inner.min(width).max(10);
    let box_height = lines.len() as i32 + 2;
    let top = ((height - box_height) / 2).max(0);
    let left = ((width - box_width) / 2).max(0);
    for y in top..top + box_height {
        screen.put(y, left, &" ".repeat(box_width as usize), Style::PLAIN);
    }
    screen.frame_box(top, left, box_height, box_width, Style::fg(Color::White).bold());
    for (index, (text, style)) in lines.iter().enumerate() {
        let x = left + ((box_width - text.chars().count() as i32) / 2).max(1);
        screen.put(top + 1 + index as i32, x, text, *style);
    }
}

/// End-of-game box: Enter/Space/click plays again, Esc/Q leaves. Keys in the
/// first half second are ignored so a held key cannot skip it by accident.
pub fn finish(screen: &mut dyn Screen, title: &str, details: &[String], score: Option<(u64, Option<u64>, &str)>) -> io::Result<After> {
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
    overlay(screen, &lines);
    screen.present()?;
    let ready = screen.now() + 0.5;
    loop {
        let Some(input) = screen.input(None)? else { continue };
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
    overlay(
        screen,
        &[
            ("PAUSED".into(), Style::fg(Color::Yellow).bold()),
            (String::new(), Style::PLAIN),
            ("P / Enter / click: resume    Esc: leave".into(), Style::fg(Color::Cyan)),
        ],
    );
    screen.present()?;
    loop {
        match screen.input(None)? {
            Some(input) if input.is_pause() => return Ok(false),
            Some(Input::Key(Key::Enter) | Input::Click { .. }) => return Ok(false),
            Some(input) if input.is_leave() => return Ok(true),
            _ => {}
        }
    }
}

/// Shown when the terminal is too small for a game.
pub fn too_small(screen: &mut dyn Screen, need_width: i32, need_height: i32) -> io::Result<Played> {
    screen.clear();
    let (height, width) = screen.size();
    screen.centered(height / 2, &format!("This game needs a {need_width}x{need_height} terminal"), Style::fg(Color::Yellow));
    screen.centered(height / 2 + 1, &format!("(now {width}x{height}) — enlarge it or press a key"), Style::PLAIN);
    screen.present()?;
    screen.input(None)?;
    Ok(Played { score: None, after: After::Leave })
}

fn menu(screen: &mut dyn Screen, title: &str, labels: &[String], mut selected: usize, footer: &str) -> io::Result<Option<usize>> {
    loop {
        screen.clear();
        let (height, width) = screen.size();
        let top = (height / 2 - labels.len() as i32 / 2 - 3).max(0);
        screen.centered(top, title, Style::fg(Color::Yellow).bold());
        let label_width = labels.iter().map(|label| label.chars().count()).max().unwrap_or(0) as i32 + 6;
        let left = ((width - label_width) / 2).max(0);
        for (index, label) in labels.iter().enumerate() {
            let text = format!(" {}. {label:<width$} ", index + 1, width = (label_width - 6) as usize);
            let style = if index == selected { Style::fg(Color::Cyan).bold().reverse() } else { Style::PLAIN };
            screen.put(top + 2 + index as i32, left, &text, style);
        }
        screen.controls(footer);
        screen.present()?;
        let row_of = |y: i32| (y - top - 2).try_into().ok().filter(|row: &usize| *row < labels.len());
        match screen.input(None)? {
            Some(input) if input.is_leave() => return Ok(None),
            Some(Input::Key(Key::Up | Key::Char('k' | 'w'))) => selected = (selected + labels.len() - 1) % labels.len(),
            Some(Input::Key(Key::Down | Key::Char('j' | 's'))) => selected = (selected + 1) % labels.len(),
            Some(Input::Key(Key::Enter | Key::Char(' '))) => return Ok(Some(selected)),
            Some(Input::Key(Key::Char(digit))) if digit.is_ascii_digit() => {
                let index = (digit as usize).wrapping_sub('1' as usize);
                if index < labels.len() {
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
    let labels: Vec<String> = GAMES
        .iter()
        .map(|(name, label)| match scores.best(name, level) {
            Some(best) if lower_is_better(name) => format!("{label:<16} best {best}s"),
            Some(best) => format!("{label:<16} best {best}"),
            None => label.to_string(),
        })
        .collect();
    let footer = "↑/↓ or mouse select · Enter / click play · Q quit";
    Ok(menu(screen, "U N L A W   A R C A D E", &labels, 0, footer)?.map(|index| GAMES[index].0))
}

pub fn difficulty_menu(screen: &mut dyn Screen, default: Level) -> io::Result<Option<Level>> {
    let labels: Vec<String> = [
        "Easy     slow start, extra help",
        "Normal   the classic game",
        "Hard     really hard",
    ]
    .map(String::from)
    .to_vec();
    let start = [Level::Easy, Level::Normal, Level::Hard].iter().position(|level| *level == default).unwrap_or(1);
    let footer = "↑/↓ or mouse select · Enter / click start · Esc back";
    Ok(menu(screen, "SELECT DIFFICULTY", &labels, start, footer)?.map(|index| [Level::Easy, Level::Normal, Level::Hard][index]))
}

pub fn play_once(screen: &mut dyn Screen, game: &str, level: Level, rng: &mut Rng, best: Option<u64>) -> io::Result<Played> {
    match game {
        "tetris" => tetris::play(screen, level, rng, best),
        "snake" => snake::play(screen, level, rng, best),
        "minesweeper" => mines::play(screen, level, rng, best),
        _ => invaders::play(screen, level, rng, best),
    }
}

/// Play `game` until the player leaves, recording best scores.
pub fn play(screen: &mut dyn Screen, game: &str, level: Level, rng: &mut Rng, scores: &mut Scores) -> io::Result<()> {
    loop {
        let played = play_once(screen, game, level, rng, scores.best(game, level))?;
        if let Some(score) = played.score {
            scores.record(game, level, score);
        }
        if played.after == After::Leave {
            return Ok(());
        }
    }
}

pub fn arcade(screen: &mut dyn Screen, default: Level, rng: &mut Rng, scores: &mut Scores) -> io::Result<()> {
    while let Some(game) = game_menu(screen, scores, default)? {
        if let Some(level) = difficulty_menu(screen, default)? {
            play(screen, game, level, rng, scores)?;
        }
    }
    Ok(())
}

fn usage() -> i32 {
    eprintln!("Usage: ul game [tetris|snake|minesweeper|invaders] [easy|normal|hard]");
    2
}

pub fn run(args: &[String], config: &Config) -> i32 {
    if matches!(args.first().map(String::as_str), Some("-h" | "--help" | "help")) {
        print!("{HELP}");
        return 0;
    }
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
    if !io::stdout().is_terminal() || !io::stdin().is_terminal() {
        eprintln!("unlaw game: terminal error: stdin and stdout must be a terminal");
        return 1;
    }
    let mut scores = Scores::load(Some(config.storage_root().join("runtime").join("arcade.toml")));
    let mut rng = Rng::from_time();
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
        reads: usize,
    }

    impl Fake {
        pub fn new(size: (i32, i32)) -> Fake {
            Fake { inputs: VecDeque::new(), size, text: Vec::new(), frames: Vec::new(), clock: 0.0, reads: 0 }
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
        fn present(&mut self) -> io::Result<()> {
            self.frames.push(self.text.clone());
            if self.frames.len() > 400 {
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
        assert_eq!(pick(&[key('k'), special(Key::Enter)]), Some("invaders"));
        assert_eq!(pick(&[key('2')]), Some("snake"));
        assert_eq!(pick(&[key('9'), special(Key::Esc)]), None);
        // Rows start two lines under the title, which sits at height/2 - 2 - 3.
        let top = 40 / 2 - 4 / 2 - 3;
        assert_eq!(pick(&[click(top + 2 + 3, 60, Button::Left)]), Some("invaders"));
        assert_eq!(pick(&[Some(Input::Hover { y: top + 3, x: 60 }), special(Key::Enter)]), Some("snake"));
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
    fn finish_ignores_early_keys_then_offers_again_or_leave() {
        let mut screen = Fake::new((30, 80)).keys(&[special(Key::Enter)]);
        screen.clock = 10.0;
        // The fake advances 0.6s per key, which passes the 0.5s guard.
        assert_eq!(finish(&mut screen, "GAME OVER", &["Score 5".into()], Some((5, Some(9), "snake"))).unwrap(), After::Again);
        assert!(screen.drew("Best 9"));
        let mut screen = Fake::new((30, 80)).keys(&[key('q')]);
        assert_eq!(finish(&mut screen, "WIN", &[], Some((3, Some(9), "minesweeper"))).unwrap(), After::Leave);
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
}
