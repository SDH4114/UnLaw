//! Big chess pieces drawn with quadrant block characters (▘▝▖▗▚▞▛▜▙▟▀▄▌▐█): every cell holds a
//! 2x2 pixel block, so a piece is a small bitmap. Large squares (7x3) get a 10x6 bitmap
//! (5x3 cells), medium squares (5x2) a 6x4 bitmap (3x2 cells); small squares keep the glyph.

use super::board::Kind;

/// Cell for a 2x2 block: bit 1 top-left, 2 top-right, 4 bottom-left, 8 bottom-right.
const QUADRANTS: [char; 16] = [
    ' ', '▘', '▝', '▀', '▖', '▌', '▞', '▛', '▗', '▚', '▐', '▜', '▄', '▙', '▟', '█',
];

#[rustfmt::skip]
const LARGE: [(Kind, [&str; 6]); 6] = [
    (Kind::Pawn, [
        "..........",
        "....##....",
        "...####...",
        "....##....",
        "...####...",
        "..######..",
    ]),
    (Kind::Knight, [
        "....###...",
        "..######..",
        ".#######..",
        ".##..###..",
        "....####..",
        "..######..",
    ]),
    (Kind::Bishop, [
        "....##....",
        "...##.#...",
        "...####...",
        "....##....",
        "...####...",
        "..######..",
    ]),
    (Kind::Rook, [
        ".##.##.##.",
        ".########.",
        "..######..",
        "..######..",
        "..######..",
        ".########.",
    ]),
    (Kind::Queen, [
        ".#..##..#.",
        ".##.##.##.",
        "..######..",
        "...####...",
        "..######..",
        ".########.",
    ]),
    (Kind::King, [
        "....##....",
        "..######..",
        "....##....",
        "..######..",
        "...####...",
        ".########.",
    ]),
];

#[rustfmt::skip]
const MEDIUM: [(Kind, [&str; 4]); 6] = [
    (Kind::Pawn,   ["......", "..##..", ".####.", ".####."]),
    (Kind::Knight, [".###..", "##.##.", "..###.", ".####."]),
    (Kind::Bishop, ["..##..", ".#.##.", "..##..", ".####."]),
    (Kind::Rook,   ["#.##.#", "######", ".####.", "######"]),
    (Kind::Queen,  ["#.##.#", ".####.", "..##..", "######"]),
    (Kind::King,   ["..##..", "######", "..##..", "######"]),
];

/// Turn a bitmap (`#` = ink) with an even number of rows and columns into rows of cells.
fn cells(bitmap: &[&str]) -> Vec<String> {
    let pixel = |row: usize, column: usize| bitmap[row].as_bytes()[column] == b'#';
    (0..bitmap.len() / 2)
        .map(|row| {
            (0..bitmap[0].len() / 2)
                .map(|column| {
                    let (y, x) = (row * 2, column * 2);
                    let bits = pixel(y, x) as usize
                        | (pixel(y, x + 1) as usize) << 1
                        | (pixel(y + 1, x) as usize) << 2
                        | (pixel(y + 1, x + 1) as usize) << 3;
                    QUADRANTS[bits]
                })
                .collect()
        })
        .collect()
}

/// Rows of cells for `kind` in a square `width` columns wide, or `None` when the square is
/// too small for a drawn piece.
pub fn sprite(kind: Kind, width: i32) -> Option<Vec<String>> {
    if width >= 7 {
        LARGE
            .iter()
            .find(|(piece, _)| *piece == kind)
            .map(|(_, bitmap)| cells(bitmap))
    } else if width >= 5 {
        MEDIUM
            .iter()
            .find(|(piece, _)| *piece == kind)
            .map(|(_, bitmap)| cells(bitmap))
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const KINDS: [Kind; 6] = [
        Kind::Pawn,
        Kind::Knight,
        Kind::Bishop,
        Kind::Rook,
        Kind::Queen,
        Kind::King,
    ];

    #[test]
    fn bitmaps_are_even_and_only_ink_or_blank() {
        for (_, bitmap) in LARGE.iter() {
            assert!(bitmap
                .iter()
                .all(|row| row.len() == 10 && row.chars().all(|c| c == '#' || c == '.')));
        }
        for (_, bitmap) in MEDIUM.iter() {
            assert!(bitmap
                .iter()
                .all(|row| row.len() == 6 && row.chars().all(|c| c == '#' || c == '.')));
        }
    }

    #[test]
    fn every_piece_has_a_distinct_sprite_per_size() {
        for width in [7, 5] {
            let drawn: Vec<Vec<String>> = KINDS
                .iter()
                .map(|kind| sprite(*kind, width).unwrap())
                .collect();
            for (index, one) in drawn.iter().enumerate() {
                assert!(one
                    .iter()
                    .all(|row| row.chars().count() == if width == 7 { 5 } else { 3 }));
                assert!(
                    drawn[index + 1..].iter().all(|other| other != one),
                    "width {width}: piece {index} repeats"
                );
            }
        }
        assert_eq!(sprite(Kind::Pawn, 3), None);
    }

    #[test]
    fn quadrants_map_to_the_right_characters() {
        assert_eq!(cells(&["#.", ".#"]), vec!["▚"]);
        assert_eq!(cells(&["##", ".."]), vec!["▀"]);
        assert_eq!(cells(&[".#", "##"]), vec!["▟"]);
        assert_eq!(cells(&["..", ".."]), vec![" "]);
    }
}
