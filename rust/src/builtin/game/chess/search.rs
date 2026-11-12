//! The chess bot: negamax alpha-beta with iterative deepening, quiescence, a transposition
//! table, null-move pruning, MVV-LVA and killer move ordering, and a piece-square evaluation.
//!
//! The search only reads a cloned board, checks a stop flag and a deadline every 1024 nodes,
//! and always returns the best move of the last finished depth (or the first legal move).

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use super::board::{Board, Kind, Move, Side};
use crate::builtin::game::{Level, Rng};

const MATE: i32 = 30_000;
const INFINITY: i32 = 32_000;
const MAX_PLY: usize = 64;

/// Piece values in centipawns for the evaluation.
const VALUE: [i32; 6] = [100, 320, 330, 500, 900, 0];

// Piece-square tables from White's side, a8 first (row 0 = rank 8): flipped for the lookup.
#[rustfmt::skip]
const PAWN: [i32; 64] = [
     0,  0,  0,  0,  0,  0,  0,  0,
    50, 50, 50, 50, 50, 50, 50, 50,
    10, 10, 20, 30, 30, 20, 10, 10,
     5,  5, 10, 25, 25, 10,  5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5, -5,-10,  0,  0,-10, -5,  5,
     5, 10, 10,-20,-20, 10, 10,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
];
#[rustfmt::skip]
const KNIGHT: [i32; 64] = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
];
#[rustfmt::skip]
const BISHOP: [i32; 64] = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
];
#[rustfmt::skip]
const ROOK: [i32; 64] = [
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10, 10, 10, 10, 10,  5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
    -5,  0,  0,  0,  0,  0,  0, -5,
     0,  0,  0,  5,  5,  0,  0,  0,
];
#[rustfmt::skip]
const QUEEN: [i32; 64] = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -10,  0,  5,  5,  5,  5,  0,-10,
     -5,  0,  5,  5,  5,  5,  0, -5,
      0,  0,  5,  5,  5,  5,  0, -5,
    -10,  5,  5,  5,  5,  5,  0,-10,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
];
#[rustfmt::skip]
const KING_MIDDLE: [i32; 64] = [
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -10,-20,-20,-20,-20,-20,-20,-10,
     20, 20,  0,  0,  0,  0, 20, 20,
     20, 30, 10,  0,  0, 10, 30, 20,
];
#[rustfmt::skip]
const KING_END: [i32; 64] = [
    -50,-40,-30,-20,-20,-30,-40,-50,
    -30,-20,-10,  0,  0,-10,-20,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 30, 40, 40, 30,-10,-30,
    -30,-10, 20, 30, 30, 20,-10,-30,
    -30,-30,  0,  0,  0,  0,-30,-30,
    -50,-30,-30,-30,-30,-30,-30,-50,
];

/// Static evaluation from the side to move, in centipawns.
pub fn evaluate(board: &Board) -> i32 {
    let mut score = [0i32; 2];
    let mut phase = 0;
    let mut bishops = [0; 2];
    for piece in board.squares.iter().flatten() {
        phase += match piece.kind {
            Kind::Knight | Kind::Bishop => 1,
            Kind::Rook => 2,
            Kind::Queen => 4,
            _ => 0,
        };
        if piece.kind == Kind::Bishop {
            bishops[piece.side.index()] += 1;
        }
    }
    // 24 = all pieces on the board; the king table blends from middlegame to endgame.
    let phase = phase.min(24);
    for (square, piece) in board.squares.iter().enumerate() {
        let Some(piece) = piece else { continue };
        // Tables are written rank 8 first from White's view.
        let index = if piece.side == Side::White {
            (7 - square / 8) * 8 + square % 8
        } else {
            square
        };
        let positional = match piece.kind {
            Kind::Pawn => PAWN[index],
            Kind::Knight => KNIGHT[index],
            Kind::Bishop => BISHOP[index],
            Kind::Rook => ROOK[index],
            Kind::Queen => QUEEN[index],
            Kind::King => (KING_MIDDLE[index] * phase + KING_END[index] * (24 - phase)) / 24,
        };
        score[piece.side.index()] += VALUE[piece.kind.index()] + positional;
    }
    for side in 0..2 {
        if bishops[side] >= 2 {
            score[side] += 30;
        }
    }
    let white = score[0] - score[1];
    if board.side == Side::White {
        white
    } else {
        -white
    }
}

#[derive(Clone, Copy, Default)]
struct Entry {
    key: u64,
    best: Option<Move>,
    depth: i32,
    score: i32,
    bound: u8,
}

const EXACT: u8 = 0;
const LOWER: u8 = 1;
const UPPER: u8 = 2;
const TABLE_BITS: u32 = 18;

pub struct Limits {
    pub depth: i32,
    pub time: Duration,
}

struct Search<'a> {
    board: Board,
    table: Vec<Entry>,
    killers: [[Option<Move>; 2]; MAX_PLY],
    nodes: u64,
    deadline: Instant,
    stop: &'a AtomicBool,
    stopped: bool,
}

impl Search<'_> {
    fn out_of_time(&mut self) -> bool {
        if self.stopped {
            return true;
        }
        if self.nodes & 1023 == 0
            && (self.stop.load(Ordering::Relaxed) || Instant::now() >= self.deadline)
        {
            self.stopped = true;
        }
        self.stopped
    }

    fn slot(&self, key: u64) -> usize {
        (key as usize) & ((1 << TABLE_BITS) - 1)
    }

    fn order(&self, moves: &mut [Move], best: Option<Move>, ply: usize) {
        let killers = self.killers.get(ply).copied().unwrap_or_default();
        let board = &self.board;
        moves.sort_by_cached_key(|mv| {
            if Some(*mv) == best {
                return -1_000_000;
            }
            if mv.is_capture() {
                let victim = board.piece(mv.to).map_or(Kind::Pawn, |piece| piece.kind);
                let attacker = board.piece(mv.from).map_or(Kind::Pawn, |piece| piece.kind);
                return -100_000 - VALUE[victim.index()] * 10 + VALUE[attacker.index()] / 10;
            }
            if mv.promotion == Some(Kind::Queen) {
                return -90_000;
            }
            if killers.contains(&Some(*mv)) {
                return -50_000;
            }
            0
        });
    }

    fn has_pieces(&self, side: Side) -> bool {
        self.board
            .squares
            .iter()
            .flatten()
            .any(|piece| piece.side == side && !matches!(piece.kind, Kind::Pawn | Kind::King))
    }

    fn quiescence(&mut self, mut alpha: i32, beta: i32, ply: usize) -> i32 {
        self.nodes += 1;
        if self.out_of_time() {
            return 0;
        }
        let stand = evaluate(&self.board);
        if stand >= beta {
            return stand;
        }
        alpha = alpha.max(stand);
        if ply >= MAX_PLY - 1 {
            return stand;
        }
        let mut moves = Vec::with_capacity(16);
        self.board.pseudo_moves(&mut moves, true);
        self.order(&mut moves, None, ply);
        for mv in moves {
            self.board.make(mv);
            if !self.board.last_move_legal() {
                self.board.unmake();
                continue;
            }
            let score = -self.quiescence(-beta, -alpha, ply + 1);
            self.board.unmake();
            if self.stopped {
                return 0;
            }
            if score >= beta {
                return score;
            }
            alpha = alpha.max(score);
        }
        alpha
    }

    fn negamax(&mut self, depth: i32, mut alpha: i32, beta: i32, ply: usize, null_ok: bool) -> i32 {
        self.nodes += 1;
        if self.out_of_time() {
            return 0;
        }
        if ply > 0
            && (self.board.halfmove >= 100
                || self.board.repetitions() >= 2
                || self.board.insufficient_material())
        {
            return 0;
        }
        let in_check = self.board.in_check();
        let depth = if in_check { depth + 1 } else { depth };
        if depth <= 0 || ply >= MAX_PLY - 1 {
            return self.quiescence(alpha, beta, ply);
        }
        let key = self.board.hash;
        let entry = self.table[self.slot(key)];
        let mut best_move = None;
        if entry.key == key {
            best_move = entry.best;
            if ply > 0 && entry.depth >= depth {
                let score = entry.score;
                match entry.bound {
                    EXACT => return score,
                    LOWER if score >= beta => return score,
                    UPPER if score <= alpha => return score,
                    _ => {}
                }
            }
        }
        // Null move: if passing still beats beta, a real move will too (not in check or pawn endings).
        if null_ok
            && !in_check
            && depth >= 3
            && ply > 0
            && self.has_pieces(self.board.side)
            && evaluate(&self.board) >= beta
        {
            let saved = self.board.make_null();
            let score = -self.negamax(depth - 3, -beta, -beta + 1, ply + 1, false);
            self.board.unmake_null(saved);
            if self.stopped {
                return 0;
            }
            if score >= beta {
                return beta;
            }
        }
        let mut moves = Vec::with_capacity(48);
        self.board.pseudo_moves(&mut moves, false);
        self.order(&mut moves, best_move, ply);
        let original_alpha = alpha;
        let mut best = -INFINITY;
        let mut legal = 0;
        for mv in moves {
            self.board.make(mv);
            if !self.board.last_move_legal() {
                self.board.unmake();
                continue;
            }
            legal += 1;
            let score = -self.negamax(depth - 1, -beta, -alpha, ply + 1, true);
            self.board.unmake();
            if self.stopped {
                return 0;
            }
            if score > best {
                best = score;
                best_move = Some(mv);
            }
            if score > alpha {
                alpha = score;
            }
            if alpha >= beta {
                if !mv.is_capture() && ply < MAX_PLY {
                    let killers = &mut self.killers[ply];
                    if killers[0] != Some(mv) {
                        killers[1] = killers[0];
                        killers[0] = Some(mv);
                    }
                }
                break;
            }
        }
        if legal == 0 {
            return if in_check { -MATE + ply as i32 } else { 0 };
        }
        let bound = if best <= original_alpha {
            UPPER
        } else if best >= beta {
            LOWER
        } else {
            EXACT
        };
        let slot = self.slot(key);
        self.table[slot] = Entry {
            key,
            best: best_move,
            depth,
            score: best,
            bound,
        };
        best
    }
}

/// Root moves with their scores at `depth` (full window: used by the easy bot to choose
/// among good moves, and by tests).
fn root_scores(board: &Board, depth: i32, stop: &AtomicBool) -> Vec<(Move, i32)> {
    let mut search = new_search(board, Duration::from_secs(30), stop);
    let moves = search.board.legal_moves();
    let mut scored = Vec::with_capacity(moves.len());
    for mv in moves {
        search.board.make(mv);
        let score = -search.negamax(depth - 1, -INFINITY, INFINITY, 1, true);
        search.board.unmake();
        scored.push((mv, score));
    }
    scored
}

fn new_search<'a>(board: &Board, time: Duration, stop: &'a AtomicBool) -> Search<'a> {
    Search {
        board: board.clone(),
        table: vec![Entry::default(); 1 << TABLE_BITS],
        killers: [[None; 2]; MAX_PLY],
        nodes: 0,
        deadline: Instant::now() + time,
        stop,
        stopped: false,
    }
}

/// Best move within `limits`; `None` only when there is no legal move.
pub fn best_move(board: &Board, limits: &Limits, rng: &mut Rng, stop: &AtomicBool) -> Option<Move> {
    let mut search = new_search(board, limits.time, stop);
    let mut moves = search.board.legal_moves();
    if moves.is_empty() {
        return None;
    }
    // Shuffle so equal moves vary between games; the ordering puts the good ones first anyway.
    rng.shuffle(&mut moves);
    let mut best = moves[0];
    for depth in 1..=limits.depth.max(1) {
        let mut alpha = -INFINITY;
        let mut depth_best = None;
        search.order(&mut moves, Some(best), 0);
        for mv in moves.iter().copied() {
            search.board.make(mv);
            let score = -search.negamax(depth - 1, -INFINITY, -alpha, 1, true);
            search.board.unmake();
            if search.stopped {
                break;
            }
            if score > alpha || depth_best.is_none() {
                alpha = score;
                depth_best = Some(mv);
            }
        }
        if search.stopped {
            // Every move compared so far at this depth was searched in full.
            if let Some(mv) = depth_best {
                best = mv;
            }
            break;
        }
        if let Some(mv) = depth_best {
            best = mv;
        }
        // A forced mate needs no deeper search.
        if alpha.abs() >= MATE - MAX_PLY as i32 {
            break;
        }
    }
    Some(best)
}

/// The move the bot plays at `level`. `clock` is the bot's remaining time, if the game is timed.
pub fn choose(
    board: &Board,
    level: Level,
    clock: Option<f64>,
    rng: &mut Rng,
    stop: &AtomicBool,
) -> Option<Move> {
    match level {
        Level::Easy => {
            let scored = root_scores(board, 2, stop);
            // Noise of ±150 cp: it plays sensible moves but misses tactics and hangs pieces.
            scored
                .into_iter()
                .max_by_key(|(_, score)| score + rng.below(301) as i32 - 150)
                .map(|(mv, _)| mv)
        }
        Level::Normal => {
            let time = budget(0.8, clock);
            best_move(board, &Limits { depth: 4, time }, rng, stop)
        }
        Level::Hard => {
            let time = budget(3.0, clock);
            best_move(
                board,
                &Limits {
                    depth: MAX_PLY as i32 - 2,
                    time,
                },
                rng,
                stop,
            )
        }
    }
}

/// Think for `seconds`, but never more than a thirtieth of the bot's clock (at least 50 ms).
fn budget(seconds: f64, clock: Option<f64>) -> Duration {
    let seconds = clock
        .map_or(seconds, |left| seconds.min(left / 30.0))
        .max(0.05);
    Duration::from_secs_f64(seconds)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn find(board: &Board, depth: i32) -> String {
        let stop = AtomicBool::new(false);
        let limits = Limits {
            depth,
            time: Duration::from_secs(20),
        };
        best_move(board, &limits, &mut Rng::seeded(3), &stop)
            .unwrap()
            .uci()
    }

    #[test]
    fn finds_mate_in_one_and_two() {
        // Back-rank mate.
        let board = Board::from_fen("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1").unwrap();
        assert_eq!(find(&board, 3), "a1a8");
        // King and queen against a king: mates within two moves (Qh8# or a quiet move first).
        let mut board = Board::from_fen("5k2/8/5K2/8/8/8/8/7Q w - - 0 1").unwrap();
        let stop = AtomicBool::new(false);
        let limits = Limits {
            depth: 5,
            time: Duration::from_secs(20),
        };
        let mut rng = Rng::seeded(1);
        for _ in 0..4 {
            if board.outcome().is_some() {
                break;
            }
            let mv = best_move(&board, &limits, &mut rng, &stop).unwrap();
            board.make(mv);
        }
        assert!(
            matches!(
                board.outcome(),
                Some(super::super::board::Outcome::Checkmate(Side::White))
            ),
            "{}",
            board.fen()
        );
    }

    #[test]
    fn takes_a_hanging_queen() {
        let board = Board::from_fen("4k3/8/8/3q4/8/8/3R4/4K3 w - - 0 1").unwrap();
        assert_eq!(find(&board, 3), "d2d5");
    }

    #[test]
    fn a_stop_flag_returns_a_legal_move_at_once() {
        let stop = AtomicBool::new(true);
        let mut board = Board::start();
        let mv = best_move(
            &board,
            &Limits {
                depth: 20,
                time: Duration::from_secs(10),
            },
            &mut Rng::seeded(1),
            &stop,
        )
        .unwrap();
        assert!(board.legal_moves().contains(&mv));
    }

    #[test]
    fn evaluation_is_symmetric() {
        let white =
            Board::from_fen("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
                .unwrap();
        let black =
            Board::from_fen("rnbqkb1r/pppp1ppp/5n2/4p3/4P3/2N5/PPPP1PPP/R1BQKBNR b KQkq - 2 3")
                .unwrap();
        assert_eq!(evaluate(&white), evaluate(&black));
    }

    /// Play a whole game between two levels; returns the outcome from White's view.
    fn game(white: Level, black: Level, seed: u64) -> Option<Side> {
        game_with_clock(white, black, seed, Some(1.5))
    }

    fn game_with_clock(white: Level, black: Level, seed: u64, clock: Option<f64>) -> Option<Side> {
        let stop = AtomicBool::new(false);
        let mut rng = Rng::seeded(seed);
        let mut board = Board::start();
        for _ in 0..120 {
            if let Some(outcome) = board.outcome() {
                return outcome.winner();
            }
            let level = if board.side == Side::White {
                white
            } else {
                black
            };
            // Short fixed thinking keeps the test fast: the clock argument caps it at 1/30.
            let mv = choose(&board, level, clock, &mut rng, &stop).unwrap();
            assert!(board.legal_moves().contains(&mv), "illegal {}", mv.uci());
            board.make(mv);
        }
        None
    }

    #[test]
    fn normal_beats_easy() {
        let mut normal_wins = 0;
        let mut easy_wins = 0;
        for seed in 1..=2 {
            let (white, black) = if seed % 2 == 0 {
                (Level::Normal, Level::Easy)
            } else {
                (Level::Easy, Level::Normal)
            };
            match game(white, black, seed) {
                Some(Side::White) if white == Level::Normal => normal_wins += 1,
                Some(Side::Black) if black == Level::Normal => normal_wins += 1,
                Some(_) => easy_wins += 1,
                None => {}
            }
        }
        assert!(
            normal_wins > easy_wins,
            "normal {normal_wins} : easy {easy_wins}"
        );
        assert_eq!(easy_wins, 0);
    }

    /// Slow (run with `cargo test --release -- --ignored hard_beats_normal`): hard has to stay hard.
    #[test]
    #[ignore]
    fn hard_beats_normal() {
        let mut hard = 0;
        let mut normal = 0;
        for seed in 1..=4 {
            let (white, black) = if seed % 2 == 0 { (Level::Hard, Level::Normal) } else { (Level::Normal, Level::Hard) };
            match game_with_clock(white, black, seed, None) {
                Some(side) if (side == Side::White) == (white == Level::Hard) => hard += 1,
                Some(_) => normal += 1,
                None => {}
            }
        }
        eprintln!("hard {hard} : normal {normal}");
        assert!(hard > normal && normal == 0, "hard {hard} : normal {normal}");
    }
}
