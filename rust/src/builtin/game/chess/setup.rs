//! The screens before a game: who plays (bot or friend), the bot's color (white, black or
//! random) and the time control, where the minutes and the increment are typed or set with
//! −/+ and presets.

use std::io;
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicUsize, Ordering};

use super::board::Side;
use super::Mode;
use crate::builtin::game::{
    banner, menu, Button, Color, Input, Item, Key, Level, Rng, Screen, Style,
};

/// Longest game and largest increment the clock accepts.
pub const MAX_MINUTES: u32 = 180;
pub const MAX_INCREMENT: u32 = 60;
/// (minutes, increment seconds) offered as one-click presets.
pub const PRESETS: [(u32, u32); 7] = [(1, 0), (3, 2), (5, 0), (5, 3), (10, 0), (10, 5), (15, 10)];

static LAST_OPPONENT: AtomicUsize = AtomicUsize::new(0);
static LAST_COLOR: AtomicUsize = AtomicUsize::new(0);
static LAST_CLOCK_ON: AtomicBool = AtomicBool::new(false);
static LAST_MINUTES: AtomicU32 = AtomicU32::new(10);
static LAST_INCREMENT: AtomicU32 = AtomicU32::new(0);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TimeControl {
    pub minutes: u32,
    pub increment: u32,
}

impl TimeControl {
    pub fn label(self) -> String {
        format!("{}+{}", self.minutes, self.increment)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Setup {
    pub mode: Mode,
    pub clock: Option<TimeControl>,
}

enum Step {
    Opponent,
    Color,
    Time(Mode),
}

/// Walk the setup screens; Esc goes one screen back, `None` = leave from the first one.
pub fn choose(screen: &mut dyn Screen, level: Level, rng: &mut Rng) -> io::Result<Option<Setup>> {
    let mut step = Step::Opponent;
    loop {
        step = match step {
            Step::Opponent => {
                let items = [
                    Item {
                        label: "Play the bot".into(),
                        detail: format!("strength: {} · then pick a color", level.name()),
                        note: String::new(),
                    },
                    Item {
                        label: "Play a friend".into(),
                        detail: "one keyboard and mouse, take turns".into(),
                        note: String::new(),
                    },
                ];
                let footer = "↑/↓ or mouse select · Enter / click choose · 1-2 jump · Esc back";
                match menu(
                    screen,
                    "C H E S S",
                    "who do you play?",
                    &items,
                    LAST_OPPONENT.load(Ordering::Relaxed).min(1),
                    footer,
                )? {
                    None => return Ok(None),
                    Some(index) => {
                        LAST_OPPONENT.store(index, Ordering::Relaxed);
                        if index == 0 {
                            Step::Color
                        } else {
                            Step::Time(Mode::Duel)
                        }
                    }
                }
            }
            Step::Color => {
                let items = [
                    Item {
                        label: "White".into(),
                        detail: "you move first".into(),
                        note: String::new(),
                    },
                    Item {
                        label: "Black".into(),
                        detail: "the bot opens, the board is flipped".into(),
                        note: String::new(),
                    },
                    Item {
                        label: "Random".into(),
                        detail: "a coin decides".into(),
                        note: String::new(),
                    },
                ];
                let footer = "↑/↓ or mouse select · Enter / click choose · 1-3 jump · Esc back";
                match menu(
                    screen,
                    "Y O U R   C O L O R",
                    "you play against the bot as",
                    &items,
                    LAST_COLOR.load(Ordering::Relaxed).min(2),
                    footer,
                )? {
                    None => Step::Opponent,
                    Some(index) => {
                        LAST_COLOR.store(index, Ordering::Relaxed);
                        let side = match index {
                            0 => Side::White,
                            1 => Side::Black,
                            _ if rng.below(2) == 0 => Side::White,
                            _ => Side::Black,
                        };
                        Step::Time(Mode::Bot(side))
                    }
                }
            }
            Step::Time(mode) => match time_control(screen)? {
                None => {
                    if mode == Mode::Duel {
                        Step::Opponent
                    } else {
                        Step::Color
                    }
                }
                Some(clock) => return Ok(Some(Setup { mode, clock })),
            },
        };
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Row {
    Clock,
    Minutes,
    Increment,
    Presets,
    Start,
}

const ROWS: [Row; 5] = [
    Row::Clock,
    Row::Minutes,
    Row::Increment,
    Row::Presets,
    Row::Start,
];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Action {
    Focus(Row),
    ClockOn(bool),
    Step(Row, i32),
    Preset(usize),
    Start,
}

struct TimeForm {
    on: bool,
    minutes: u32,
    increment: u32,
    row: usize,
    preset: usize,
    /// The next digit replaces the field instead of extending it (just focused).
    fresh: bool,
    /// Clickable spans drawn this frame: (row, first column, last column, action).
    hits: Vec<(i32, i32, i32, Action)>,
}

impl TimeForm {
    fn new() -> TimeForm {
        TimeForm::with(LAST_CLOCK_ON.load(Ordering::Relaxed), LAST_MINUTES.load(Ordering::Relaxed), LAST_INCREMENT.load(Ordering::Relaxed))
    }

    /// The form opens on Start when a clock was chosen last time, else on the on/off switch.
    fn with(on: bool, minutes: u32, increment: u32) -> TimeForm {
        let preset = PRESETS.iter().position(|preset| *preset == (minutes, increment)).unwrap_or(0);
        TimeForm { on, minutes, increment, row: if on { 4 } else { 0 }, preset, fresh: true, hits: Vec::new() }
    }

    fn focus(&mut self, row: Row) {
        self.row = ROWS
            .iter()
            .position(|candidate| *candidate == row)
            .unwrap_or(0);
        self.fresh = true;
    }

    fn field(&mut self, row: Row) -> Option<(&mut u32, u32)> {
        match row {
            Row::Minutes => Some((&mut self.minutes, MAX_MINUTES)),
            Row::Increment => Some((&mut self.increment, MAX_INCREMENT)),
            _ => None,
        }
    }

    fn step(&mut self, row: Row, by: i32) {
        if let Some((value, max)) = self.field(row) {
            *value = (*value as i32 + by).clamp(0, max as i32) as u32;
            self.on = true;
        }
    }

    fn digit(&mut self, digit: u32) {
        let fresh = self.fresh;
        let row = ROWS[self.row];
        if let Some((value, max)) = self.field(row) {
            let typed = if fresh { digit } else { *value * 10 + digit };
            // A digit that would overflow starts the number again.
            *value = if typed > max { digit.min(max) } else { typed };
            self.on = true;
            self.fresh = false;
        }
    }

    fn backspace(&mut self) {
        let row = ROWS[self.row];
        if let Some((value, _)) = self.field(row) {
            *value /= 10;
        }
        self.fresh = false;
    }

    fn apply(&mut self, preset: usize) {
        (self.minutes, self.increment) = PRESETS[preset];
        self.preset = preset;
        self.on = true;
    }

    fn result(&self) -> Option<TimeControl> {
        // Zero minutes would lose on time at once: at least one minute.
        self.on.then(|| TimeControl {
            minutes: self.minutes.max(1),
            increment: self.increment,
        })
    }

    fn remember(&self) {
        // Tests run in parallel and share these: they always start from the defaults.
        if cfg!(test) {
            return;
        }
        LAST_CLOCK_ON.store(self.on, Ordering::Relaxed);
        LAST_MINUTES.store(self.minutes.max(1), Ordering::Relaxed);
        LAST_INCREMENT.store(self.increment, Ordering::Relaxed);
    }

    fn act(&mut self, action: Action) -> bool {
        match action {
            Action::Focus(row) => self.focus(row),
            Action::ClockOn(on) => {
                self.on = on;
                self.focus(Row::Clock);
            }
            Action::Step(row, by) => {
                self.focus(row);
                self.step(row, by);
            }
            Action::Preset(index) => {
                self.apply(index);
                self.focus(Row::Presets);
            }
            Action::Start => return true,
        }
        false
    }

    fn draw(&mut self, screen: &mut dyn Screen) {
        screen.clear();
        self.hits.clear();
        let (height, width) = screen.size();
        let box_width = 52.min(width);
        let box_height = 13;
        let top = ((height - 1 - box_height - 5) / 2).max(0) + 5;
        let left = ((width - box_width) / 2).max(0);
        banner(screen, top - 5, "T I M E   C O N T R O L");
        screen.centered(
            top - 2,
            "type a number, use −/+ or pick a preset",
            Style::fg(Color::Gray),
        );
        screen.panel(
            top,
            left,
            box_height,
            box_width,
            "Clock",
            Style::fg(Color::DarkCyan),
        );
        let focused = ROWS[self.row];
        let label_x = left + 3;
        let value_x = left + 24;
        let label = |screen: &mut dyn Screen, y: i32, row: Row, text: &str| {
            let style = if focused == row {
                Style::fg(Color::Cyan).bold()
            } else {
                Style::fg(Color::White)
            };
            screen.put(
                y,
                label_x - 2,
                if focused == row { "▸" } else { " " },
                Style::fg(Color::Cyan).bold(),
            );
            screen.put(y, label_x, text, style);
        };
        // Clock on/off.
        let y = top + 2;
        label(screen, y, Row::Clock, "Clock");
        let mut x = value_x;
        for (text, on) in [(" On ", true), (" Off ", false)] {
            let chosen = self.on == on;
            let style = if chosen {
                Style::fg(Color::Cyan).bold().reverse()
            } else {
                Style::fg(Color::Gray)
            };
            screen.put(y, x, text, style);
            self.hits.push((
                y,
                x,
                x + text.chars().count() as i32 - 1,
                Action::ClockOn(on),
            ));
            x += text.chars().count() as i32 + 1;
        }
        // Minutes and increment: [−] value [+].
        let fields = [
            (Row::Minutes, "Minutes per side", self.minutes, "min"),
            (Row::Increment, "Increment per move", self.increment, "s"),
        ];
        for (index, (row, text, value, unit)) in fields.into_iter().enumerate() {
            let y = top + 4 + index as i32 * 2;
            label(screen, y, row, text);
            let dim = if self.on {
                Style::PLAIN
            } else {
                Style::PLAIN.dim()
            };
            let button = Style::fg(Color::Gray).bold();
            screen.put(y, value_x, "[−]", button);
            self.hits
                .push((y, value_x, value_x + 2, Action::Step(row, -1)));
            let shown = if focused == row && !self.fresh {
                format!("{value}_")
            } else {
                value.to_string()
            };
            let field_style = if focused == row {
                Style::fg(Color::Yellow).bold().reverse()
            } else {
                Style::fg(Color::Yellow).bold()
            };
            screen.put(
                y,
                value_x + 4,
                &format!(" {shown:>4} "),
                Style {
                    dim: dim.dim,
                    ..field_style
                },
            );
            self.hits
                .push((y, value_x + 4, value_x + 9, Action::Focus(row)));
            screen.put(y, value_x + 11, "[+]", button);
            self.hits
                .push((y, value_x + 11, value_x + 13, Action::Step(row, 1)));
            screen.put(y, value_x + 15, unit, Style::fg(Color::Gray));
        }
        // Presets.
        let y = top + 8;
        label(screen, y, Row::Presets, "Presets");
        let mut x = label_x;
        let y = y + 1;
        for (index, (minutes, increment)) in PRESETS.iter().enumerate() {
            let text = format!(" {minutes}+{increment} ");
            let current = self.on && (self.minutes, self.increment) == (*minutes, *increment);
            let style = if focused == Row::Presets && index == self.preset {
                Style::fg(Color::Cyan).bold().reverse()
            } else if current {
                Style::fg(Color::Green).bold()
            } else {
                Style::fg(Color::Gray)
            };
            screen.put(y, x, &text, style);
            self.hits.push((
                y,
                x,
                x + text.chars().count() as i32 - 1,
                Action::Preset(index),
            ));
            x += text.chars().count() as i32 + 1;
        }
        // Summary and start.
        let y = top + box_height - 2;
        let summary = match self.result() {
            None => "no clock: think as long as you like".to_string(),
            Some(clock) if clock.increment == 0 => format!("{} min each", clock.minutes),
            Some(clock) => format!(
                "{} min each, +{} s per move",
                clock.minutes, clock.increment
            ),
        };
        screen.put(y, label_x, &summary, Style::fg(Color::Gray));
        let start = " Start ▶ ";
        let start_x = left + box_width - 3 - start.chars().count() as i32;
        let style = if focused == Row::Start {
            Style::fg(Color::Green).bold().reverse()
        } else {
            Style::fg(Color::Green).bold()
        };
        screen.put(y, start_x, start, style);
        self.hits.push((
            y,
            start_x,
            start_x + start.chars().count() as i32 - 1,
            Action::Start,
        ));
        screen.controls("↑/↓ field · type digits, ⌫ erase, ←/→ −/+ · Enter start · Esc back");
    }
}

/// The time control screen: `Ok(None)` = back, `Ok(Some(None))` = no clock.
fn time_control(screen: &mut dyn Screen) -> io::Result<Option<Option<TimeControl>>> {
    run_form(screen, TimeForm::new())
}

fn run_form(screen: &mut dyn Screen, mut form: TimeForm) -> io::Result<Option<Option<TimeControl>>> {
    loop {
        form.draw(screen);
        screen.present()?;
        let Some(input) = screen.input(None)? else {
            continue;
        };
        let row = ROWS[form.row];
        match input {
            Input::Key(Key::Esc) => return Ok(None),
            Input::Key(Key::Up) => form.row = (form.row + ROWS.len() - 1) % ROWS.len(),
            Input::Key(Key::Down) => form.row = (form.row + 1) % ROWS.len(),
            Input::Key(Key::Left | Key::Right) => {
                let by = if input == Input::Key(Key::Left) {
                    -1
                } else {
                    1
                };
                match row {
                    Row::Clock => form.on = !form.on,
                    Row::Minutes | Row::Increment => form.step(row, by),
                    Row::Presets => {
                        form.preset =
                            (form.preset as i32 + by).rem_euclid(PRESETS.len() as i32) as usize
                    }
                    Row::Start => {}
                }
            }
            Input::Key(Key::Backspace) => form.backspace(),
            Input::Key(Key::Enter) => {
                if row == Row::Presets {
                    form.apply(form.preset);
                }
                form.remember();
                return Ok(Some(form.result()));
            }
            Input::Key(Key::Char(' ')) => match row {
                Row::Clock => form.on = !form.on,
                Row::Presets => form.apply(form.preset),
                Row::Start => {
                    form.remember();
                    return Ok(Some(form.result()));
                }
                _ => {}
            },
            Input::Key(Key::Char(digit @ '0'..='9')) => form.digit(digit as u32 - '0' as u32),
            Input::Key(Key::Char('-' | '_')) => form.step(row, -1),
            Input::Key(Key::Char('+' | '=')) => form.step(row, 1),
            Input::Key(Key::Char('q' | 'Q')) => return Ok(None),
            Input::Click {
                y,
                x,
                button: Button::Left,
            } => {
                let hit = form
                    .hits
                    .iter()
                    .find(|(row, first, last, _)| *row == y && (*first..=*last).contains(&x))
                    .map(|hit| hit.3);
                if let Some(action) = hit {
                    if form.act(action) {
                        form.remember();
                        return Ok(Some(form.result()));
                    }
                }
            }
            _ => {}
        }
        if !matches!(
            input,
            Input::Key(Key::Char('0'..='9') | Key::Backspace) | Input::Hover { .. }
        ) && ROWS[form.row] != row
        {
            form.fresh = true;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::builtin::game::testing::*;

    fn off() -> TimeForm {
        TimeForm::with(false, 10, 0)
    }

    #[test]
    fn typed_minutes_and_increment_start_a_clock() {
        let mut screen = Fake::new((30, 100)).keys(&[
            special(Key::Down),
            key('2'),
            key('5'),
            special(Key::Down),
            key('7'),
            special(Key::Backspace),
            key('3'),
            special(Key::Enter),
        ]);
        assert_eq!(run_form(&mut screen, off()).unwrap(), Some(Some(TimeControl { minutes: 25, increment: 3 })));
        assert!(screen.drew("Minutes per side"));
    }

    #[test]
    fn a_preset_by_keys_off_by_default_and_esc_goes_back() {
        let keys = [special(Key::Down), special(Key::Down), special(Key::Down), special(Key::Right), special(Key::Enter)];
        let mut screen = Fake::new((30, 100)).keys(&keys);
        // 7+0 is not a preset, so the preset cursor starts on the first one.
        assert_eq!(run_form(&mut screen, TimeForm::with(false, 7, 0)).unwrap(), Some(Some(TimeControl { minutes: 3, increment: 2 })));
        let mut screen = Fake::new((30, 100)).keys(&[special(Key::Enter)]);
        assert_eq!(run_form(&mut screen, off()).unwrap(), Some(None), "Enter right away keeps the clock off");
        let mut screen = Fake::new((30, 100)).keys(&[special(Key::Esc)]);
        assert_eq!(run_form(&mut screen, off()).unwrap(), None, "Esc goes back");
    }

    #[test]
    fn clicks_on_minus_plus_presets_and_start() {
        let mut form = off();
        form.draw(&mut Fake::new((30, 100)));
        let find = |action: Action| form.hits.iter().find(|hit| hit.3 == action).map(|hit| click(hit.0, hit.1, Button::Left)).unwrap();
        let plus = find(Action::Step(Row::Minutes, 1));
        let mut screen = Fake::new((30, 100)).keys(&[plus, plus, find(Action::Start)]);
        assert_eq!(run_form(&mut screen, off()).unwrap(), Some(Some(TimeControl { minutes: 12, increment: 0 })));
        let mut screen = Fake::new((30, 100)).keys(&[find(Action::Preset(5)), find(Action::Start)]);
        assert_eq!(run_form(&mut screen, off()).unwrap(), Some(Some(TimeControl { minutes: 10, increment: 5 })));
        let mut screen = Fake::new((30, 100)).keys(&[find(Action::Preset(5)), find(Action::ClockOn(false)), find(Action::Start)]);
        assert_eq!(run_form(&mut screen, off()).unwrap(), Some(None));
    }

    #[test]
    fn values_are_clamped() {
        let mut form = off();
        form.focus(Row::Minutes);
        for digit in [9, 9, 9] {
            form.digit(digit);
        }
        assert!(form.minutes <= MAX_MINUTES);
        form.focus(Row::Increment);
        form.step(Row::Increment, 100);
        assert_eq!(form.increment, MAX_INCREMENT);
        form.minutes = 0;
        assert_eq!(form.result().unwrap().minutes, 1, "zero minutes means one");
    }

    #[test]
    fn the_flow_goes_bot_color_time_and_back() {
        // Bot → Black → time screen → Esc back to colors → Random → time screen → Enter.
        let mut screen = Fake::new((30, 100)).keys(&[key('1'), key('2'), special(Key::Esc), key('3'), special(Key::Enter)]);
        let setup = choose(&mut screen, Level::Normal, &mut Rng::seeded(4)).unwrap().unwrap();
        assert!(matches!(setup.mode, Mode::Bot(_)));
        assert!(screen.drew("Y O U R   C O L O R"));
        assert!(screen.drew("T I M E   C O N T R O L"));
        // A friend game skips the color screen; Esc on the first screen leaves.
        let mut screen = Fake::new((30, 100)).keys(&[key('2'), special(Key::Enter)]);
        assert_eq!(choose(&mut screen, Level::Normal, &mut Rng::seeded(4)).unwrap().unwrap().mode, Mode::Duel);
        let mut screen = Fake::new((30, 100)).keys(&[special(Key::Esc)]);
        assert_eq!(choose(&mut screen, Level::Normal, &mut Rng::seeded(4)).unwrap(), None);
    }
}
