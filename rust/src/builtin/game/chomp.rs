//! Chomp: an original maze chase. Every level is a freshly generated,
//! mirror-symmetric maze without dead ends. Four hunters with their own habits
//! alternate between resting in their corners and hunting; a power pellet turns
//! them blue and edible for a while, and eaten hunters fly back to the lair as
//! eyes. Moves are tile-based with buffered turns, so a turn pressed early
//! fires at the next junction.

use std::collections::VecDeque;
use std::io;

use super::{finish, inputs_until, pause, too_small, After, Button, Color, Input, Key, Level, Played, Rng, Screen, Style, FRAME};

pub type Cell = (i32, i32);

pub const ROWS: i32 = 21;
pub const COLUMNS: i32 = 27;
const MID: i32 = COLUMNS / 2;
const TUNNEL_ROW: i32 = 9;
const GATE: Cell = (8, MID);
/// Just outside the gate: where hunters enter the maze.
const DOOR: Cell = (7, MID);
const LAIR: Cell = (10, MID);
const START: Cell = (15, MID);
const FIRST_SEED: u64 = 0xC0FFEE;
const EXTRA_LOOPS: usize = 6;
const EXTRA_LIFE_AT: u64 = 10_000;
const POWER: [Cell; 4] = [(3, 1), (3, COLUMNS - 2), (ROWS - 4, 1), (ROWS - 4, COLUMNS - 2)];

const PELLET: u8 = 1;
const POWER_PELLET: u8 = 2;

const UP: Cell = (-1, 0);
const DOWN: Cell = (1, 0);
const LEFT: Cell = (0, -1);
const RIGHT: Cell = (0, 1);
/// Order also breaks ties between equally good moves.
const DIRS: [Cell; 4] = [UP, LEFT, DOWN, RIGHT];

fn slot((y, x): Cell) -> usize {
    (y * COLUMNS + x) as usize
}

/// One tile in `dir`; columns wrap so the side tunnel connects both edges.
fn step((y, x): Cell, (dy, dx): Cell) -> Cell {
    (y + dy, (x + dx).rem_euclid(COLUMNS))
}

fn back((dy, dx): Cell) -> Cell {
    (-dy, -dx)
}

fn manhattan(a: Cell, b: Cell) -> i32 {
    (a.0 - b.0).abs() + (a.1 - b.1).abs()
}

fn in_tunnel((y, x): Cell) -> bool {
    y == TUNNEL_ROW && (x <= 4 || x >= COLUMNS - 5)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Tile {
    Wall,
    Open,
    /// Only hunters pass the lair's gate.
    Gate,
    Lair,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Maze {
    tiles: Vec<Tile>,
}

/// Odd coordinates outside the lair and the tunnel: the rooms the generator connects.
fn is_room((y, x): Cell) -> bool {
    y % 2 == 1
        && x % 2 == 1
        && (1..ROWS - 1).contains(&y)
        && (1..COLUMNS - 1).contains(&x)
        && !((9..=11).contains(&y) && (11..=15).contains(&x))
        && !(y == TUNNEL_ROW && (x <= 3 || x >= COLUMNS - 4))
}

/// Walls the generator never opens: the border, the lair and the tunnel sides.
fn locked((y, x): Cell) -> bool {
    y == 0
        || y == ROWS - 1
        || x == 0
        || x == COLUMNS - 1
        || ((8..=12).contains(&y) && (10..=16).contains(&x))
        || ((y - TUNNEL_ROW).abs() == 1 && (x <= 4 || x >= COLUMNS - 5))
}

/// The four walls around a room with the room behind each.
fn walls_of(room: Cell) -> [(Cell, Cell); 4] {
    DIRS.map(|(dy, dx)| ((room.0 + dy, room.1 + dx), (room.0 + 2 * dy, room.1 + 2 * dx)))
}

impl Maze {
    pub fn tile(&self, (y, x): Cell) -> Tile {
        if !(0..ROWS).contains(&y) || !(0..COLUMNS).contains(&x) {
            return Tile::Wall;
        }
        self.tiles[slot((y, x))]
    }

    fn set(&mut self, cell: Cell, tile: Tile) {
        self.tiles[slot(cell)] = tile;
    }

    /// Open a tile and its mirror image.
    fn open(&mut self, (y, x): Cell) {
        self.set((y, x), Tile::Open);
        self.set((y, COLUMNS - 1 - x), Tile::Open);
    }

    /// Open neighbours the player could walk to.
    pub fn exits(&self, cell: Cell) -> usize {
        DIRS.iter().filter(|&&dir| self.tile(step(cell, dir)) == Tile::Open).count()
    }

    /// A random spanning tree over the left half, mirrored, then braided so no
    /// corridor ends blind, plus a few extra loops.
    pub fn generate(seed: u64) -> Maze {
        let mut rng = Rng::seeded(seed);
        let mut maze = Maze { tiles: vec![Tile::Wall; (ROWS * COLUMNS) as usize] };
        for y in 9..=11 {
            for x in 11..=15 {
                maze.set((y, x), Tile::Lair);
            }
        }
        maze.set(GATE, Tile::Gate);
        for y in 7..=13 {
            maze.open((y, 9));
        }
        for x in 9..=MID {
            maze.open((7, x));
            maze.open((13, x));
        }
        for x in 0..=8 {
            maze.open((TUNNEL_ROW, x));
        }
        let rooms: Vec<Cell> = (1..ROWS).flat_map(|y| (1..=MID).map(move |x| (y, x))).filter(|&cell| is_room(cell)).collect();
        for &room in &rooms {
            maze.open(room);
        }
        let mut seen = vec![false; maze.tiles.len()];
        seen[slot(START)] = true;
        let mut stack = vec![START];
        while let Some(&room) = stack.last() {
            let next: Vec<(Cell, Cell)> = walls_of(room)
                .into_iter()
                .filter(|&(wall, far)| far.1 <= MID && is_room(far) && !locked(wall) && !seen[slot(far)])
                .collect();
            if next.is_empty() {
                stack.pop();
                continue;
            }
            let (wall, far) = next[rng.below(next.len())];
            maze.open(wall);
            seen[slot(far)] = true;
            stack.push(far);
        }
        for &room in &rooms {
            if maze.exits(room) >= 2 {
                continue;
            }
            let closed: Vec<(Cell, Cell)> = walls_of(room)
                .into_iter()
                .filter(|&(wall, far)| is_room(far) && !locked(wall) && maze.tile(wall) == Tile::Wall)
                .collect();
            let dead: Vec<(Cell, Cell)> = closed.iter().copied().filter(|&(_, far)| maze.exits(far) < 2).collect();
            let pool = if dead.is_empty() { closed } else { dead };
            if !pool.is_empty() {
                maze.open(pool[rng.below(pool.len())].0);
            }
        }
        let mut walls: Vec<Cell> = rooms
            .iter()
            .flat_map(|&room| walls_of(room))
            .filter(|&(wall, far)| wall.1 <= MID && is_room(far) && !locked(wall) && maze.tile(wall) == Tile::Wall)
            .map(|(wall, _)| wall)
            .collect();
        walls.sort();
        walls.dedup();
        rng.shuffle(&mut walls);
        for &wall in walls.iter().take(EXTRA_LOOPS) {
            maze.open(wall);
        }
        maze
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    /// Runs the shortest path to the player.
    Hound,
    /// Cuts off the junction the player is heading for.
    Fox,
    /// Goes where it last heard the player eat, then listens around.
    Owl,
    /// Guards the power pellets and only hunts when the player comes close.
    Moth,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum State {
    Home,
    Leaving,
    Active,
    Eyes,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Hunter {
    pub kind: Kind,
    pub pos: Cell,
    pub dir: Cell,
    pub state: State,
    pub frightened: bool,
    reverse: bool,
    progress: f64,
}

impl Hunter {
    fn start(kind: Kind) -> Hunter {
        let (pos, state) = match kind {
            Kind::Hound => (DOOR, State::Active),
            Kind::Fox => (LAIR, State::Home),
            Kind::Owl => ((LAIR.0, LAIR.1 - 2), State::Home),
            Kind::Moth => ((LAIR.0, LAIR.1 + 2), State::Home),
        };
        Hunter { kind, pos, dir: LEFT, state, frightened: false, reverse: false, progress: 0.0 }
    }

    fn corner(&self) -> Cell {
        match self.kind {
            Kind::Hound => (1, COLUMNS - 2),
            Kind::Fox => (1, 1),
            Kind::Owl => (ROWS - 2, COLUMNS - 2),
            Kind::Moth => (ROWS - 2, 1),
        }
    }

    fn color(&self) -> Color {
        match self.kind {
            Kind::Hound => Color::Red,
            Kind::Fox => Color::Magenta,
            Kind::Owl => Color::Cyan,
            Kind::Moth => Color::Green,
        }
    }
}

pub struct Rules {
    pub lives: u32,
    /// Player speed in tiles per second.
    pub speed: f64,
    /// Hunter speed as a share of the player's: level 1, gain per level, cap.
    pub hunters: (f64, f64, f64),
    /// Fright seconds: level 1, loss per level, floor; none after `fright_until`.
    pub fright: (f64, f64, f64),
    pub fright_until: u32,
    /// Pellets eaten before Fox, Owl and Moth leave the lair on level 1.
    pub release: [usize; 3],
    /// A hunter also leaves when no pellet was eaten for this long.
    pub release_seconds: f64,
    /// How often Owl hears where the player last ate (seconds), and how far.
    pub listen: f64,
    pub hearing: i32,
    /// Moth leaves its pellets for a player this close.
    pub guard: i32,
    /// Hound speeds up once this share of the pellets is left.
    pub hound_rush: f64,
}

pub fn rules(level: Level) -> Rules {
    match level {
        Level::Easy => Rules {
            lives: 5,
            speed: 7.0,
            hunters: (0.72, 0.03, 0.9),
            fright: (9.0, 0.5, 3.0),
            fright_until: u32::MAX,
            release: [0, 40, 80],
            release_seconds: 6.0,
            listen: 5.0,
            hearing: 5,
            guard: 4,
            hound_rush: 0.1,
        },
        Level::Normal => Rules {
            lives: 3,
            speed: 8.0,
            hunters: (0.85, 0.03, 1.0),
            fright: (7.0, 1.0, 1.0),
            fright_until: 12,
            release: [0, 30, 60],
            release_seconds: 4.0,
            listen: 3.0,
            hearing: 8,
            guard: 7,
            hound_rush: 0.2,
        },
        Level::Hard => Rules {
            lives: 2,
            speed: 9.0,
            hunters: (0.97, 0.015, 1.04),
            fright: (2.0, 0.0, 2.0),
            fright_until: 4,
            release: [0, 0, 20],
            release_seconds: 2.5,
            listen: 1.5,
            hearing: 12,
            guard: 10,
            hound_rush: 0.4,
        },
    }
}

/// Seconds of rest, hunt, rest, … per level; after the last one they hunt for good.
fn phases(level: Level, number: u32) -> &'static [f64] {
    match (level, number) {
        (Level::Easy, _) => &[9.0, 15.0, 9.0, 15.0, 7.0, 20.0, 5.0],
        (Level::Normal, 1..=2) => &[7.0, 20.0, 7.0, 20.0, 5.0, 20.0, 5.0],
        (Level::Normal, _) => &[5.0, 20.0, 5.0, 25.0, 3.0, 30.0, 1.0],
        (Level::Hard, 1..=2) => &[3.0, 25.0, 2.0, 30.0, 1.0],
        (Level::Hard, _) => &[1.0, 40.0, 1.0],
    }
}

/// Bonus item of a level: points, glyph, color.
fn prize(number: u32) -> (u64, &'static str, Color) {
    match number {
        1 => (100, "◆", Color::Cyan),
        2 => (300, "♣", Color::Green),
        3 => (500, "♠", Color::Magenta),
        4 => (700, "♥", Color::Red),
        n => ((1000 + 500 * (n as u64 - 5)).min(5000), "★", Color::Yellow),
    }
}

fn lay_food(maze: &Maze) -> Vec<u8> {
    let mut food = vec![0; (ROWS * COLUMNS) as usize];
    for y in 0..ROWS {
        for x in 0..COLUMNS {
            let middle = (7..=13).contains(&y) && (9..=17).contains(&x);
            let tunnel = y == TUNNEL_ROW && (x <= 8 || x >= COLUMNS - 9);
            if maze.tile((y, x)) == Tile::Open && !middle && !tunnel && (y, x) != START {
                food[slot((y, x))] = PELLET;
            }
        }
    }
    for cell in POWER {
        food[slot(cell)] = POWER_PELLET;
    }
    food
}

#[derive(Debug, PartialEq, Eq)]
pub enum Step {
    Playing,
    Over,
}

pub struct Chomp {
    pub difficulty: Level,
    pub rules: Rules,
    /// Level number, from 1.
    pub number: u32,
    pub maze: Maze,
    pub food: Vec<u8>,
    pub total: usize,
    pub pellets_left: usize,
    pub eaten: usize,
    pub player: Cell,
    pub dir: Cell,
    pub want: Option<Cell>,
    pub moving: bool,
    chew: bool,
    progress: f64,
    pub hunters: [Hunter; 4],
    pub lives: u32,
    pub score: u64,
    extra_given: bool,
    phase: usize,
    phase_left: f64,
    pub fright_left: f64,
    combo: u32,
    release_timer: f64,
    /// Pellets eaten since the last lost life, which releases hunters sooner.
    since_death: Option<usize>,
    pub last_meal: Option<Cell>,
    /// Where Owl last heard the player eat.
    pub sound: Option<Cell>,
    sound_timer: f64,
    pub bonus: Option<f64>,
    pub popup: Option<(Cell, u64, f64)>,
    /// Seconds of the short stops: after eating a hunter, before a life, dying, level cleared.
    pub freeze: f64,
    pub ready: f64,
    pub dying: f64,
    pub clear: f64,
    time: f64,
}

impl Chomp {
    pub fn new(difficulty: Level) -> Chomp {
        let rules = rules(difficulty);
        let maze = Maze::generate(FIRST_SEED);
        let mut game = Chomp {
            difficulty,
            number: 1,
            food: Vec::new(),
            maze,
            total: 0,
            pellets_left: 0,
            eaten: 0,
            player: START,
            dir: LEFT,
            want: None,
            moving: false,
            chew: false,
            progress: 0.0,
            hunters: [Kind::Hound, Kind::Fox, Kind::Owl, Kind::Moth].map(Hunter::start),
            lives: rules.lives,
            score: 0,
            extra_given: false,
            phase: 0,
            phase_left: 0.0,
            fright_left: 0.0,
            combo: 0,
            release_timer: 0.0,
            since_death: None,
            last_meal: None,
            sound: None,
            sound_timer: 0.0,
            bonus: None,
            popup: None,
            freeze: 0.0,
            ready: 0.0,
            dying: 0.0,
            clear: 0.0,
            time: 0.0,
            rules,
        };
        game.lay_level();
        game
    }

    fn lay_level(&mut self) {
        self.food = lay_food(&self.maze);
        self.total = self.food.iter().filter(|&&food| food != 0).count();
        self.pellets_left = self.total;
        self.eaten = 0;
        self.since_death = None;
        self.last_meal = None;
        self.reset_actors();
    }

    fn next_level(&mut self, rng: &mut Rng) {
        self.number += 1;
        self.maze = Maze::generate(rng.below(1 << 30) as u64 + 1);
        self.lay_level();
    }

    /// Everyone back to the start; pellets stay as they are.
    fn reset_actors(&mut self) {
        self.player = START;
        self.dir = LEFT;
        self.want = None;
        self.moving = false;
        self.progress = 0.0;
        self.hunters = [Kind::Hound, Kind::Fox, Kind::Owl, Kind::Moth].map(Hunter::start);
        self.phase = 0;
        self.phase_left = phases(self.difficulty, self.number)[0];
        self.fright_left = 0.0;
        self.combo = 0;
        self.release_timer = 0.0;
        self.sound = None;
        self.sound_timer = self.rules.listen;
        self.bonus = None;
        self.popup = None;
        self.ready = 2.0;
    }

    pub fn hunting(&self) -> bool {
        self.phase % 2 == 1 || self.phase >= phases(self.difficulty, self.number).len()
    }

    pub fn fright_seconds(&self) -> f64 {
        let (start, loss, floor) = self.rules.fright;
        if self.number > self.rules.fright_until {
            return 0.0;
        }
        (start - loss * (self.number - 1) as f64).max(floor)
    }

    pub fn hunter_speed(&self, index: usize) -> f64 {
        let hunter = self.hunters[index];
        let (start, gain, cap) = self.rules.hunters;
        let base = self.rules.speed * (start + gain * (self.number - 1) as f64).min(cap);
        let rush = hunter.kind == Kind::Hound && (self.pellets_left as f64) <= self.total as f64 * self.rules.hound_rush;
        match hunter.state {
            State::Home => 0.0,
            State::Eyes => self.rules.speed * 2.0,
            State::Leaving => base * 0.6,
            State::Active if hunter.frightened || in_tunnel(hunter.pos) => base * 0.5,
            State::Active if rush => base * 1.08,
            State::Active => base,
        }
    }

    /// Queue a turn for the next junction; reversing happens at once.
    pub fn turn(&mut self, dir: Cell) {
        if dir == back(self.dir) {
            self.dir = dir;
            self.want = None;
        } else {
            self.want = Some(dir);
        }
    }

    /// Turn toward a clicked tile along the axis with the larger distance.
    pub fn steer_toward(&mut self, (y, x): Cell) {
        let (dy, dx) = (y - self.player.0, x - self.player.1);
        if dy == 0 && dx == 0 {
            return;
        }
        let dir = if dy.abs() > dx.abs() {
            if dy < 0 { UP } else { DOWN }
        } else if dx < 0 {
            LEFT
        } else {
            RIGHT
        };
        self.turn(dir);
    }

    pub fn update(&mut self, seconds: f64, rng: &mut Rng) -> Step {
        self.time += seconds;
        if let Some((cell, points, left)) = self.popup {
            self.popup = (left > seconds).then_some((cell, points, left - seconds));
        }
        if self.freeze > 0.0 {
            self.freeze -= seconds;
            return Step::Playing;
        }
        if self.ready > 0.0 {
            self.ready -= seconds;
            return Step::Playing;
        }
        if self.dying > 0.0 {
            self.dying -= seconds;
            if self.dying <= 0.0 {
                self.lives -= 1;
                if self.lives == 0 {
                    return Step::Over;
                }
                self.since_death = Some(0);
                self.reset_actors();
            }
            return Step::Playing;
        }
        if self.clear > 0.0 {
            self.clear -= seconds;
            if self.clear <= 0.0 {
                self.next_level(rng);
            }
            return Step::Playing;
        }
        self.tick(seconds);
        let mut left = seconds;
        while left > 1e-9 && self.dying <= 0.0 && self.clear <= 0.0 && self.freeze <= 0.0 {
            let slice = left.min(FRAME);
            left -= slice;
            self.advance(slice, rng);
        }
        Step::Playing
    }

    fn tick(&mut self, seconds: f64) {
        if self.fright_left > 0.0 {
            // Rest/hunt phases wait while the hunters are frightened.
            self.fright_left -= seconds;
            if self.fright_left <= 0.0 {
                self.fright_left = 0.0;
                for hunter in &mut self.hunters {
                    hunter.frightened = false;
                }
            }
        } else if self.phase < phases(self.difficulty, self.number).len() {
            self.phase_left -= seconds;
            if self.phase_left <= 0.0 {
                self.phase += 1;
                self.phase_left = phases(self.difficulty, self.number).get(self.phase).copied().unwrap_or(f64::INFINITY);
                for hunter in &mut self.hunters {
                    if hunter.state == State::Active {
                        hunter.reverse = true;
                    }
                }
            }
        }
        if let Some(bonus) = self.bonus {
            self.bonus = (bonus > seconds).then_some(bonus - seconds);
        }
        self.sound_timer -= seconds;
        if self.sound_timer <= 0.0 {
            self.sound_timer = self.rules.listen;
            self.sound = self.last_meal;
        }
        self.release_timer += seconds;
        self.release();
    }

    /// Let the next hunter out of the lair once enough pellets were eaten or
    /// the player stopped eating for a while.
    fn release(&mut self) {
        let Some(index) = (1..4).find(|&index| self.hunters[index].state == State::Home) else { return };
        let (eaten, threshold) = match self.since_death {
            Some(eaten) => (eaten, [0, 8, 20][index - 1]),
            None => {
                let [fox, owl, moth] = self.rules.release;
                let thresholds = match self.number {
                    1 => [fox, owl, moth],
                    2 => [0, 0, moth * 2 / 3],
                    _ => [0, 0, 0],
                };
                (self.eaten, thresholds[index - 1])
            }
        };
        if eaten >= threshold || self.release_timer >= self.rules.release_seconds {
            self.hunters[index].state = State::Leaving;
            self.release_timer = 0.0;
        }
    }

    fn advance(&mut self, seconds: f64, rng: &mut Rng) {
        let before_player = self.player;
        let before = self.hunters.map(|hunter| hunter.pos);
        self.progress = (self.progress + self.rules.speed * seconds).min(1.0);
        if self.progress >= 1.0 {
            self.progress -= 1.0;
            self.move_player();
        }
        for index in 0..4 {
            let speed = self.hunter_speed(index);
            let hunter = &mut self.hunters[index];
            hunter.progress = (hunter.progress + speed * seconds).min(1.0);
            if hunter.progress >= 1.0 {
                hunter.progress -= 1.0;
                self.move_hunter(index, rng);
            }
        }
        self.collide(before_player, before);
    }

    fn move_player(&mut self) {
        if let Some(want) = self.want {
            if self.maze.tile(step(self.player, want)) == Tile::Open {
                self.dir = want;
                self.want = None;
            }
        }
        let next = step(self.player, self.dir);
        self.moving = self.maze.tile(next) == Tile::Open;
        if self.moving {
            self.player = next;
            self.chew = !self.chew;
            self.eat();
        }
    }

    fn add(&mut self, points: u64) {
        self.score += points;
        if !self.extra_given && self.score >= EXTRA_LIFE_AT {
            self.extra_given = true;
            self.lives += 1;
        }
    }

    fn eat(&mut self) {
        let at = slot(self.player);
        match self.food[at] {
            PELLET => {
                self.add(10);
                // Chewing costs a moment, so hunters gain on a player eating.
                self.progress -= 0.15;
            }
            POWER_PELLET => {
                self.add(50);
                self.frighten();
            }
            _ => {}
        }
        if self.food[at] != 0 {
            self.food[at] = 0;
            self.eaten += 1;
            self.pellets_left -= 1;
            self.last_meal = Some(self.player);
            self.release_timer = 0.0;
            if let Some(eaten) = &mut self.since_death {
                *eaten += 1;
            }
            if self.eaten == self.total * 3 / 10 || self.eaten == self.total * 7 / 10 {
                self.bonus = Some(9.0);
            }
            if self.pellets_left == 0 {
                self.clear = 2.0;
            }
        }
        if self.player == START && self.bonus.is_some() {
            let points = prize(self.number).0;
            self.add(points);
            self.bonus = None;
            self.popup = Some((START, points, 1.5));
        }
    }

    fn frighten(&mut self) {
        self.combo = 0;
        let seconds = self.fright_seconds();
        self.fright_left = seconds;
        for hunter in &mut self.hunters {
            if hunter.state == State::Active {
                hunter.reverse = true;
            }
            if seconds > 0.0 && hunter.state != State::Eyes {
                hunter.frightened = true;
            }
        }
    }

    /// Where a hunting or resting hunter heads; `None` means wander.
    pub fn target(&self, index: usize) -> Option<Cell> {
        let hunter = self.hunters[index];
        if !self.hunting() {
            return Some(hunter.corner());
        }
        match hunter.kind {
            Kind::Hound => Some(self.player),
            Kind::Fox => {
                let ahead = self.junction_ahead();
                Some(if manhattan(hunter.pos, ahead) <= 2 { self.player } else { ahead })
            }
            Kind::Owl => match self.sound {
                Some(sound) if manhattan(hunter.pos, sound) > 2 => Some(sound),
                _ => (manhattan(hunter.pos, self.player) <= self.rules.hearing).then_some(self.player),
            },
            Kind::Moth => {
                let pellets = POWER.into_iter().filter(|&cell| self.food[slot(cell)] == POWER_PELLET);
                match pellets.min_by_key(|&cell| manhattan(cell, self.player)) {
                    Some(pellet) if manhattan(hunter.pos, self.player) > self.rules.guard => Some(pellet),
                    _ => Some(self.player),
                }
            }
        }
    }

    /// The next junction (or wall) in the player's direction, at most 12 tiles on.
    fn junction_ahead(&self) -> Cell {
        let mut cell = self.player;
        if !self.moving {
            return cell;
        }
        for _ in 0..12 {
            let next = step(cell, self.dir);
            if self.maze.tile(next) != Tile::Open {
                break;
            }
            cell = next;
            if self.maze.exits(cell) >= 3 {
                break;
            }
        }
        cell
    }

    /// Path lengths to `target`; `gate` also lets them cross the gate and lair.
    fn distances(&self, target: Cell, gate: bool) -> Vec<u32> {
        let passable = |cell: Cell| match self.maze.tile(cell) {
            Tile::Open => true,
            Tile::Gate | Tile::Lair => gate,
            Tile::Wall => false,
        };
        let mut distance = vec![u32::MAX; (ROWS * COLUMNS) as usize];
        if !passable(target) {
            return distance;
        }
        distance[slot(target)] = 0;
        let mut queue = VecDeque::from([target]);
        while let Some(cell) = queue.pop_front() {
            for dir in DIRS {
                let next = step(cell, dir);
                if passable(next) && distance[slot(next)] == u32::MAX {
                    distance[slot(next)] = distance[slot(cell)] + 1;
                    queue.push_back(next);
                }
            }
        }
        distance
    }

    fn toward(&self, from: Cell, options: &[Cell], target: Cell, gate: bool) -> Cell {
        let distance = self.distances(target, gate);
        options.iter().copied().min_by_key(|&dir| distance[slot(step(from, dir))]).unwrap_or(LEFT)
    }

    fn move_hunter(&mut self, index: usize, rng: &mut Rng) {
        let hunter = self.hunters[index];
        let dir = match hunter.state {
            State::Home => return,
            State::Leaving => self.toward(hunter.pos, &DIRS, DOOR, true),
            State::Eyes => self.toward(hunter.pos, &DIRS, LAIR, true),
            State::Active if hunter.reverse && self.maze.tile(step(hunter.pos, back(hunter.dir))) == Tile::Open => back(hunter.dir),
            State::Active => {
                // Hunters never turn back on their own, only at phase changes.
                let mut options: Vec<Cell> = DIRS
                    .into_iter()
                    .filter(|&dir| dir != back(hunter.dir) && self.maze.tile(step(hunter.pos, dir)) == Tile::Open)
                    .collect();
                if options.is_empty() {
                    options.push(back(hunter.dir));
                }
                match self.target(index) {
                    Some(target) if !hunter.frightened => self.toward(hunter.pos, &options, target, false),
                    _ => options[rng.below(options.len())],
                }
            }
        };
        let hunter = &mut self.hunters[index];
        hunter.reverse = false;
        hunter.dir = dir;
        hunter.pos = step(hunter.pos, dir);
        match hunter.state {
            State::Leaving if hunter.pos == DOOR => {
                hunter.state = State::Active;
                hunter.dir = LEFT;
            }
            State::Eyes if hunter.pos == LAIR => hunter.state = State::Leaving,
            _ => {}
        }
    }

    /// Meeting on a tile or passing through each other both count.
    fn collide(&mut self, before_player: Cell, before: [Cell; 4]) {
        for (index, start) in before.into_iter().enumerate() {
            let hunter = self.hunters[index];
            if matches!(hunter.state, State::Home | State::Eyes) {
                continue;
            }
            let met = hunter.pos == self.player || (hunter.pos == before_player && start == self.player);
            if !met {
                continue;
            }
            if !hunter.frightened {
                self.dying = 1.5;
                return;
            }
            let points = 200 << self.combo.min(3);
            self.combo += 1;
            self.add(points);
            self.hunters[index].state = State::Eyes;
            self.hunters[index].frightened = false;
            self.popup = Some((self.player, points, 1.0));
            self.freeze = 0.5;
        }
    }
}

struct Layout {
    top: i32,
    left: i32,
}

const DYING: [&str; 9] = ["Ɔ", "U", "C", "∩", "Ɔ", "U", "*", "·", " "];

fn mouth(dir: Cell) -> &'static str {
    match dir {
        UP => "U",
        DOWN => "∩",
        RIGHT => "C",
        _ => "Ɔ",
    }
}

fn draw(screen: &mut dyn Screen, game: &Chomp, layout: &Layout, best: Option<u64>) {
    screen.clear();
    let best = best.map(|best| format!(" · Best {best}")).unwrap_or_default();
    let title = format!("CHOMP · {} · Score {}{best} · Level {}", game.difficulty.name(), game.score, game.number);
    screen.centered(0, &title, Style::fg(Color::Yellow).bold());
    let at = |(y, x): Cell| (layout.top + y, layout.left + x * 2);
    let blink = |rate: f64| (game.time * rate) as i64 % 2 == 0;
    let wall = Style::fg(if game.clear > 0.0 && blink(4.0) { Color::White } else { Color::DarkBlue });
    for y in 0..ROWS {
        for x in 0..COLUMNS {
            let (row, column) = at((y, x));
            match game.maze.tile((y, x)) {
                Tile::Wall => screen.put(row, column, "██", wall),
                Tile::Gate => screen.put(row, column, "──", Style::fg(Color::Magenta)),
                _ => match game.food[slot((y, x))] {
                    PELLET => screen.put(row, column, "· ", Style::fg(Color::White)),
                    POWER_PELLET if game.ready > 0.0 || blink(3.0) => screen.put(row, column, "● ", Style::fg(Color::White).bold()),
                    _ => {}
                },
            }
        }
    }
    if game.bonus.is_some() {
        let (_, glyph, color) = prize(game.number);
        let (row, column) = at(START);
        screen.put(row, column, glyph, Style::fg(color).bold());
    }
    if game.dying <= 0.0 && game.clear <= 0.0 {
        for hunter in &game.hunters {
            let (glyph, style) = if hunter.state == State::Eyes {
                ("°°", Style::fg(Color::White).bold())
            } else if hunter.frightened {
                let ending = game.fright_left < 2.0 && blink(4.0);
                ("Ѫ", Style::fg(if ending { Color::White } else { Color::Blue }).bold())
            } else {
                ("Ѫ", Style::fg(hunter.color()).bold())
            };
            let (row, column) = at(hunter.pos);
            screen.put(row, column, glyph, style);
        }
    }
    if game.freeze <= 0.0 || game.popup.is_none_or(|(cell, _, _)| cell != game.player) {
        let glyph = if game.dying > 0.0 {
            let frame = ((1.5 - game.dying) / 1.5 * DYING.len() as f64) as usize;
            DYING[frame.min(DYING.len() - 1)]
        } else if game.moving && game.chew {
            "●"
        } else {
            mouth(game.dir)
        };
        let (row, column) = at(game.player);
        screen.put(row, column, glyph, Style::fg(Color::Yellow).bold());
    }
    if let Some((cell, points, _)) = game.popup {
        let (row, column) = at(cell);
        screen.put(row, column, &points.to_string(), Style::fg(Color::Cyan).bold());
    }
    if game.ready > 0.0 {
        screen.put(layout.top + 13, layout.left + COLUMNS - 3, "READY!", Style::fg(Color::Yellow).bold());
    }
    let status = layout.top + ROWS;
    let lives = format!("Lives {}", "C ".repeat(game.lives as usize));
    screen.put(status, layout.left, lives.trim_end(), Style::fg(Color::Yellow));
    let level = format!("Level {}", game.number);
    screen.put(status, layout.left + COLUMNS * 2 - level.chars().count() as i32, &level, Style::fg(Color::Gray));
    screen.controls("←↑↓→ / WASD move · click to steer · P pause · Esc quit");
}

pub fn play(screen: &mut dyn Screen, level: Level, rng: &mut Rng, best: Option<u64>) -> io::Result<Played> {
    let (height, width) = screen.size();
    if height < ROWS + 3 || width < COLUMNS * 2 + 2 {
        return too_small(screen, COLUMNS * 2 + 2, ROWS + 3);
    }
    let layout = Layout { top: 1, left: (width - COLUMNS * 2) / 2 };
    let mut game = Chomp::new(level);
    let mut last = screen.now();
    loop {
        draw(screen, &game, &layout, best);
        screen.present()?;
        let deadline = screen.now() + FRAME;
        for input in inputs_until(screen, deadline)? {
            match input {
                Input::Key(Key::Up | Key::Char('w' | 'W')) => game.turn(UP),
                Input::Key(Key::Down | Key::Char('s' | 'S')) => game.turn(DOWN),
                Input::Key(Key::Left | Key::Char('a' | 'A')) => game.turn(LEFT),
                Input::Key(Key::Right | Key::Char('d' | 'D')) => game.turn(RIGHT),
                Input::Click { y, x, button: Button::Left } => game.steer_toward((y - layout.top, (x - layout.left).div_euclid(2))),
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
        let seconds = (now - last).min(0.25);
        last = now;
        if game.update(seconds, rng) == Step::Over {
            draw(screen, &game, &layout, best);
            let details = [format!("Score {} · Level {}", game.score, game.number)];
            let after = finish(screen, "GAME OVER", &details, Some((game.score, best, "chomp")))?;
            return Ok(Played { score: Some(game.score), after });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::super::testing::*;
    use super::*;

    /// A game already past READY with every hunter shut in the lair.
    fn quiet(level: Level) -> Chomp {
        let mut game = Chomp::new(level);
        game.ready = 0.0;
        for hunter in &mut game.hunters {
            hunter.state = State::Home;
            hunter.pos = LAIR;
        }
        game.rules.release_seconds = f64::INFINITY;
        game.rules.release = [usize::MAX; 3];
        game
    }

    fn reachable(maze: &Maze) -> Vec<bool> {
        let mut seen = vec![false; (ROWS * COLUMNS) as usize];
        seen[slot(START)] = true;
        let mut queue = VecDeque::from([START]);
        while let Some(cell) = queue.pop_front() {
            for dir in DIRS {
                let next = step(cell, dir);
                if maze.tile(next) == Tile::Open && !seen[slot(next)] {
                    seen[slot(next)] = true;
                    queue.push_back(next);
                }
            }
        }
        seen
    }

    #[test]
    fn mazes_are_symmetric_braided_and_connected() {
        for seed in (1..60).chain([FIRST_SEED]) {
            let maze = Maze::generate(seed);
            let seen = reachable(&maze);
            for y in 0..ROWS {
                for x in 0..COLUMNS {
                    assert_eq!(maze.tile((y, x)), maze.tile((y, COLUMNS - 1 - x)), "seed {seed} asymmetric at {y},{x}");
                    if maze.tile((y, x)) == Tile::Open {
                        assert!(maze.exits((y, x)) >= 2, "seed {seed}: dead end at {y},{x}");
                        assert!(seen[slot((y, x))], "seed {seed}: {y},{x} unreachable");
                    }
                }
            }
            assert_eq!(maze.tile((TUNNEL_ROW, 0)), Tile::Open);
            assert_eq!(maze.tile(GATE), Tile::Gate);
            assert_eq!(maze.tile(LAIR), Tile::Lair);
            for x in [0, COLUMNS - 1] {
                for y in (0..ROWS).filter(|&y| y != TUNNEL_ROW) {
                    assert_eq!(maze.tile((y, x)), Tile::Wall, "seed {seed}: border open at {y},{x}");
                }
            }
        }
        assert_eq!(Maze::generate(5), Maze::generate(5));
        assert_ne!(Maze::generate(5), Maze::generate(6));
    }

    #[test]
    fn food_fills_the_maze_but_not_the_middle() {
        let game = Chomp::new(Level::Normal);
        assert!(game.total > 150, "{} pellets", game.total);
        assert_eq!(game.food[slot(START)], 0);
        assert_eq!(game.food[slot(DOOR)], 0);
        assert_eq!(game.food[slot((TUNNEL_ROW, 1))], 0);
        assert!(POWER.iter().all(|&cell| game.food[slot(cell)] == POWER_PELLET));
    }

    #[test]
    fn turns_wait_for_an_opening_and_reversals_are_instant() {
        let mut game = quiet(Level::Normal);
        game.player = (1, 1);
        game.dir = RIGHT;
        game.turn(DOWN);
        let mut moves = 0;
        while game.dir != DOWN {
            let below_open = game.maze.tile(step(game.player, DOWN)) == Tile::Open;
            let before = game.player;
            game.move_player();
            moves += 1;
            if below_open {
                assert_eq!(game.player, step(before, DOWN));
            } else {
                assert_eq!(game.player.0, before.0, "moved down through a wall");
            }
            assert!(moves < 30);
        }
        game.turn(UP);
        assert_eq!(game.dir, UP, "reverse is immediate");
        assert_eq!(game.want, None);
    }

    #[test]
    fn walls_stop_the_player_and_the_tunnel_wraps() {
        let mut game = quiet(Level::Normal);
        game.player = (1, 1);
        game.dir = UP;
        game.move_player();
        assert_eq!(game.player, (1, 1));
        assert!(!game.moving);
        game.player = (TUNNEL_ROW, 1);
        game.dir = LEFT;
        game.move_player();
        game.move_player();
        assert_eq!(game.player, (TUNNEL_ROW, COLUMNS - 1));
        assert!(in_tunnel(game.player));
    }

    #[test]
    fn eating_scores_and_slows_the_player_a_little() {
        let mut game = quiet(Level::Normal);
        let pellet = (1..COLUMNS).map(|x| (1, x)).find(|&cell| game.food[slot(cell)] == PELLET).unwrap();
        game.player = (pellet.0, pellet.1 - 1);
        game.dir = RIGHT;
        game.move_player();
        assert_eq!((game.score, game.eaten, game.last_meal), (10, 1, Some(pellet)));
        assert!(game.progress < 0.0);
        assert_eq!(game.pellets_left, game.total - 1);
    }

    #[test]
    fn each_hunter_has_its_own_target() {
        let mut game = quiet(Level::Normal);
        game.phase = 1;
        assert!(game.hunting());
        for hunter in &mut game.hunters {
            hunter.state = State::Active;
            hunter.pos = (ROWS - 2, COLUMNS - 2);
        }
        game.player = (1, 1);
        game.dir = RIGHT;
        game.moving = true;
        assert_eq!(game.target(0), Some(game.player), "Hound chases");
        let ahead = game.junction_ahead();
        assert_ne!(ahead, game.player);
        assert_eq!(game.target(1), Some(ahead), "Fox cuts off");
        game.hunters[1].pos = ahead;
        assert_eq!(game.target(1), Some(game.player), "Fox at the junction goes for the player");
        game.sound = Some((5, 5));
        assert_eq!(game.target(2), Some((5, 5)), "Owl goes to the sound");
        game.hunters[2].pos = (5, 6);
        assert_eq!(game.target(2), None, "Owl wanders when the player is out of earshot");
        game.sound = None;
        game.hunters[2].pos = (2, 2);
        assert_eq!(game.target(2), Some(game.player), "Owl hears a near player");
        assert_eq!(game.target(3), Some(POWER[0]), "Moth guards the power pellet nearest the player");
        game.hunters[3].pos = (2, 1);
        assert_eq!(game.target(3), Some(game.player), "Moth attacks a close player");
        game.hunters[3].pos = (ROWS - 2, COLUMNS - 2);
        for cell in POWER {
            game.food[slot(cell)] = 0;
        }
        assert_eq!(game.target(3), Some(game.player), "with no pellets left Moth hunts");
        game.phase = 0;
        assert_eq!(game.target(0), Some((1, COLUMNS - 2)), "resting hunters go to their corners");
    }

    #[test]
    fn hunters_follow_the_shortest_path_and_never_turn_back() {
        let mut game = quiet(Level::Normal);
        game.phase = 1;
        game.hunters[0] = Hunter { state: State::Active, pos: (1, 1), dir: RIGHT, ..game.hunters[0] };
        game.player = (ROWS - 2, COLUMNS - 2);
        let start = manhattan(game.hunters[0].pos, game.player);
        let mut rng = Rng::constant(0);
        let mut last_dir = RIGHT;
        for _ in 0..12 {
            game.move_hunter(0, &mut rng);
            assert_ne!(game.hunters[0].dir, back(last_dir), "turned back");
            last_dir = game.hunters[0].dir;
        }
        assert!(manhattan(game.hunters[0].pos, game.player) < start);
        game.hunters[0].reverse = true;
        game.move_hunter(0, &mut rng);
        assert_eq!(game.hunters[0].dir, back(last_dir), "phase changes turn hunters around");
    }

    #[test]
    fn power_pellets_frighten_and_hunters_score_in_a_row() {
        let mut game = quiet(Level::Normal);
        game.hunters[0] = Hunter { state: State::Active, pos: (5, 5), ..game.hunters[0] };
        game.player = (POWER[0].0 - 1, POWER[0].1);
        game.dir = DOWN;
        game.move_player();
        assert_eq!(game.score, 50);
        assert_eq!(game.fright_left, 7.0);
        assert!(game.hunters.iter().all(|hunter| hunter.frightened));
        assert!(game.hunters[0].reverse);
        for (index, points) in [200, 400, 800, 1600].into_iter().enumerate() {
            let score = game.score;
            game.hunters[index].state = State::Active;
            game.hunters[index].pos = game.player;
            game.collide(game.player, game.hunters.map(|hunter| hunter.pos));
            assert_eq!(game.score - score, points);
            assert_eq!(game.hunters[index].state, State::Eyes);
        }
        assert_eq!(game.dying, 0.0);
        game.update(0.1, &mut Rng::constant(0));
        assert!(game.freeze <= 0.5, "eating pauses the game briefly");
    }

    #[test]
    fn eyes_return_to_the_lair_and_come_back_out() {
        let mut game = quiet(Level::Normal);
        game.hunters[0] = Hunter { state: State::Eyes, pos: (1, 1), ..game.hunters[0] };
        let mut rng = Rng::constant(0);
        let mut states = Vec::new();
        for _ in 0..80 {
            game.move_hunter(0, &mut rng);
            if states.last() != Some(&game.hunters[0].state) {
                states.push(game.hunters[0].state);
            }
            if game.hunters[0].state == State::Active {
                break;
            }
        }
        assert_eq!(states, [State::Eyes, State::Leaving, State::Active]);
        assert_eq!(game.hunters[0].pos, DOOR);
    }

    #[test]
    fn passing_through_a_hunter_kills_and_a_life_is_lost() {
        let mut game = quiet(Level::Normal);
        game.hunters[0] = Hunter { state: State::Active, pos: (1, 1), ..game.hunters[0] };
        game.player = (1, 2);
        let mut before = game.hunters.map(|hunter| hunter.pos);
        before[0] = (1, 2);
        game.collide((1, 1), before);
        assert!(game.dying > 0.0, "swapped tiles count as a hit");
        let mut rng = Rng::constant(0);
        game.update(2.0, &mut rng);
        assert_eq!(game.lives, 2);
        assert_eq!(game.player, START);
        assert!(game.ready > 0.0);
        assert_eq!(game.hunters[0].pos, DOOR);
        game.lives = 1;
        game.ready = 0.0;
        game.dying = 0.1;
        assert_eq!(game.update(0.2, &mut rng), Step::Over);
    }

    #[test]
    fn extra_life_and_bonus_prize() {
        let mut game = quiet(Level::Normal);
        game.add(EXTRA_LIFE_AT);
        game.add(EXTRA_LIFE_AT);
        assert_eq!(game.lives, 4, "only one extra life");
        game.bonus = Some(5.0);
        game.player = (START.0, START.1 - 1);
        game.food[slot(START)] = 0;
        game.dir = RIGHT;
        game.move_player();
        assert_eq!(game.bonus, None);
        assert_eq!(game.popup.map(|(_, points, _)| points), Some(100));
    }

    #[test]
    fn clearing_the_maze_moves_on_to_a_faster_new_level() {
        let mut game = quiet(Level::Normal);
        let speed = game.hunter_speed(0);
        let fright = game.fright_seconds();
        let maze = game.maze.clone();
        let last = (1..COLUMNS).map(|x| (1, x)).find(|&cell| game.food[slot(cell)] == PELLET).unwrap();
        game.food.iter_mut().for_each(|food| *food = 0);
        game.food[slot(last)] = PELLET;
        game.pellets_left = 1;
        game.player = (last.0, last.1 - 1);
        game.dir = RIGHT;
        game.move_player();
        assert!(game.clear > 0.0);
        game.update(3.0, &mut Rng::seeded(3));
        assert_eq!(game.number, 2);
        assert_ne!(game.maze, maze);
        assert_eq!(game.pellets_left, game.total);
        assert!(game.hunter_speed(0) > speed);
        assert!(game.fright_seconds() < fright);
    }

    #[test]
    fn hard_is_faster_with_shorter_fright_that_runs_out() {
        let normal = Chomp::new(Level::Normal);
        let mut hard = Chomp::new(Level::Hard);
        assert!(hard.hunter_speed(0) > normal.hunter_speed(0));
        assert!(hard.fright_seconds() < normal.fright_seconds());
        assert!(hard.lives < normal.lives);
        hard.number = 5;
        assert_eq!(hard.fright_seconds(), 0.0);
        assert_eq!(Chomp::new(Level::Easy).lives, 5);
    }

    #[test]
    fn hunters_leave_the_lair_one_by_one() {
        let mut game = Chomp::new(Level::Normal);
        game.ready = 0.0;
        game.update(FRAME, &mut Rng::constant(0));
        assert_eq!(game.hunters[1].state, State::Leaving, "Fox leaves at once");
        assert_eq!(game.hunters[2].state, State::Home);
        game.release_timer = game.rules.release_seconds;
        game.update(FRAME, &mut Rng::constant(0));
        assert_eq!(game.hunters[2].state, State::Leaving, "an idle player releases Owl");
    }

    #[test]
    fn clicks_steer_along_the_longer_axis() {
        let mut game = quiet(Level::Normal);
        game.dir = LEFT;
        game.steer_toward((START.0 - 5, START.1 + 1));
        assert_eq!(game.want, Some(UP));
        game.steer_toward((START.0, START.1 + 3));
        assert_eq!(game.dir, RIGHT);
    }

    #[test]
    fn plays_on_a_screen_until_game_over_then_offers_again() {
        let mut screen = Fake::new((24, 80)).idle(30_000).keys(&[special(Key::Esc)]);
        let played = play(&mut screen, Level::Hard, &mut Rng::constant(0), Some(1000)).unwrap();
        assert_eq!(played.after, After::Leave);
        assert!(played.score.is_some());
        assert!(screen.drew("GAME OVER"));
        assert!(screen.drew("Best 1000"));
        assert!(screen.drew("click to steer"));
    }

    #[test]
    fn pause_and_quit_and_small_terminal() {
        let mut screen = Fake::new((24, 80)).keys(&[key('p'), key('p'), key('q')]);
        assert_eq!(play(&mut screen, Level::Easy, &mut Rng::constant(0), None).unwrap().score, None);
        assert!(screen.drew("PAUSED"));
        assert!(screen.drew("READY!"));
        let mut small = Fake::new((20, 50)).keys(&[key('x')]);
        assert_eq!(play(&mut small, Level::Easy, &mut Rng::constant(0), None).unwrap().after, After::Leave);
        assert!(small.drew("needs a 56x24 terminal"));
    }
}
