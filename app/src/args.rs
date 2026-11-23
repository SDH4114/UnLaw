//! Placeholders in an `app.toml` argument list: the only way a panel's field
//! values reach a command. Each template element becomes at most one argv
//! element, so a value with spaces, quotes or a leading dash stays one argument
//! and nothing ever goes through a shell.

use std::collections::BTreeMap;

/// A field value as the panel sends it.
#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Text(String),
    Bool(bool),
}

impl Value {
    pub fn truthy(&self) -> bool {
        match self {
            Value::Bool(on) => *on,
            Value::Text(text) => !text.trim().is_empty(),
        }
    }

    fn text(&self) -> String {
        match self {
            Value::Bool(on) => on.to_string(),
            Value::Text(text) => text.clone(),
        }
    }
}

/// One `{...}` placeholder: `{id}`, `{id?then}` or `{id?then:else}`.
#[derive(Debug, PartialEq)]
struct Placeholder<'a> {
    id: &'a str,
    choice: Option<(&'a str, &'a str)>,
}

enum Piece<'a> {
    Text(String),
    Slot(Placeholder<'a>),
}

fn placeholder(inner: &str) -> Result<Placeholder<'_>, String> {
    let (id, choice) = match inner.split_once('?') {
        None => (inner, None),
        Some((id, rest)) => (id, Some(rest.split_once(':').unwrap_or((rest, "")))),
    };
    if id.is_empty() || !id.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-') {
        return Err(format!("bad placeholder {{{inner}}}: the name must be letters, digits, _ or -"));
    }
    Ok(Placeholder { id, choice })
}

fn pieces(template: &str) -> Result<Vec<Piece<'_>>, String> {
    let mut pieces = Vec::new();
    let mut text = String::new();
    let mut rest = template;
    while let Some(index) = rest.find(['{', '}']) {
        text.push_str(&rest[..index]);
        let after = &rest[index + 1..];
        if rest[index..].starts_with("{{") {
            text.push('{');
            rest = &rest[index + 2..];
        } else if rest[index..].starts_with("}}") {
            text.push('}');
            rest = &rest[index + 2..];
        } else if rest[index..].starts_with('}') {
            return Err(format!("unmatched }} in {template:?} (write }}}} for a brace)"));
        } else {
            let end = after.find(['}', '{']).filter(|&end| after[end..].starts_with('}'));
            let Some(end) = end else {
                return Err(format!("unclosed {{ in {template:?} (write {{{{ for a brace)"));
            };
            if !text.is_empty() {
                pieces.push(Piece::Text(std::mem::take(&mut text)));
            }
            pieces.push(Piece::Slot(placeholder(&after[..end])?));
            rest = &after[end + 1..];
        }
    }
    text.push_str(rest);
    if !text.is_empty() {
        pieces.push(Piece::Text(text));
    }
    Ok(pieces)
}

/// The field names a template uses, for checking a panel when it is loaded.
pub fn ids(template: &[String]) -> Result<Vec<String>, String> {
    let mut found = Vec::new();
    for element in template {
        for piece in pieces(element)? {
            if let Piece::Slot(slot) = piece {
                if !found.iter().any(|id| id == slot.id) {
                    found.push(slot.id.to_string());
                }
            }
        }
    }
    Ok(found)
}

/// Fill a template with field values. An element that ends up empty is left
/// out, so optional fields disappear instead of passing "".
pub fn expand(template: &[String], values: &BTreeMap<String, Value>) -> Result<Vec<String>, String> {
    let mut argv = Vec::new();
    for element in template {
        let mut out = String::new();
        for piece in pieces(element)? {
            match piece {
                Piece::Text(text) => out.push_str(&text),
                Piece::Slot(slot) => {
                    let value = values.get(slot.id).ok_or_else(|| format!("no field named {:?}", slot.id))?;
                    match slot.choice {
                        None => out.push_str(&value.text()),
                        Some((then, otherwise)) => out.push_str(if value.truthy() { then } else { otherwise }),
                    }
                }
            }
        }
        if !out.is_empty() {
            argv.push(out);
        }
    }
    Ok(argv)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn words(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    fn values(items: &[(&str, Value)]) -> BTreeMap<String, Value> {
        items.iter().map(|(k, v)| (k.to_string(), v.clone())).collect()
    }

    #[test]
    fn values_stay_one_argument_each() {
        let v =
            values(&[("text", Value::Text("buy milk; rm -rf ~ \"x\"".into())), ("n", Value::Text("--force".into()))]);
        assert_eq!(
            expand(&words(&["add", "{text}", "{n}"]), &v).unwrap(),
            words(&["add", "buy milk; rm -rf ~ \"x\"", "--force"])
        );
    }

    #[test]
    fn choices_and_empty_elements() {
        let v = values(&[
            ("lid", Value::Bool(true)),
            ("screen", Value::Bool(false)),
            ("until", Value::Text("".into())),
            ("dur", Value::Text("2h".into())),
        ]);
        let template =
            words(&["{until?until}", "{until}", "{dur}", "{screen?:--no-display}", "{lid?--lid}", "{lid?a:b}"]);
        assert_eq!(expand(&template, &v).unwrap(), words(&["2h", "--no-display", "--lid", "a"]));
    }

    #[test]
    fn text_around_placeholders_and_braces() {
        let v = values(&[("t", Value::Text("18:00".into()))]);
        assert_eq!(
            expand(&words(&["--at={t}", "{{x}}", "{{{t}}}"]), &v).unwrap(),
            words(&["--at=18:00", "{x}", "{18:00}"])
        );
    }

    #[test]
    fn errors_are_reported() {
        let v = values(&[]);
        assert!(expand(&words(&["{missing}"]), &v).unwrap_err().contains("missing"));
        assert!(expand(&words(&["{open"]), &v).unwrap_err().contains("unclosed"));
        assert!(expand(&words(&["close}"]), &v).unwrap_err().contains("unmatched"));
        assert!(expand(&words(&["{bad name}"]), &v).is_err());
        assert!(expand(&words(&["{}"]), &v).is_err());
    }

    #[test]
    fn ids_lists_each_name_once() {
        assert_eq!(ids(&words(&["{a}", "{b?x}", "{a?:y}", "plain"])).unwrap(), words(&["a", "b"]));
    }
}
