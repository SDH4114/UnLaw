//! `ul app` and `ul browser`: open a macOS application or the configured
//! homepage with `open`. Part of the core, so they are always installed.

use std::process::Command;

use crate::commands::exit_code;
use crate::config::Config;

pub const APP_HELP: &str = "Open a macOS application by name.
Usage: ul app <application>
Example: ul app \"Visual Studio Code\"
";

pub const BROWSER_HELP: &str = "Open a link, search the web, or open the configured homepage in your default browser.
Usage: ul browser [link | words...]
  (none)   Open apps.browser_url (default https://www.google.com/)
  link     An http(s) address; without a scheme https:// is added (github.com/x)
           Other schemes (file:, javascript:, ...) are refused.
  words    Anything else is searched: apps.search_url + the words
           (default https://www.google.com/search?q=)
Settings: apps.browser_url, apps.search_url
Examples:
  ul browser
  ul browser github.com/SDH4114/UnLaw
  ul browser rust borrow checker
  ul config set apps.search_url \"https://duckduckgo.com/?q=\"
";

/// An http(s) URL from what the user typed: `example.com/x` gets `https://`.
/// Refuses spaces, control characters and every other scheme, so `open` never
/// gets an option, a file or a script.
fn web_link(text: &str) -> Result<String, String> {
    let text = text.trim();
    if text.is_empty() || text.chars().any(|c| c.is_whitespace() || c.is_control()) {
        return Err(format!("not a link: {text:?}"));
    }
    let lower = text.to_ascii_lowercase();
    let (link, host) = if let Some(rest) = lower.strip_prefix("https://").or_else(|| lower.strip_prefix("http://")) {
        (text.to_string(), rest.to_string())
    } else if lower.contains("://") || lower.starts_with("javascript:") || lower.starts_with("file:") || lower.starts_with("data:") {
        return Err(format!("only http and https links open: {text}"));
    } else {
        (format!("https://{text}"), lower)
    };
    let host = host.split(['/', '?', '#']).next().unwrap_or("");
    let name = host.rsplit_once('@').map_or(host, |(_, name)| name);
    let name = name.split(':').next().unwrap_or("");
    let plausible = name == "localhost" || (name.contains('.') && !name.starts_with('.') && !name.ends_with('.'));
    if !plausible || !name.starts_with(|c: char| c.is_ascii_alphanumeric() || c == '[') {
        return Err(format!("not a link: {text}"));
    }
    Ok(link)
}

fn is_help(args: &[String]) -> bool {
    matches!(args.first().map(String::as_str), Some("-h" | "--help" | "help"))
}

fn open(name: &str, args: &[String]) -> i32 {
    match Command::new("open").args(args).status() {
        Ok(status) => exit_code(status),
        Err(error) => {
            eprintln!("unlaw {name}: {error}");
            1
        }
    }
}

pub fn app(args: &[String]) -> i32 {
    if is_help(args) {
        print!("{APP_HELP}");
        return 0;
    }
    if args.is_empty() {
        eprintln!("Usage: ul app <application>");
        return 2;
    }
    open("app", &["-a".to_string(), args.join(" ")])
}

pub fn browser(args: &[String], config: &Config) -> i32 {
    if is_help(args) {
        print!("{BROWSER_HELP}");
        return 0;
    }
    if args.is_empty() {
        return open("browser", &[config.string("apps.browser_url")]);
    }
    if let [text] = args {
        if let Ok(link) = web_link(text) {
            return open("browser", &[link]);
        }
    }
    match search_link(&args.join(" "), &config.string("apps.search_url")) {
        Ok(link) => open("browser", &[link]),
        Err(error) => {
            eprintln!("ul browser: {error}");
            eprintln!("Usage: ul browser [link | words...]");
            2
        }
    }
}

/// `apps.search_url` + the words, percent-encoded. Refuses what looks like an
/// option or another scheme (`-a`, `file:///etc/hosts`), and a search address
/// that is not http(s), so `open` only ever gets a web page.
fn search_link(words: &str, search_url: &str) -> Result<String, String> {
    let words = words.trim();
    let lower = words.to_ascii_lowercase();
    if words.is_empty() || words.starts_with('-') || words.chars().any(char::is_control) {
        return Err(format!("not a link or a search: {words:?}"));
    }
    if lower.contains("://") || ["javascript:", "file:", "data:"].iter().any(|scheme| lower.starts_with(scheme)) {
        return Err(format!("only http and https links open: {words}"));
    }
    let base = web_link(search_url).map_err(|_| format!("apps.search_url is not an http(s) address: {search_url:?}"))?;
    let mut query = String::new();
    for byte in words.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => query.push(byte as char),
            _ => query.push_str(&format!("%{byte:02X}")),
        }
    }
    Ok(format!("{base}{query}"))
}

#[cfg(test)]
mod tests {
    use super::{search_link, web_link};

    #[test]
    fn words_are_searched_and_options_or_schemes_are_not() {
        let google = "https://www.google.com/search?q=";
        assert_eq!(search_link("rust borrow checker", google).unwrap(), "https://www.google.com/search?q=rust%20borrow%20checker");
        assert_eq!(search_link("кофе & tea", google).unwrap(), "https://www.google.com/search?q=%D0%BA%D0%BE%D1%84%D0%B5%20%26%20tea");
        for bad in ["-a", "file:///etc/hosts", "javascript:alert(1)", "", "x\ny"] {
            assert!(search_link(bad, google).is_err(), "{bad}");
        }
        assert!(search_link("hello", "file:///x?q=").is_err());
    }

    #[test]
    fn links_get_a_scheme_and_others_are_refused() {
        assert_eq!(web_link("github.com/SDH4114/UnLaw").unwrap(), "https://github.com/SDH4114/UnLaw");
        assert_eq!(web_link(" https://example.com/a?b=1#c ").unwrap(), "https://example.com/a?b=1#c");
        assert_eq!(web_link("HTTP://Example.com").unwrap(), "HTTP://Example.com");
        assert_eq!(web_link("localhost:8080/x").unwrap(), "https://localhost:8080/x");
        for bad in ["", "-a", "--args", "file:///etc/passwd", "javascript:alert(1)", "ftp://x.org", "two words.com",
            "hello", ".com", "example.", "https://", "a\u{7}.com", "data:text/html,x"] {
            assert!(web_link(bad).is_err(), "{bad:?}");
        }
    }
}
