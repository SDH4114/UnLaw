//! Space Invaders close to the arcade original: a 5x11 formation of three
//! alien types that speeds up as it shrinks, only the lowest alien of a column
//! fires, one player shot on screen at a time, erodible shields, the mystery
//! UFO, lives, an extra life at 1500 points and ever lower, faster waves.

use std::collections::HashSet;
use std::io;

use super::{finish, inputs_until, pause, too_small, After, Button, Color, Input, Key, Level, Played, Rng, Screen, Style, FRAME};

pub const COLUMNS: i32 = 11;
pub const ROWS: i32 = 5;
const SPACING: i32 = 4;
const EXTRA_LIFE_AT: u64 = 1500;

pub struct Rules {
    pub lives: u32,
    /// Chance per frame that the formation fires.
    pub fire_chance: f64,
    pub max_alien_shots: usize,
    /// Frames between alien shot moves (lower is faster).
    pub shot_delay: u32,
    /// Seconds per formation step with all 55 aliens alive.
    pub step_seconds: f64,
    pub start_drop: i32,
}

pub fn rules(level: Level) -> Rules {
    match level {
        Level::Easy => Rules { lives: 5, fire_chance: 0.015, max_alien_shots: 2, shot_delay: 3, step_seconds: 0.9, start_drop: 0 },
        Level::Normal => Rules { lives: 3, fire_chance: 0.035, max_alien_shots: 3, shot_delay: 2, step_seconds: 0.65, start_drop: 0 },
        Level::Hard => Rules { lives: 2, fire_chance: 0.12, max_alien_shots: 7, shot_delay: 1, step_seconds: 0.4, start_drop: 2 },
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Alien {
    pub y: i32,
    /// Left column of the 3-character sprite.
    pub x: i32,
    /// 0 bottom (10 points), 1 middle (20), 2 top (30).
    pub kind: u8,
}

impl Alien {
    fn points(&self) -> u64 {
        [10, 20, 30][self.kind as usize]
    }

    fn covers(&self, (y, x): (i32, i32)) -> bool {
        y == self.y && (self.x..self.x + 3).contains(&x)
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum Event {
    None,
    Hit,
    LifeLost,
    WaveCleared,
    GameOver,
}

pub struct Invaders {
    pub height: i32,
    pub width: i32,
    pub aliens: Vec<Alien>,
    direction: i32,
    step_timer: f64,
    pub animation: bool,
    pub player: i32,
    target: Option<i32>,
    pub shot: Option<(i32, i32)>,
    pub alien_shots: Vec<(i32, i32)>,
    pub shields: HashSet<(i32, i32)>,
    pub ufo: Option<(f64, f64)>,
    ufo_timer: f64,
    pub score: u64,
    pub lives: u32,
    pub wave: u32,
    extra_life_given: bool,
    pub respawn: f64,
    frame: u32,
    pub rules: Rules,
}

impl Invaders {
    pub fn new(level: Level, height: i32, width: i32) -> Invaders {
        let rules = rules(level);
        let mut game = Invaders {
            height,
            width,
            aliens: Vec::new(),
            direction: 1,
            step_timer: 0.0,
            animation: false,
            player: width / 2,
            target: None,
            shot: None,
            alien_shots: Vec::new(),
            shields: HashSet::new(),
            ufo: None,
            ufo_timer: 0.0,
            score: 0,
            lives: rules.lives,
            wave: 1,
            extra_life_given: false,
            respawn: 0.0,
            frame: 0,
            rules,
        };
        game.start_wave();
        game
    }

    pub fn player_row(&self) -> i32 {
        self.height - 1
    }

    fn start_wave(&mut self) {
        let drop = (self.rules.start_drop + self.wave as i32 - 1).min(5);
        let left = (self.width - (COLUMNS - 1) * SPACING - 3) / 2;
        self.aliens = (0..ROWS)
            .flat_map(|row| {
                let kind = match row {
                    0 => 2,
                    1 | 2 => 1,
                    _ => 0,
                };
                (0..COLUMNS).map(move |column| Alien { y: 3 + drop + row * 2, x: left + column * SPACING, kind })
            })
            .collect();
        self.direction = 1;
        self.step_timer = 0.0;
        self.shot = None;
        self.alien_shots.clear();
        // Four shields, 7 wide and 3 tall, with the classic notch underneath.
        let top = self.player_row() - 5;
        self.shields.clear();
        for index in 0..4 {
            let center = self.width * (2 * index + 1) / 8;
            for dy in 0..3 {
                for dx in -3i32..=3 {
                    if !(dy == 2 && dx.abs() <= 1) {
                        self.shields.insert((top + dy, center + dx));
                    }
                }
            }
        }
    }

    /// Seconds per formation step: faster as aliens die and in later waves.
    pub fn step_interval(&self) -> f64 {
        let alive = self.aliens.len() as f64 / (ROWS * COLUMNS) as f64;
        (self.rules.step_seconds * alive * 0.92f64.powi(self.wave as i32 - 1)).max(0.03)
    }

    pub fn move_player(&mut self, columns: i32) {
        self.target = None;
        self.player = (self.player + columns).clamp(1, self.width - 2);
    }

    pub fn aim(&mut self, column: i32) {
        self.target = Some(column.clamp(1, self.width - 2));
    }

    /// Fire if the player's single shot is not already on screen.
    pub fn fire(&mut self) -> bool {
        if self.shot.is_some() || self.respawn > 0.0 {
            return false;
        }
        self.shot = Some((self.player_row() - 1, self.player));
        true
    }

    fn add_score(&mut self, points: u64) {
        self.score += points;
        if !self.extra_life_given && self.score >= EXTRA_LIFE_AT {
            self.extra_life_given = true;
            self.lives += 1;
        }
    }

    fn alien_fire(&mut self, rng: &mut Rng) {
        if self.alien_shots.len() >= self.rules.max_alien_shots || !rng.chance(self.rules.fire_chance) {
            return;
        }
        // Only the lowest alien of a column can fire, as in the arcade.
        let mut columns: Vec<i32> = self.aliens.iter().map(|alien| alien.x).collect();
        columns.sort_unstable();
        columns.dedup();
        if columns.is_empty() {
            return;
        }
        let column = columns[rng.below(columns.len())];
        if let Some(shooter) = self.aliens.iter().filter(|alien| alien.x == column).max_by_key(|alien| alien.y) {
            self.alien_shots.push((shooter.y + 1, shooter.x + 1));
        }
    }

    /// Advance one frame.
    pub fn update(&mut self, seconds: f64, rng: &mut Rng) -> Event {
        self.frame += 1;
        if self.respawn > 0.0 {
            self.respawn -= seconds;
            return Event::None;
        }
        if let Some(target) = self.target {
            let step = (target - self.player).clamp(-2, 2);
            self.player += step;
            if step == 0 {
                self.target = None;
            }
        }
        let mut event = Event::None;
        // The player's shot climbs a row per frame.
        if let Some((y, x)) = self.shot {
            let next = (y - 1, x);
            self.shot = (next.0 > 0).then_some(next);
            if let Some(cell) = self.shot {
                if let Some(index) = self.aliens.iter().position(|alien| alien.covers(cell)) {
                    let alien = self.aliens.remove(index);
                    self.add_score(alien.points());
                    self.shot = None;
                    event = Event::Hit;
                } else if self.shields.remove(&cell) {
                    self.shot = None;
                } else if let Some(position) = self.alien_shots.iter().position(|shot| *shot == cell) {
                    self.alien_shots.remove(position);
                    self.shot = None;
                } else if let Some((ufo_x, _)) = self.ufo {
                    if cell.0 == 1 && (ufo_x as i32..ufo_x as i32 + 5).contains(&cell.1) {
                        self.add_score([50, 100, 150, 300][rng.below(4)]);
                        self.ufo = None;
                        self.shot = None;
                        event = Event::Hit;
                    }
                }
            }
        }
        if self.aliens.is_empty() {
            self.wave += 1;
            self.start_wave();
            return Event::WaveCleared;
        }
        if self.frame % self.rules.shot_delay == 0 {
            let player_row = self.player_row();
            let mut hit_player = false;
            let mut remaining = Vec::new();
            for (y, x) in std::mem::take(&mut self.alien_shots) {
                let next = (y + 1, x);
                if self.shields.remove(&next) || next.0 > player_row {
                    continue;
                }
                if next.0 == player_row && (self.player - 1..=self.player + 1).contains(&next.1) {
                    hit_player = true;
                    continue;
                }
                remaining.push(next);
            }
            self.alien_shots = remaining;
            if hit_player {
                self.lives = self.lives.saturating_sub(1);
                self.alien_shots.clear();
                self.shot = None;
                if self.lives == 0 {
                    return Event::GameOver;
                }
                self.respawn = 1.0;
                return Event::LifeLost;
            }
        }
        self.step_timer += seconds;
        if self.step_timer >= self.step_interval() {
            self.step_timer = 0.0;
            self.animation = !self.animation;
            let edge = self.aliens.iter().any(|alien| alien.x + self.direction < 1 || alien.x + 3 + self.direction > self.width - 1);
            for alien in &mut self.aliens {
                if edge {
                    alien.y += 1;
                } else {
                    alien.x += self.direction;
                }
            }
            if edge {
                self.direction = -self.direction;
            }
            // Aliens chew through shields they reach, and win if they land.
            let aliens = self.aliens.clone();
            self.shields.retain(|cell| !aliens.iter().any(|alien| alien.covers(*cell)));
            if self.aliens.iter().any(|alien| alien.y >= self.player_row()) {
                return Event::GameOver;
            }
        }
        self.alien_fire(rng);
        self.ufo_timer += seconds;
        match self.ufo {
            Some((x, speed)) => {
                let next = x + speed;
                self.ufo = (next > -5.0 && next < self.width as f64).then_some((next, speed));
            }
            None if self.ufo_timer > 18.0 && rng.chance(0.01) => {
                self.ufo_timer = 0.0;
                self.ufo = Some(if rng.below(2) == 0 { (0.0, 0.5) } else { ((self.width - 5) as f64, -0.5) });
            }
            None => {}
        }
        event
    }
}

const SPRITES: [[&str; 2]; 3] = [["<M>", ">M<"], ["/O\\", "\\O/"], ["{@}", "}@{"]];
const ALIEN_COLORS: [Color; 3] = [Color::Green, Color::Cyan, Color::Magenta];

struct Layout {
    top: i32,
    left: i32,
}

fn draw(screen: &mut dyn Screen, game: &Invaders, layout: &Layout, level: Level, best: Option<u64>) {
    screen.clear();
    let lives = "♥".repeat(game.lives as usize);
    let best = best.map(|best| format!(" · Best {best}")).unwrap_or_default();
    let title = format!("SPACE INVADERS · {} · Score {} · Lives {lives} · Wave {}{best}", level.name(), game.score, game.wave);
    screen.centered(0, &title, Style::fg(Color::Yellow).bold());
    screen.frame_box(layout.top, layout.left, game.height + 2, game.width + 2, Style::fg(Color::Gray));
    let at = |y: i32, x: i32| (layout.top + 1 + y, layout.left + 1 + x);
    for &(y, x) in &game.shields {
        let (sy, sx) = at(y, x);
        screen.put(sy, sx, "█", Style::fg(Color::Green).dim());
    }
    for alien in &game.aliens {
        let (y, x) = at(alien.y, alien.x);
        screen.put(y, x, SPRITES[alien.kind as usize][game.animation as usize], Style::fg(ALIEN_COLORS[alien.kind as usize]).bold());
    }
    if let Some((x, _)) = game.ufo {
        let (y, sx) = at(1, x as i32);
        screen.put(y, sx, "<=O=>", Style::fg(Color::Red).bold());
    }
    if let Some((y, x)) = game.shot {
        let (sy, sx) = at(y, x);
        screen.put(sy, sx, "│", Style::fg(Color::Yellow).bold());
    }
    for &(y, x) in &game.alien_shots {
        let (sy, sx) = at(y, x);
        screen.put(sy, sx, "¦", Style::fg(Color::White).bold());
    }
    let (y, x) = at(game.player_row(), game.player - 1);
    let blink = game.respawn > 0.0 && (game.respawn * 8.0) as i32 % 2 == 0;
    if !blink {
        screen.put(y, x, "▄█▄", Style::fg(Color::Green).bold());
    }
    screen.controls("←→ / A D move · Space / click fire · mouse moves the cannon · P pause · Esc quit");
}

pub fn play(screen: &mut dyn Screen, level: Level, rng: &mut Rng, best: Option<u64>) -> io::Result<Played> {
    let (height, width) = screen.size();
    let field_height = (height - 4).min(30);
    let field_width = (width - 2).min(90);
    if field_height < 20 || field_width < 56 {
        return too_small(screen, 58, 24);
    }
    let layout = Layout { top: 1, left: (width - field_width - 2) / 2 };
    let mut game = Invaders::new(level, field_height, field_width);
    let mut last = screen.now();
    loop {
        draw(screen, &game, &layout, level, best);
        screen.present()?;
        let deadline = screen.now() + FRAME;
        for input in inputs_until(screen, deadline)? {
            match input {
                Input::Key(Key::Left | Key::Char('a' | 'A')) => game.move_player(-2),
                Input::Key(Key::Right | Key::Char('d' | 'D')) => game.move_player(2),
                Input::Key(Key::Char(' ') | Key::Up | Key::Char('w' | 'W')) | Input::Click { button: Button::Left, .. } => {
                    game.fire();
                }
                Input::Hover { x, .. } => game.aim(x - layout.left - 1),
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
        let event = game.update((now - last).min(0.25), rng);
        last = now;
        if event == Event::GameOver {
            draw(screen, &game, &layout, level, best);
            let details = [format!("Score {} · Wave {}", game.score, game.wave)];
            let after = finish(screen, "GAME OVER — the invaders won", &details, Some((game.score, best, "invaders")))?;
            return Ok(Played { score: Some(game.score), after });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::super::testing::*;
    use super::*;

    fn game(level: Level) -> Invaders {
        Invaders::new(level, 24, 70)
    }

    fn run_frames(game: &mut Invaders, frames: usize, rng: &mut Rng) -> Vec<Event> {
        (0..frames).map(|_| game.update(FRAME, rng)).filter(|event| *event != Event::None).collect()
    }

    #[test]
    fn the_formation_is_5_by_11_with_three_kinds() {
        let invaders = game(Level::Normal);
        assert_eq!(invaders.aliens.len(), 55);
        assert_eq!(invaders.aliens.iter().filter(|a| a.kind == 2).count(), 11);
        assert_eq!(invaders.aliens.iter().filter(|a| a.kind == 1).count(), 22);
        assert_eq!(invaders.shields.len(), 4 * (21 - 3));
        assert_eq!(invaders.lives, 3);
        assert_eq!(game(Level::Hard).lives, 2);
        assert!(game(Level::Hard).aliens[0].y > invaders.aliens[0].y, "hard starts lower");
    }

    #[test]
    fn only_one_player_shot_at_a_time() {
        let mut invaders = game(Level::Normal);
        assert!(invaders.fire());
        assert!(!invaders.fire());
        let mut rng = Rng::constant(999_999);
        run_frames(&mut invaders, 40, &mut rng);
        assert!(invaders.fire(), "the first shot is gone");
    }

    #[test]
    fn shots_kill_aliens_for_their_points() {
        let mut invaders = game(Level::Normal);
        let target = *invaders.aliens.iter().filter(|a| a.kind == 0).max_by_key(|a| a.y).unwrap();
        invaders.shields.clear();
        invaders.player = target.x + 1;
        invaders.fire();
        let mut rng = Rng::constant(999_999);
        let events = run_frames(&mut invaders, 30, &mut rng);
        assert!(events.contains(&Event::Hit));
        assert_eq!(invaders.score, 10);
        assert_eq!(invaders.aliens.len(), 54);
    }

    #[test]
    fn shields_absorb_shots_and_erode() {
        let mut invaders = game(Level::Normal);
        let shield = *invaders.shields.iter().max_by_key(|(y, x)| (*y, -*x)).unwrap();
        invaders.player = shield.1;
        let before = invaders.shields.len();
        invaders.fire();
        run_frames(&mut invaders, 10, &mut Rng::constant(999_999));
        assert_eq!(invaders.shields.len(), before - 1);
        assert_eq!(invaders.score, 0);
    }

    #[test]
    fn the_formation_speeds_up_as_it_shrinks_and_in_later_waves() {
        let mut invaders = game(Level::Normal);
        let full = invaders.step_interval();
        invaders.aliens.truncate(5);
        assert!(invaders.step_interval() < full / 5.0);
        invaders.aliens.truncate(1);
        assert!(invaders.step_interval() >= 0.03);
        let mut later = game(Level::Normal);
        later.wave = 4;
        assert!(later.step_interval() < full);
    }

    #[test]
    fn the_formation_marches_and_drops_at_the_edges() {
        let mut invaders = game(Level::Easy);
        let start_y = invaders.aliens[0].y;
        let mut rng = Rng::constant(999_999);
        for _ in 0..2000 {
            invaders.update(FRAME, &mut rng);
            if invaders.aliens[0].y > start_y {
                break;
            }
        }
        assert!(invaders.aliens[0].y > start_y, "dropped a row at the edge");
        assert_eq!(invaders.direction, -1, "and turned around");
    }

    #[test]
    fn alien_shots_cost_lives_then_the_game() {
        let mut invaders = game(Level::Normal);
        invaders.shields.clear();
        let row = invaders.player_row();
        invaders.alien_shots.push((row - 1, invaders.player));
        let events = run_frames(&mut invaders, 4, &mut Rng::constant(999_999));
        assert_eq!(events, vec![Event::LifeLost]);
        assert_eq!(invaders.lives, 2);
        assert!(!invaders.fire(), "no firing while respawning");
        invaders.respawn = 0.0;
        invaders.lives = 1;
        invaders.alien_shots.push((row - 1, invaders.player));
        assert_eq!(run_frames(&mut invaders, 4, &mut Rng::constant(999_999)), vec![Event::GameOver]);
    }

    #[test]
    fn only_the_lowest_alien_of_a_column_fires_and_hard_fires_more() {
        let mut invaders = game(Level::Normal);
        invaders.alien_fire(&mut Rng::constant(0));
        let (y, x) = invaders.alien_shots[0];
        let column: Vec<&Alien> = invaders.aliens.iter().filter(|a| a.x + 1 == x).collect();
        assert_eq!(y, column.iter().map(|a| a.y).max().unwrap() + 1);
        assert!(rules(Level::Hard).fire_chance > 3.0 * rules(Level::Normal).fire_chance);
        let mut hard = game(Level::Hard);
        let mut rng = Rng::seeded(9);
        let mut shots = 0;
        for _ in 0..300 {
            hard.update(FRAME, &mut rng);
            shots = shots.max(hard.alien_shots.len());
        }
        assert!(shots >= 3, "hard keeps several shots in the air, saw {shots}");
    }

    #[test]
    fn landing_aliens_win_and_clearing_a_wave_starts_a_faster_one() {
        let mut invaders = game(Level::Normal);
        let row = invaders.player_row();
        invaders.aliens.truncate(1);
        let width = invaders.width;
        invaders.aliens[0] = Alien { y: row - 1, x: width - 4, kind: 0 }; // at the edge: it drops onto the player
        invaders.step_timer = 10.0;
        assert_eq!(invaders.update(FRAME, &mut Rng::constant(999_999)), Event::GameOver);
        let mut cleared = game(Level::Normal);
        cleared.aliens.clear();
        assert_eq!(cleared.update(FRAME, &mut Rng::constant(999_999)), Event::WaveCleared);
        assert_eq!(cleared.wave, 2);
        assert_eq!(cleared.aliens.len(), 55);
        assert!(cleared.aliens[0].y > game(Level::Normal).aliens[0].y, "the next wave starts lower");
    }

    #[test]
    fn extra_life_ufo_and_mouse_aim() {
        let mut invaders = game(Level::Normal);
        invaders.add_score(1490);
        invaders.add_score(20);
        assert_eq!(invaders.lives, 4);
        invaders.add_score(2000);
        assert_eq!(invaders.lives, 4, "only one extra life");
        invaders.ufo = Some((30.0, 0.0));
        invaders.shot = Some((2, 32));
        assert_eq!(invaders.update(FRAME, &mut Rng::constant(3)), Event::Hit);
        assert_eq!(invaders.score, 3510 + 300);
        invaders.aim(5);
        let mut rng = Rng::constant(999_999);
        run_frames(&mut invaders, 40, &mut rng);
        assert_eq!(invaders.player, 5);
        invaders.move_player(-100);
        assert_eq!(invaders.player, 1);
    }

    #[test]
    fn plays_on_a_screen_and_ends() {
        let mut inputs = vec![key(' '), special(Key::Left), special(Key::Right), Some(Input::Hover { y: 10, x: 20 }), click(5, 5, Button::Left)];
        inputs.extend(std::iter::repeat_n(None, 6000));
        let mut screen = Fake::new((26, 80)).keys(&inputs).keys(&[special(Key::Esc)]);
        let played = play(&mut screen, Level::Hard, &mut Rng::seeded(4), None).unwrap();
        assert_eq!(played.after, After::Leave);
        assert!(screen.drew("GAME OVER"));
        let mut quit = Fake::new((26, 80)).keys(&[key('p'), key('p'), key('q')]);
        assert_eq!(play(&mut quit, Level::Easy, &mut Rng::seeded(4), None).unwrap().score, None);
        let mut small = Fake::new((20, 50)).keys(&[key('x')]);
        assert_eq!(play(&mut small, Level::Easy, &mut Rng::seeded(4), None).unwrap().after, After::Leave);
    }
}
