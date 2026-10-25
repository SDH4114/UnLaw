//! Fuzzy matching for pickers and completion (fzf-like scoring).
//!
//! Space-separated terms must all match. A term matches when its chars
//! appear in order; the score rewards word starts, path components,
//! consecutive runs and the file name, and penalizes gaps.

fn is_separator(c: char) -> bool {
    matches!(c, '/' | '\\' | '_' | '-' | '.' | ' ' | ':' | '(' | ')')
}

fn subsequence(pattern: &[char], text: &[char], eq: &impl Fn(char, char) -> bool) -> bool {
    let mut index = 0;
    for c in text {
        if index < pattern.len() && eq(pattern[index], *c) {
            index += 1;
        }
    }
    index == pattern.len()
}

fn boundary(text: &[char], at: usize) -> bool {
    at == 0 || is_separator(text[at - 1]) || (text[at].is_uppercase() && text[at - 1].is_lowercase())
}

/// Positions starting at `start`: each next char is the consecutive one, else the
/// next word start that still leaves room for the rest, else the first occurrence.
fn greedy(pattern: &[char], text: &[char], start: usize, eq: &impl Fn(char, char) -> bool) -> Option<Vec<usize>> {
    let mut positions = vec![start];
    for (number, p) in pattern.iter().enumerate().skip(1) {
        let from = positions.last().copied().unwrap_or(0) + 1;
        let mut choice = None;
        for at in from..text.len() {
            if !eq(*p, text[at]) {
                continue;
            }
            if choice.is_none() {
                choice = Some(at);
            }
            if (at == from || boundary(text, at)) && subsequence(&pattern[number + 1..], &text[at + 1..], eq) {
                choice = Some(at);
                break;
            }
        }
        positions.push(choice?);
    }
    Some(positions)
}

fn score_positions(positions: &[usize], pattern: &[char], text: &[char], case_sensitive: bool) -> i64 {
    let file_start = text.iter().rposition(|c| *c == '/').map_or(0, |at| at + 1);
    let mut score: i64 = 0;
    let mut run = 0i64;
    for (number, found) in positions.iter().copied().enumerate() {
        score += 16;
        if found == 0 || found == file_start {
            score += 12;
        } else if is_separator(text[found - 1]) {
            score += 9;
        } else if text[found].is_uppercase() && text[found - 1].is_lowercase() {
            score += 7;
        }
        if number > 0 {
            let previous = positions[number - 1];
            if previous + 1 == found {
                run += 1;
                score += 6 + run.min(4);
            } else {
                run = 0;
                score -= ((found - previous - 1) as i64).min(12);
            }
        }
        if found >= file_start {
            score += 4;
        }
        if case_sensitive && pattern[number] == text[found] {
            score += 1;
        }
    }
    score - (text.len() as i64) / 24
}

fn term(pattern: &[char], text: &[char], case_sensitive: bool) -> Option<(i64, Vec<usize>)> {
    let eq = |a: char, b: char| if case_sensitive { a == b } else { a.to_lowercase().eq(b.to_lowercase()) };
    if !subsequence(pattern, text, &eq) {
        return None;
    }
    // Try several starts (word starts first) and keep the best placement.
    let mut starts: Vec<usize> = (0..text.len()).filter(|at| eq(pattern[0], text[*at])).collect();
    starts.sort_by_key(|at| !boundary(text, *at));
    starts.truncate(24);
    starts
        .into_iter()
        .filter_map(|start| greedy(pattern, text, start, &eq))
        .map(|positions| (score_positions(&positions, pattern, text, case_sensitive), positions))
        .max_by_key(|(score, positions)| (*score, std::cmp::Reverse(positions[0])))
}

/// Score and matched char positions, or None when `pattern` does not match `text`.
pub fn score(pattern: &str, text: &str) -> Option<(i64, Vec<usize>)> {
    let chars: Vec<char> = text.chars().collect();
    let mut total = 0;
    let mut positions = Vec::new();
    let mut any = false;
    for part in pattern.split_whitespace() {
        any = true;
        let (negate, part) = match part.strip_prefix('!') {
            Some(rest) if !rest.is_empty() => (true, rest),
            _ => (false, part),
        };
        let pattern: Vec<char> = part.chars().collect();
        let case_sensitive = pattern.iter().any(|c| c.is_uppercase());
        let found = term(&pattern, &chars, case_sensitive);
        match (found, negate) {
            (Some(_), true) | (None, false) => return None,
            (None, true) => {}
            (Some((score, found)), false) => {
                total += score;
                positions.extend(found);
            }
        }
    }
    if !any {
        return Some((0, Vec::new()));
    }
    positions.sort_unstable();
    positions.dedup();
    Some((total, positions))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rank<'a>(pattern: &str, items: &[&'a str]) -> Vec<&'a str> {
        let mut scored: Vec<(i64, &str)> =
            items.iter().filter_map(|item| score(pattern, item).map(|(score, _)| (score, *item))).collect();
        scored.sort_by_key(|entry| std::cmp::Reverse(entry.0));
        scored.into_iter().map(|(_, item)| item).collect()
    }

    #[test]
    fn prefers_file_names_and_word_starts() {
        let items = ["src/editor.rs", "src/render.rs", "tests/editor_test.rs", "docs/readme.md"];
        assert_eq!(rank("edit", &items)[0], "src/editor.rs");
        assert_eq!(rank("rend", &items), vec!["src/render.rs"]);
        assert_eq!(rank("et", &items)[0], "tests/editor_test.rs");
        assert!(score("xyz", "src/editor.rs").is_none());
    }

    #[test]
    fn terms_and_negation() {
        assert!(score("src rs", "src/editor.rs").is_some());
        assert!(score("src !test", "src/test.rs").is_none());
        assert!(score("src !test", "src/main.rs").is_some());
        let (_, positions) = score("ed", "src/editor.rs").unwrap();
        assert_eq!(positions, vec![4, 5]);
    }

    #[test]
    fn smart_case() {
        assert!(score("Ed", "src/editor.rs").is_none());
        assert!(score("ed", "src/Editor.rs").is_some());
    }
}
