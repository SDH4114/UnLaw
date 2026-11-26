//! Panels the app draws itself (`view = "awake"`, `view = "system"` in a
//! command's app.toml). The page never builds argv: it names what it wants
//! (`data`) or what to do (`act` with plain values), and these functions turn
//! that into the exact `ul` arguments after checking every value.

use serde_json::Value as Json;

/// The reads a view needs, each as (key in the answer, argv after `ul`).
/// `first` is the panel's first read after opening: slow or rarely changing
/// things (the lid rule probe runs sudo -n) are read only then.
pub fn reads(view: &str, first: bool) -> Vec<(&'static str, Vec<String>)> {
    let argv = |words: &[&str]| words.iter().map(|word| word.to_string()).collect::<Vec<_>>();
    match view {
        "awake" => {
            let mut list = vec![
                ("status", argv(&["awake", "status", "--json"])),
                ("schedules", argv(&["awake", "schedule", "list", "--json"])),
            ];
            if first {
                // Exit 0 = the sudoers rule works; the text is not needed.
                list.push(("lid", argv(&["awake", "lid", "status"])));
            }
            list
        }
        "system" => vec![("sys", argv(&["sys", "--json"]))],
        _ => Vec::new(),
    }
}

/// What a view's button asks for, as argv after `ul`; an error names the bad value.
pub fn act(view: &str, request: &Json) -> Result<Vec<String>, String> {
    let what = request["do"].as_str().unwrap_or("");
    match (view, what) {
        ("awake", "start") => {
            let span = text(request, "span")?;
            if span != "on" && !is_span(&span) {
                return Err(format!("not a duration: {span:?}"));
            }
            Ok(with_flags(vec!["awake".into(), span], request))
        }
        ("awake", "until") => {
            let time = clock(request, "time")?;
            let mut argv = vec!["awake".to_string(), "until".into()];
            if let Some(date) = request["date"].as_str() {
                if !is_date(date) {
                    return Err(format!("not a date: {date:?}"));
                }
                argv.push(date.into());
            }
            argv.push(time);
            Ok(with_flags(argv, request))
        }
        ("awake", "stop") => Ok(vec!["awake".into(), "off".into()]),
        ("awake", "schedule-add") => {
            let (from, to) = (clock(request, "from")?, clock(request, "to")?);
            if from == to {
                return Err("a schedule needs a start and a different end".into());
            }
            let days = text(request, "days")?;
            if !["daily", "weekdays", "weekends"].contains(&days.as_str()) {
                return Err(format!("days must be daily, weekdays or weekends, not {days:?}"));
            }
            let argv =
                vec!["awake".into(), "schedule".into(), "add".into(), format!("{from}-{to}"), "--days".into(), days];
            Ok(with_flags(argv, request))
        }
        ("awake", "schedule-rm") => {
            let id = request["id"].as_u64().filter(|id| (1..=1_000_000).contains(id)).ok_or("no schedule id")?;
            Ok(vec!["awake".into(), "schedule".into(), "rm".into(), id.to_string()])
        }
        _ => Err(format!("{view} cannot {what:?}")),
    }
}

fn text(request: &Json, key: &str) -> Result<String, String> {
    request[key].as_str().map(str::to_string).ok_or_else(|| format!("{key} is missing"))
}

/// `--no-display` unless the screen should stay on, `--lid` when asked.
fn with_flags(mut argv: Vec<String>, request: &Json) -> Vec<String> {
    if request["display"].as_bool() == Some(false) {
        argv.push("--no-display".into());
    }
    if request["lid"].as_bool() == Some(true) {
        argv.push("--lid".into());
    }
    argv
}

/// 30m, 2h, 90m: what the chips send (at most a week, like `ul awake`).
fn is_span(span: &str) -> bool {
    let (number, unit) = span.split_at(span.len().saturating_sub(1));
    let minutes = match (number.parse::<u64>(), unit) {
        (Ok(count), "m") => count,
        (Ok(count), "h") => count * 60,
        _ => return false,
    };
    !number.is_empty()
        && number.len() <= 5
        && number.bytes().all(|byte| byte.is_ascii_digit())
        && (1..=7 * 24 * 60).contains(&minutes)
}

/// HH:MM on a 24-hour clock.
fn clock(request: &Json, key: &str) -> Result<String, String> {
    let time = text(request, key)?;
    let ok = time.len() == 5
        && time.as_bytes()[2] == b':'
        && matches!((time[..2].parse::<u8>(), time[3..].parse::<u8>()), (Ok(hour), Ok(minute)) if hour < 24 && minute < 60)
        && time.bytes().enumerate().all(|(index, byte)| index == 2 || byte.is_ascii_digit());
    if ok {
        Ok(time)
    } else {
        Err(format!("{key} is not HH:MM: {time:?}"))
    }
}

fn is_date(date: &str) -> bool {
    let bytes = date.as_bytes();
    bytes.len() == 10
        && bytes[4] == b'-'
        && bytes[7] == b'-'
        && bytes.iter().enumerate().all(|(index, byte)| index == 4 || index == 7 || byte.is_ascii_digit())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn words(argv: &[String]) -> String {
        argv.join(" ")
    }

    #[test]
    fn awake_starts_with_checked_values() {
        let start = act("awake", &json!({"do": "start", "span": "2h", "display": true, "lid": false})).unwrap();
        assert_eq!(words(&start), "awake 2h");
        let start = act("awake", &json!({"do": "start", "span": "on", "display": false, "lid": true})).unwrap();
        assert_eq!(words(&start), "awake on --no-display --lid");
        let until = act("awake", &json!({"do": "until", "time": "21:30", "date": "2026-11-25"})).unwrap();
        assert_eq!(words(&until), "awake until 2026-11-25 21:30");
        assert_eq!(words(&act("awake", &json!({"do": "stop"})).unwrap()), "awake off");
        for span in ["0m", "2d", "-1h", "1h --lid", "", "169h", "on;rm"] {
            assert!(act("awake", &json!({"do": "start", "span": span})).is_err(), "{span}");
        }
        for time in ["24:00", "9:30", "21:60", "--lid", "aa:bb"] {
            assert!(act("awake", &json!({"do": "until", "time": time})).is_err(), "{time}");
        }
        assert!(act("awake", &json!({"do": "until", "time": "10:00", "date": "--now"})).is_err());
    }

    #[test]
    fn schedules_are_added_and_removed_by_id() {
        let add = act(
            "awake",
            &json!({"do": "schedule-add", "from": "23:00", "to": "06:00", "days": "weekdays", "display": false}),
        );
        assert_eq!(words(&add.unwrap()), "awake schedule add 23:00-06:00 --days weekdays --no-display");
        assert!(act("awake", &json!({"do": "schedule-add", "from": "08:00", "to": "08:00", "days": "daily"})).is_err());
        assert!(act("awake", &json!({"do": "schedule-add", "from": "08:00", "to": "09:00", "days": "--all"})).is_err());
        assert_eq!(words(&act("awake", &json!({"do": "schedule-rm", "id": 3})).unwrap()), "awake schedule rm 3");
        assert!(act("awake", &json!({"do": "schedule-rm", "id": "--all"})).is_err());
        assert!(act("system", &json!({"do": "stop"})).is_err());
    }

    #[test]
    fn the_lid_rule_is_probed_only_on_the_first_read() {
        assert_eq!(reads("awake", true).len(), 3);
        assert_eq!(reads("awake", false).len(), 2);
        assert_eq!(reads("system", false)[0].1, vec!["sys", "--json"]);
        assert!(reads("kitchen", true).is_empty());
    }
}
