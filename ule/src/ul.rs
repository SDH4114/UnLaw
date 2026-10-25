//! Unlaw integration: running ul commands, the command list, local models (`ul lm`),
//! and checking Unlaw's config.toml after it is saved.

use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use crate::editor::Editor;
use crate::jobs::{quote, spawn, Handoff, JobKind};
use crate::text::Pos;

/// The ul executable: $ULE_UL, the `ul` next to ule, then PATH.
pub fn ul_path() -> Option<PathBuf> {
    if let Some(path) = std::env::var_os("ULE_UL").filter(|value| !value.is_empty()) {
        return Some(PathBuf::from(path));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let sibling = dir.join("ul");
            if sibling.is_file() {
                return Some(sibling);
            }
        }
    }
    let path = std::env::var_os("PATH")?;
    std::env::split_paths(&path).map(|dir| dir.join("ul")).find(|candidate| candidate.is_file())
}

fn ul_command() -> Result<String, String> {
    ul_path()
        .map(|path| quote(&path.to_string_lossy()))
        .ok_or_else(|| "ul was not found (install Unlaw or set ULE_UL)".into())
}

/// `ul commands --describe` as (name, description).
pub fn commands() -> Vec<(String, String)> {
    let Some(ul) = ul_path() else {
        return Vec::new();
    };
    let Ok(output) =
        Command::new(ul).args(["commands", "--describe"]).stdin(Stdio::null()).stderr(Stdio::null()).output()
    else {
        return Vec::new();
    };
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter_map(|line| {
            let line = line.trim_end();
            let (name, description) = line.split_once(char::is_whitespace)?;
            Some((name.to_string(), description.trim().to_string()))
        })
        .filter(|(name, _)| !name.is_empty())
        .collect()
}

/// `ul <args>`: into the panel, or with the terminal handed over for interactive commands.
pub fn run(ed: &mut Editor, args: &str, interactive: bool) -> Result<(), String> {
    let ul = ul_command()?;
    let command = format!("{ul} {args}");
    if interactive {
        ed.handoff = Some(Handoff { command, wait: true });
        return Ok(());
    }
    crate::jobs::run_shell(ed, &command, "[ul]")
}

/// Asks the local model; the answer streams into the `[ask]` buffer in the panel.
pub fn ask(ed: &mut Editor, question: &str, context: Option<String>) -> Result<(), String> {
    let ul = ul_command()?;
    let doc = ed.output_doc("[ask]");
    let header = match &context {
        Some(context) => format!("› {question}\n  (with {} lines of context)\n", context.lines().count()),
        None => format!("› {question}\n"),
    };
    if let Some(document) = ed.docs.get_mut(&doc) {
        document.set_content(&header);
        document.set_language(ed.languages.by_name("markdown"));
    }
    let command = format!("{ul} lm {}", quote(question));
    spawn(ed, "ul lm", &command, context, doc, JobKind::Output)?;
    ed.show_in_panel(doc);
    ed.info("asking the local model… (answer in the panel, <space>o focuses it)");
    Ok(())
}

/// Rewrites `start..end` of `doc` with the local model; applied when the answer arrives.
pub fn ai_edit(
    ed: &mut Editor,
    instruction: &str,
    doc: usize,
    start: Pos,
    end: Pos,
    version: i32,
    original: String,
) -> Result<(), String> {
    let ul = ul_command()?;
    let language = ed.docs.get(&doc).map(|document| ed.language_name(document)).unwrap_or_default();
    let prompt = format!(
        "Rewrite the following {language} code: {instruction}. Reply with only the complete rewritten code in one code block, no explanation."
    );
    let command = format!("{ul} lm {}", quote(&prompt));
    let output = ed.output_doc("[ai]");
    spawn(
        ed,
        "AI edit",
        &command,
        Some(original.clone()),
        output,
        JobKind::AiEdit { doc, start, end, version, original },
    )?;
    ed.info("rewriting with the local model…");
    Ok(())
}

/// The code from a model answer: the first fenced block, else the whole text.
pub fn extract_code(answer: &str) -> String {
    let mut inside = false;
    let mut code = Vec::new();
    for line in answer.lines() {
        if line.trim_start().starts_with("```") {
            if inside {
                return code.join("\n") + "\n";
            }
            inside = true;
            continue;
        }
        if inside {
            code.push(line);
        }
    }
    if inside && !code.is_empty() {
        return code.join("\n") + "\n";
    }
    answer.trim().to_string() + "\n"
}

/// After saving Unlaw's own config.toml, `ul config check` reports problems right away.
pub fn check_after_save(path: &Path) -> Option<String> {
    let config = crate::config::config_dir().join("config.toml");
    let same = path == config || std::fs::canonicalize(path).ok() == std::fs::canonicalize(&config).ok();
    if !same {
        return None;
    }
    let ul = ul_path()?;
    let output = Command::new(ul).args(["config", "check"]).stdin(Stdio::null()).output().ok()?;
    if output.status.success() {
        Some("ul config check ✓".into())
    } else {
        let error = String::from_utf8_lossy(&output.stderr);
        let text = if error.trim().is_empty() {
            String::from_utf8_lossy(&output.stdout).into_owned()
        } else {
            error.into_owned()
        };
        Some(format!("ul config check: {}", text.trim()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn code_from_answers() {
        assert_eq!(extract_code("Here:\n```rust\nfn a() {}\n```\nDone."), "fn a() {}\n");
        assert_eq!(extract_code("fn a() {}"), "fn a() {}\n");
    }
}
