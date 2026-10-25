//! Named commands: what key bindings, the command palette and `:name` run.

use std::path::PathBuf;

use crate::document::DocKind;
use crate::edit;
use crate::editor::{Editor, Focus, Mode};
use crate::text::Pos;
use crate::widgets::{InputAction, Prompt, PromptKind};

/// (name, description). The palette lists them; ule.toml bindings refer to them.
pub const COMMANDS: &[(&str, &str)] = &[
    ("save", "save the file"),
    ("save_all", "save every modified file"),
    ("quit", "close the window, quit ule when it is the last"),
    ("quit_all", "quit ule (asks about unsaved files)"),
    ("close_window", "close the window"),
    ("write_quit", "save and close"),
    ("file_picker", "find a file in the project"),
    ("git_files", "files changed in git"),
    ("grep", "search the project (ripgrep)"),
    ("grep_word", "search the project for the word under the cursor"),
    ("grep_selection", "search the project for the selection"),
    ("buffer_picker", "switch between open files"),
    ("recent_files", "recently opened files"),
    ("last_picker", "reopen the last picker"),
    ("explorer", "toggle the file explorer"),
    ("explorer_reveal", "show the current file in the explorer"),
    ("panel", "toggle the output panel"),
    ("command_palette", "search all commands"),
    ("keymap_picker", "search key bindings"),
    ("split", "split the window below"),
    ("vsplit", "split the window to the right"),
    ("only", "close all other windows"),
    ("focus_left", "go to the window on the left"),
    ("focus_down", "go to the window below"),
    ("focus_up", "go to the window above"),
    ("focus_right", "go to the window on the right"),
    ("focus_next", "go to the next window"),
    ("run", "run the current file (language's run command)"),
    ("run_again", "run the last command again"),
    ("symbols", "symbols in this file (LSP)"),
    ("workspace_symbols", "symbols in the project (LSP)"),
    ("diagnostics", "list diagnostics"),
    ("line_diagnostics", "show diagnostics on the cursor line"),
    ("diagnostic_next", "next diagnostic"),
    ("diagnostic_prev", "previous diagnostic"),
    ("error_next", "next error"),
    ("error_prev", "previous error"),
    ("goto_definition", "go to definition (LSP)"),
    ("goto_declaration", "go to declaration (LSP)"),
    ("goto_type_definition", "go to type definition (LSP)"),
    ("goto_implementation", "go to implementation (LSP)"),
    ("references", "find references (LSP)"),
    ("hover", "show documentation (LSP)"),
    ("rename", "rename the symbol (LSP)"),
    ("code_action", "code actions and quick fixes (LSP)"),
    ("format", "format the file (formatter or LSP)"),
    ("lsp_info", "language server status"),
    ("lsp_restart", "restart language servers"),
    ("complete", "open completion"),
    ("goto_file", "open the file path under the cursor"),
    ("open_external", "open the URL or path under the cursor with macOS"),
    ("reveal_in_finder", "show the current file in Finder"),
    ("location_next", "next file:line in the output"),
    ("location_prev", "previous file:line in the output"),
    ("open_config", "edit ule.toml"),
    ("reload_config", "reload ule.toml"),
    ("theme_picker", "choose a theme"),
    ("language_picker", "set the file's language"),
    ("help", "ule help"),
    ("new_file", "create a file"),
    ("scratch", "new scratch buffer"),
    ("buffer_next", "next buffer"),
    ("buffer_prev", "previous buffer"),
    ("buffer_close", "close the buffer"),
    ("buffer_close_force", "close the buffer, discarding changes"),
    ("buffer_only", "close all other buffers"),
    ("alternate_buffer", "switch to the previous file"),
    ("git_status", "git status"),
    ("git_diff", "git diff"),
    ("git_diff_file", "git diff of this file"),
    ("git_log", "git log"),
    ("git_blame", "who changed this line"),
    ("git_commit", "commit and push with ul git"),
    ("ul_picker", "run a ul command"),
    ("ul_todo", "show the TODO board (ul todo)"),
    ("ul_doctor", "run ul doctor"),
    ("ul_config", "edit Unlaw's config.toml"),
    ("ul_agent", "open the local agent (ula)"),
    ("ul_lm", "chat with the local model (ul lm)"),
    ("ask", "ask the local model (selection is included)"),
    ("ask_file", "ask the local model about this file"),
    ("ai_edit", "rewrite the selection with the local model"),
    ("ai_explain", "explain the selection or file with the local model"),
    ("toggle", "toggle an option: toggle wrap"),
    ("line_numbers", "cycle relative/absolute/off line numbers"),
    ("clear", "clear search highlight, messages and popups"),
    ("move_line_down", "move the line down"),
    ("move_line_up", "move the line up"),
    ("move_selection_down", "move the selected lines down"),
    ("move_selection_up", "move the selected lines up"),
    ("comment_line", "toggle comment on the line"),
    ("suspend", "suspend to the shell (fg returns)"),
    ("macro_replay", "replay the last recorded macro"),
    ("normal_mode", "leave insert/visual mode"),
    ("undo", "undo"),
    ("redo", "redo"),
    ("command_mode", "open the : command line"),
    ("search", "search forward"),
];

pub fn names() -> Vec<&'static str> {
    COMMANDS.iter().map(|(name, _)| *name).collect()
}

fn word_under_cursor(ed: &Editor) -> Option<String> {
    crate::motion::word_at(&ed.doc().text, ed.cursor()).map(|(_, _, word)| word)
}

fn selection_text(ed: &Editor) -> Option<String> {
    let (start, end, kind) = ed.selection()?;
    let doc = ed.doc();
    Some(if kind == crate::editor::VisualKind::Line {
        edit::lines_text(ed, start.line, end.line)
    } else {
        doc.text.slice(start, doc.text.next(end).unwrap_or(end))
    })
}

/// Text under the cursor that looks like a path or URL (stops at spaces and quotes).
pub fn path_under_cursor(ed: &Editor) -> Option<String> {
    let cursor = ed.cursor();
    let chars: Vec<char> = ed.doc().text.line(cursor.line).chars().collect();
    let stop = |c: char| c.is_whitespace() || "\"'`()[]{}<>,;".contains(c);
    if chars.is_empty() {
        return None;
    }
    let mut start = cursor.col.min(chars.len() - 1);
    if stop(chars[start]) {
        return None;
    }
    while start > 0 && !stop(chars[start - 1]) {
        start -= 1;
    }
    let mut end = cursor.col;
    while end < chars.len() && !stop(chars[end]) {
        end += 1;
    }
    let text: String = chars[start..end].iter().collect();
    Some(text.trim_end_matches(['.', ':']).to_string()).filter(|text| !text.is_empty())
}

pub fn run(
    ed: &mut Editor,
    name: &str,
    args: &[String],
    count: Option<usize>,
    register: Option<char>,
) -> Result<(), String> {
    let n = count.unwrap_or(1);
    match name {
        "save" => crate::ex::run(ed, "w"),
        "save_all" => crate::ex::run(ed, "wa"),
        "quit" => crate::ex::run(ed, "q"),
        "quit_all" => crate::ex::run(ed, "qa"),
        "close_window" => crate::ex::run(ed, "close"),
        "write_quit" => crate::ex::run(ed, "x"),
        "file_picker" => crate::picker::open_files(ed, false),
        "git_files" => crate::picker::open_files(ed, true),
        "grep" => crate::picker::open_grep(ed, ""),
        "grep_word" => {
            let word = word_under_cursor(ed).ok_or("no word under the cursor")?;
            crate::picker::open_grep(ed, &word);
        }
        "grep_selection" => {
            let text = selection_text(ed).unwrap_or_default();
            crate::vim::exit_visual(ed);
            crate::picker::open_grep(ed, text.lines().next().unwrap_or(""));
        }
        "buffer_picker" => crate::picker::open_buffers(ed),
        "recent_files" => crate::picker::open_recent(ed),
        "last_picker" => {
            if let Some(picker) = ed.last_picker.take() {
                ed.picker = Some(picker);
            } else {
                return Err("no picker opened yet".into());
            }
        }
        "explorer" => {
            if ed.explorer.is_some() && ed.focus_area == Focus::Explorer {
                ed.explorer = None;
                ed.focus_area = Focus::View;
            } else if ed.explorer.is_some() {
                ed.focus_area = Focus::Explorer;
            } else {
                let root = ed.cwd.clone();
                let mut explorer = crate::explorer::Explorer::new(root, ed.options.hidden_files);
                if let Some(path) = ed.doc().path.clone() {
                    explorer.reveal(&path);
                }
                ed.explorer = Some(explorer);
                ed.focus_area = Focus::Explorer;
            }
        }
        "explorer_reveal" => {
            let path = ed.doc().path.clone().ok_or("this buffer has no file")?;
            if ed.explorer.is_none() {
                ed.explorer = Some(crate::explorer::Explorer::new(ed.cwd.clone(), ed.options.hidden_files));
            }
            if let Some(explorer) = ed.explorer.as_mut() {
                explorer.reveal(&path);
            }
            ed.focus_area = Focus::Explorer;
        }
        "panel" => {
            if ed.panel_visible && ed.panel != Some(ed.focus) {
                // Visible but not focused: focus it first, a second press hides it.
                if let Some(panel) = ed.panel {
                    ed.focus = panel;
                    return Ok(());
                }
            }
            ed.toggle_panel();
            if ed.panel_visible {
                if let Some(panel) = ed.panel {
                    ed.focus = panel;
                }
            }
        }
        "command_palette" => crate::picker::open_commands(ed),
        "keymap_picker" => crate::picker::open_keymaps(ed),
        "split" => ed.split(false),
        "vsplit" => ed.split(true),
        "only" => ed.only_view(),
        "focus_left" => ed.focus_direction('h'),
        "focus_down" => ed.focus_direction('j'),
        "focus_up" => ed.focus_direction('k'),
        "focus_right" => ed.focus_direction('l'),
        "focus_next" => ed.focus_next(),
        "run" => crate::jobs::run_current(ed, args)?,
        "run_again" => {
            let command = ed.last_run.clone().ok_or("nothing has been run yet")?;
            crate::jobs::run_shell(ed, &command, "[run]")?;
        }
        "symbols" => crate::lsp::document_symbols(ed)?,
        "workspace_symbols" => crate::lsp::workspace_symbols(ed, args.join(" ").as_str())?,
        "diagnostics" => crate::picker::open_diagnostics(ed),
        "line_diagnostics" => crate::lsp::show_line_diagnostics(ed),
        "diagnostic_next" => crate::lsp::goto_diagnostic(ed, true, false, n),
        "diagnostic_prev" => crate::lsp::goto_diagnostic(ed, false, false, n),
        "error_next" => crate::lsp::goto_diagnostic(ed, true, true, n),
        "error_prev" => crate::lsp::goto_diagnostic(ed, false, true, n),
        "goto_definition" => crate::lsp::goto(ed, "textDocument/definition")?,
        "goto_declaration" => crate::lsp::goto(ed, "textDocument/declaration")?,
        "goto_type_definition" => crate::lsp::goto(ed, "textDocument/typeDefinition")?,
        "goto_implementation" => crate::lsp::goto(ed, "textDocument/implementation")?,
        "references" => crate::lsp::references(ed)?,
        "hover" => crate::lsp::hover(ed)?,
        "rename" => {
            let word = word_under_cursor(ed).unwrap_or_default();
            if args.is_empty() {
                ed.prompt = Some(Prompt::new(
                    PromptKind::Input { title: "Rename to".into(), action: InputAction::LspRename },
                    &word,
                ));
            } else {
                crate::lsp::rename(ed, &args.join(" "))?;
            }
        }
        "code_action" => crate::lsp::code_actions(ed)?,
        "format" => {
            let doc = ed.view().doc;
            let message = crate::format::format_doc(ed, doc)?;
            ed.info(message);
        }
        "lsp_info" => {
            let text = crate::lsp::info(ed);
            ed.popup =
                Some(crate::widgets::Popup::new(crate::widgets::PopupKind::Info, "Language servers", &text, false));
        }
        "lsp_restart" => crate::lsp::restart(ed),
        "complete" => crate::complete::trigger(ed, true),
        "goto_file" => goto_file(ed)?,
        "open_external" => {
            let target = path_under_cursor(ed).ok_or("nothing to open under the cursor")?;
            let target = if target.contains("://") {
                target
            } else {
                resolve_path(ed, &target).map(|path| path.to_string_lossy().into_owned()).ok_or("no such file")?
            };
            std::process::Command::new("open").arg(&target).spawn().map_err(|error| format!("open: {error}"))?;
            ed.info(format!("opened {target}"));
        }
        "reveal_in_finder" => {
            let path = ed.doc().path.clone().ok_or("this buffer has no file")?;
            std::process::Command::new("open")
                .arg("-R")
                .arg(&path)
                .spawn()
                .map_err(|error| format!("open: {error}"))?;
        }
        "location_next" => crate::jobs::goto_location(ed, true, n)?,
        "location_prev" => crate::jobs::goto_location(ed, false, n)?,
        "open_config" => {
            let path = crate::config::config_path();
            if !path.exists() {
                if let Some(parent) = path.parent() {
                    std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
                }
                std::fs::write(&path, crate::config::TEMPLATE).map_err(|error| error.to_string())?;
            }
            ed.open(&path)?;
            ed.info("ule.toml: :config-reload (or <space>fc again later) applies changes");
        }
        "reload_config" => crate::ex::run(ed, "config-reload"),
        "theme_picker" => crate::picker::open_themes(ed),
        "language_picker" => crate::picker::open_languages(ed),
        "help" => crate::help::open(ed, args.first().map(String::as_str)),
        "new_file" => {
            let dir = ed
                .doc()
                .path
                .as_ref()
                .and_then(|path| path.parent().map(PathBuf::from))
                .unwrap_or_else(|| ed.cwd.clone());
            let start = crate::document::display_path(&dir);
            let start = if start.is_empty() { String::new() } else { format!("{start}/") };
            ed.prompt = Some(Prompt::new(
                PromptKind::Input { title: "New file".into(), action: InputAction::NewFile(dir) },
                &start,
            ));
        }
        "scratch" => {
            let id = ed.scratch("[scratch]", DocKind::Scratch);
            ed.show_doc(id);
        }
        "buffer_next" => ed.cycle_buffer(n as isize),
        "buffer_prev" => ed.cycle_buffer(-(n as isize)),
        "buffer_close" => {
            let id = ed.view().doc;
            ed.close_doc(id, false)?;
        }
        "buffer_close_force" => {
            let id = ed.view().doc;
            ed.close_doc(id, true)?;
        }
        "buffer_only" => {
            let keep = ed.view().doc;
            let others: Vec<usize> = ed.buffers.iter().copied().filter(|id| *id != keep).collect();
            let mut kept = Vec::new();
            for id in others {
                if ed.close_doc(id, false).is_err() {
                    kept.push(ed.docs[&id].title());
                }
            }
            if !kept.is_empty() {
                return Err(format!("kept (unsaved): {}", kept.join(", ")));
            }
        }
        "alternate_buffer" => {
            let alternate = ed.view().alternate.filter(|id| ed.docs.contains_key(id)).ok_or("no previous file")?;
            ed.show_doc(alternate);
        }
        "git_status" => crate::jobs::run_shell(ed, "git status -sb", "[git]")?,
        "git_diff" => crate::jobs::run_shell(ed, "git diff --stat && git diff", "[git diff]")?,
        "git_diff_file" => {
            let path = ed.doc().path.clone().ok_or("this buffer has no file")?;
            crate::jobs::run_shell(
                ed,
                &format!("git diff -- {}", crate::jobs::quote(&path.to_string_lossy())),
                "[git diff]",
            )?;
        }
        "git_log" => crate::jobs::run_shell(ed, "git log --oneline --graph --decorate -40", "[git]")?,
        "git_blame" => {
            let path = ed.doc().path.clone().ok_or("this buffer has no file")?;
            let line = ed.cursor().line + 1;
            let output = std::process::Command::new("git")
                .args(["blame", "-L", &format!("{line},{line}"), "--date=short"])
                .arg(&path)
                .current_dir(path.parent().unwrap_or(&ed.cwd))
                .output()
                .map_err(|error| format!("git: {error}"))?;
            let text = String::from_utf8_lossy(if output.status.success() { &output.stdout } else { &output.stderr })
                .trim()
                .to_string();
            ed.info(text);
        }
        "git_commit" => {
            ed.prompt = Some(Prompt::new(
                PromptKind::Input { title: "Commit message (ul git)".into(), action: InputAction::GitCommit },
                "",
            ));
        }
        "ul_picker" => crate::picker::open_ul(ed),
        "ul_todo" => crate::ul::run(ed, "todo", false)?,
        "ul_doctor" => crate::ul::run(ed, "doctor", false)?,
        "ul_config" => {
            let path = crate::config::config_dir().join("config.toml");
            ed.open(&path)?;
        }
        "ul_agent" => crate::ul::run(ed, "agent", true)?,
        "ul_lm" => crate::ul::run(ed, "lm", true)?,
        "ask" => {
            let selection = selection_text(ed);
            if selection.is_some() {
                crate::vim::exit_visual(ed);
            }
            if args.is_empty() {
                let title = if selection.is_some() { "Ask about the selection" } else { "Ask" };
                ed.prompt = Some(Prompt::new(
                    PromptKind::Input { title: title.into(), action: InputAction::Ask { with_selection: selection } },
                    "",
                ));
            } else {
                crate::ul::ask(ed, &args.join(" "), selection)?;
            }
        }
        "ask_file" => {
            let content = ed.doc().text.to_string_lf();
            let name = ed.doc().file_name();
            let context = format!("File {name}:\n```\n{content}\n```");
            ed.prompt = Some(Prompt::new(
                PromptKind::Input {
                    title: format!("Ask about {name}"),
                    action: InputAction::Ask { with_selection: Some(context) },
                },
                "",
            ));
        }
        "ai_edit" => {
            let Some((start, end, kind)) = ed.selection() else {
                return Err("select the code to rewrite first (v / V)".into());
            };
            let text = selection_text(ed).unwrap_or_default();
            let (from, to) = if kind == crate::editor::VisualKind::Line {
                (Pos::new(start.line, 0), Pos::new(end.line, ed.doc().text.line_len(end.line)))
            } else {
                (start, ed.doc().text.next(end).unwrap_or(end))
            };
            crate::vim::exit_visual(ed);
            let doc = ed.view().doc;
            let version = ed.doc().version;
            ed.prompt = Some(Prompt::new(
                PromptKind::Input {
                    title: "Rewrite the selection to".into(),
                    action: InputAction::AiEdit { doc, start: from, end: to, version, text },
                },
                "",
            ));
        }
        "ai_explain" => {
            let selection = selection_text(ed);
            if selection.is_some() {
                crate::vim::exit_visual(ed);
            }
            let text = selection.unwrap_or_else(|| ed.doc().text.to_string_lf());
            crate::ul::ask(ed, "Explain this code briefly: what it does and anything surprising.", Some(text))?;
        }
        "toggle" => {
            let option = args.first().ok_or("toggle what? e.g. toggle wrap")?;
            let on = ed.options.toggle(option)?;
            if option == "hlsearch" {
                ed.hlsearch_active = on;
            }
            ed.info(format!("{option}: {}", if on { "on" } else { "off" }));
        }
        "line_numbers" => {
            use crate::config::LineNumbers;
            ed.options.line_numbers = match ed.options.line_numbers {
                LineNumbers::Relative => LineNumbers::Absolute,
                LineNumbers::Absolute => LineNumbers::Off,
                LineNumbers::Off => LineNumbers::Relative,
            };
            let value = ed.options.get("line_numbers").unwrap_or_default();
            ed.info(format!("line numbers: {value}"));
        }
        "clear" => {
            ed.hlsearch_active = false;
            ed.message = None;
            ed.popup = None;
            ed.completion = None;
            if matches!(ed.mode, Mode::Visual(_)) {
                crate::vim::exit_visual(ed);
            }
        }
        "move_line_down" | "move_line_up" => {
            let down = name == "move_line_down";
            let cursor = ed.cursor();
            for step in 0..n {
                let line = if down { cursor.line + step } else { cursor.line.saturating_sub(step) };
                if !edit::move_lines(ed, line, line, down) {
                    break;
                }
            }
            let moved =
                if down { (cursor.line + n).min(ed.doc().text.last_line()) } else { cursor.line.saturating_sub(n) };
            ed.view_mut().cursor = Pos::new(moved, cursor.col);
            if ed.mode == Mode::Normal {
                edit::commit(ed);
                ed.clamp_cursor();
            }
        }
        "move_selection_down" | "move_selection_up" => {
            let Some((start, end, _)) = ed.selection() else {
                return Ok(());
            };
            let down = name == "move_selection_down";
            if edit::move_lines(ed, start.line, end.line, down) {
                let shift = |pos: Pos| Pos::new(if down { pos.line + 1 } else { pos.line - 1 }, pos.col);
                ed.anchor = shift(ed.anchor);
                let cursor = shift(ed.cursor());
                ed.view_mut().cursor = cursor;
                edit::commit(ed);
            }
        }
        "comment_line" => {
            let line = ed.cursor().line;
            edit::toggle_comment(ed, line, line + n - 1);
            edit::commit(ed);
        }
        "suspend" => ed.suspend_requested = true,
        "macro_replay" => {
            let name = ed.vim.last_recorded.ok_or("no macro recorded yet (q<letter> … q)")?;
            crate::vim::play_macro(ed, name, n);
        }
        "normal_mode" => match ed.mode {
            Mode::Insert | Mode::Replace => crate::vim::leave_insert(ed),
            Mode::Visual(_) => crate::vim::exit_visual(ed),
            Mode::Normal => {}
        },
        "undo" => {
            let cursor = ed.cursor();
            if let Some(pos) = ed.doc_mut().undo(cursor) {
                ed.set_cursor(pos);
            }
        }
        "redo" => {
            let cursor = ed.cursor();
            if let Some(pos) = ed.doc_mut().redo(cursor) {
                ed.set_cursor(pos);
            }
        }
        "command_mode" => ed.prompt = Some(Prompt::new(PromptKind::Command, "")),
        "search" => {
            let cursor = ed.cursor();
            let scroll = ed.view().scroll;
            ed.prompt = Some(Prompt::new(PromptKind::Search { forward: true, origin: cursor, scroll }, ""));
        }
        other => return Err(format!("unknown command {other:?} (:commands lists them)")),
    }
    let _ = register;
    Ok(())
}

/// A path relative to the current file's folder, then to the working directory.
pub fn resolve_path(ed: &Editor, text: &str) -> Option<PathBuf> {
    let expanded = crate::document::absolute(std::path::Path::new(text));
    if std::path::Path::new(text).is_absolute() || text.starts_with("~/") {
        return expanded.exists().then_some(expanded);
    }
    if let Some(dir) = ed.doc().path.as_ref().and_then(|path| path.parent()) {
        let candidate = dir.join(text);
        if candidate.exists() {
            return Some(candidate);
        }
    }
    let candidate = ed.cwd.join(text);
    candidate.exists().then_some(candidate)
}

/// `gf`: opens `path`, `path:line` or `path:line:col` under the cursor.
fn goto_file(ed: &mut Editor) -> Result<(), String> {
    let text = path_under_cursor(ed).ok_or("no path under the cursor")?;
    let (path, line, col) = crate::jobs::split_location(&text);
    let resolved = resolve_path(ed, &path).ok_or_else(|| format!("no file {path}"))?;
    ed.push_jump();
    ed.open(&resolved)?;
    if let Some(line) = line {
        ed.set_cursor(Pos::new(line.saturating_sub(1), col.unwrap_or(1).saturating_sub(1)));
        ed.align_cursor('z');
    }
    Ok(())
}
