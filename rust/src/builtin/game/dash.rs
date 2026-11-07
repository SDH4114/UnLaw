//! Dash: an endless runner in the spirit of the offline browser dinosaur game,
//! with its own character (a fox) and art. The fox runs on its own, the world
//! scrolls by and keeps accelerating; jump over cacti and low birds, duck under
//! middle ones, run under high ones. A jump has a fixed height (a terminal
//! cannot tell how long a key is held); Down in the air drops fast, and a duck
//! lasts a third of a second that key repeats keep extending.
//!
//! Space is measured in terminal columns and rows. The gap between obstacles
//! always grows with the speed, so a perfect player can never be cornered
//! (`a_perfect_player_survives_every_difficulty...` checks it with a bot).

use std::io;

use super::{center_block, finish, fits, inputs_until, pause, too_small, wait_for_room, After, Button, Color, Input, Key, Level, Played, Rng, Scores, Screen, Style, Ticker};

/// Left edge and width of the fox, in columns.
const FOX_X: f64 = 6.0;
const FOX_W: f64 = 6.0;
const STAND_H: f64 = 3.0;
const DUCK_H: f64 = 2.0;
/// Jump: fixed apex (rows) and air time (seconds) fix gravity and take-off speed.
const APEX: f64 = 6.0;
const AIR_SECONDS: f64 = 0.72;
const GRAVITY: f64 = 8.0 * APEX / (AIR_SECONDS * AIR_SECONDS);
const JUMP_SPEED: f64 = 4.0 * APEX / AIR_SECONDS;
/// Down in the air: gravity multiplier and the minimum downward speed.
const DROP_GRAVITY: f64 = 3.0;
const DROP_SPEED: f64 = 12.0;
const DUCK_SECONDS: f64 = 0.35;
/// Hitboxes are the sprites shrunk by this much on every side (forgiving).
const SHRINK_X: f64 = 0.5;
const SHRINK_Y: f64 = 0.3;
const CLOUD_PARALLAX: f64 = 0.2;
/// 10 points a second at the normal start speed of 32 columns a second.
const POINTS_PER_COLUMN: f64 = 10.0 / 32.0;
const FLASH_SECONDS: f64 = 0.8;
const NIGHT_FROM: u64 = 700;
const NIGHT_UNTIL: u64 = 950;
const DAY_LENGTH: u64 = 1000;
const MIN_SKY: i32 = 10;
const MAX_SKY: i32 = 13;
const MAX_WIDTH: i32 = 100;

pub struct Rules {
    /// Speeds in columns per second and the acceleration per second.
    pub start: f64,
    pub max: f64,
    pub accel: f64,
    /// Smallest gap between obstacles: `gap_per_speed * speed + gap_flat`; the real gap adds up to `jitter` times that.
    pub gap_per_speed: f64,
    pub gap_flat: f64,
    pub jitter: f64,
    pub min_group: usize,
    pub max_group: usize,
    /// Fliers appear from this score on, with this chance per obstacle.
    pub bird_after: u64,
    pub bird_chance: f64,
    pub high_birds: bool,
    /// Groups mix cactus sizes, and a cactus may be followed at the minimum gap by a middle flier.
    pub mixed: bool,
    pub combo_chance: f64,
}

pub fn rules(level: Level) -> Rules {
    match level {
        Level::Easy => Rules {
            start: 26.0,
            max: 48.0,
            accel: 0.25,
            gap_per_speed: 0.7,
            gap_flat: 14.0,
            jitter: 1.0,
            min_group: 1,
            max_group: 2,
            bird_after: 400,
            bird_chance: 0.2,
            high_birds: false,
            mixed: false,
            combo_chance: 0.0,
        },
        Level::Normal => Rules {
            start: 32.0,
            max: 62.0,
            accel: 0.4,
            gap_per_speed: 0.5,
            gap_flat: 10.0,
            jitter: 0.9,
            min_group: 1,
            max_group: 3,
            bird_after: 250,
            bird_chance: 0.3,
            high_birds: true,
            mixed: false,
            combo_chance: 0.0,
        },
        Level::Hard => Rules {
            start: 42.0,
            max: 84.0,
            accel: 0.7,
            gap_per_speed: 0.56,
            gap_flat: 6.0,
            jitter: 0.5,
            min_group: 2,
            max_group: 3,
            bird_after: 0,
            bird_chance: 0.4,
            high_birds: true,
            mixed: true,
            combo_chance: 0.25,
        },
    }
}

/// Height of a flier: low ones must be jumped, middle ones jumped or ducked under, high ones run under.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Lane {
    Low,
    Mid,
    High,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    Small,
    Large,
    Wide,
    Bird(Lane),
}

impl Kind {
    /// Width and height in cells.
    fn size(self) -> (f64, f64) {
        match self {
            Kind::Small => (3.0, 2.0),
            Kind::Large => (3.0, 4.0),
            Kind::Wide => (5.0, 3.0),
            Kind::Bird(_) => (5.0, 2.0),
        }
    }

    /// Height of the bottom edge above the ground, in rows.
    fn lift(self) -> f64 {
        match self {
            Kind::Bird(Lane::Mid) => 2.0,
            Kind::Bird(Lane::High) => 4.0,
            _ => 0.0,
        }
    }

    /// Top row first; `frame` selects the wing position of birds.
    fn sprite(self, frame: usize) -> &'static [&'static str] {
        match (self, frame % 2) {
            (Kind::Small, _) => &["▗█▖", "▝█▘"],
            (Kind::Large, _) => &["▗█▖", "▟█▙", "▝█▘", " █ "],
            (Kind::Wide, _) => &[" ▗█▖ ", "▐▐█▌▌", " ▝█▘ "],
            (Kind::Bird(_), 0) => &["╲ ▄ ╱", "◀████"],
            (Kind::Bird(_), _) => &["╱ ▄ ╲", "◀████"],
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Obstacle {
    pub kind: Kind,
    pub x: f64,
}

impl Obstacle {
    fn size(&self) -> (f64, f64) {
        self.kind.size()
    }

    fn y(&self) -> f64 {
        self.kind.lift()
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Event {
    Running,
    Died,
}

pub struct Dash {
    pub rules: Rules,
    /// Width of the field in columns and its height above the ground in rows.
    pub width: f64,
    pub sky: i32,
    pub started: bool,
    pub dead: bool,
    pub speed: f64,
    /// Points from distance (shown rounded down).
    pub distance_score: f64,
    pub fox_y: f64,
    pub fox_vy: f64,
    fast_drop: bool,
    duck_left: f64,
    /// Steps taken, for the leg animation.
    steps: f64,
    pub time: f64,
    pub flash: f64,
    next_flash: u64,
    pub obstacles: Vec<Obstacle>,
    /// Cloud x (columns, may be fractional) and row below the top of the sky.
    pub clouds: Vec<(f64, i32)>,
    cloud_wait: f64,
    /// Empty columns between the last obstacle's right edge and the field's right edge.
    clear_space: f64,
    next_gap: f64,
    combo: bool,
    pub ground_offset: f64,
}

impl Dash {
    pub fn new(level: Level, width: i32, sky: i32) -> Dash {
        let rules = rules(level);
        let width = width as f64;
        Dash {
            speed: rules.start,
            rules,
            width,
            sky,
            started: false,
            dead: false,
            distance_score: 0.0,
            fox_y: 0.0,
            fox_vy: 0.0,
            fast_drop: false,
            duck_left: 0.0,
            steps: 0.0,
            time: 0.0,
            flash: 0.0,
            next_flash: 100,
            obstacles: Vec::new(),
            clouds: vec![(width * 0.3, 1), (width * 0.75, 3)],
            cloud_wait: 0.0,
            clear_space: 0.0,
            next_gap: width * 0.6,
            combo: false,
            ground_offset: 0.0,
        }
    }

    pub fn score(&self) -> u64 {
        self.distance_score as u64
    }

    /// Night falls at 700 points for 250 points, then every 1000 points again.
    pub fn night(&self) -> bool {
        (NIGHT_FROM..NIGHT_UNTIL).contains(&(self.score() % DAY_LENGTH))
    }

    pub fn on_ground(&self) -> bool {
        self.fox_y <= 0.0 && self.fox_vy <= 0.0
    }

    pub fn ducking(&self) -> bool {
        self.on_ground() && self.duck_left > 0.0
    }

    pub fn leg_frame(&self) -> usize {
        self.steps as usize % 2
    }

    /// Jump (the first jump also starts the run); ignored in the air.
    pub fn jump(&mut self) {
        if self.dead {
            return;
        }
        self.started = true;
        if self.on_ground() {
            self.fox_vy = JUMP_SPEED;
            self.fox_y = 0.0001;
            self.duck_left = 0.0;
        }
    }

    /// Duck on the ground, drop fast in the air. Key repeats keep it going.
    pub fn duck(&mut self) {
        if self.dead || !self.started {
            return;
        }
        if !self.on_ground() {
            self.fast_drop = true;
            self.fox_vy = self.fox_vy.min(-DROP_SPEED);
        }
        self.duck_left = DUCK_SECONDS;
    }

    /// Does the fox touch an obstacle? Both hitboxes are shrunk, so near misses pass.
    pub fn hits(&self) -> bool {
        let height = if self.ducking() { DUCK_H } else { STAND_H };
        let (fx0, fx1) = (FOX_X + SHRINK_X, FOX_X + FOX_W - SHRINK_X);
        let (fy0, fy1) = (self.fox_y + SHRINK_Y, self.fox_y + height - SHRINK_Y);
        self.obstacles.iter().any(|obstacle| {
            let (width, tall) = obstacle.size();
            let (x0, x1) = (obstacle.x + SHRINK_X, obstacle.x + width - SHRINK_X);
            let (y0, y1) = (obstacle.y() + SHRINK_Y, obstacle.y() + tall - SHRINK_Y);
            fx0 < x1 && x0 < fx1 && fy0 < y1 && y0 < fy1
        })
    }

    pub fn update(&mut self, dt: f64, rng: &mut Rng) -> Event {
        if !self.started || self.dead {
            return Event::Running;
        }
        self.time += dt;
        self.speed = (self.speed + self.rules.accel * dt).min(self.rules.max);
        let travel = self.speed * dt;
        self.ground_offset += travel;
        self.steps += travel / 4.0;
        self.distance_score += travel * POINTS_PER_COLUMN;
        while self.score() >= self.next_flash {
            self.flash = FLASH_SECONDS;
            self.next_flash += 100;
        }
        self.flash = (self.flash - dt).max(0.0);
        self.duck_left = (self.duck_left - dt).max(0.0);
        if !self.on_ground() {
            let gravity = if self.fast_drop { GRAVITY * DROP_GRAVITY } else { GRAVITY };
            self.fox_vy -= gravity * dt;
            self.fox_y += self.fox_vy * dt;
            if self.fox_y <= 0.0 {
                self.fox_y = 0.0;
                self.fox_vy = 0.0;
                self.fast_drop = false;
            }
        }
        for obstacle in &mut self.obstacles {
            obstacle.x -= travel;
        }
        self.obstacles.retain(|obstacle| obstacle.x + obstacle.size().0 > -1.0);
        self.clear_space += travel;
        if self.clear_space >= self.next_gap {
            self.spawn(rng);
        }
        self.move_clouds(travel, rng);
        if self.hits() {
            self.dead = true;
            return Event::Died;
        }
        Event::Running
    }

    fn min_gap(&self) -> f64 {
        self.rules.gap_per_speed * self.speed + self.rules.gap_flat
    }

    /// How many cacti may stand together: larger groups come as the speed rises.
    fn group_cap(&self) -> usize {
        let progress = (self.speed - self.rules.start) / (self.rules.max - self.rules.start);
        let cap = if progress < 0.25 { 1 } else if progress < 0.5 { 2 } else { 3 };
        cap.max(self.rules.min_group).min(self.rules.max_group)
    }

    fn spawn(&mut self, rng: &mut Rng) {
        // Place it exactly `next_gap` behind the previous obstacle, even if a frame overshot.
        let mut x = self.width - self.clear_space + self.next_gap;
        let bird = self.score() >= self.rules.bird_after && (self.combo || rng.chance(self.rules.bird_chance));
        if bird {
            let lane = if self.combo {
                Lane::Mid
            } else {
                match rng.below(if self.rules.high_birds { 3 } else { 2 }) {
                    0 => Lane::Low,
                    1 => Lane::Mid,
                    _ => Lane::High,
                }
            };
            self.obstacles.push(Obstacle { kind: Kind::Bird(lane), x });
            x += Kind::Bird(lane).size().0;
            self.combo = false;
        } else {
            let pick = |rng: &mut Rng| [Kind::Small, Kind::Large, Kind::Wide][rng.below(3)];
            let count = 1 + rng.below(self.group_cap());
            let mut kind = pick(rng);
            for _ in 0..count {
                if self.rules.mixed {
                    kind = pick(rng);
                }
                self.obstacles.push(Obstacle { kind, x });
                x += kind.size().0 + 1.0;
            }
            x -= 1.0;
            self.combo = self.rules.mixed && self.score() >= self.rules.bird_after && rng.chance(self.rules.combo_chance);
        }
        self.clear_space = self.width - x;
        let jitter = if self.combo { 0.0 } else { self.rules.jitter * rng.below(1000) as f64 / 1000.0 };
        self.next_gap = self.min_gap() * (1.0 + jitter);
    }

    fn move_clouds(&mut self, travel: f64, rng: &mut Rng) {
        for cloud in &mut self.clouds {
            cloud.0 -= travel * CLOUD_PARALLAX;
        }
        self.clouds.retain(|cloud| cloud.0 > -10.0);
        self.cloud_wait -= travel * CLOUD_PARALLAX;
        if self.cloud_wait <= 0.0 && self.clouds.iter().all(|cloud| cloud.0 < self.width - 12.0) {
            self.clouds.push((self.width, rng.below(((self.sky - 6).max(1)) as usize) as i32));
            self.cloud_wait = 14.0 + rng.below(30) as f64;
        }
    }
}

struct Layout {
    left: i32,
    /// First screen row of the sky, just inside the frame.
    sky_top: i32,
}

impl Layout {
    fn ground(&self, dash: &Dash) -> i32 {
        self.sky_top + dash.sky
    }
}

/// Draw sprite rows clipped to the field; spaces stay transparent.
fn blit(screen: &mut dyn Screen, rows: &[&str], top: i32, x: i32, layout: &Layout, width: i32, style: Style) {
    for (dy, row) in rows.iter().enumerate() {
        let mut run = String::new();
        let mut start = 0;
        let flush = |screen: &mut dyn Screen, run: &mut String, start: i32| {
            if !run.is_empty() {
                screen.put(top + dy as i32, layout.left + start, run, style);
                run.clear();
            }
        };
        for (index, ch) in row.chars().enumerate() {
            let column = x + index as i32;
            if ch != ' ' && (0..width).contains(&column) {
                if run.is_empty() {
                    start = column;
                }
                run.push(ch);
            } else {
                flush(screen, &mut run, start);
            }
        }
        flush(screen, &mut run, start);
    }
}

fn fox_sprite(dash: &Dash) -> &'static [&'static str] {
    if dash.dead {
        &["  ▲▲  ", "▄▆██✕▶", "  ▚▞  "]
    } else if dash.ducking() {
        if dash.leg_frame() == 0 { &["▄▆█▜█▶", " ▌▐ ▌ "] } else { &["▄▆█▜█▶", " ▐▌ ▐ "] }
    } else if !dash.on_ground() {
        &["  ▲▲  ", "▄▆███▶", "  ▐▌  "]
    } else if dash.leg_frame() == 0 {
        &["  ▲▲  ", "▄▆███▶", "  ▌ ▐ "]
    } else {
        &["  ▲▲  ", "▄▆███▶", "  ▐▌  "]
    }
}

fn speck(column: i64, row: i64) -> char {
    let hash = ((column.wrapping_mul(2_654_435_761) ^ row.wrapping_mul(40_503)) as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15) >> 40;
    match (row, hash % 19) {
        (1, 0) => '.',
        (1, 1) => '-',
        (2, 0) => '·',
        (2, 1) => '.',
        _ => ' ',
    }
}

fn draw(screen: &mut dyn Screen, dash: &Dash, layout: &Layout, level: Level, best: Option<u64>) {
    screen.clear();
    let width = dash.width as i32;
    let night = dash.night();
    let tone = |style: Style| if night { style.on(Color::DarkBlue) } else { style };
    let stats = [
        ("SPEED", format!("{:.1}x", dash.speed / dash.rules.start)),
        ("BEST", best.map(|best| format!("{best:05}")).unwrap_or_else(|| "—".into())),
    ];
    screen.hud(layout.sky_top - 2, layout.left - 1, width + 2, &format!("DASH · {}", level.name()), &stats);
    screen.frame_box(layout.sky_top - 1, layout.left - 1, dash.sky + 5, width + 2, Style::fg(if night { Color::Blue } else { Color::Gray }));
    let ground = layout.ground(dash);
    if night {
        let blank = " ".repeat(width as usize);
        for y in layout.sky_top..ground + 3 {
            screen.put(y, layout.left, &blank, tone(Style::PLAIN));
        }
        screen.put(layout.sky_top + 1, layout.left + width - 8, "◐", tone(Style::fg(Color::Yellow).bold()));
    }
    for &(x, row) in &dash.clouds {
        blit(screen, &["  ▄▄▄  ", "▄█████▄"], layout.sky_top + row, x.round() as i32, layout, width, tone(Style::fg(Color::Gray).dim()));
    }
    let line = tone(Style::fg(if night { Color::White } else { Color::Gray }));
    screen.put(ground, layout.left - 1, &format!("├{}┤", "─".repeat(width as usize)), line);
    for row in 1..=2 {
        let specks: String = (0..width).map(|x| speck(dash.ground_offset as i64 + x as i64, row as i64)).collect();
        screen.put(ground + row, layout.left, &specks, tone(Style::fg(Color::Gray).dim()));
    }
    let row_of = |y: f64, height: f64| ground - (y.round() as i32) - height as i32;
    let flap = (dash.time * 8.0) as usize;
    for obstacle in &dash.obstacles {
        let (_, height) = obstacle.size();
        let color = if matches!(obstacle.kind, Kind::Bird(_)) { Color::Cyan } else { Color::Green };
        let top = row_of(obstacle.y(), height);
        blit(screen, obstacle.kind.sprite(flap), top, obstacle.x.round() as i32, layout, width, tone(Style::fg(color).bold()));
    }
    let sprite = fox_sprite(dash);
    let fox_style = if dash.dead { Style::fg(Color::Red).bold() } else { Style::fg(Color::DarkYellow).bold() };
    blit(screen, sprite, row_of(dash.fox_y, sprite.len() as f64), FOX_X as i32, layout, width, tone(fox_style));
    let hi = best.unwrap_or(0).max(dash.score());
    let flash_hidden = dash.flash > 0.0 && (dash.flash * 6.0) as i64 % 2 == 1;
    let score = if flash_hidden { "     ".to_string() } else { format!("{:05}", dash.score()) };
    let hud = if hi > 0 { format!("HI {hi:05}  {score}") } else { score };
    screen.put(layout.sky_top, layout.left + width - hud.chars().count() as i32 - 1, &hud, tone(Style::fg(if night { Color::White } else { Color::Gray }).bold()));
    if !dash.started {
        screen.centered(layout.sky_top + dash.sky / 2 - 1, "Press Space to start", tone(Style::fg(Color::Yellow).bold()));
    }
    screen.controls("Space/↑/W/click jump · ↓/S duck · P pause · Esc quit");
}

pub fn play(screen: &mut dyn Screen, level: Level, rng: &mut Rng, best: Option<u64>, scores: Option<&mut Scores>) -> io::Result<Played> {
    // Rows: HUD, frame, sky, ground, two speck rows, frame, controls.
    let (height, width) = screen.size();
    let sky = (height - 7).min(MAX_SKY);
    let field = (width - 4).min(MAX_WIDTH);
    if sky < MIN_SKY || field < 56 {
        return too_small(screen, 60, MIN_SKY + 7);
    }
    let (need_width, need_height) = (field + 2, sky + 7);
    let mut game = Dash::new(level, field, sky);
    let mut last = screen.now();
    let mut ticker = Ticker::new(last);
    loop {
        if !fits(screen, need_width, need_height) {
            if !wait_for_room(screen, need_width, need_height)? {
                return Ok(Played { score: None, after: After::Leave });
            }
            last = screen.now();
            ticker.reset(last);
        }
        let (top, left) = center_block(screen.size(), sky + 5, field + 2);
        let layout = Layout { left: left + 1, sky_top: top + 1 };
        draw(screen, &game, &layout, level, best);
        screen.present()?;
        let deadline = ticker.deadline(screen.now());
        for input in inputs_until(screen, deadline)? {
            match input {
                Input::Key(Key::Char(' ' | 'w' | 'W') | Key::Up) | Input::Click { button: Button::Left, .. } => game.jump(),
                Input::Key(Key::Down | Key::Char('s' | 'S')) => game.duck(),
                input if input.is_pause() => {
                    if pause(screen)? {
                        return Ok(Played { score: None, after: After::Leave });
                    }
                    last = screen.now();
                    ticker.reset(last);
                }
                input if input.is_leave() => return Ok(Played { score: None, after: After::Leave }),
                _ => {}
            }
        }
        let now = screen.now();
        let event = game.update((now - last).min(0.25), rng);
        last = now;
        if event == Event::Died {
            draw(screen, &game, &layout, level, best);
            let details = [format!("Score {:05} · Speed {:.1}x", game.score(), game.speed / game.rules.start)];
            let after = finish(screen, "GAME OVER", &details, Some((game.score(), best, "dash")), scores.map(|scores| (scores, level)))?;
            return Ok(Played { score: Some(game.score()), after });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::super::testing::*;
    use super::super::FRAME;
    use super::*;

    fn game(level: Level) -> Dash {
        Dash::new(level, 78, 12)
    }

    fn run(game: &mut Dash, seconds: f64, rng: &mut Rng) -> Event {
        let mut event = Event::Running;
        for _ in 0..(seconds / FRAME).round() as usize {
            event = game.update(FRAME, rng);
            if event == Event::Died {
                break;
            }
        }
        event
    }

    fn place(game: &mut Dash, kind: Kind, x: f64) {
        game.obstacles.clear();
        game.obstacles.push(Obstacle { kind, x });
    }

    /// Plays like a careful human: jumps in the middle of the allowed take-off interval, ducks late.
    fn bot(game: &mut Dash) {
        let mut ahead: Vec<&Obstacle> = game.obstacles.iter().filter(|o| o.x + o.size().0 > FOX_X + SHRINK_X).collect();
        ahead.sort_by(|a, b| a.x.total_cmp(&b.x));
        let Some(first) = ahead.first().copied() else { return };
        // Neighbours closer than two columns act as one obstacle.
        let mut end = first.x + first.size().0;
        let mut top = first.y() + first.size().1 - 0.6;
        for next in &ahead[1..] {
            if next.x - end > 2.0 {
                break;
            }
            end = next.x + next.size().0;
            top = top.max(next.y() + next.size().1 - 0.6);
        }
        let start_in = (first.x + SHRINK_X - (FOX_X + FOX_W - SHRINK_X)) / game.speed;
        let end_in = (end - SHRINK_X - (FOX_X + SHRINK_X)) / game.speed;
        match first.kind {
            Kind::Bird(Lane::High) => {}
            Kind::Bird(Lane::Mid) => {
                if start_in < 0.15 {
                    game.duck();
                }
            }
            _ => {
                if start_in + end_in <= AIR_SECONDS && top < APEX {
                    game.jump();
                }
            }
        }
    }

    #[test]
    fn nothing_moves_until_the_first_jump_starts_the_run() {
        let mut dash = game(Level::Normal);
        let mut rng = Rng::constant(0);
        assert!(!dash.started);
        run(&mut dash, 1.0, &mut rng);
        assert_eq!(dash.score(), 0);
        assert!(dash.obstacles.is_empty());
        dash.jump();
        assert!(dash.started);
        run(&mut dash, 1.0, &mut rng);
        assert!(dash.score() > 0);
    }

    #[test]
    fn a_jump_has_a_fixed_parabolic_arc() {
        let mut dash = game(Level::Normal);
        let mut rng = Rng::constant(0);
        dash.jump();
        let (mut peak, mut peak_time, mut air) = (0.0f64, 0.0f64, 0.0f64);
        while dash.fox_y > 0.0 || air == 0.0 {
            dash.update(0.005, &mut rng);
            air += 0.005;
            if dash.fox_y > peak {
                peak = dash.fox_y;
                peak_time = air;
            }
            dash.obstacles.clear();
        }
        assert!((peak - 6.0).abs() < 0.2, "apex {peak}");
        assert!((air - 0.72).abs() < 0.05, "air time {air}");
        assert!((peak_time - air / 2.0).abs() < 0.05, "symmetric arc");
        dash.jump();
        let before = dash.fox_y;
        dash.update(0.05, &mut rng);
        assert!(dash.fox_y > before, "can jump again once landed");
    }

    #[test]
    fn jumping_in_the_air_does_nothing_and_down_drops_fast() {
        let mut slow = game(Level::Normal);
        let mut fast = game(Level::Normal);
        let mut rng = Rng::constant(0);
        for dash in [&mut slow, &mut fast] {
            dash.jump();
            run(dash, 0.2, &mut rng);
        }
        let velocity = slow.fox_vy;
        slow.jump();
        assert_eq!(slow.fox_vy, velocity, "no double jump");
        fast.duck();
        let mut frames = (0, 0);
        while slow.fox_y > 0.0 {
            slow.update(FRAME, &mut rng);
            slow.obstacles.clear();
            frames.0 += 1;
        }
        while fast.fox_y > 0.0 {
            fast.update(FRAME, &mut rng);
            fast.obstacles.clear();
            frames.1 += 1;
        }
        assert!(frames.1 * 2 < frames.0, "fast drop {frames:?}");
    }

    #[test]
    fn ducking_lasts_a_third_of_a_second_and_repeats_extend_it() {
        let mut dash = game(Level::Normal);
        let mut rng = Rng::constant(0);
        dash.jump();
        run(&mut dash, 1.0, &mut rng);
        dash.obstacles.clear();
        assert!(!dash.ducking());
        dash.duck();
        assert!(dash.ducking());
        run(&mut dash, 0.30, &mut rng);
        assert!(dash.ducking());
        dash.duck(); // key repeat
        run(&mut dash, 0.30, &mut rng);
        assert!(dash.ducking(), "extended by the repeat");
        run(&mut dash, 0.10, &mut rng);
        assert!(!dash.ducking());
    }

    #[test]
    fn hitboxes_decide_between_jumping_ducking_and_running_under() {
        let hit = |kind: Kind, setup: &dyn Fn(&mut Dash)| {
            let mut dash = game(Level::Normal);
            dash.jump();
            dash.fox_y = 0.0;
            dash.fox_vy = 0.0;
            setup(&mut dash);
            place(&mut dash, kind, FOX_X + 1.0);
            dash.hits()
        };
        let stand = |_: &mut Dash| {};
        let ducked = |dash: &mut Dash| dash.duck();
        let airborne = |dash: &mut Dash| dash.fox_y = 4.5;
        assert!(hit(Kind::Small, &stand));
        assert!(!hit(Kind::Small, &airborne));
        assert!(hit(Kind::Large, &|dash: &mut Dash| dash.fox_y = 2.0));
        assert!(!hit(Kind::Large, &airborne));
        assert!(hit(Kind::Bird(Lane::Low), &stand));
        assert!(
            hit(Kind::Bird(Lane::Low), &ducked),
            "a low flier must be jumped"
        );
        assert!(!hit(Kind::Bird(Lane::Low), &airborne));
        assert!(hit(Kind::Bird(Lane::Mid), &stand));
        assert!(
            !hit(Kind::Bird(Lane::Mid), &ducked),
            "duck under the middle flier"
        );
        assert!(
            !hit(Kind::Bird(Lane::Mid), &|dash: &mut Dash| dash.fox_y = 4.0),
            "or jump over it"
        );
        assert!(
            !hit(Kind::Bird(Lane::High), &stand),
            "run under the high flier"
        );
        assert!(!hit(Kind::Bird(Lane::High), &ducked));
        // Touching only the transparent edge of the sprite is forgiven.
        let mut dash = game(Level::Normal);
        dash.jump();
        dash.fox_y = 0.0;
        place(&mut dash, Kind::Small, FOX_X + FOX_W - 0.4);
        assert!(!dash.hits());
    }

    #[test]
    fn speed_climbs_to_a_maximum_that_grows_with_difficulty() {
        let mut maxima = Vec::new();
        for level in [Level::Easy, Level::Normal, Level::Hard] {
            let mut dash = Dash::new(level, 78, 12);
            let start = dash.speed;
            dash.started = true;
            let mut rng = Rng::constant(0);
            for _ in 0..300 {
                dash.update(0.1, &mut rng);
                dash.obstacles.clear();
            }
            assert!(dash.speed > start, "{level:?} accelerates");
            for _ in 0..3000 {
                dash.update(0.1, &mut rng);
                dash.obstacles.clear();
            }
            assert_eq!(dash.speed, dash.rules.max);
            maxima.push((start, dash.rules.max));
        }
        assert!(maxima[0].0 < maxima[1].0 && maxima[1].0 < maxima[2].0);
        assert!(maxima[0].1 < maxima[1].1 && maxima[1].1 < maxima[2].1);
    }

    #[test]
    fn the_score_is_about_ten_a_second_at_the_start() {
        let mut dash = game(Level::Normal);
        dash.jump();
        let mut rng = Rng::constant(0);
        run(&mut dash, 1.0, &mut rng);
        assert!((9..=12).contains(&dash.score()), "{}", dash.score());
    }

    #[test]
    fn the_score_flashes_every_hundred_points() {
        let mut dash = game(Level::Normal);
        dash.jump();
        let mut rng = Rng::constant(0);
        dash.distance_score = 99.9;
        assert_eq!(dash.flash, 0.0);
        dash.update(FRAME, &mut rng);
        assert!(dash.flash > 0.5, "flash starts at 100");
        run(&mut dash, 1.0, &mut rng);
        assert_eq!(dash.flash, 0.0);
        dash.update(FRAME, &mut rng);
        assert_eq!(dash.flash, 0.0, "not again until 200");
    }

    #[test]
    fn night_falls_after_700_points_and_ends_again() {
        let mut dash = game(Level::Normal);
        for (score, night) in [
            (0.0, false),
            (699.0, false),
            (700.0, true),
            (949.0, true),
            (950.0, false),
            (1699.0, false),
            (1700.0, true),
        ] {
            dash.distance_score = score;
            assert_eq!(dash.night(), night, "score {score}");
        }
    }

    #[test]
    fn a_perfect_player_survives_every_difficulty_so_gaps_are_always_fair() {
        for level in [Level::Easy, Level::Normal, Level::Hard] {
            for seed in 1..=20 {
                let mut dash = Dash::new(level, 98, 13);
                let mut rng = Rng::seeded(seed);
                dash.jump();
                for frame in 0..(300.0 / FRAME) as usize {
                    bot(&mut dash);
                    let event = dash.update(FRAME, &mut rng);
                    assert_eq!(
                        event,
                        Event::Running,
                        "{level:?} seed {seed} died at {:.1}s, score {}",
                        frame as f64 * FRAME,
                        dash.score()
                    );
                }
                assert!(dash.score() > 1000, "{level:?} reached {}", dash.score());
            }
        }
    }

    #[test]
    fn obstacle_variety_and_flier_rules_follow_the_difficulty() {
        let seen = |level: Level, seconds: f64| {
            let mut dash = Dash::new(level, 98, 13);
            let mut rng = Rng::seeded(3);
            let mut kinds: Vec<(Kind, u64)> = Vec::new();
            dash.jump();
            for _ in 0..(seconds / FRAME) as usize {
                bot(&mut dash);
                dash.update(FRAME, &mut rng);
                for o in &dash.obstacles {
                    if o.x > 90.0
                        && !kinds
                            .iter()
                            .any(|(k, s)| *k == o.kind && *s == dash.score())
                    {
                        kinds.push((o.kind, dash.score()));
                    }
                }
            }
            kinds
        };
        let normal = seen(Level::Normal, 200.0);
        assert!(
            normal
                .iter()
                .filter(|(k, _)| matches!(k, Kind::Bird(_)))
                .all(|(_, score)| *score >= 250),
            "fliers wait for the threshold"
        );
        for lane in [Lane::Low, Lane::Mid, Lane::High] {
            assert!(
                normal.iter().any(|(k, _)| *k == Kind::Bird(lane)),
                "normal has {lane:?} fliers"
            );
        }
        for kind in [Kind::Small, Kind::Large, Kind::Wide] {
            assert!(
                normal.iter().any(|(k, _)| *k == kind),
                "normal has {kind:?}"
            );
        }
        let easy = seen(Level::Easy, 300.0);
        assert!(
            !easy.iter().any(|(k, _)| *k == Kind::Bird(Lane::High)),
            "easy has no high fliers"
        );
        assert!(
            easy.iter().any(|(k, _)| matches!(k, Kind::Bird(_))),
            "easy still has fliers later"
        );
        let hard = seen(Level::Hard, 20.0);
        assert!(
            hard.iter()
                .any(|(k, score)| matches!(k, Kind::Bird(_)) && *score < 100),
            "hard has fliers from the start"
        );
    }

    #[test]
    fn clouds_drift_slower_than_the_ground_and_respawn() {
        let mut dash = game(Level::Normal);
        dash.jump();
        let mut rng = Rng::seeded(5);
        let first = dash.clouds[0].0;
        dash.update(0.1, &mut rng);
        let moved = first - dash.clouds[0].0;
        assert!(
            moved > 0.0 && moved < dash.speed * 0.1 * 0.5,
            "parallax {moved}"
        );
        for _ in 0..600 {
            dash.update(FRAME, &mut rng);
            dash.obstacles.clear();
        }
        assert!(
            dash.clouds.iter().any(|(x, _)| *x > 30.0),
            "new clouds keep arriving"
        );
    }

    #[test]
    fn running_legs_and_wings_animate() {
        let mut dash = game(Level::Normal);
        dash.jump();
        dash.fox_y = 0.0;
        let mut rng = Rng::constant(0);
        let mut frames = std::collections::HashSet::new();
        for _ in 0..30 {
            dash.update(FRAME, &mut rng);
            dash.obstacles.clear();
            frames.insert(dash.leg_frame());
        }
        assert_eq!(frames.len(), 2);
        assert_ne!(
            Kind::Bird(Lane::Low).sprite(0),
            Kind::Bird(Lane::Low).sprite(1)
        );
    }

    #[test]
    fn a_collision_ends_the_run_and_idle_players_die_on_the_first_obstacle() {
        let mut dash = game(Level::Normal);
        let mut rng = Rng::constant(0);
        dash.jump();
        dash.fox_y = 0.0;
        dash.fox_vy = 0.0;
        assert_eq!(run(&mut dash, 10.0, &mut rng), Event::Died);
        assert!(dash.dead);
        let score = dash.score();
        assert!(score > 20);
        assert_eq!(
            dash.update(1.0, &mut rng),
            Event::Running,
            "a dead run stands still"
        );
        assert_eq!(dash.score(), score);
    }

    #[test]
    fn plays_on_a_screen_shows_the_start_prompt_hud_and_records_the_score() {
        let path = std::env::temp_dir().join(format!("unlaw-dash-{}.toml", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let mut scores = Scores::load(Some(path.clone()));
        // Start, then several seconds of blind jumps (each delivered key also lets 0.6 s pass), then idle until the crash.
        let mut inputs = vec![];
        for _ in 0..6 {
            inputs.push(key(' '));
            inputs.extend(std::iter::repeat_n(None, 10));
        }
        inputs.extend(std::iter::repeat_n(None, 600));
        let mut screen = Fake::new((24, 80)).keys(&inputs).keys(&[special(Key::Esc)]);
        let played = play(
            &mut screen,
            Level::Normal,
            &mut Rng::seeded(2),
            Some(1234),
            Some(&mut scores),
        )
        .unwrap();
        assert_eq!(played.after, After::Leave);
        let score = played.score.expect("the run ended in a collision");
        assert!(score > 0);
        assert!(screen.drew("Press Space to start"));
        assert!(screen.drew("HI 01234"));
        assert!(screen.drew("GAME OVER"));
        assert!(screen.drew("duck"));
        assert_eq!(scores.best("dash", Level::Normal), Some(score));
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn pause_quit_and_small_terminal() {
        let mut screen = Fake::new((24, 80)).keys(&[key(' '), key('p'), key('p'), key('q')]);
        assert_eq!(
            play(&mut screen, Level::Easy, &mut Rng::constant(0), None, None)
                .unwrap()
                .score,
            None
        );
        assert!(screen.drew("PAUSED"));
        let mut small = Fake::new((10, 30)).keys(&[key('x')]);
        assert_eq!(
            play(&mut small, Level::Easy, &mut Rng::constant(0), None, None)
                .unwrap()
                .after,
            After::Leave
        );
        assert!(small.drew("needs a 60x17 terminal"));
    }

    #[test]
    fn keys_and_clicks_jump_and_duck() {
        let mut screen = Fake::new((24, 80)).keys(&[
            special(Key::Up),
            special(Key::Down),
            key('w'),
            key('s'),
            click(5, 5, Button::Left),
            key('q'),
        ]);
        assert_eq!(
            play(
                &mut screen,
                Level::Normal,
                &mut Rng::constant(0),
                None,
                None
            )
            .unwrap()
            .score,
            None
        );
        assert!(screen.drew("█"));
    }
}
