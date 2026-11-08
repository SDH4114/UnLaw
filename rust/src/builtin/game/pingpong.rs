//! Ping Pong: an old-arcade table tennis game. Two paddles, one square ball, first to 11.
//! One player against a bot (three difficulties) or two players on one keyboard.
//!
//! The ball and paddles move on half rows (drawn with ▀ ▄ █), so motion stays smooth in a
//! terminal. Where the ball meets the paddle sets the return angle, every hit speeds it up,
//! and a paddle moving at the moment of the hit adds spin.
//!
//! Two players need to hold keys at the same time. Terminals with the kitty keyboard protocol
//! (and the desk page) report key releases, so a held key moves a paddle until it is let go;
//! elsewhere a press moves a paddle for a moment and key repeat keeps it going.

use std::io;
use std::sync::atomic::{AtomicUsize, Ordering};

use super::{
    center_block, finish, fits, inputs_until, menu, pause, too_small, wait_for_room, After, Color,
    Input, Item, Key, Level, Played, Rng, Scores, Screen, Style, Ticker,
};

/// Points that win a match.
pub const WIN: u32 = 11;
const MIN_WIDTH: i32 = 56;
const MAX_WIDTH: i32 = 100;
const MIN_HEIGHT: i32 = 14;
const MAX_HEIGHT: i32 = 24;
/// The ball is 2 columns by 1 row: square on screen.
const BALL_W: f64 = 2.0;
const BALL_H: f64 = 1.0;
/// Columns between the side wall and a paddle.
const PADDLE_GAP: f64 = 2.0;
/// Human paddle speed, rows per second.
const PADDLE_SPEED: f64 = 30.0;
/// Without key releases a press moves the paddle this long; key repeats extend it.
const TAP_SECONDS: f64 = 0.12;
const SERVE_SECONDS: f64 = 1.0;
/// Steepest return, in radians on screen (a row counts as two columns).
const MAX_ANGLE: f64 = 1.0;
/// Share of the paddle's speed passed to the ball as spin.
const SPIN: f64 = 0.2;
/// Largest step of the simulation, so a fast ball can never jump over a paddle.
const STEP: f64 = 0.4;

/// The mode chosen last, preselected when a match starts again.
static LAST_MODE: AtomicUsize = AtomicUsize::new(0);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    /// The player is on the left, the bot on the right.
    Bot,
    Duel,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Side {
    Left,
    Right,
}

impl Side {
    fn index(self) -> usize {
        match self {
            Side::Left => 0,
            Side::Right => 1,
        }
    }

    fn other(self) -> Side {
        match self {
            Side::Left => Side::Right,
            Side::Right => Side::Left,
        }
    }

    /// Direction of a ball moving away from this side.
    fn away(self) -> f64 {
        match self {
            Side::Left => 1.0,
            Side::Right => -1.0,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Rules {
    /// Ball speed on screen (columns per second) at the serve, its ceiling and the factor per hit.
    pub start: f64,
    pub max: f64,
    pub accel: f64,
    /// Paddle height in rows.
    pub paddle: f64,
    /// Bot paddle speed (rows per second), its aiming error (rows), its reaction time (seconds),
    /// and whether it aims with the paddle edge for steep returns.
    pub bot_speed: f64,
    pub bot_error: f64,
    pub bot_reaction: f64,
    pub bot_aims: bool,
}

pub fn rules(level: Level) -> Rules {
    match level {
        Level::Easy => Rules {
            start: 28.0,
            max: 56.0,
            accel: 1.04,
            paddle: 5.0,
            bot_speed: 13.0,
            bot_error: 5.0,
            bot_reaction: 0.4,
            bot_aims: false,
        },
        Level::Normal => Rules {
            start: 38.0,
            max: 80.0,
            accel: 1.05,
            paddle: 4.0,
            bot_speed: 21.0,
            bot_error: 3.0,
            bot_reaction: 0.2,
            bot_aims: false,
        },
        Level::Hard => Rules {
            start: 50.0,
            max: 110.0,
            accel: 1.07,
            paddle: 3.0,
            bot_speed: 30.0,
            bot_error: 2.2,
            bot_reaction: 0.08,
            bot_aims: true,
        },
    }
}

/// One direction key of a paddle: held until released, or for a moment after a press.
#[derive(Clone, Copy, Debug, Default)]
struct Hold {
    held: bool,
    until: f64,
    pressed_at: f64,
}

impl Hold {
    fn active(&self, now: f64) -> bool {
        self.held || now < self.until
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Paddle {
    /// Top edge, in rows from the top of the field.
    pub y: f64,
    /// Rows per second of the last move (spin).
    pub velocity: f64,
    up: Hold,
    down: Hold,
    /// Where the pointer wants the paddle's center.
    target: Option<f64>,
}

#[derive(Clone, Copy, Debug)]
struct Bot {
    /// Planned paddle center; `None` drifts back to the middle.
    aim: Option<f64>,
    /// The bot plans its return this many seconds after the ball turned toward it.
    think_at: Option<f64>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Ball {
    /// Top-left corner in columns and rows.
    pub x: f64,
    pub y: f64,
    pub vx: f64,
    pub vy: f64,
    /// Speed on screen, columns per second.
    pub speed: f64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Event {
    Running,
    Point(Side),
    Won(Side),
}

pub struct Game {
    pub rules: Rules,
    pub mode: Mode,
    pub width: f64,
    pub height: f64,
    pub ball: Ball,
    pub paddles: [Paddle; 2],
    pub score: [u32; 2],
    pub rally: u32,
    pub longest: u32,
    /// Seconds left before the ball is served, and who it goes to.
    pub serve_in: f64,
    serve_to: Side,
    /// Key releases are reported: a press holds until its release.
    pub releases: bool,
    bot: Bot,
    time: f64,
}

impl Game {
    pub fn new(level: Level, mode: Mode, width: i32, height: i32, rng: &mut Rng) -> Game {
        let rules = rules(level);
        let (width, height) = (width as f64, height as f64);
        let paddle = Paddle {
            y: (height - rules.paddle) / 2.0,
            velocity: 0.0,
            up: Hold::default(),
            down: Hold::default(),
            target: None,
        };
        let serve_to = if rng.chance(0.5) {
            Side::Left
        } else {
            Side::Right
        };
        let mut game = Game {
            rules,
            mode,
            width,
            height,
            ball: Ball {
                x: 0.0,
                y: 0.0,
                vx: 0.0,
                vy: 0.0,
                speed: rules.start,
            },
            paddles: [paddle; 2],
            score: [0, 0],
            rally: 0,
            longest: 0,
            serve_in: SERVE_SECONDS,
            serve_to,
            releases: false,
            bot: Bot {
                aim: None,
                think_at: None,
            },
            time: 0.0,
        };
        game.center_ball();
        game
    }

    fn center_ball(&mut self) {
        self.ball = Ball {
            x: (self.width - BALL_W) / 2.0,
            y: (self.height - BALL_H) / 2.0,
            vx: 0.0,
            vy: 0.0,
            speed: self.rules.start,
        };
    }

    /// Column of a paddle's face side: the left paddle's right edge, the right paddle's left edge.
    pub fn paddle_x(&self, side: Side) -> f64 {
        match side {
            Side::Left => PADDLE_GAP,
            Side::Right => self.width - PADDLE_GAP - 1.0,
        }
    }

    pub fn bot_side(&self) -> Option<Side> {
        (self.mode == Mode::Bot).then_some(Side::Right)
    }

    /// A direction key went down (`up`: toward the top).
    pub fn press(&mut self, side: Side, up: bool) {
        let now = self.time;
        let releases = self.releases;
        let paddle = &mut self.paddles[side.index()];
        paddle.target = None;
        let (pressed, other) = if up {
            (&mut paddle.up, &mut paddle.down)
        } else {
            (&mut paddle.down, &mut paddle.up)
        };
        if releases {
            pressed.held = true;
        } else {
            pressed.until = now + TAP_SECONDS;
            // Without releases the opposite key cannot be held: a new direction replaces it.
            other.until = 0.0;
        }
        pressed.pressed_at = now;
    }

    pub fn release(&mut self, side: Side, up: bool) {
        let paddle = &mut self.paddles[side.index()];
        let hold = if up { &mut paddle.up } else { &mut paddle.down };
        hold.held = false;
        hold.until = 0.0;
    }

    /// Forget every held key (after a pause, when releases may have been missed).
    pub fn let_go(&mut self) {
        for paddle in &mut self.paddles {
            paddle.up = Hold::default();
            paddle.down = Hold::default();
        }
    }

    /// The pointer moved to row `y` of the field: that paddle follows it.
    pub fn point(&mut self, side: Side, y: f64) {
        self.paddles[side.index()].target = Some(y.clamp(0.0, self.height));
    }

    fn launch(&mut self, rng: &mut Rng) {
        self.center_ball();
        let angle = (rng.below(1001) as f64 / 1000.0 - 0.5) * 0.9;
        // Toward the receiver: moving away from the other side.
        self.aim_ball(self.serve_to.other().away(), angle);
        self.rally = 0;
    }

    /// Set the ball's velocity from a direction (+1 right, -1 left) and an angle on screen.
    fn aim_ball(&mut self, direction: f64, angle: f64) {
        self.ball.vx = direction.signum() * self.ball.speed * angle.cos();
        // A row is two columns tall on screen.
        self.ball.vy = self.ball.speed * angle.sin() / 2.0;
    }

    pub fn update(&mut self, dt: f64, rng: &mut Rng) -> Event {
        self.time += dt;
        self.move_paddles(dt, rng);
        if self.serve_in > 0.0 {
            self.serve_in -= dt;
            if self.serve_in <= 0.0 {
                self.serve_in = 0.0;
                self.launch(rng);
            }
            return Event::Running;
        }
        let distance = (self.ball.vx * dt).abs().max((self.ball.vy * dt).abs());
        let steps = (distance / STEP).ceil().max(1.0) as usize;
        let step = dt / steps as f64;
        for _ in 0..steps {
            if let Some(event) = self.step_ball(step) {
                return event;
            }
        }
        Event::Running
    }

    fn step_ball(&mut self, dt: f64) -> Option<Event> {
        let before = self.ball;
        self.ball.x += self.ball.vx * dt;
        self.ball.y += self.ball.vy * dt;
        let floor = self.height - BALL_H;
        if self.ball.y < 0.0 {
            self.ball.y = -self.ball.y;
            self.ball.vy = self.ball.vy.abs();
        } else if self.ball.y > floor {
            self.ball.y = 2.0 * floor - self.ball.y;
            self.ball.vy = -self.ball.vy.abs();
        }
        // The face of each paddle is a plane the ball crosses at most once per step.
        let left_face = self.paddle_x(Side::Left) + 1.0;
        let right_face = self.paddle_x(Side::Right);
        if self.ball.vx < 0.0
            && before.x >= left_face
            && self.ball.x < left_face
            && self.touches(Side::Left)
        {
            self.ball.x = left_face;
            self.hit(Side::Left);
        } else if self.ball.vx > 0.0
            && before.x + BALL_W <= right_face
            && self.ball.x + BALL_W > right_face
            && self.touches(Side::Right)
        {
            self.ball.x = right_face - BALL_W;
            self.hit(Side::Right);
        }
        if self.ball.x + BALL_W < 0.0 {
            return Some(self.score_point(Side::Right));
        }
        if self.ball.x > self.width {
            return Some(self.score_point(Side::Left));
        }
        None
    }

    fn touches(&self, side: Side) -> bool {
        let paddle = &self.paddles[side.index()];
        self.ball.y < paddle.y + self.rules.paddle && self.ball.y + BALL_H > paddle.y
    }

    fn hit(&mut self, side: Side) {
        let paddle = self.paddles[side.index()];
        let half = self.rules.paddle / 2.0 + BALL_H / 2.0;
        let offset = ((self.ball.y + BALL_H / 2.0 - (paddle.y + self.rules.paddle / 2.0)) / half)
            .clamp(-1.0, 1.0);
        self.ball.speed = (self.ball.speed * self.rules.accel).min(self.rules.max);
        self.aim_ball(side.away(), offset * MAX_ANGLE);
        self.ball.vy += paddle.velocity * SPIN;
        self.rally += 1;
        self.longest = self.longest.max(self.rally);
        self.bot.aim = None;
        self.bot.think_at = None;
    }

    fn score_point(&mut self, winner: Side) -> Event {
        self.score[winner.index()] += 1;
        self.center_ball();
        self.bot = Bot {
            aim: None,
            think_at: None,
        };
        if self.score[winner.index()] >= WIN {
            return Event::Won(winner);
        }
        // The next serve goes to the side that lost the point.
        self.serve_to = winner.other();
        self.serve_in = SERVE_SECONDS;
        Event::Point(winner)
    }

    fn move_paddles(&mut self, dt: f64, rng: &mut Rng) {
        for side in [Side::Left, Side::Right] {
            let wanted = if Some(side) == self.bot_side() {
                self.bot_velocity(rng)
            } else {
                self.human_velocity(side)
            };
            let limit = self.height - self.rules.paddle;
            let paddle = &mut self.paddles[side.index()];
            let y = (paddle.y + wanted * dt).clamp(0.0, limit);
            paddle.velocity = if dt > 0.0 { (y - paddle.y) / dt } else { 0.0 };
            paddle.y = y;
        }
    }

    fn human_velocity(&mut self, side: Side) -> f64 {
        let now = self.time;
        let half = self.rules.paddle / 2.0;
        let paddle = &mut self.paddles[side.index()];
        match (paddle.up.active(now), paddle.down.active(now)) {
            (true, true) => {
                if paddle.up.pressed_at >= paddle.down.pressed_at {
                    -PADDLE_SPEED
                } else {
                    PADDLE_SPEED
                }
            }
            (true, false) => -PADDLE_SPEED,
            (false, true) => PADDLE_SPEED,
            (false, false) => match paddle.target {
                Some(target) => toward(paddle.y + half, target, PADDLE_SPEED),
                None => 0.0,
            },
        }
    }

    /// Where the ball's center will be when it reaches `face_x`, folding in wall bounces.
    pub fn predict(&self, face_x: f64) -> f64 {
        let ball = &self.ball;
        if ball.vx == 0.0 {
            return ball.y + BALL_H / 2.0;
        }
        // Contact happens when the leading edge reaches the face.
        let leading = if ball.vx > 0.0 {
            ball.x + BALL_W
        } else {
            ball.x
        };
        let time = ((face_x - leading) / ball.vx).max(0.0);
        let span = self.height - BALL_H;
        let raw = ball.y + ball.vy * time;
        // Reflect into [0, span]: a triangle wave with period 2 * span.
        let period = 2.0 * span;
        let folded = raw.rem_euclid(period);
        let y = if folded > span {
            period - folded
        } else {
            folded
        };
        y + BALL_H / 2.0
    }

    fn bot_velocity(&mut self, rng: &mut Rng) -> f64 {
        let Some(side) = self.bot_side() else {
            return 0.0;
        };
        let coming = self.serve_in <= 0.0 && self.ball.vx * side.away() < 0.0;
        if coming && self.bot.aim.is_none() {
            match self.bot.think_at {
                None => self.bot.think_at = Some(self.time + self.rules.bot_reaction),
                Some(at) if self.time >= at => {
                    let face = self.paddle_x(side) + if side == Side::Left { 1.0 } else { 0.0 };
                    let error = (rng.below(2001) as f64 / 1000.0 - 1.0) * self.rules.bot_error;
                    // Aiming bots meet the ball off-center for a steeper return.
                    let edge = if self.rules.bot_aims {
                        (rng.below(2001) as f64 / 1000.0 - 1.0) * self.rules.paddle * 0.4
                    } else {
                        0.0
                    };
                    self.bot.aim = Some(self.predict(face) + error - edge);
                }
                Some(_) => {}
            }
        }
        let target = match self.bot.aim {
            Some(aim) if coming => aim,
            _ => self.height / 2.0,
        };
        let center = self.paddles[side.index()].y + self.rules.paddle / 2.0;
        // Drifting back to the middle is unhurried.
        let speed = if coming {
            self.rules.bot_speed
        } else {
            self.rules.bot_speed * 0.5
        };
        toward(center, target, speed)
    }
}

/// Velocity that moves `from` to `to` at `speed`, stopping inside a small dead zone.
fn toward(from: f64, to: f64, speed: f64) -> f64 {
    let gap = to - from;
    if gap.abs() < 0.25 {
        0.0
    } else {
        speed * gap.signum()
    }
}

const DIGITS: [[&str; 5]; 10] = [
    ["111", "101", "101", "101", "111"],
    ["010", "110", "010", "010", "111"],
    ["111", "001", "111", "100", "111"],
    ["111", "001", "111", "001", "111"],
    ["101", "101", "111", "001", "001"],
    ["111", "100", "111", "001", "111"],
    ["111", "100", "111", "101", "111"],
    ["111", "001", "001", "001", "001"],
    ["111", "101", "111", "101", "111"],
    ["111", "101", "111", "001", "111"],
];

/// A picture on half rows: each cell is a top and a bottom half with an optional color.
struct Halves {
    width: usize,
    cells: Vec<Option<Color>>,
}

impl Halves {
    fn new(width: usize, rows: usize) -> Halves {
        Halves {
            width,
            cells: vec![None; width * rows * 2],
        }
    }

    fn fill(&mut self, x: i64, half_row: i64, color: Color) {
        let rows = (self.cells.len() / self.width) as i64;
        if (0..self.width as i64).contains(&x) && (0..rows).contains(&half_row) {
            self.cells[half_row as usize * self.width + x as usize] = Some(color);
        }
    }

    fn rect(&mut self, x: f64, y: f64, width: f64, height: f64, color: Color) {
        let (left, right) = (x.round() as i64, (x + width).round() as i64);
        let (top, bottom) = (
            (y * 2.0).round() as i64,
            ((y + height) * 2.0).round() as i64,
        );
        for half in top..bottom.max(top + 1) {
            for column in left..right.max(left + 1) {
                self.fill(column, half, color);
            }
        }
    }

    fn number(&mut self, value: u32, right: i64, top_half: i64, color: Color) {
        let text = value.to_string();
        let mut x = right - (text.len() as i64 * 8 - 2);
        for digit in text.bytes() {
            for (row, line) in DIGITS[(digit - b'0') as usize].iter().enumerate() {
                for (column, bit) in line.bytes().enumerate() {
                    if bit == b'1' {
                        self.fill(x + column as i64 * 2, top_half + row as i64, color);
                        self.fill(x + column as i64 * 2 + 1, top_half + row as i64, color);
                    }
                }
            }
            x += 8;
        }
    }

    /// Draw row by row, one `put` per run of equal style.
    fn draw(&self, screen: &mut dyn Screen, top: i32, left: i32) {
        let rows = self.cells.len() / self.width / 2;
        for row in 0..rows {
            let mut run = String::new();
            let mut run_style = Style::PLAIN;
            let mut run_start = 0;
            for column in 0..self.width {
                let upper = self.cells[(row * 2) * self.width + column];
                let lower = self.cells[(row * 2 + 1) * self.width + column];
                let (glyph, style) = match (upper, lower) {
                    (None, None) => (' ', Style::PLAIN),
                    (Some(a), Some(b)) if a == b => ('█', Style::fg(a)),
                    (Some(a), None) => ('▀', Style::fg(a)),
                    (None, Some(b)) => ('▄', Style::fg(b)),
                    (Some(a), Some(b)) => ('▀', Style::fg(a).on(b)),
                };
                if style != run_style && !run.is_empty() {
                    screen.put(top + row as i32, left + run_start as i32, &run, run_style);
                    run.clear();
                }
                if run.is_empty() {
                    run_start = column;
                    run_style = style;
                }
                run.push(glyph);
            }
            if !run.is_empty() {
                screen.put(top + row as i32, left + run_start as i32, &run, run_style);
            }
        }
    }
}

fn names(mode: Mode) -> [&'static str; 2] {
    match mode {
        Mode::Bot => ["YOU", "BOT"],
        Mode::Duel => ["LEFT", "RIGHT"],
    }
}

fn draw(
    screen: &mut dyn Screen,
    game: &Game,
    top: i32,
    left: i32,
    level: Level,
    best: Option<u64>,
) {
    screen.clear();
    let (width, height) = (game.width as i32, game.height as i32);
    let mode = match game.mode {
        Mode::Bot => "vs bot",
        Mode::Duel => "2 players",
    };
    let mut stats = vec![
        ("RALLY", game.rally.to_string()),
        ("FIRST TO", WIN.to_string()),
    ];
    if game.mode == Mode::Bot {
        stats.push((
            "BEST",
            best.map(|best| format!("+{best}"))
                .unwrap_or_else(|| "—".into()),
        ));
    }
    screen.hud(
        top - 2,
        left - 1,
        width + 2,
        &format!("PING PONG · {} · {mode}", level.name()),
        &stats,
    );
    screen.frame_box(
        top - 1,
        left - 1,
        height + 2,
        width + 2,
        Style::fg(Color::Gray),
    );
    let mut halves = Halves::new(width as usize, height as usize);
    let middle = width as i64 / 2;
    halves.number(game.score[0], middle - 5, 2, Color::Gray);
    halves.number(
        game.score[1],
        middle + 5 + 6 + if game.score[1] >= 10 { 8 } else { 0 },
        2,
        Color::Gray,
    );
    for half in 0..height as i64 * 2 {
        if half % 4 < 2 {
            halves.fill(middle, half, Color::Gray);
        }
    }
    let colors = [
        Color::Cyan,
        if game.mode == Mode::Bot {
            Color::Red
        } else {
            Color::Magenta
        },
    ];
    for side in [Side::Left, Side::Right] {
        halves.rect(
            game.paddle_x(side),
            game.paddles[side.index()].y,
            1.0,
            game.rules.paddle,
            colors[side.index()],
        );
    }
    let blink = game.serve_in > 0.0 && (game.serve_in * 4.0) as i64 % 2 == 1;
    if !blink {
        halves.rect(game.ball.x, game.ball.y, BALL_W, BALL_H, Color::White);
    }
    halves.draw(screen, top, left);
    let [left_name, right_name] = names(game.mode);
    screen.put(top, left + 1, left_name, Style::fg(colors[0]).bold());
    screen.put(
        top,
        left + width - 1 - right_name.len() as i32,
        right_name,
        Style::fg(colors[1]).bold(),
    );
    if game.serve_in > 0.0 && game.score == [0, 0] {
        screen.centered(
            top + height - 2,
            &format!("first to {WIN} · get ready"),
            Style::fg(Color::Yellow).bold(),
        );
    }
    screen.controls(match game.mode {
        Mode::Bot => "W/S or ↑/↓ or mouse move · P pause · Esc quit",
        Mode::Duel => "left W/S · right ↑/↓ · mouse moves the nearer paddle · P pause · Esc quit",
    });
}

fn choose_mode(screen: &mut dyn Screen, level: Level) -> io::Result<Option<Mode>> {
    let items = [
        Item {
            label: "1 player".into(),
            detail: "you against the bot".into(),
            note: String::new(),
        },
        Item {
            label: "2 players".into(),
            detail: "left W/S, right ↑/↓, one keyboard".into(),
            note: String::new(),
        },
    ];
    let subtitle = format!("first to {WIN} · {}", level.name());
    let footer = "↑/↓ or mouse select · Enter / click start · 1-2 jump · Esc back";
    let chosen = menu(
        screen,
        "P I N G   P O N G",
        &subtitle,
        &items,
        LAST_MODE.load(Ordering::Relaxed).min(1),
        footer,
    )?;
    if let Some(index) = chosen {
        LAST_MODE.store(index, Ordering::Relaxed);
    }
    Ok(chosen.map(|index| if index == 0 { Mode::Bot } else { Mode::Duel }))
}

/// Which side a key moves, and whether it moves up.
fn steer(mode: Mode, key: Key) -> Option<(Side, bool)> {
    let side_of_arrows = if mode == Mode::Duel {
        Side::Right
    } else {
        Side::Left
    };
    match key {
        Key::Char('w' | 'W') => Some((Side::Left, true)),
        Key::Char('s' | 'S') => Some((Side::Left, false)),
        Key::Up => Some((side_of_arrows, true)),
        Key::Down => Some((side_of_arrows, false)),
        _ => None,
    }
}

pub fn play(
    screen: &mut dyn Screen,
    level: Level,
    rng: &mut Rng,
    best: Option<u64>,
    scores: Option<&mut Scores>,
) -> io::Result<Played> {
    let (height, width) = screen.size();
    let field_height = (height - 4).min(MAX_HEIGHT);
    let field_width = (width - 2).min(MAX_WIDTH);
    if field_height < MIN_HEIGHT || field_width < MIN_WIDTH {
        return too_small(screen, MIN_WIDTH + 2, MIN_HEIGHT + 4);
    }
    let Some(mode) = choose_mode(screen, level)? else {
        return Ok(Played {
            score: None,
            after: After::Leave,
        });
    };
    let (need_width, need_height) = (field_width + 2, field_height + 4);
    let mut game = Game::new(level, mode, field_width, field_height, rng);
    game.releases = screen.set_releases(true);
    let mut last = screen.now();
    let mut ticker = Ticker::new(last);
    loop {
        if !fits(screen, need_width, need_height) {
            screen.set_releases(false);
            let room = wait_for_room(screen, need_width, need_height)?;
            game.releases = screen.set_releases(room);
            if !room {
                return Ok(Played {
                    score: None,
                    after: After::Leave,
                });
            }
            game.let_go();
            last = screen.now();
            ticker.reset(last);
        }
        let (block_top, left) = center_block(screen.size(), field_height + 2, field_width + 2);
        let (top, left) = (block_top + 1, left + 1);
        draw(screen, &game, top, left, level, best);
        screen.present()?;
        let deadline = ticker.deadline(screen.now());
        for input in inputs_until(screen, deadline)? {
            match input {
                Input::Key(key) if steer(mode, key).is_some() => {
                    let (side, up) = steer(mode, key).expect("checked");
                    game.press(side, up);
                }
                Input::Release(key) => {
                    if let Some((side, up)) = steer(mode, key) {
                        game.release(side, up);
                    }
                }
                Input::Hover { y, x } | Input::Click { y, x, .. } => {
                    let side = if mode == Mode::Duel && x >= left + field_width / 2 {
                        Side::Right
                    } else {
                        Side::Left
                    };
                    game.point(side, (y - top) as f64 + 0.5);
                }
                input if input.is_pause() => {
                    screen.set_releases(false);
                    if pause(screen)? {
                        return Ok(Played {
                            score: None,
                            after: After::Leave,
                        });
                    }
                    game.releases = screen.set_releases(true);
                    game.let_go();
                    last = screen.now();
                    ticker.reset(last);
                }
                input if input.is_leave() => {
                    screen.set_releases(false);
                    return Ok(Played {
                        score: None,
                        after: After::Leave,
                    });
                }
                _ => {}
            }
        }
        let now = screen.now();
        let event = game.update((now - last).min(0.25), rng);
        last = now;
        if let Event::Won(winner) = event {
            draw(screen, &game, top, left, level, best);
            screen.set_releases(false);
            let [left_name, right_name] = names(mode);
            let title = match (mode, winner) {
                (Mode::Bot, Side::Left) => "YOU WIN".to_string(),
                (Mode::Bot, Side::Right) => "THE BOT WINS".to_string(),
                (Mode::Duel, side) => format!(
                    "{} WINS",
                    if side == Side::Left {
                        left_name
                    } else {
                        right_name
                    }
                ),
            };
            let details = [format!(
                "{left_name} {} : {} {right_name} · longest rally {}",
                game.score[0], game.score[1], game.longest
            )];
            // Against the bot the record is the winning margin; a loss or a duel records nothing.
            let margin = (mode == Mode::Bot && winner == Side::Left)
                .then(|| u64::from(game.score[0] - game.score[1]));
            let after = finish(
                screen,
                &title,
                &details,
                margin.map(|margin| (margin, best, "pingpong")),
                scores.map(|scores| (scores, level)),
            )?;
            return Ok(Played {
                score: margin,
                after,
            });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::super::testing::*;
    use super::super::FRAME;
    use super::*;

    fn game(level: Level, mode: Mode) -> Game {
        let mut game = Game::new(level, mode, 80, 20, &mut Rng::seeded(1));
        game.serve_in = 0.0;
        game
    }

    fn run(game: &mut Game, seconds: f64, rng: &mut Rng) -> Event {
        for _ in 0..(seconds / FRAME).round() as usize {
            let event = game.update(FRAME, rng);
            if event != Event::Running {
                return event;
            }
        }
        Event::Running
    }

    fn serve_at(game: &mut Game, y: f64, vx: f64, vy: f64) {
        game.ball = Ball {
            x: game.width / 2.0,
            y,
            vx,
            vy,
            speed: vx.abs(),
        };
        game.serve_in = 0.0;
    }

    #[test]
    fn the_ball_bounces_off_the_walls() {
        let mut game = game(Level::Normal, Mode::Duel);
        serve_at(&mut game, 1.0, 1.0, -20.0);
        game.update(0.2, &mut Rng::seeded(1));
        assert!(game.ball.vy > 0.0, "the top wall turns the ball down");
        assert!(game.ball.y >= 0.0);
        let y = game.height - 2.0;
        serve_at(&mut game, y, 1.0, 20.0);
        game.update(0.2, &mut Rng::seeded(1));
        assert!(game.ball.vy < 0.0, "the bottom wall turns the ball up");
        assert!(game.ball.y <= game.height - BALL_H);
    }

    #[test]
    fn a_paddle_returns_the_ball_and_its_edge_gives_a_steeper_angle() {
        let mut center = game(Level::Normal, Mode::Duel);
        let paddle_center = center.paddles[0].y + center.rules.paddle / 2.0;
        serve_at(&mut center, paddle_center - BALL_H / 2.0, -40.0, 0.0);
        assert_eq!(run(&mut center, 1.0, &mut Rng::seeded(1)), Event::Running);
        assert!(center.ball.vx > 0.0, "returned to the right");
        assert!(center.ball.vy.abs() < 1.0, "a center hit goes straight");
        assert_eq!(center.rally, 1);
        let mut edge = game(Level::Normal, Mode::Duel);
        let y = edge.paddles[0].y - 0.6;
        serve_at(&mut edge, y, -40.0, 0.0);
        run(&mut edge, 1.0, &mut Rng::seeded(1));
        assert!(edge.ball.vx > 0.0);
        assert!(
            edge.ball.vy < -5.0,
            "a top-edge hit goes up steeply: {}",
            edge.ball.vy
        );
        assert!(edge.ball.speed > 40.0, "every hit speeds the ball up");
    }

    #[test]
    fn the_fastest_ball_never_passes_through_a_paddle() {
        for level in [Level::Easy, Level::Normal, Level::Hard] {
            let mut game = game(level, Mode::Duel);
            let max = game.rules.max;
            let y = game.paddles[1].y + game.rules.paddle / 2.0 - BALL_H / 2.0;
            serve_at(&mut game, y, max, 0.0);
            game.ball.speed = max;
            // 10 columns before the paddle: one huge frame (max/4 columns) crosses its face,
            // and the sub-steps must still meet it.
            game.ball.x = game.paddle_x(Side::Right) - BALL_W - 10.0;
            assert!(max * 0.25 > 10.0 + 1.0 + BALL_W);
            game.update(0.25, &mut Rng::seeded(1));
            assert!(
                game.ball.vx < 0.0,
                "{level:?}: the right paddle returned it"
            );
        }
    }

    #[test]
    fn a_miss_scores_for_the_other_side_and_the_next_serve_goes_to_the_loser() {
        let mut game = game(Level::Normal, Mode::Duel);
        game.paddles[0].y = 0.0;
        let y = game.height - 2.0;
        serve_at(&mut game, y, -40.0, 0.0);
        assert_eq!(
            run(&mut game, 2.0, &mut Rng::seeded(1)),
            Event::Point(Side::Right)
        );
        assert_eq!(game.score, [0, 1]);
        assert!(game.serve_in > 0.0);
        run(&mut game, SERVE_SECONDS + FRAME, &mut Rng::seeded(1));
        assert!(
            game.ball.vx < 0.0,
            "served toward the left, who lost the point"
        );
    }

    #[test]
    fn eleven_points_win_the_match() {
        let mut game = game(Level::Normal, Mode::Duel);
        game.score = [10, 3];
        game.paddles[1].y = 0.0;
        let y = game.height - 2.0;
        serve_at(&mut game, y, 40.0, 0.0);
        assert_eq!(
            run(&mut game, 2.0, &mut Rng::seeded(1)),
            Event::Won(Side::Left)
        );
        assert_eq!(game.score, [11, 3]);
    }

    #[test]
    fn held_keys_move_until_released_and_taps_move_briefly() {
        let mut rng = Rng::seeded(1);
        let mut held = game(Level::Normal, Mode::Duel);
        held.serve_in = 100.0;
        held.releases = true;
        let start = held.paddles[0].y;
        held.press(Side::Left, false);
        held.update(0.2, &mut rng);
        assert!(held.paddles[0].y > start + 5.0, "a held key keeps moving");
        held.release(Side::Left, false);
        let stopped = held.paddles[0].y;
        held.update(0.2, &mut rng);
        assert_eq!(held.paddles[0].y, stopped, "a release stops it");
        // Both players at once: one paddle up, the other down.
        held.press(Side::Left, true);
        held.press(Side::Right, false);
        let (left, right) = (held.paddles[0].y, held.paddles[1].y);
        held.update(0.1, &mut rng);
        assert!(held.paddles[0].y < left && held.paddles[1].y > right);

        let mut tapped = game(Level::Normal, Mode::Duel);
        tapped.serve_in = 100.0;
        let start = tapped.paddles[0].y;
        tapped.press(Side::Left, false);
        for _ in 0..30 {
            tapped.update(FRAME, &mut rng);
        }
        let moved = tapped.paddles[0].y - start;
        assert!(
            moved > 2.0 && moved < 5.0,
            "a tap without releases moves a little: {moved}"
        );
    }

    #[test]
    fn the_pointer_steers_a_paddle() {
        let mut game = game(Level::Normal, Mode::Bot);
        game.serve_in = 100.0;
        game.point(Side::Left, 2.0);
        game.update(1.0, &mut Rng::seeded(1));
        let center = game.paddles[0].y + game.rules.paddle / 2.0;
        assert!((center - 2.0).abs() < 1.0, "paddle center {center}");
    }

    #[test]
    fn prediction_folds_wall_bounces() {
        let mut game = game(Level::Normal, Mode::Bot);
        serve_at(&mut game, 0.0, 40.0, 40.0);
        game.ball.x = 0.0;
        let face = game.paddle_x(Side::Right);
        let predicted = game.predict(face);
        assert!((BALL_H / 2.0..=game.height - BALL_H / 2.0).contains(&predicted));
        let mut copy = Game::new(Level::Normal, Mode::Duel, 80, 20, &mut Rng::seeded(1));
        copy.ball = game.ball;
        copy.serve_in = 0.0;
        copy.paddles[1].y = -100.0;
        while copy.ball.x + BALL_W < face {
            copy.step_ball(0.001);
        }
        assert!(
            (copy.ball.y + BALL_H / 2.0 - predicted).abs() < 0.2,
            "{} vs {predicted}",
            copy.ball.y
        );
    }

    /// The right bot at `level` against a scripted left player of fixed, middling skill:
    /// (points the bot won, points it lost) in ten minutes of play.
    fn bot_points(level: Level, seed: u64) -> (u32, u32) {
        let mut rng = Rng::seeded(seed);
        let mut player_rng = Rng::seeded(seed + 1000);
        let mut game = Game::new(level, Mode::Bot, 80, 20, &mut rng);
        let mut wins = 0;
        let mut lost = 0;
        let mut plan: Option<f64> = None;
        for _ in 0..(600.0 / FRAME) as usize {
            let coming = game.serve_in <= 0.0 && game.ball.vx < 0.0;
            if coming && plan.is_none() {
                let error = (player_rng.below(2001) as f64 / 1000.0 - 1.0) * 3.0;
                plan = Some(game.predict(game.paddle_x(Side::Left) + 1.0) + error);
            }
            if !coming {
                plan = None;
            }
            let center = game.paddles[0].y + game.rules.paddle / 2.0;
            let aim = plan.unwrap_or(game.height / 2.0);
            game.paddles[0].y = (game.paddles[0].y + toward(center, aim, 18.0) * FRAME)
                .clamp(0.0, game.height - game.rules.paddle);
            match game.update(FRAME, &mut rng) {
                Event::Point(Side::Right) | Event::Won(Side::Right) => wins += 1,
                Event::Point(Side::Left) | Event::Won(Side::Left) => lost += 1,
                _ => {}
            }
            if game.score.iter().any(|&points| points >= WIN) {
                // A new match: the finished one leaves the ball at rest.
                game.score = [0, 0];
                game.serve_in = SERVE_SECONDS;
            }
        }
        (wins, lost)
    }

    #[test]
    fn harder_bots_win_more_points_against_the_same_player() {
        let share = |level: Level| {
            let (won, lost) = (0..3)
                .map(|seed| bot_points(level, seed))
                .fold((0, 0), |(w, l), (a, b)| (w + a, l + b));
            assert!(
                won + lost > 30,
                "{level:?}: too few points to judge ({won}:{lost})"
            );
            f64::from(won) / f64::from(won + lost)
        };
        let (easy, normal, hard) = (share(Level::Easy), share(Level::Normal), share(Level::Hard));
        assert!(easy < 0.25, "easy should lose most points: {easy:.2}");
        assert!(
            easy < normal && normal < hard,
            "bot share of points: easy {easy:.2}, normal {normal:.2}, hard {hard:.2}"
        );
        assert!(hard > 0.5, "hard should beat a decent player: {hard:.2}");
    }

    #[test]
    fn the_hard_bot_is_never_faster_than_a_person() {
        // Hard stays beatable: steep returns can still outrun its paddle.
        for level in [Level::Easy, Level::Normal, Level::Hard] {
            assert!(rules(level).bot_speed <= PADDLE_SPEED);
        }
    }

    #[test]
    fn mode_menu_then_a_two_player_match_draws_and_leaves() {
        let mut screen = Fake::new((30, 100))
            .keys(&[key('2')])
            .idle(40);
        let played = play(&mut screen, Level::Normal, &mut Rng::seeded(2), None, None).unwrap();
        assert_eq!(played.after, After::Leave);
        assert!(screen.drew("PING PONG"));
        assert!(screen.drew("LEFT"));
        assert!(screen.drew("RIGHT"));
        assert!(screen.drew("left W/S"));
    }

    #[test]
    fn a_small_terminal_is_explained() {
        let mut screen = Fake::new((10, 40)).keys(&[key('q')]);
        let played = play(&mut screen, Level::Normal, &mut Rng::seeded(2), None, None).unwrap();
        assert_eq!(played.after, After::Leave);
    }

    #[test]
    fn releases_are_on_during_a_match_and_off_before_leaving() {
        let mut screen = Fake::new((30, 100)).keys(&[key('1'), key('s')]).idle(5);
        screen.releases = true;
        play(&mut screen, Level::Easy, &mut Rng::seeded(2), None, None).unwrap();
        assert!(screen.drew("YOU"));
        assert_eq!(screen.release_requests.first(), Some(&true));
        assert_eq!(screen.release_requests.last(), Some(&false), "menus must not get releases");
    }
}
