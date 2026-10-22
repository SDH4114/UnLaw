//! Snake: eat ●, grow and speed up. Cells are two characters wide so the snake
//! moves equally fast in both directions. Turns are buffered, so quick
//! double turns are never lost.

use std::collections::{HashSet, VecDeque};
use std::io;

use super::{finish, inputs_until, pause, too_small, After, Button, Color, Input, Key, Level, Played, Rng, Screen, Style, FRAME};

type Cell = (i32, i32);

const UP: Cell = (-1, 0);
const DOWN: Cell = (1, 0);
const LEFT: Cell = (0, -1);
const RIGHT: Cell = (0, 1);

pub struct Rules {
    pub wrap: bool,
    pub speed: f64,
    pub accel: f64,
    pub max_speed: f64,
    pub growth: u32,
    pub multiplier: u64,
    pub obstacles: usize,
    pub bonus_every: u32,
    pub bonus_seconds: f64,
}

pub fn rules(level: Level) -> Rules {
    match level {
        Level::Easy => Rules {
            wrap: true,
            speed: 7.0,
            accel: 0.15,
            max_speed: 12.0,
            growth: 1,
            multiplier: 1,
            obstacles: 0,
            bonus_every: 5,
            bonus_seconds: 8.0,
        },
        Level::Normal => Rules {
            wrap: false,
            speed: 10.0,
            accel: 0.25,
            max_speed: 18.0,
            growth: 1,
            multiplier: 2,
            obstacles: 0,
            bonus_every: 5,
            bonus_seconds: 6.0,
        },
        Level::Hard => Rules {
            wrap: false,
            speed: 14.0,
            accel: 0.45,
            max_speed: 28.0,
            growth: 2,
            multiplier: 3,
            obstacles: 10,
            bonus_every: 4,
            bonus_seconds: 4.0,
        },
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum Step {
    Moved,
    Ate,
    Died,
    Won,
}

pub struct Snake {
    pub rows: i32,
    pub columns: i32,
    pub body: VecDeque<Cell>,
    pub direction: Cell,
    turns: VecDeque<Cell>,
    pub food: Cell,
    pub bonus: Option<(Cell, f64)>,
    pub obstacles: HashSet<Cell>,
    grow: u32,
    pub score: u64,
    pub eaten: u32,
    pub speed: f64,
    pub rules: Rules,
}

impl Snake {
    pub fn new(level: Level, rows: i32, columns: i32, rng: &mut Rng) -> Snake {
        let rules = rules(level);
        let body: VecDeque<Cell> = (0..4).map(|offset| (rows / 2, columns / 2 - offset)).collect();
        let mut snake = Snake {
            rows,
            columns,
            body,
            direction: RIGHT,
            turns: VecDeque::new(),
            food: (rows / 3, columns / 3),
            bonus: None,
            obstacles: HashSet::new(),
            grow: 0,
            score: 0,
            eaten: 0,
            speed: rules.speed,
            rules,
        };
        snake.add_obstacles(snake.rules.obstacles, rng);
        snake
    }

    fn occupied(&self, cell: Cell) -> bool {
        self.body.contains(&cell) || self.obstacles.contains(&cell) || self.bonus.is_some_and(|(bonus, _)| bonus == cell)
    }

    fn free_cells(&self, keep_clear_of_head: i32) -> Vec<Cell> {
        let head = self.body[0];
        (0..self.rows)
            .flat_map(|y| (0..self.columns).map(move |x| (y, x)))
            .filter(|&cell| !self.occupied(cell) && cell != self.food)
            .filter(|&(y, x)| (y - head.0).abs() + (x - head.1).abs() > keep_clear_of_head)
            .collect()
    }

    fn add_obstacles(&mut self, count: usize, rng: &mut Rng) {
        for _ in 0..count {
            // Keep the area around the head clear and stay off the head's row.
            let free: Vec<Cell> = self.free_cells(4).into_iter().filter(|(y, _)| *y != self.body[0].0).collect();
            if free.is_empty() {
                return;
            }
            self.obstacles.insert(free[rng.below(free.len())]);
        }
    }

    /// Queue a turn; reversing into yourself or repeating a direction is ignored.
    pub fn turn(&mut self, direction: Cell) {
        let last = self.turns.back().copied().unwrap_or(self.direction);
        if direction != last && direction != (-last.0, -last.1) && self.turns.len() < 3 {
            self.turns.push_back(direction);
        }
    }

    /// Turn toward a clicked cell, relative to the head.
    pub fn steer_toward(&mut self, cell: Cell) {
        let last = self.turns.back().copied().unwrap_or(self.direction);
        let head = self.body[0];
        let (dy, dx) = (cell.0 - head.0, cell.1 - head.1);
        if last.0 == 0 && dy != 0 {
            self.turn(if dy < 0 { UP } else { DOWN });
        } else if last.1 == 0 && dx != 0 {
            self.turn(if dx < 0 { LEFT } else { RIGHT });
        }
    }

    pub fn step(&mut self, seconds: f64, rng: &mut Rng) -> Step {
        if let Some(direction) = self.turns.pop_front() {
            self.direction = direction;
        }
        if let Some((cell, left)) = self.bonus {
            self.bonus = (left - seconds > 0.0).then_some((cell, left - seconds));
        }
        let head = self.body[0];
        let mut next = (head.0 + self.direction.0, head.1 + self.direction.1);
        if self.rules.wrap {
            next = (next.0.rem_euclid(self.rows), next.1.rem_euclid(self.columns));
        } else if !(0..self.rows).contains(&next.0) || !(0..self.columns).contains(&next.1) {
            return Step::Died;
        }
        // The tail moves away this step unless the snake is growing.
        let leaving = (self.grow == 0).then(|| *self.body.back().unwrap());
        let hits_body = self.body.iter().any(|&part| part == next && Some(part) != leaving);
        if hits_body || self.obstacles.contains(&next) {
            return Step::Died;
        }
        self.body.push_front(next);
        if self.grow == 0 {
            self.body.pop_back();
        } else {
            self.grow -= 1;
        }
        let multiplier = self.rules.multiplier;
        if let Some((cell, left)) = self.bonus {
            if cell == next {
                self.score += 50 * multiplier + (left * 5.0) as u64 * multiplier;
                self.bonus = None;
                return Step::Ate;
            }
        }
        if next != self.food {
            return Step::Moved;
        }
        self.score += 10 * multiplier;
        self.eaten += 1;
        self.grow += self.rules.growth;
        self.speed = (self.speed + self.rules.accel).min(self.rules.max_speed);
        let free = self.free_cells(0);
        if free.is_empty() {
            return Step::Won;
        }
        self.food = free[rng.below(free.len())];
        if self.eaten % self.rules.bonus_every == 0 {
            let free = self.free_cells(2);
            if !free.is_empty() {
                self.bonus = Some((free[rng.below(free.len())], self.rules.bonus_seconds));
            }
        }
        if self.rules.obstacles > 0 && self.eaten % 5 == 0 && self.obstacles.len() < 40 {
            self.add_obstacles(3, rng);
        }
        Step::Ate
    }
}

struct Layout {
    top: i32,
    left: i32,
}

fn draw(screen: &mut dyn Screen, snake: &Snake, layout: &Layout, level: Level, best: Option<u64>) {
    screen.clear();
    let best = best.map(|best| format!(" · Best {best}")).unwrap_or_default();
    let title = format!("SNAKE · {} · Score {}{best} · Length {}", level.name(), snake.score, snake.body.len());
    screen.centered(0, &title, Style::fg(Color::Yellow).bold());
    let (top, left) = (layout.top, layout.left);
    let wall = if snake.rules.wrap { Style::fg(Color::Gray).dim() } else { Style::fg(Color::White) };
    screen.frame_box(top, left, snake.rows + 2, snake.columns * 2 + 2, wall);
    let at = |(y, x): Cell| (top + 1 + y, left + 1 + x * 2);
    for &cell in &snake.obstacles {
        let (y, x) = at(cell);
        screen.put(y, x, "▓▓", Style::fg(Color::Gray));
    }
    let (y, x) = at(snake.food);
    screen.put(y, x, "● ", Style::fg(Color::Red).bold());
    if let Some((cell, left)) = snake.bonus {
        let (y, x) = at(cell);
        let style = if left < 1.5 { Style::fg(Color::Yellow).dim() } else { Style::fg(Color::Yellow).bold() };
        screen.put(y, x, "★ ", style);
    }
    for (index, &part) in snake.body.iter().enumerate().rev() {
        let (y, x) = at(part);
        let style = if index == 0 { Style::fg(Color::Yellow).bold() } else { Style::fg(Color::Green) };
        screen.put(y, x, if index == 0 { "██" } else { "▓▓" }, style);
    }
    screen.controls("←↑↓→ / WASD move · click to steer · P pause · Esc quit");
}

pub fn play(screen: &mut dyn Screen, level: Level, rng: &mut Rng, best: Option<u64>) -> io::Result<Played> {
    let (height, width) = screen.size();
    let rows = (height - 4).min(30);
    let columns = ((width - 2) / 2).min(40);
    if rows < 12 || columns < 20 {
        return too_small(screen, 42, 16);
    }
    let layout = Layout { top: 1, left: (width - (columns * 2 + 2)) / 2 };
    let mut snake = Snake::new(level, rows, columns, rng);
    let mut next_step = screen.now() + 1.0 / snake.speed;
    loop {
        draw(screen, &snake, &layout, level, best);
        screen.present()?;
        let deadline = (screen.now() + FRAME).min(next_step);
        for input in inputs_until(screen, deadline)? {
            match input {
                Input::Key(Key::Up | Key::Char('w' | 'W')) => snake.turn(UP),
                Input::Key(Key::Down | Key::Char('s' | 'S')) => snake.turn(DOWN),
                Input::Key(Key::Left | Key::Char('a' | 'A')) => snake.turn(LEFT),
                Input::Key(Key::Right | Key::Char('d' | 'D')) => snake.turn(RIGHT),
                Input::Click { y, x, button: Button::Left } => {
                    snake.steer_toward((y - layout.top - 1, (x - layout.left - 1).div_euclid(2)));
                }
                input if input.is_pause() => {
                    if pause(screen)? {
                        return Ok(Played { score: None, after: After::Leave });
                    }
                    next_step = screen.now() + 1.0 / snake.speed;
                }
                input if input.is_leave() => return Ok(Played { score: None, after: After::Leave }),
                _ => {}
            }
        }
        if next_step - screen.now() >= 1e-4 {
            continue;
        }
        let interval = 1.0 / snake.speed;
        next_step += interval;
        if next_step < screen.now() {
            next_step = screen.now() + interval;
        }
        let outcome = snake.step(interval, rng);
        if matches!(outcome, Step::Died | Step::Won) {
            draw(screen, &snake, &layout, level, best);
            let title = if outcome == Step::Won { "YOU WIN — the board is full!" } else { "GAME OVER" };
            let details = [format!("Score {} · Length {}", snake.score, snake.body.len())];
            let after = finish(screen, title, &details, Some((snake.score, best, "snake")))?;
            return Ok(Played { score: Some(snake.score), after });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::super::testing::*;
    use super::*;

    fn snake(level: Level) -> Snake {
        Snake::new(level, 12, 20, &mut Rng::constant(0))
    }

    #[test]
    fn starts_moving_right_with_food_ahead_of_it() {
        let snake = snake(Level::Normal);
        assert_eq!(snake.body.iter().copied().collect::<Vec<_>>(), vec![(6, 10), (6, 9), (6, 8), (6, 7)]);
        assert_eq!(snake.food, (4, 6));
        assert_eq!(snake.direction, RIGHT);
        assert!(snake.obstacles.is_empty());
    }

    #[test]
    fn turns_are_buffered_and_reversals_ignored() {
        let mut snake = snake(Level::Normal);
        snake.turn(LEFT); // reverse: ignored
        snake.turn(RIGHT); // same direction: ignored
        snake.turn(UP);
        snake.turn(LEFT); // quick second turn is kept
        let mut rng = Rng::constant(0);
        snake.step(0.1, &mut rng);
        assert_eq!(snake.body[0], (5, 10));
        snake.step(0.1, &mut rng);
        assert_eq!(snake.body[0], (5, 9));
    }

    #[test]
    fn eating_scores_grows_and_speeds_up() {
        let mut snake = snake(Level::Normal);
        snake.food = (6, 11);
        let speed = snake.speed;
        let mut rng = Rng::constant(0);
        assert_eq!(snake.step(0.1, &mut rng), Step::Ate);
        assert_eq!(snake.score, 20, "normal doubles points");
        assert!(snake.speed > speed);
        snake.step(0.1, &mut rng);
        assert_eq!(snake.body.len(), 5);
    }

    #[test]
    fn walls_kill_except_on_easy() {
        let mut normal = snake(Level::Normal);
        let mut rng = Rng::constant(0);
        normal.food = (0, 0);
        let mut outcome = Step::Moved;
        for _ in 0..20 {
            outcome = normal.step(0.1, &mut rng);
            if outcome == Step::Died {
                break;
            }
        }
        assert_eq!(outcome, Step::Died);
        let mut easy = snake(Level::Easy);
        easy.food = (0, 0);
        for _ in 0..30 {
            assert_ne!(easy.step(0.1, &mut rng), Step::Died);
        }
        assert_eq!(easy.body[0].0, 6, "wrapped around instead of dying");
    }

    #[test]
    fn running_into_itself_dies_but_chasing_the_tail_is_fine() {
        let mut snake = snake(Level::Normal);
        snake.food = (0, 0);
        snake.grow = 2;
        let mut rng = Rng::constant(0);
        snake.step(0.1, &mut rng);
        snake.step(0.1, &mut rng); // length 6
        for direction in [DOWN, LEFT, UP] {
            snake.turn(direction);
            if direction == UP {
                assert_eq!(snake.step(0.1, &mut rng), Step::Died);
            } else {
                snake.step(0.1, &mut rng);
            }
        }
        let mut circle = Snake::new(Level::Normal, 12, 20, &mut Rng::constant(0));
        circle.food = (0, 0);
        circle.body = [(5, 5), (5, 6), (6, 6), (6, 5)].into_iter().collect();
        circle.direction = DOWN;
        assert_eq!(circle.step(0.1, &mut rng), Step::Moved, "the tail moves out of the way");
    }

    #[test]
    fn bonus_food_appears_scores_more_and_expires() {
        let mut snake = snake(Level::Hard);
        let mut rng = Rng::constant(0);
        snake.eaten = snake.rules.bonus_every - 1;
        snake.food = (6, 11);
        snake.step(0.1, &mut rng);
        let (cell, seconds) = snake.bonus.expect("bonus appears");
        assert_eq!(seconds, 4.0);
        assert!(!snake.body.contains(&cell));
        snake.bonus = Some(((6, 12), 2.0));
        let before = snake.score;
        assert_eq!(snake.step(0.1, &mut rng), Step::Ate);
        assert_eq!(snake.score - before, 150 + 9 * 3);
        snake.bonus = Some(((0, 0), 0.05));
        snake.step(0.1, &mut rng);
        assert_eq!(snake.bonus, None);
    }

    #[test]
    fn hard_has_obstacles_away_from_the_head() {
        let snake = Snake::new(Level::Hard, 12, 20, &mut Rng::seeded(7));
        assert_eq!(snake.obstacles.len(), 10);
        let head = snake.body[0];
        assert!(snake.obstacles.iter().all(|&(y, x)| (y - head.0).abs() + (x - head.1).abs() > 4 && y != head.0));
        assert_eq!(snake.rules.growth, 2);
    }

    #[test]
    fn clicks_steer_relative_to_the_head() {
        let mut snake = snake(Level::Normal);
        snake.steer_toward((2, 3)); // above and left while moving right: go up
        snake.step(0.1, &mut Rng::constant(0));
        assert_eq!(snake.direction, UP);
        snake.steer_toward((5, 15)); // then right
        snake.step(0.1, &mut Rng::constant(0));
        assert_eq!(snake.direction, RIGHT);
    }

    #[test]
    fn plays_on_a_screen_until_game_over_then_offers_again() {
        let mut screen = Fake::new((24, 80)).idle(400).keys(&[special(Key::Esc)]);
        let played = play(&mut screen, Level::Normal, &mut Rng::constant(0), Some(1000)).unwrap();
        assert_eq!(played.after, After::Leave);
        assert!(screen.drew("GAME OVER"));
        assert!(screen.drew("Best 1000"));
        assert!(screen.drew("click to steer"));
    }

    #[test]
    fn pause_and_quit_and_small_terminal() {
        let mut screen = Fake::new((24, 80)).keys(&[key('p'), key('p'), key('q')]);
        assert_eq!(play(&mut screen, Level::Easy, &mut Rng::constant(0), None).unwrap().score, None);
        assert!(screen.drew("PAUSED"));
        let mut small = Fake::new((10, 30)).keys(&[key('x')]);
        assert_eq!(play(&mut small, Level::Easy, &mut Rng::constant(0), None).unwrap().after, After::Leave);
    }
}
