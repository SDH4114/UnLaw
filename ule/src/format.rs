//! Formatting: the language's formatter (stdin → stdout) or the language server.
//!
//! With `format_on_save = "auto"` a file is formatted on save only when its
//! project has the formatter's own config (rustfmt.toml, .prettierrc, ruff in
//! pyproject.toml, ...), so repositories that do not use a formatter are not reformatted.

use std::io::Write;
use std::path::Path;
use std::process::{Command, Stdio};

use crate::config::FormatOnSave;
use crate::editor::Editor;
use crate::text::{char_len, Pos};

fn which(program: &str) -> bool {
    if program.contains('/') {
        return Path::new(program).is_file();
    }
    std::env::var_os("PATH").is_some_and(|path| std::env::split_paths(&path).any(|dir| dir.join(program).is_file()))
}

/// The project has a config for this formatter (searched up to the repository or home).
fn has_formatter_config(path: &Path, configs: &[String], formatter: &[String]) -> bool {
    let home = crate::config::home();
    let mut dir = path.parent();
    while let Some(current) = dir {
        if configs.iter().any(|name| current.join(name).exists()) {
            return true;
        }
        // Python tools keep their settings in pyproject.toml.
        if let Ok(text) = std::fs::read_to_string(current.join("pyproject.toml")) {
            let tool = formatter.first().map(String::as_str).unwrap_or("");
            if (tool == "ruff" && text.contains("[tool.ruff")) || (tool == "black" && text.contains("[tool.black")) {
                return true;
            }
        }
        if current.join(".git").exists() || current == home {
            return false;
        }
        dir = current.parent();
    }
    false
}

fn external(ed: &Editor, doc: usize) -> Option<Vec<String>> {
    let document = ed.docs.get(&doc)?;
    let lang = document.lang.and_then(|index| ed.languages.get(index))?;
    let program = lang.formatter.first()?;
    if !which(program) {
        return None;
    }
    let path = document.path.as_ref().map(|path| path.to_string_lossy().into_owned()).unwrap_or_default();
    Some(lang.formatter.iter().map(|arg| arg.replace("{file}", &path)).collect())
}

fn run_formatter(command: &[String], input: &str, cwd: &Path) -> Result<String, String> {
    let mut child = Command::new(&command[0])
        .args(&command[1..])
        .current_dir(cwd)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("{}: {error}", command[0]))?;
    let mut stdin = child.stdin.take().expect("piped stdin");
    let input = input.to_string();
    let writer = std::thread::spawn(move || {
        let _ = stdin.write_all(input.as_bytes());
    });
    let output = child.wait_with_output().map_err(|error| error.to_string())?;
    let _ = writer.join();
    if !output.status.success() {
        let error = String::from_utf8_lossy(&output.stderr);
        let first = error.lines().find(|line| !line.trim().is_empty()).unwrap_or("failed");
        return Err(format!("{}: {first}", command[0]));
    }
    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}

/// Replaces only the lines that differ, so the cursor and undo stay meaningful.
pub fn apply_text(ed: &mut Editor, doc: usize, new: &str) -> bool {
    let Some(document) = ed.docs.get_mut(&doc) else {
        return false;
    };
    let new = new.strip_suffix('\n').unwrap_or(new);
    let old_lines: Vec<String> = document.text.lines().map(str::to_string).collect();
    let new_lines: Vec<&str> = new.split('\n').collect();
    if old_lines.iter().map(String::as_str).eq(new_lines.iter().copied()) {
        return false;
    }
    let prefix = old_lines.iter().zip(&new_lines).take_while(|(a, b)| a.as_str() == **b).count();
    let max_suffix = old_lines.len().min(new_lines.len()) - prefix;
    let suffix = old_lines
        .iter()
        .rev()
        .zip(new_lines.iter().rev())
        .take(max_suffix)
        .take_while(|(a, b)| a.as_str() == **b)
        .count();
    let old_end = old_lines.len() - suffix;
    let new_middle = new_lines[prefix..new_lines.len() - suffix].join("\n");
    let cursor = ed.views.values().find(|view| view.doc == doc).map_or(Pos::default(), |view| view.cursor);
    let document = ed.docs.get_mut(&doc).expect("document");
    document.commit(cursor);
    if old_end > prefix {
        let start = Pos::new(prefix, 0);
        let end = Pos::new(old_end - 1, char_len(&old_lines[old_end - 1]));
        if new_lines.len() - suffix > prefix {
            document.replace(start, end, &new_middle, cursor);
        } else {
            // Lines were only removed: take the newline with them.
            let (start, end) = if old_end < old_lines.len() {
                (start, Pos::new(old_end, 0))
            } else if prefix > 0 {
                (Pos::new(prefix - 1, char_len(&old_lines[prefix - 1])), end)
            } else {
                (start, end)
            };
            document.remove(start, end, cursor);
        }
    } else {
        // Lines were only added.
        let at = Pos::new(prefix, 0);
        if prefix < old_lines.len() {
            document.insert(at, &format!("{new_middle}\n"), cursor);
        } else {
            let end = document.text.end();
            document.insert(end, &format!("\n{new_middle}"), cursor);
        }
    }
    document.commit(cursor);
    let views: Vec<usize> = ed.views.values().filter(|view| view.doc == doc).map(|view| view.id).collect();
    for view in views {
        let clamped = ed.docs[&doc].text.clamp(ed.views[&view].cursor);
        ed.views.get_mut(&view).expect("view").cursor = clamped;
    }
    true
}

fn format_with(ed: &mut Editor, doc: usize) -> Result<Option<String>, String> {
    if let Some(command) = external(ed, doc) {
        let document = &ed.docs[&doc];
        let cwd =
            document.path.as_ref().and_then(|path| path.parent()).map_or_else(|| ed.cwd.clone(), Path::to_path_buf);
        let input = document.content(true);
        let output = run_formatter(&command, &input, &cwd)?;
        if output.trim().is_empty() && !input.trim().is_empty() {
            return Err(format!("{} printed nothing", command[0]));
        }
        let changed = apply_text(ed, doc, &output);
        return Ok(Some(if changed {
            format!("formatted with {}", command[0])
        } else {
            format!("{}: already formatted", command[0])
        }));
    }
    if crate::lsp::format_sync(ed, doc)? {
        return Ok(Some("formatted by the language server".into()));
    }
    Ok(None)
}

pub fn format_doc(ed: &mut Editor, doc: usize) -> Result<String, String> {
    match format_with(ed, doc)? {
        Some(message) => Ok(message),
        None => {
            let name = ed.docs.get(&doc).map(|document| ed.language_name(document)).unwrap_or_default();
            Err(format!("no formatter for {name}: install one or set formatter = [...] under [languages.{name}]"))
        }
    }
}

pub fn on_save(ed: &mut Editor, doc: usize, path: &Path) -> Result<(), String> {
    let Some(document) = ed.docs.get(&doc) else {
        return Ok(());
    };
    let Some(lang) = document.lang.and_then(|index| ed.languages.get(index)) else {
        return Ok(());
    };
    match ed.options.format_on_save {
        FormatOnSave::Never => return Ok(()),
        FormatOnSave::Always => {}
        FormatOnSave::Auto => {
            if !has_formatter_config(path, &lang.formatter_configs, &lang.formatter) {
                return Ok(());
            }
        }
    }
    format_with(ed, doc).map(|_| ())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::Config;

    #[test]
    fn minimal_replacement_keeps_unchanged_lines() {
        crate::clipboard::disable();
        let mut ed = Editor::new(Config::default());
        let doc = ed.view().doc;
        ed.doc_mut().set_content("a\nb  \nc\nd\n");
        assert!(apply_text(&mut ed, doc, "a\nb\nc\nd\n"));
        assert_eq!(ed.doc().text.to_string_lf(), "a\nb\nc\nd");
        assert!(apply_text(&mut ed, doc, "a\nc\nd\n"));
        assert_eq!(ed.doc().text.to_string_lf(), "a\nc\nd");
        assert!(apply_text(&mut ed, doc, "a\nc\nx\ny\nd\n"));
        assert_eq!(ed.doc().text.to_string_lf(), "a\nc\nx\ny\nd");
        assert!(apply_text(&mut ed, doc, "a\nc\nx\ny\nd\ne\n"));
        assert_eq!(ed.doc().text.to_string_lf(), "a\nc\nx\ny\nd\ne");
        assert!(!apply_text(&mut ed, doc, "a\nc\nx\ny\nd\ne\n"));
        let cursor = ed.cursor();
        assert!(ed.doc_mut().undo(cursor).is_some());
        assert_eq!(ed.doc().text.to_string_lf(), "a\nc\nx\ny\nd");
    }
}
