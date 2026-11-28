//! Status text for a pinned command: `{path|filter}` over the JSON a command
//! prints (`ul awake status --json`), or the command's own text.

use serde_json::Value;

use crate::spec::Status;

/// At most this many characters reach the menu bar.
pub const MAX_STATUS: usize = 40;

#[derive(Clone, Debug, PartialEq)]
pub struct StatusText {
    pub text: String,
    /// `on`, `off` or `warn`, when the command or `when` says so.
    pub state: Option<String>,
    /// The icon for this state (`status.icon` / `status.otherwise_icon`), when the description sets one.
    pub icon: Option<String>,
}

fn lookup<'a>(json: &'a Value, path: &str) -> Option<&'a Value> {
    path.split('.').try_fold(json, |value, key| match value {
        Value::Array(items) => key.parse::<usize>().ok().and_then(|index| items.get(index)),
        Value::Object(map) => map.get(key),
        _ => None,
    })
}

fn number_text(number: f64) -> String {
    if number.fract() == 0.0 && number.abs() < 1e15 {
        format!("{}", number as i64)
    } else {
        let text = format!("{number:.2}");
        text.trim_end_matches('0').trim_end_matches('.').to_string()
    }
}

fn plain(value: &Value) -> String {
    match value {
        Value::Null => String::new(),
        Value::Bool(on) => on.to_string(),
        Value::Number(number) => number.as_f64().map(number_text).unwrap_or_default(),
        Value::String(text) => text.clone(),
        other => other.to_string(),
    }
}

/// Seconds as `m:ss` under an hour, `h:mm` from an hour on.
pub fn clock(seconds: f64) -> String {
    let seconds = seconds.max(0.0).round() as u64;
    if seconds >= 3600 {
        format!("{}:{:02}", seconds / 3600, seconds % 3600 / 60)
    } else {
        format!("{}:{:02}", seconds / 60, seconds % 60)
    }
}

/// A JSON number, or a string holding one (`"50"`), as some commands print them.
fn as_number(value: &Value) -> Option<f64> {
    value.as_f64().or_else(|| value.as_str().and_then(|text| text.trim().parse().ok()))
}

fn filtered(value: &Value, filter: &str) -> Result<String, String> {
    if filter.is_empty() {
        return Ok(plain(value));
    }
    if !["int", "pct", "clock", "gb", "speed", "weather"].contains(&filter) {
        return Err(format!("unknown filter |{filter} (int, pct, clock, gb, speed, weather)"));
    }
    let Some(number) = as_number(value) else {
        return Ok(if value.is_null() { "–".into() } else { plain(value) });
    };
    Ok(match filter {
        // A WMO weather code (Open-Meteo, `ul weather --json`) as a menu bar icon name.
        "weather" => weather_icon(number as i64).into(),
        "pct" => format!("{}%", number.round() as i64),
        "clock" => clock(number),
        // 1024^3, the way macOS (Activity Monitor, About This Mac) counts memory "GB".
        "gb" => format!("{:.1} GB", number / 1_073_741_824.0),
        // Bytes per second, short enough for the menu bar.
        "speed" if number < 1_000_000.0 => format!("{} KB/s", (number / 1000.0).round() as i64),
        "speed" => format!("{:.1} MB/s", number / 1_000_000.0),
        _ => format!("{}", number.round() as i64),
    })
}

/// The icon of a WMO weather code, the same groups as the weather view's (views.js `wxIcon`).
pub fn weather_icon(code: i64) -> &'static str {
    match code {
        0 => "sun",
        1 | 2 => "cloudsun",
        3 => "overcast",
        45 | 48 => "fog",
        71..=77 | 85 | 86 => "snow",
        95..=99 => "storm",
        51..=67 | 80..=82 => "rain",
        _ => "cloud",
    }
}

/// Fill `text` from `json`. A missing value shows as `–`.
pub fn render(text: &str, json: &Value) -> Result<String, String> {
    let mut out = String::new();
    let mut rest = text;
    while let Some(index) = rest.find(['{', '}']) {
        out.push_str(&rest[..index]);
        let tail = &rest[index..];
        if tail.starts_with("{{") || tail.starts_with("}}") {
            out.push_str(&tail[..1]);
            rest = &tail[2..];
            continue;
        }
        if tail.starts_with('}') {
            return Err("unmatched } (write }} for a brace)".into());
        }
        let Some(end) = tail.find('}') else {
            return Err("unclosed { (write {{ for a brace)".into());
        };
        let inner = &tail[1..end];
        let (path, filter) = inner.split_once('|').unwrap_or((inner, ""));
        let (path, filter) = (path.trim(), filter.trim());
        if path.is_empty() || path.contains('{') {
            return Err(format!("bad placeholder {{{inner}}}"));
        }
        // `{used/total}`: the first value as a percent of the second.
        let ratio;
        let found = match path.split_once('/') {
            Some((part, whole)) => {
                let number = |path: &str| lookup(json, path.trim()).and_then(as_number);
                ratio = match (number(part), number(whole)) {
                    (Some(part), Some(whole)) if whole != 0.0 => {
                        serde_json::Number::from_f64(part / whole * 100.0).map(Value::Number)
                    }
                    _ => None,
                };
                ratio.as_ref()
            }
            None => lookup(json, path),
        };
        match found {
            Some(value) => out.push_str(&filtered(value, filter)?),
            None => {
                filtered(&Value::Null, filter)?;
                out.push('–');
            }
        }
        rest = &tail[end + 1..];
    }
    out.push_str(rest);
    Ok(out)
}

/// Control characters out, whitespace runs folded, at most `MAX_STATUS` characters.
pub fn clean(text: &str) -> String {
    let folded = text.split_whitespace().collect::<Vec<_>>().join(" ");
    let printable: String = folded.chars().filter(|c| !c.is_control()).collect();
    if printable.chars().count() > MAX_STATUS {
        printable.chars().take(MAX_STATUS - 1).chain(std::iter::once('…')).collect()
    } else {
        printable
    }
}

fn truthy(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) => false,
        Some(Value::Bool(on)) => *on,
        Some(Value::Number(number)) => number.as_f64().is_some_and(|n| n != 0.0),
        Some(Value::String(text)) => !text.is_empty(),
        Some(Value::Array(items)) => !items.is_empty(),
        Some(Value::Object(map)) => !map.is_empty(),
    }
}

/// What a pinned item shows after its status command printed `stdout`.
pub fn status_text(status: &Status, stdout: &str) -> StatusText {
    let json: Option<Value> = serde_json::from_str(stdout.trim()).ok().filter(Value::is_object);
    let Some(json) = json else {
        let line = stdout.lines().map(str::trim).find(|line| !line.is_empty()).unwrap_or("");
        return StatusText { text: clean(line), state: None, icon: None };
    };
    let state = json.get("state").and_then(Value::as_str).filter(|state| ["on", "off", "warn"].contains(state));
    if let Some(when) = &status.when {
        if !truthy(lookup(&json, when)) {
            let text = status.otherwise.clone().unwrap_or_default();
            return StatusText {
                text: clean(&text),
                state: Some(state.unwrap_or("off").to_string()),
                icon: status.otherwise_icon.clone(),
            };
        }
    }
    let text = match &status.text {
        Some(template) => render(template, &json).unwrap_or_else(|error| format!("error: {error}")),
        None => json.get("text").map(plain).unwrap_or_default(),
    };
    let default_state = status.when.as_ref().map(|_| "on");
    let icon = match &status.icon {
        Some(template) if template.contains('{') => render(template, &json).ok().filter(|name| name != "–"),
        other => other.clone(),
    };
    StatusText { text: clean(&text), state: state.or(default_state).map(str::to_string), icon }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn status(text: Option<&str>, when: Option<&str>, otherwise: Option<&str>) -> Status {
        Status {
            args: vec![],
            every: 15,
            text: text.map(Into::into),
            when: when.map(Into::into),
            otherwise: otherwise.map(Into::into),
            icon: None,
            otherwise_icon: None,
        }
    }

    #[test]
    fn awake_is_a_full_cup_or_an_empty_one() {
        let s = Status {
            text: Some(String::new()),
            otherwise: Some(String::new()),
            icon: Some("cup-hot".into()),
            otherwise_icon: Some("cup".into()),
            ..status(None, Some("active"), None)
        };
        let on = status_text(&s, r#"{"active": true, "remaining_seconds": 5040}"#);
        assert_eq!((on.text.as_str(), on.icon.as_deref()), ("", Some("cup-hot")));
        let off = status_text(&s, r#"{"active": false}"#);
        assert_eq!((off.text.as_str(), off.icon.as_deref()), ("", Some("cup")));
    }

    #[test]
    fn awake_shows_time_left_or_off() {
        let s = status(Some("{remaining_seconds|clock}"), Some("active"), Some("off"));
        let on = status_text(&s, r#"{"active": true, "remaining_seconds": 5040}"#);
        assert_eq!(on, StatusText { text: "1:24".into(), state: Some("on".into()), icon: None });
        let short = status_text(&s, r#"{"active": true, "remaining_seconds": 125}"#);
        assert_eq!(short.text, "2:05");
        let forever = status_text(&s, r#"{"active": true, "remaining_seconds": null}"#);
        assert_eq!(forever.text, "–");
        let off = status_text(&s, r#"{"active": false, "remaining_seconds": null}"#);
        assert_eq!(off, StatusText { text: "off".into(), state: Some("off".into()), icon: None });
    }

    #[test]
    fn sys_numbers_and_filters() {
        let json =
            json!({"cpu": {"usage_percent": 14.6}, "memory": {"used_bytes": 14657470464u64}, "list": [{"n": 2.5}]});
        assert_eq!(
            render("CPU {cpu.usage_percent|int}% · {memory.used_bytes|gb}", &json).unwrap(),
            "CPU 15% · 13.7 GB"
        );
        let memory = json!({"memory": {"used_bytes": 13_778_000_000u64, "total_bytes": 19_327_352_832u64, "zero": 0}});
        assert_eq!(render("RAM {memory.used_bytes/memory.total_bytes|pct}", &memory).unwrap(), "RAM 71%");
        assert_eq!(render("{a/b|pct}", &json!({"a": "50", "b": "100"})).unwrap(), "50%", "numbers as text count too");
        assert_eq!(render("{memory.used_bytes / memory.total_bytes|int}", &memory).unwrap(), "71");
        assert_eq!(
            render("{memory.used_bytes/memory.zero|pct} {memory.nope/memory.total_bytes}", &memory).unwrap(),
            "– –"
        );
        assert_eq!(render("{memory.total_bytes|gb}", &memory).unwrap(), "18.0 GB", "18 GB like About This Mac");
        assert_eq!(render("{cpu.usage_percent|pct} {list.0.n} {nope} {{x}}", &json).unwrap(), "15% 2.5 – {x}");
        assert!(render("{cpu.usage_percent|weird}", &json).unwrap_err().contains("unknown filter"));
        assert!(render("{nope|weird}", &json).is_err(), "a bad filter is an error even without a value");
        assert!(render("{open", &json).is_err());
        let net = json!({"down": 2_480_000, "up": 640});
        assert_eq!(render("{down|speed} {up|speed}", &net).unwrap(), "2.5 MB/s 1 KB/s");
    }

    #[test]
    fn plain_text_and_text_key() {
        let s = status(None, None, None);
        assert_eq!(status_text(&s, "\n  42 cards \u{1b}[31m\nmore").text, "42 cards [31m");
        assert_eq!(
            status_text(&s, r#"{"text": "hi", "state": "warn"}"#),
            StatusText { text: "hi".into(), state: Some("warn".into()), icon: None }
        );
        assert_eq!(status_text(&s, r#"{"text": "x", "state": "evil"}"#).state, None);
        assert_eq!(status_text(&s, "").text, "");
    }

    #[test]
    fn long_text_is_cut() {
        let s = status(None, None, None);
        let text = status_text(&s, &"x".repeat(100)).text;
        assert_eq!(text.chars().count(), MAX_STATUS);
        assert!(text.ends_with('…'));
    }

    #[test]
    fn clock_formats() {
        assert_eq!(clock(0.0), "0:00");
        assert_eq!(clock(59.6), "1:00");
        assert_eq!(clock(3600.0), "1:00");
        assert_eq!(clock(-5.0), "0:00");
        assert_eq!(clock(86400.0 * 7.0), "168:00");
    }

    #[test]
    fn the_weather_shows_its_sky_and_temperature() {
        let spec = crate::spec::parse("weather", include_str!("../defaults/weather.toml")).unwrap();
        let status = spec.status.unwrap();
        let reading = r#"{"current": {"weather_code": 61, "temperature": 12.6}}"#;
        let shown = status_text(&status, reading);
        assert_eq!((shown.text.as_str(), shown.icon.as_deref()), ("13°", Some("rain")));
        let clear = status_text(&status, r#"{"current": {"weather_code": 0, "temperature": -0.4}}"#);
        assert_eq!((clear.text.as_str(), clear.icon.as_deref()), ("0°", Some("sun")));
        // No reading (no city yet): the description's own icon stays.
        assert_eq!(status_text(&status, "{}").icon, None);
    }
}
