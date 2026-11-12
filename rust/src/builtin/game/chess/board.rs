//! Chess rules: position, legal moves, make/unmake, SAN, FEN and the end of a game.
//!
//! Squares are 0..64 with a1 = 0, h1 = 7, a8 = 56. Moves are generated pseudo-legally and kept
//! when the mover's king is not attacked afterwards. Every position carries a Zobrist hash, used
//! for threefold repetition and by the bot's transposition table.

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Side {
    White,
    Black,
}

impl Side {
    pub fn index(self) -> usize {
        match self {
            Side::White => 0,
            Side::Black => 1,
        }
    }

    pub fn other(self) -> Side {
        match self {
            Side::White => Side::Black,
            Side::Black => Side::White,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Side::White => "White",
            Side::Black => "Black",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Kind {
    Pawn,
    Knight,
    Bishop,
    Rook,
    Queen,
    King,
}

impl Kind {
    pub fn index(self) -> usize {
        self as usize
    }

    /// SAN letter (empty for pawns).
    pub fn letter(self) -> &'static str {
        match self {
            Kind::Pawn => "",
            Kind::Knight => "N",
            Kind::Bishop => "B",
            Kind::Rook => "R",
            Kind::Queen => "Q",
            Kind::King => "K",
        }
    }

    /// Material in pawns, as shown in the side panel.
    pub fn points(self) -> i32 {
        match self {
            Kind::Pawn => 1,
            Kind::Knight | Kind::Bishop => 3,
            Kind::Rook => 5,
            Kind::Queen => 9,
            Kind::King => 0,
        }
    }

    fn from_letter(letter: char) -> Option<Kind> {
        Some(match letter.to_ascii_lowercase() {
            'p' => Kind::Pawn,
            'n' => Kind::Knight,
            'b' => Kind::Bishop,
            'r' => Kind::Rook,
            'q' => Kind::Queen,
            'k' => Kind::King,
            _ => return None,
        })
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Piece {
    pub side: Side,
    pub kind: Kind,
}

impl Piece {
    pub fn new(side: Side, kind: Kind) -> Piece {
        Piece { side, kind }
    }

    fn zobrist_index(self) -> usize {
        self.side.index() * 6 + self.kind.index()
    }

    #[cfg(test)]
    fn fen_letter(self) -> char {
        let letter = match self.kind {
            Kind::Pawn => 'p',
            Kind::Knight => 'n',
            Kind::Bishop => 'b',
            Kind::Rook => 'r',
            Kind::Queen => 'q',
            Kind::King => 'k',
        };
        if self.side == Side::White {
            letter.to_ascii_uppercase()
        } else {
            letter
        }
    }
}

pub fn file_of(square: u8) -> i32 {
    (square % 8) as i32
}

pub fn rank_of(square: u8) -> i32 {
    (square / 8) as i32
}

pub fn square_at(file: i32, rank: i32) -> Option<u8> {
    ((0..8).contains(&file) && (0..8).contains(&rank)).then(|| (rank * 8 + file) as u8)
}

pub fn square_name(square: u8) -> String {
    format!("{}{}", (b'a' + square % 8) as char, square / 8 + 1)
}

pub fn parse_square(name: &str) -> Option<u8> {
    let mut chars = name.chars();
    let file = chars.next()?;
    let rank = chars.next()?;
    if chars.next().is_some() || !('a'..='h').contains(&file) || !('1'..='8').contains(&rank) {
        return None;
    }
    square_at(file as i32 - 'a' as i32, rank as i32 - '1' as i32)
}

pub const CASTLE_WK: u8 = 1;
pub const CASTLE_WQ: u8 = 2;
pub const CASTLE_BK: u8 = 4;
pub const CASTLE_BQ: u8 = 8;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Move {
    pub from: u8,
    pub to: u8,
    pub promotion: Option<Kind>,
    pub flags: u8,
}

impl Move {
    pub const CAPTURE: u8 = 1;
    pub const EN_PASSANT: u8 = 2;
    pub const CASTLE: u8 = 4;
    pub const DOUBLE: u8 = 8;

    fn new(from: u8, to: u8, flags: u8) -> Move {
        Move {
            from,
            to,
            promotion: None,
            flags,
        }
    }

    pub fn is_capture(self) -> bool {
        self.flags & Move::CAPTURE != 0
    }

    /// Coordinate notation, e.g. `e2e4`, `e7e8q` (tests).
    #[cfg(test)]
    pub fn uci(self) -> String {
        let mut text = square_name(self.from) + &square_name(self.to);
        if let Some(kind) = self.promotion {
            text.push_str(&kind.letter().to_ascii_lowercase());
        }
        text
    }
}

/// How a finished game ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Outcome {
    Checkmate(Side),
    Resigned(Side),
    /// The side whose flag fell; a winner without mating material makes it a draw.
    Flag(Side),
    Stalemate,
    FiftyMoves,
    Repetition,
    Material,
    FlagNoMaterial,
}

impl Outcome {
    pub fn winner(self) -> Option<Side> {
        match self {
            Outcome::Checkmate(winner) => Some(winner),
            Outcome::Resigned(loser) | Outcome::Flag(loser) => Some(loser.other()),
            _ => None,
        }
    }

    pub fn describe(self) -> String {
        match self {
            Outcome::Checkmate(winner) => format!("Checkmate · {} wins", winner.name()),
            Outcome::Resigned(loser) => {
                format!("{} resigned · {} wins", loser.name(), loser.other().name())
            }
            Outcome::Flag(loser) => format!(
                "{} ran out of time · {} wins",
                loser.name(),
                loser.other().name()
            ),
            Outcome::Stalemate => "Draw · stalemate".into(),
            Outcome::FiftyMoves => "Draw · 50-move rule".into(),
            Outcome::Repetition => "Draw · threefold repetition".into(),
            Outcome::Material => "Draw · insufficient material".into(),
            Outcome::FlagNoMaterial => "Draw · time out, no mating material".into(),
        }
    }
}

#[derive(Clone, Debug)]
struct Undo {
    mv: Move,
    captured: Option<Piece>,
    castling: u8,
    en_passant: Option<u8>,
    halfmove: u32,
    hash: u64,
}

#[derive(Clone, Debug)]
pub struct Board {
    pub squares: [Option<Piece>; 64],
    pub side: Side,
    pub castling: u8,
    pub en_passant: Option<u8>,
    pub halfmove: u32,
    pub fullmove: u32,
    pub hash: u64,
    kings: [u8; 2],
    history: Vec<Undo>,
}

struct Zobrist {
    pieces: [[u64; 64]; 12],
    side: u64,
    castling: [u64; 16],
    en_passant: [u64; 8],
}

const fn splitmix(state: u64) -> (u64, u64) {
    let state = state.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = state;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    (state, z ^ (z >> 31))
}

const fn zobrist() -> Zobrist {
    let mut table = Zobrist {
        pieces: [[0; 64]; 12],
        side: 0,
        castling: [0; 16],
        en_passant: [0; 8],
    };
    let mut state = 0x1234_5678_9ABC_DEF0u64;
    let mut piece = 0;
    while piece < 12 {
        let mut square = 0;
        while square < 64 {
            let (next, value) = splitmix(state);
            state = next;
            table.pieces[piece][square] = value;
            square += 1;
        }
        piece += 1;
    }
    let (next, value) = splitmix(state);
    state = next;
    table.side = value;
    let mut index = 0;
    while index < 16 {
        let (next, value) = splitmix(state);
        state = next;
        table.castling[index] = value;
        index += 1;
    }
    let mut file = 0;
    while file < 8 {
        let (next, value) = splitmix(state);
        state = next;
        table.en_passant[file] = value;
        file += 1;
    }
    table
}

static ZOBRIST: Zobrist = zobrist();

const KNIGHT: [(i32, i32); 8] = [
    (1, 2),
    (2, 1),
    (2, -1),
    (1, -2),
    (-1, -2),
    (-2, -1),
    (-2, 1),
    (-1, 2),
];
const KING: [(i32, i32); 8] = [
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
    (-1, 0),
    (-1, -1),
    (0, -1),
    (1, -1),
];
const ORTHOGONAL: [(i32, i32); 4] = [(1, 0), (0, 1), (-1, 0), (0, -1)];
const DIAGONAL: [(i32, i32); 4] = [(1, 1), (-1, 1), (-1, -1), (1, -1)];

pub const START_FEN: &str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

/// Castling rights lost when a piece leaves or arrives on a square (rook and king homes).
fn castling_mask(square: u8) -> u8 {
    match square {
        0 => CASTLE_WQ,
        7 => CASTLE_WK,
        4 => CASTLE_WK | CASTLE_WQ,
        56 => CASTLE_BQ,
        63 => CASTLE_BK,
        60 => CASTLE_BK | CASTLE_BQ,
        _ => 0,
    }
}

impl Default for Board {
    fn default() -> Board {
        Board::start()
    }
}

impl Board {
    pub fn start() -> Board {
        Board::from_fen(START_FEN).expect("the start position is valid")
    }

    pub fn from_fen(fen: &str) -> Result<Board, String> {
        let fields: Vec<&str> = fen.split_whitespace().collect();
        if fields.len() < 4 {
            return Err("FEN needs at least 4 fields".into());
        }
        let mut squares = [None; 64];
        let rows: Vec<&str> = fields[0].split('/').collect();
        if rows.len() != 8 {
            return Err("FEN needs 8 ranks".into());
        }
        for (row, text) in rows.iter().enumerate() {
            let rank = 7 - row as i32;
            let mut file = 0;
            for letter in text.chars() {
                if let Some(skip) = letter.to_digit(10) {
                    file += skip as i32;
                    continue;
                }
                let kind = Kind::from_letter(letter).ok_or(format!("bad piece {letter}"))?;
                let side = if letter.is_ascii_uppercase() {
                    Side::White
                } else {
                    Side::Black
                };
                let square = square_at(file, rank).ok_or("rank too long")?;
                squares[square as usize] = Some(Piece::new(side, kind));
                file += 1;
            }
            if file != 8 {
                return Err(format!("rank {} has {file} files", rank + 1));
            }
        }
        let side = match fields[1] {
            "w" => Side::White,
            "b" => Side::Black,
            other => return Err(format!("bad side {other}")),
        };
        let mut castling = 0;
        for letter in fields[2].chars() {
            castling |= match letter {
                'K' => CASTLE_WK,
                'Q' => CASTLE_WQ,
                'k' => CASTLE_BK,
                'q' => CASTLE_BQ,
                '-' => 0,
                other => return Err(format!("bad castling {other}")),
            };
        }
        let en_passant = match fields[3] {
            "-" => None,
            name => Some(parse_square(name).ok_or(format!("bad en passant {name}"))?),
        };
        let halfmove = fields
            .get(4)
            .and_then(|text| text.parse().ok())
            .unwrap_or(0);
        let fullmove = fields
            .get(5)
            .and_then(|text| text.parse().ok())
            .unwrap_or(1)
            .max(1);
        let mut kings = [64u8; 2];
        for (square, piece) in squares.iter().enumerate() {
            if let Some(Piece {
                side,
                kind: Kind::King,
            }) = piece
            {
                if kings[side.index()] != 64 {
                    return Err("two kings of one color".into());
                }
                kings[side.index()] = square as u8;
            }
        }
        if kings.contains(&64) {
            return Err("a king is missing".into());
        }
        let mut board = Board {
            squares,
            side,
            castling,
            en_passant,
            halfmove,
            fullmove,
            hash: 0,
            kings,
            history: Vec::new(),
        };
        board.hash = board.compute_hash();
        Ok(board)
    }

    #[cfg(test)]
    pub fn fen(&self) -> String {
        let mut text = String::new();
        for rank in (0..8).rev() {
            let mut empty = 0;
            for file in 0..8 {
                match self.squares[(rank * 8 + file) as usize] {
                    Some(piece) => {
                        if empty > 0 {
                            text.push_str(&empty.to_string());
                            empty = 0;
                        }
                        text.push(piece.fen_letter());
                    }
                    None => empty += 1,
                }
            }
            if empty > 0 {
                text.push_str(&empty.to_string());
            }
            if rank > 0 {
                text.push('/');
            }
        }
        text.push_str(if self.side == Side::White {
            " w "
        } else {
            " b "
        });
        let rights: String = [
            (CASTLE_WK, 'K'),
            (CASTLE_WQ, 'Q'),
            (CASTLE_BK, 'k'),
            (CASTLE_BQ, 'q'),
        ]
        .iter()
        .filter(|(bit, _)| self.castling & bit != 0)
        .map(|(_, letter)| *letter)
        .collect();
        text.push_str(if rights.is_empty() { "-" } else { &rights });
        text.push(' ');
        text.push_str(&self.en_passant.map_or("-".into(), square_name));
        text.push_str(&format!(" {} {}", self.halfmove, self.fullmove));
        text
    }

    fn compute_hash(&self) -> u64 {
        let mut hash = 0;
        for (square, piece) in self.squares.iter().enumerate() {
            if let Some(piece) = piece {
                hash ^= ZOBRIST.pieces[piece.zobrist_index()][square];
            }
        }
        if self.side == Side::Black {
            hash ^= ZOBRIST.side;
        }
        hash ^= ZOBRIST.castling[self.castling as usize];
        if let Some(square) = self.en_passant {
            hash ^= ZOBRIST.en_passant[(square % 8) as usize];
        }
        hash
    }

    pub fn piece(&self, square: u8) -> Option<Piece> {
        self.squares[square as usize]
    }

    pub fn king(&self, side: Side) -> u8 {
        self.kings[side.index()]
    }

    /// Number of moves made since the position was set up.
    pub fn ply(&self) -> usize {
        self.history.len()
    }

    pub fn last_move(&self) -> Option<Move> {
        self.history.last().map(|undo| undo.mv)
    }

    /// Is `square` attacked by a piece of `by`?
    pub fn attacked(&self, square: u8, by: Side) -> bool {
        let (file, rank) = (file_of(square), rank_of(square));
        let is = |target: Option<u8>, kinds: &[Kind]| -> bool {
            target
                .and_then(|square| self.squares[square as usize])
                .is_some_and(|piece| piece.side == by && kinds.contains(&piece.kind))
        };
        // A pawn of `by` attacks from one rank behind it (seen from `by`).
        let pawn_rank = if by == Side::White {
            rank - 1
        } else {
            rank + 1
        };
        if is(square_at(file - 1, pawn_rank), &[Kind::Pawn])
            || is(square_at(file + 1, pawn_rank), &[Kind::Pawn])
        {
            return true;
        }
        if KNIGHT
            .iter()
            .any(|(df, dr)| is(square_at(file + df, rank + dr), &[Kind::Knight]))
        {
            return true;
        }
        if KING
            .iter()
            .any(|(df, dr)| is(square_at(file + df, rank + dr), &[Kind::King]))
        {
            return true;
        }
        let slides = |directions: &[(i32, i32)], kinds: &[Kind]| -> bool {
            directions.iter().any(|(df, dr)| {
                let (mut f, mut r) = (file + df, rank + dr);
                while let Some(target) = square_at(f, r) {
                    if let Some(piece) = self.squares[target as usize] {
                        return piece.side == by && kinds.contains(&piece.kind);
                    }
                    f += df;
                    r += dr;
                }
                false
            })
        };
        slides(&ORTHOGONAL, &[Kind::Rook, Kind::Queen])
            || slides(&DIAGONAL, &[Kind::Bishop, Kind::Queen])
    }

    pub fn in_check(&self) -> bool {
        self.attacked(self.king(self.side), self.side.other())
    }

    /// Moves that follow piece movement but may leave the own king in check.
    pub fn pseudo_moves(&self, out: &mut Vec<Move>, captures_only: bool) {
        let side = self.side;
        for from in 0..64u8 {
            let Some(piece) = self.squares[from as usize] else {
                continue;
            };
            if piece.side != side {
                continue;
            }
            match piece.kind {
                Kind::Pawn => self.pawn_moves(from, out, captures_only),
                Kind::Knight => self.steps(from, &KNIGHT, out, captures_only),
                Kind::King => {
                    self.steps(from, &KING, out, captures_only);
                    if !captures_only {
                        self.castles(from, out);
                    }
                }
                Kind::Bishop => self.slides(from, &DIAGONAL, out, captures_only),
                Kind::Rook => self.slides(from, &ORTHOGONAL, out, captures_only),
                Kind::Queen => {
                    self.slides(from, &DIAGONAL, out, captures_only);
                    self.slides(from, &ORTHOGONAL, out, captures_only);
                }
            }
        }
    }

    fn push_target(&self, from: u8, to: u8, out: &mut Vec<Move>, captures_only: bool) -> bool {
        match self.squares[to as usize] {
            None => {
                if !captures_only {
                    out.push(Move::new(from, to, 0));
                }
                true
            }
            Some(piece) => {
                if piece.side != self.side {
                    out.push(Move::new(from, to, Move::CAPTURE));
                }
                false
            }
        }
    }

    fn steps(&self, from: u8, deltas: &[(i32, i32)], out: &mut Vec<Move>, captures_only: bool) {
        for (df, dr) in deltas {
            if let Some(to) = square_at(file_of(from) + df, rank_of(from) + dr) {
                self.push_target(from, to, out, captures_only);
            }
        }
    }

    fn slides(
        &self,
        from: u8,
        directions: &[(i32, i32)],
        out: &mut Vec<Move>,
        captures_only: bool,
    ) {
        for (df, dr) in directions {
            let (mut f, mut r) = (file_of(from) + df, rank_of(from) + dr);
            while let Some(to) = square_at(f, r) {
                if !self.push_target(from, to, out, captures_only) {
                    break;
                }
                f += df;
                r += dr;
            }
        }
    }

    fn pawn_moves(&self, from: u8, out: &mut Vec<Move>, captures_only: bool) {
        let (file, rank) = (file_of(from), rank_of(from));
        let (forward, start, last) = if self.side == Side::White {
            (1, 1, 7)
        } else {
            (-1, 6, 0)
        };
        let push = |out: &mut Vec<Move>, to: u8, flags: u8| {
            if rank_of(to) == last {
                for kind in [Kind::Queen, Kind::Rook, Kind::Bishop, Kind::Knight] {
                    out.push(Move {
                        from,
                        to,
                        promotion: Some(kind),
                        flags,
                    });
                }
            } else {
                out.push(Move::new(from, to, flags));
            }
        };
        if let Some(to) = square_at(file, rank + forward) {
            // Promotions count as "captures" for quiescence: they change the material a lot.
            if self.squares[to as usize].is_none() && (!captures_only || rank_of(to) == last) {
                push(out, to, 0);
                if !captures_only && rank == start {
                    let double = square_at(file, rank + 2 * forward).expect("on the board");
                    if self.squares[double as usize].is_none() {
                        out.push(Move::new(from, double, Move::DOUBLE));
                    }
                }
            }
        }
        for df in [-1, 1] {
            let Some(to) = square_at(file + df, rank + forward) else {
                continue;
            };
            match self.squares[to as usize] {
                Some(piece) if piece.side != self.side => push(out, to, Move::CAPTURE),
                None if self.en_passant == Some(to) => {
                    out.push(Move::new(from, to, Move::CAPTURE | Move::EN_PASSANT))
                }
                _ => {}
            }
        }
    }

    fn castles(&self, from: u8, out: &mut Vec<Move>) {
        let (king_side, queen_side, home) = match self.side {
            Side::White => (CASTLE_WK, CASTLE_WQ, 4u8),
            Side::Black => (CASTLE_BK, CASTLE_BQ, 60u8),
        };
        if from != home {
            return;
        }
        let enemy = self.side.other();
        let empty = |squares: &[u8]| {
            squares
                .iter()
                .all(|square| self.squares[*square as usize].is_none())
        };
        let safe = |squares: &[u8]| squares.iter().all(|square| !self.attacked(*square, enemy));
        if self.castling & king_side != 0
            && empty(&[home + 1, home + 2])
            && safe(&[home, home + 1, home + 2])
        {
            out.push(Move::new(home, home + 2, Move::CASTLE));
        }
        if self.castling & queen_side != 0
            && empty(&[home - 1, home - 2, home - 3])
            && safe(&[home, home - 1, home - 2])
        {
            out.push(Move::new(home, home - 2, Move::CASTLE));
        }
    }

    fn set(&mut self, square: u8, piece: Option<Piece>) {
        if let Some(old) = self.squares[square as usize] {
            self.hash ^= ZOBRIST.pieces[old.zobrist_index()][square as usize];
        }
        if let Some(new) = piece {
            self.hash ^= ZOBRIST.pieces[new.zobrist_index()][square as usize];
            if new.kind == Kind::King {
                self.kings[new.side.index()] = square;
            }
        }
        self.squares[square as usize] = piece;
    }

    /// Play `mv` (pseudo-legal); always pair with `unmake`.
    pub fn make(&mut self, mv: Move) {
        let piece = self.squares[mv.from as usize].expect("a move starts on a piece");
        let captured_square = if mv.flags & Move::EN_PASSANT != 0 {
            square_at(file_of(mv.to), rank_of(mv.from)).expect("on the board")
        } else {
            mv.to
        };
        let captured = self.squares[captured_square as usize];
        self.history.push(Undo {
            mv,
            captured,
            castling: self.castling,
            en_passant: self.en_passant,
            halfmove: self.halfmove,
            hash: self.hash,
        });
        if captured_square != mv.to {
            self.set(captured_square, None);
        }
        self.set(mv.from, None);
        self.set(
            mv.to,
            Some(
                mv.promotion
                    .map_or(piece, |kind| Piece::new(piece.side, kind)),
            ),
        );
        if mv.flags & Move::CASTLE != 0 {
            let (rook_from, rook_to) = if mv.to > mv.from {
                (mv.from + 3, mv.from + 1)
            } else {
                (mv.from - 4, mv.from - 1)
            };
            let rook = self.squares[rook_from as usize];
            self.set(rook_from, None);
            self.set(rook_to, rook);
        }
        self.hash ^= ZOBRIST.castling[self.castling as usize];
        self.castling &= !(castling_mask(mv.from) | castling_mask(mv.to));
        self.hash ^= ZOBRIST.castling[self.castling as usize];
        if let Some(square) = self.en_passant {
            self.hash ^= ZOBRIST.en_passant[(square % 8) as usize];
        }
        self.en_passant = (mv.flags & Move::DOUBLE != 0).then(|| (mv.from + mv.to) / 2);
        if let Some(square) = self.en_passant {
            self.hash ^= ZOBRIST.en_passant[(square % 8) as usize];
        }
        self.halfmove = if piece.kind == Kind::Pawn || captured.is_some() {
            0
        } else {
            self.halfmove + 1
        };
        if self.side == Side::Black {
            self.fullmove += 1;
        }
        self.side = self.side.other();
        self.hash ^= ZOBRIST.side;
    }

    pub fn unmake(&mut self) {
        let Some(undo) = self.history.pop() else {
            return;
        };
        let mv = undo.mv;
        self.side = self.side.other();
        if self.side == Side::Black {
            self.fullmove -= 1;
        }
        let moved = self.squares[mv.to as usize].expect("the moved piece is there");
        let piece = if mv.promotion.is_some() {
            Piece::new(moved.side, Kind::Pawn)
        } else {
            moved
        };
        self.set(mv.to, None);
        self.set(mv.from, Some(piece));
        if mv.flags & Move::CASTLE != 0 {
            let (rook_from, rook_to) = if mv.to > mv.from {
                (mv.from + 3, mv.from + 1)
            } else {
                (mv.from - 4, mv.from - 1)
            };
            let rook = self.squares[rook_to as usize];
            self.set(rook_to, None);
            self.set(rook_from, rook);
        }
        if mv.flags & Move::EN_PASSANT != 0 {
            let square = square_at(file_of(mv.to), rank_of(mv.from)).expect("on the board");
            self.set(square, undo.captured);
        } else if undo.captured.is_some() {
            self.set(mv.to, undo.captured);
        }
        self.castling = undo.castling;
        self.en_passant = undo.en_passant;
        self.halfmove = undo.halfmove;
        self.hash = undo.hash;
    }

    /// Pass the turn (the bot's null-move pruning). Never used when in check.
    pub fn make_null(&mut self) -> (Option<u8>, u64) {
        let saved = (self.en_passant, self.hash);
        if let Some(square) = self.en_passant.take() {
            self.hash ^= ZOBRIST.en_passant[(square % 8) as usize];
        }
        self.side = self.side.other();
        self.hash ^= ZOBRIST.side;
        saved
    }

    pub fn unmake_null(&mut self, saved: (Option<u8>, u64)) {
        self.side = self.side.other();
        (self.en_passant, self.hash) = saved;
    }

    /// Does the side that just moved leave its king safe?
    pub fn last_move_legal(&self) -> bool {
        let mover = self.side.other();
        !self.attacked(self.king(mover), self.side)
    }

    pub fn legal_moves(&mut self) -> Vec<Move> {
        let mut pseudo = Vec::with_capacity(64);
        self.pseudo_moves(&mut pseudo, false);
        pseudo
            .into_iter()
            .filter(|mv| {
                self.make(*mv);
                let legal = self.last_move_legal();
                self.unmake();
                legal
            })
            .collect()
    }

    /// How many times the current position has occurred (same side, rights and pieces).
    pub fn repetitions(&self) -> usize {
        let mut count = 1;
        let reversible = (self.halfmove as usize).min(self.history.len());
        let mut back = 2;
        while back <= reversible {
            if self.history[self.history.len() - back].hash == self.hash {
                count += 1;
            }
            back += 2;
        }
        count
    }

    /// True when `side` cannot ever give mate: a bare king, or a king with one knight or bishop.
    pub fn cannot_mate(&self, side: Side) -> bool {
        let mut minors = 0;
        for piece in self
            .squares
            .iter()
            .flatten()
            .filter(|piece| piece.side == side)
        {
            match piece.kind {
                Kind::King => {}
                Kind::Knight | Kind::Bishop => minors += 1,
                _ => return false,
            }
        }
        minors <= 1
    }

    /// Neither side can mate: K v K, K+minor v K, or only bishops all on one square color.
    pub fn insufficient_material(&self) -> bool {
        let mut bishops = [false; 2];
        let mut others = 0;
        for (square, piece) in self.squares.iter().enumerate() {
            let Some(piece) = piece else { continue };
            match piece.kind {
                Kind::King => {}
                Kind::Bishop => {
                    bishops[(file_of(square as u8) + rank_of(square as u8)) as usize % 2] = true
                }
                Kind::Knight => others += 1,
                _ => return false,
            }
        }
        let bishop_count = self
            .squares
            .iter()
            .flatten()
            .filter(|piece| piece.kind == Kind::Bishop)
            .count();
        match (others, bishop_count) {
            (0, 0) | (1, 0) | (0, 1) => true,
            (0, _) => !(bishops[0] && bishops[1]),
            _ => false,
        }
    }

    /// The game's result when it is over by the rules (clock and resignation aside).
    pub fn outcome(&mut self) -> Option<Outcome> {
        if self.legal_moves().is_empty() {
            return Some(if self.in_check() {
                Outcome::Checkmate(self.side.other())
            } else {
                Outcome::Stalemate
            });
        }
        if self.insufficient_material() {
            return Some(Outcome::Material);
        }
        if self.halfmove >= 100 {
            return Some(Outcome::FiftyMoves);
        }
        if self.repetitions() >= 3 {
            return Some(Outcome::Repetition);
        }
        None
    }

    /// Standard algebraic notation of a legal move in the current position.
    pub fn san(&mut self, mv: Move) -> String {
        let piece = self.squares[mv.from as usize].expect("a move starts on a piece");
        let mut text = String::new();
        if mv.flags & Move::CASTLE != 0 {
            text.push_str(if mv.to > mv.from { "O-O" } else { "O-O-O" });
        } else {
            if piece.kind == Kind::Pawn {
                if mv.is_capture() {
                    text.push((b'a' + mv.from % 8) as char);
                }
            } else {
                text.push_str(piece.kind.letter());
                let rivals: Vec<Move> = self
                    .legal_moves()
                    .into_iter()
                    .filter(|other| {
                        other.to == mv.to
                            && other.from != mv.from
                            && self.squares[other.from as usize] == Some(piece)
                    })
                    .collect();
                if !rivals.is_empty() {
                    let same_file = rivals
                        .iter()
                        .any(|other| file_of(other.from) == file_of(mv.from));
                    let same_rank = rivals
                        .iter()
                        .any(|other| rank_of(other.from) == rank_of(mv.from));
                    let name = square_name(mv.from);
                    if !same_file {
                        text.push_str(&name[..1]);
                    } else if !same_rank {
                        text.push_str(&name[1..]);
                    } else {
                        text.push_str(&name);
                    }
                }
            }
            if mv.is_capture() {
                text.push('x');
            }
            text.push_str(&square_name(mv.to));
            if let Some(kind) = mv.promotion {
                text.push('=');
                text.push_str(kind.letter());
            }
        }
        self.make(mv);
        if self.in_check() {
            text.push(if self.legal_moves().is_empty() {
                '#'
            } else {
                '+'
            });
        }
        self.unmake();
        text
    }

    /// Pieces of `side` missing from a full set (promotions can make a count negative: 0 then).
    pub fn captured(&self, side: Side) -> Vec<Kind> {
        let full = [
            (Kind::Queen, 1),
            (Kind::Rook, 2),
            (Kind::Bishop, 2),
            (Kind::Knight, 2),
            (Kind::Pawn, 8),
        ];
        let mut lost = Vec::new();
        for (kind, count) in full {
            let have = self
                .squares
                .iter()
                .flatten()
                .filter(|piece| piece.side == side && piece.kind == kind)
                .count();
            lost.extend(std::iter::repeat_n(kind, (count as usize).saturating_sub(have)));
        }
        lost
    }

    /// White's material minus Black's, in pawns.
    pub fn material_balance(&self) -> i32 {
        self.squares
            .iter()
            .flatten()
            .map(|piece| {
                if piece.side == Side::White {
                    piece.kind.points()
                } else {
                    -piece.kind.points()
                }
            })
            .sum()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn perft(board: &mut Board, depth: u32) -> u64 {
        if depth == 0 {
            return 1;
        }
        let mut moves = Vec::new();
        board.pseudo_moves(&mut moves, false);
        let mut nodes = 0;
        for mv in moves {
            board.make(mv);
            if board.last_move_legal() {
                nodes += perft(board, depth - 1);
            }
            board.unmake();
        }
        nodes
    }

    fn check_perft(fen: &str, expected: &[u64]) {
        let mut board = Board::from_fen(fen).unwrap();
        let before = (board.fen(), board.hash);
        for (depth, count) in expected.iter().enumerate() {
            assert_eq!(
                perft(&mut board, depth as u32 + 1),
                *count,
                "{fen} depth {}",
                depth + 1
            );
        }
        assert_eq!(
            (board.fen(), board.hash),
            before,
            "make/unmake restores the position"
        );
    }

    #[test]
    fn perft_start_position() {
        check_perft(START_FEN, &[20, 400, 8902, 197_281]);
    }

    #[test]
    fn perft_kiwipete_castling_en_passant_promotions() {
        check_perft(
            "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
            &[48, 2039, 97_862],
        );
    }

    #[test]
    fn perft_rook_endgame_with_en_passant_pins() {
        check_perft(
            "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
            &[14, 191, 2812, 43_238],
        );
    }

    #[test]
    fn the_hash_is_updated_incrementally() {
        let mut board =
            Board::from_fen("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
                .unwrap();
        for _ in 0..3 {
            let moves = board.legal_moves();
            for mv in moves {
                board.make(mv);
                assert_eq!(board.hash, board.compute_hash(), "{}", mv.uci());
                board.unmake();
            }
            let mv = board.legal_moves()[5];
            board.make(mv);
        }
    }

    #[test]
    fn fen_round_trips() {
        for fen in [
            START_FEN,
            "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
            "8/8/8/3pP3/8/8/8/k6K w - d6 0 42",
        ] {
            assert_eq!(Board::from_fen(fen).unwrap().fen(), fen);
        }
        assert!(Board::from_fen("8/8/8/8/8/8/8/8 w - - 0 1").is_err());
    }

    fn play(board: &mut Board, sans: &[&str]) {
        for expected in sans {
            let mv = board
                .legal_moves()
                .into_iter()
                .find(|mv| board.clone().san(*mv) == *expected)
                .unwrap_or_else(|| panic!("no move {expected}"));
            board.make(mv);
        }
    }

    #[test]
    fn san_with_disambiguation_checks_and_mate() {
        let mut board = Board::start();
        play(
            &mut board,
            &["e4", "e5", "Qh5", "Nc6", "Bc4", "Nf6", "Qxf7#"],
        );
        assert_eq!(board.outcome(), Some(Outcome::Checkmate(Side::White)));
        let mut rooks = Board::from_fen("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1").unwrap();
        let names: Vec<String> = rooks
            .legal_moves()
            .into_iter()
            .map(|mv| rooks.clone().san(mv))
            .collect();
        assert!(names.contains(&"O-O-O".to_string()), "{names:?}");
        let mut pair = Board::from_fen("4k3/8/8/8/8/8/4K3/R6R w - - 0 1").unwrap();
        let pair_names: Vec<String> = pair.legal_moves().into_iter().map(|mv| pair.clone().san(mv)).collect();
        assert!(pair_names.contains(&"Rad1".to_string()), "{pair_names:?}");
        assert!(pair_names.contains(&"Rhd1".to_string()));
        assert!(names.contains(&"O-O".to_string()));
        assert!(names.contains(&"O-O-O".to_string()));
        assert!(names.contains(&"Ra8+".to_string()));
        let mut knights = Board::from_fen("4k3/8/8/8/8/N7/8/N3K3 w - - 0 1").unwrap();
        let names: Vec<String> = knights
            .legal_moves()
            .into_iter()
            .map(|mv| knights.clone().san(mv))
            .collect();
        assert!(names.contains(&"N1c2".to_string()) && names.contains(&"N3c2".to_string()), "{names:?}");
        let mut promote = Board::from_fen("4k3/1P6/8/8/8/8/8/4K3 w - - 0 1").unwrap();
        let names: Vec<String> = promote
            .legal_moves()
            .into_iter()
            .map(|mv| promote.clone().san(mv))
            .collect();
        assert!(names.contains(&"b8=Q+".to_string()), "{names:?}");
        assert!(names.contains(&"b8=N".to_string()));
    }

    #[test]
    fn en_passant_and_castling_rules() {
        let mut board = Board::start();
        play(&mut board, &["e4", "a6", "e5", "d5", "exd6"]);
        assert!(
            board.piece(parse_square("d5").unwrap()).is_none(),
            "the passed pawn is taken"
        );
        // Castling is refused through an attacked square.
        let mut through = Board::from_fen("4k3/8/8/8/8/8/5r2/4K2R w K - 0 1").unwrap();
        assert!(!through
            .legal_moves()
            .iter()
            .any(|mv| mv.flags & Move::CASTLE != 0));
        // Moving the rook loses the right.
        let mut rook = Board::from_fen("4k3/8/8/8/8/8/8/4K2R w K - 0 1").unwrap();
        play(&mut rook, &["Rh2", "Kd8", "Rh1", "Ke8"]);
        assert!(!rook
            .legal_moves()
            .iter()
            .any(|mv| mv.flags & Move::CASTLE != 0));
    }

    #[test]
    fn draws_by_stalemate_material_fifty_moves_and_repetition() {
        assert_eq!(
            Board::from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
                .unwrap()
                .outcome(),
            Some(Outcome::Stalemate)
        );
        assert_eq!(
            Board::from_fen("8/8/4k3/8/8/2B5/8/4K3 w - - 0 1")
                .unwrap()
                .outcome(),
            Some(Outcome::Material)
        );
        assert_eq!(
            Board::from_fen("8/8/4k3/8/8/2B5/1b6/4K3 w - - 0 1")
                .unwrap()
                .outcome(),
            Some(Outcome::Material),
            "same-color bishops"
        );
        assert_eq!(
            Board::from_fen("8/8/4k3/8/8/2B5/2b5/4K3 w - - 0 1")
                .unwrap()
                .outcome(),
            None,
            "opposite bishops can mate"
        );
        assert_eq!(
            Board::from_fen("8/8/4k3/8/8/8/8/R3K3 w - - 100 80")
                .unwrap()
                .outcome(),
            Some(Outcome::FiftyMoves)
        );
        let mut board = Board::start();
        play(
            &mut board,
            &["Nf3", "Nf6", "Ng1", "Ng8", "Nf3", "Nf6", "Ng1"],
        );
        assert_eq!(board.outcome(), None);
        play(&mut board, &["Ng8"]);
        assert_eq!(board.outcome(), Some(Outcome::Repetition));
        assert!(Board::from_fen("8/8/4k3/8/8/8/8/2N1K3 w - - 0 1")
            .unwrap()
            .cannot_mate(Side::White));
        assert!(!Board::from_fen("8/8/4k3/8/8/8/P7/4K3 w - - 0 1")
            .unwrap()
            .cannot_mate(Side::White));
    }

    #[test]
    fn captured_pieces_and_balance() {
        let mut board = Board::start();
        play(&mut board, &["e4", "d5", "exd5", "Qxd5"]);
        assert_eq!(board.captured(Side::White), vec![Kind::Pawn]);
        assert_eq!(board.captured(Side::Black), vec![Kind::Pawn]);
        assert_eq!(board.material_balance(), 0);
    }
}
