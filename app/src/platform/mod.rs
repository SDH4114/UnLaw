//! The OS side of the app: menu bar symbols, notifications, terminals and
//! opening files and links. Only macOS exists for now; Linux and Windows get
//! their own module with the same functions.

#[cfg(target_os = "macos")]
mod macos;
#[cfg(target_os = "macos")]
pub use macos::*;

/// `'text'` for a POSIX shell: the terminal runs a typed command line.
pub fn shell_quote(word: &str) -> String {
    if !word.is_empty() && word.chars().all(|c| c.is_ascii_alphanumeric() || "-_./=:@,+%".contains(c)) {
        return word.to_string();
    }
    format!("'{}'", word.replace('\'', r"'\''"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quoting() {
        assert_eq!(shell_quote("awake"), "awake");
        assert_eq!(shell_quote("/Users/a b/ul"), "'/Users/a b/ul'");
        assert_eq!(shell_quote("it's"), r"'it'\''s'");
        assert_eq!(shell_quote(""), "''");
        assert_eq!(shell_quote("$(rm)"), "'$(rm)'");
    }
}
