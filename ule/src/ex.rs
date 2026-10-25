//! The `:` command line: ranges, :w/:q/:e family, :s, :g, :sort, :normal,
//! :!, :set, ul integration, and the prompt keys (history, completion, incsearch).

use std::path::{Path, PathBuf};

use crate::document::{absolute, display_path};
use crate::edit;
use crate::editor::{Editor, Mode};
use crate::keys::{Code, Key};
use crate::text::{char_len, Pos};
use crate::widgets::{ConfirmAction, InputAction, Prompt, PromptKind};

/// Ex command names for completion (named commands from commands.rs are added too).
pub const EX: &[(&str, &str)] = &[
    ("write", "save (:w path saves as)"),
    ("wall", "save all modified files"),
    ("quit", "close window / quit"),
    ("qall", "quit ule"),
    ("wq", "save and close"),
    ("xit", "save if modified and close"),
    ("xall", "save all and quit"),
    ("edit", "open a file (:e! reloads)"),
    ("enew", "new empty buffer"),
    ("buffer", "switch to a buffer by number or name"),
    ("bnext", "next buffer"),
    ("bprevious", "previous buffer"),
    ("bdelete", "close a buffer"),
    ("buffers", "list buffers"),
    ("split", "split below (optionally a file)"),
    ("vsplit", "split right (optionally a file)"),
    ("close", "close the window"),
    ("only", "only this window"),
    ("substitute", "s/pattern/replacement/flags"),
    ("global", "g/pattern/d or g/pattern/normal keys"),
    ("vglobal", "v/pattern/d: lines NOT matching"),
    ("nohlsearch", "clear search highlight"),
    ("set", "set an option: set wrap, set ts=2, set nowrap, set wrap!"),
    ("theme", "switch theme"),
    ("colorscheme", "switch theme"),
    ("sort", "sort lines (sort u, sort n, sort! reverse)"),
    ("delete", "delete lines in the range"),
    ("yank", "yank lines in the range"),
    ("normal", "run normal-mode keys on each line of the range"),
    ("read", "insert a file (or :r !cmd output) below"),
    ("cd", "change the working directory"),
    ("pwd", "print the working directory"),
    ("ul", "run a ul command in the panel (:ul! hands over the terminal)"),
    ("run", "run a shell command in the panel (default: the file's run command)"),
    ("ask", "ask the local model (ul lm)"),
    ("ai", "rewrite the range with the local model"),
    ("grep", "search the project"),
    ("find", "find a file"),
    ("format", "format the file"),
    ("lsp", "lsp info | restart | stop"),
    ("config", "edit ule.toml"),
    ("config-reload", "reload ule.toml"),
    ("help", "help"),
    ("commands", "command palette"),
    ("keys", "key binding picker"),
    ("registers", "show registers"),
    ("marks", "show marks"),
    ("lang", "set the language: lang python"),
    ("explore", "file explorer"),
    ("terminal", "open a shell (exit returns)"),
    ("rename", "rename the file on disk"),
    ("trash", "move the file to the Trash"),
    ("copy-path", "copy the file's path to the clipboard"),
    ("retab", "convert indentation to the current tab settings"),
    ("messages", "show recent messages"),
];

const SHORT: &[(&str, &str)] = &[
    ("w", "write"),
    ("wa", "wall"),
    ("q", "quit"),
    ("qa", "qall"),
    ("quita", "qall"),
    ("x", "xit"),
    ("xa", "xall"),
    ("wqa", "xall"),
    ("e", "edit"),
    ("b", "buffer"),
    ("bn", "bnext"),
    ("bp", "bprevious"),
    ("bN", "bprevious"),
    ("bd", "bdelete"),
    ("bw", "bdelete"),
    ("ls", "buffers"),
    ("sp", "split"),
    ("vs", "vsplit"),
    ("vsp", "vsplit"),
    ("clo", "close"),
    ("on", "only"),
    ("s", "substitute"),
    ("g", "global"),
    ("v", "vglobal"),
    ("noh", "nohlsearch"),
    ("se", "set"),
    ("colo", "colorscheme"),
    ("sor", "sort"),
    ("d", "delete"),
    ("y", "yank"),
    ("norm", "normal"),
    ("r", "read"),
    ("f", "find"),
    ("fmt", "format"),
    ("h", "help"),
    ("reg", "registers"),
    ("setf", "lang"),
    ("Ex", "explore"),
    ("Explore", "explore"),
    ("term", "terminal"),
    ("mv", "rename"),
    ("rm", "trash"),
    ("mes", "messages"),
];

fn expand_name(name: &str) -> String {
    if let Some((_, full)) = SHORT.iter().find(|(short, _)| *short == name) {
        return full.to_string();
    }
    if EX.iter().any(|(full, _)| *full == name) {
        return name.to_string();
    }
    // Unique prefixes of ex commands work like vim abbreviations.
    let matches: Vec<&str> = EX.iter().map(|(full, _)| *full).filter(|full| full.starts_with(name)).collect();
    if matches.len() == 1 && name.len() >= 2 {
        return matches[0].to_string();
    }
    name.to_string()
}

/// Splits `3,5s/a/b/` into (range text, name, bang, args).
fn split_command(line: &str) -> (String, String, bool, String) {
    let line = line.trim_start_matches([':', ' ']);
    let chars: Vec<char> = line.chars().collect();
    let mut index = 0;
    // Range: digits . $ % , ; + - 'x /pat/ ?pat?
    while index < chars.len() {
        let c = chars[index];
        if c.is_ascii_digit() || ".$%,;+-".contains(c) {
            index += 1;
        } else if c == '\'' && index + 1 < chars.len() {
            index += 2;
        } else if (c == '/' || c == '?') && index == 0
            || ((c == '/' || c == '?') && index > 0 && ",;".contains(chars[index - 1]))
        {
            let close =
                (index + 1..chars.len()).find(|at| chars[*at] == c && chars[*at - 1] != '\\').unwrap_or(chars.len());
            index = (close + 1).min(chars.len());
        } else {
            break;
        }
    }
    let range: String = chars[..index].iter().collect();
    let rest: String = chars[index..].iter().collect();
    let rest = rest.trim_start();
    // `s/a/b/`, `g/x/d`, `!cmd`, `&` and `>`/`<` have no space before their argument.
    let first = rest.chars().next().unwrap_or(' ');
    if first == '!' || first == '&' || first == '>' || first == '<' || first == '=' {
        let count = rest.chars().take_while(|c| *c == first).count();
        let name: String = std::iter::repeat_n(first, count).collect();
        return (range, name, false, rest[count..].trim().to_string());
    }
    let name_len = rest.chars().take_while(|c| c.is_alphanumeric() || *c == '_' || *c == '-').count();
    let mut name: String = rest.chars().take(name_len).collect();
    let mut after: String = rest.chars().skip(name_len).collect();
    // `s/` style: the name ends where the delimiter starts.
    for short in ["s", "g", "v", "substitute", "global", "vglobal"] {
        if name.starts_with(short)
            && name.len() > short.len()
            && name[short.len()..].chars().all(|c| !c.is_alphanumeric())
        {
            after = format!("{}{after}", &name[short.len()..]);
            name = short.to_string();
        }
    }
    if name == "s" || name == "g" || name == "v" || name == "substitute" {
        if let Some(c) = after.chars().next() {
            if !c.is_alphanumeric() && c != ' ' && c != '!' {
                return (range, name, false, after);
            }
        }
    }
    let bang = after.starts_with('!');
    let args = if bang { after[1..].trim().to_string() } else { after.trim().to_string() };
    (range, name, bang, args)
}

/// Parses a range into 0-based (first, last) lines; None when the text has no range.
fn parse_range(ed: &Editor, text: &str) -> Result<Option<(usize, usize)>, String> {
    if text.is_empty() {
        return Ok(None);
    }
    let last = ed.doc().text.last_line();
    if text == "%" {
        return Ok(Some((0, last)));
    }
    let cursor = ed.cursor().line;
    let address = |part: &str| -> Result<usize, String> {
        let part = part.trim();
        let chars: Vec<char> = part.chars().collect();
        let mut index = 0;
        let mut line: isize = cursor as isize;
        if index < chars.len() {
            match chars[index] {
                '.' => index += 1,
                '$' => {
                    line = last as isize;
                    index += 1;
                }
                '\'' => {
                    let mark = *chars.get(index + 1).ok_or("mark name missing")?;
                    line = match mark {
                        '<' => ed.last_visual.map(|(_, a, b, _)| a.min(b).line).ok_or("no visual selection")? as isize,
                        '>' => ed.last_visual.map(|(_, a, b, _)| a.max(b).line).ok_or("no visual selection")? as isize,
                        c => ed.doc().marks.get(&c).ok_or(format!("mark {c} not set"))?.line as isize,
                    };
                    index += 2;
                }
                '/' | '?' => {
                    let delimiter = chars[index];
                    let close = (index + 1..chars.len()).find(|at| chars[*at] == delimiter).unwrap_or(chars.len());
                    let pattern: String = chars[index + 1..close].iter().collect();
                    let regex = ed.compile_search(&pattern)?;
                    let doc = ed.doc();
                    let found = if delimiter == '/' {
                        (cursor + 1..=last).chain(0..=cursor).find(|line| regex.is_match(doc.text.line(*line)))
                    } else {
                        (0..cursor).rev().chain((cursor..=last).rev()).find(|line| regex.is_match(doc.text.line(*line)))
                    };
                    line = found.ok_or(format!("pattern not found: {pattern}"))? as isize;
                    index = (close + 1).min(chars.len());
                }
                c if c.is_ascii_digit() => {
                    let digits: String = chars[index..].iter().take_while(|c| c.is_ascii_digit()).collect();
                    index += digits.len();
                    line = digits.parse::<isize>().map_err(|_| "bad line number")? - 1;
                }
                _ => {}
            }
        }
        // Offsets: +3, -2, + (1).
        while index < chars.len() {
            let sign = match chars[index] {
                '+' => 1,
                '-' => -1,
                _ => return Err(format!("bad range {part:?}")),
            };
            index += 1;
            let digits: String = chars[index..].iter().take_while(|c| c.is_ascii_digit()).collect();
            index += digits.len();
            line += sign * digits.parse::<isize>().unwrap_or(1);
        }
        Ok(line.clamp(0, last as isize) as usize)
    };
    let parts: Vec<&str> = text.split([',', ';']).collect();
    let first = address(parts[0])?;
    let second = if parts.len() > 1 { address(parts[1])? } else { first };
    Ok(Some((first.min(second), first.max(second))))
}

fn expand_percent(ed: &Editor, args: &str) -> String {
    let path = ed.doc().path.as_ref().map(|path| crate::jobs::quote(&path.to_string_lossy()));
    let mut out = String::new();
    let mut chars = args.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\\' && chars.peek() == Some(&'%') {
            out.push('%');
            chars.next();
        } else if c == '%' {
            match &path {
                Some(path) => out.push_str(path),
                None => out.push('%'),
            }
        } else {
            out.push(c);
        }
    }
    out
}

/// Runs one command line (without the leading `:`).
pub fn run(ed: &mut Editor, line: &str) {
    let line = line.trim();
    if line.is_empty() {
        return;
    }
    if let Err(error) = execute(ed, line) {
        ed.error(error);
    }
}

fn execute(ed: &mut Editor, line: &str) -> Result<(), String> {
    let (range_text, raw_name, bang, args) = split_command(line);
    let range = parse_range(ed, &range_text)?;
    let name = expand_name(&raw_name);
    if name.is_empty() {
        // `:42`, `:$`, `:'a`: go to the line.
        if let Some((_, last)) = range {
            ed.push_jump();
            let col = ed.doc().text.first_non_blank(last);
            ed.set_cursor(Pos::new(last, col));
            ed.center_cursor_if_offscreen();
        }
        return Ok(());
    }
    let doc_id = ed.view().doc;
    let lines = || range.unwrap_or((ed.cursor().line, ed.cursor().line));
    match name.as_str() {
        "write" | "wq" | "xit" => {
            let path = (!args.is_empty()).then(|| PathBuf::from(&args));
            let modified =
                ed.doc().modified() || path.is_some() || ed.doc().path.as_ref().is_some_and(|path| !path.exists());
            if name != "xit" || modified {
                if let Some((first, last)) = range.filter(|_| path.is_some()) {
                    // `:5,10w part.txt` writes only those lines.
                    let text = edit::lines_text(ed, first, last);
                    let target = absolute(path.as_deref().unwrap_or(Path::new("")));
                    std::fs::write(&target, text).map_err(|error| format!("{}: {error}", target.display()))?;
                    ed.info(format!("\"{}\" {} lines written", display_path(&target), last - first + 1));
                } else {
                    let message = ed.save(doc_id, path, bang)?;
                    ed.info(message);
                }
            }
            if name != "write" {
                close_or_quit(ed, false)?;
            }
        }
        "wall" | "xall" => {
            let ids: Vec<usize> = ed.docs.values().filter(|doc| doc.modified()).map(|doc| doc.id).collect();
            let mut saved = 0;
            for id in ids {
                ed.save(id, None, bang)?;
                saved += 1;
            }
            ed.info(format!("{saved} file(s) written"));
            if name == "xall" {
                ed.remember_positions();
                ed.quit = true;
            }
        }
        "quit" => close_or_quit(ed, bang)?,
        "qall" => {
            if bang {
                ed.remember_positions();
                ed.quit = true;
            } else {
                let unsaved = ed.modified_docs();
                if unsaved.is_empty() {
                    ed.remember_positions();
                    ed.quit = true;
                } else {
                    ed.prompt = Some(Prompt::new(
                        PromptKind::Confirm {
                            question: format!("Unsaved: {}. Quit and discard?", unsaved.join(", ")),
                            action: ConfirmAction::QuitAll,
                        },
                        "",
                    ));
                }
            }
        }
        "close" => {
            if !ed.close_view() {
                return Err("this is the last window (:q quits)".into());
            }
        }
        "only" => ed.only_view(),
        "edit" => {
            if args.is_empty() {
                let doc = ed.doc();
                if doc.path.is_none() {
                    return Err("no file name".into());
                }
                if doc.modified() && !bang {
                    return Err("unsaved changes (:e! discards them)".into());
                }
                let cursor = ed.cursor();
                ed.doc_mut().reload(cursor).map_err(|error| error.to_string())?;
                ed.lsp_changed_all();
                ed.clamp_cursor();
                ed.info("reloaded");
            } else {
                let path = PathBuf::from(expand_percent(ed, &args).trim_matches('\''));
                let (path, line, col) = crate::jobs::split_location(&path.to_string_lossy());
                ed.push_jump();
                ed.open(Path::new(&path))?;
                if let Some(line) = line {
                    ed.set_cursor(Pos::new(line.saturating_sub(1), col.unwrap_or(1).saturating_sub(1)));
                    ed.align_cursor('z');
                }
            }
        }
        "enew" => {
            let id = ed.scratch("[scratch]", crate::document::DocKind::Scratch);
            ed.show_doc(id);
        }
        "buffer" => {
            if args.is_empty() {
                crate::picker::open_buffers(ed);
                return Ok(());
            }
            let target = if let Ok(number) = args.parse::<usize>() {
                ed.buffers.get(number.saturating_sub(1)).copied()
            } else {
                ed.buffers.iter().copied().find(|id| ed.docs[id].title().contains(&args))
            };
            let id = target.ok_or(format!("no buffer {args}"))?;
            ed.show_doc(id);
        }
        "bnext" => ed.cycle_buffer(1),
        "bprevious" => ed.cycle_buffer(-1),
        "bdelete" => {
            let id = if args.is_empty() {
                doc_id
            } else if let Ok(number) = args.parse::<usize>() {
                *ed.buffers.get(number.saturating_sub(1)).ok_or(format!("no buffer {number}"))?
            } else {
                ed.buffers
                    .iter()
                    .copied()
                    .find(|id| ed.docs[id].title().contains(&args))
                    .ok_or(format!("no buffer {args}"))?
            };
            ed.close_doc(id, bang)?;
        }
        "buffers" => crate::picker::open_buffers(ed),
        "split" | "vsplit" => {
            ed.split(name == "vsplit");
            if !args.is_empty() {
                ed.open(Path::new(&expand_percent(ed, &args)))?;
            }
        }
        "substitute" | "&" | "&&" => {
            let (first, last) = range.unwrap_or((ed.cursor().line, ed.cursor().line));
            substitute(ed, first, last, if name == "substitute" { &args } else { "" })?;
        }
        "global" | "vglobal" => {
            let (first, last) = range.unwrap_or((0, ed.doc().text.last_line()));
            global(ed, first, last, &args, name == "vglobal" || bang)?;
        }
        "nohlsearch" => ed.hlsearch_active = false,
        "set" => set(ed, &args)?,
        "theme" | "colorscheme" => {
            if args.is_empty() {
                crate::picker::open_themes(ed);
            } else {
                apply_theme(ed, &args)?;
            }
        }
        "sort" => {
            let (first, last) = range.unwrap_or((0, ed.doc().text.last_line()));
            sort(ed, first, last, &args, bang);
        }
        "delete" | "yank" => {
            let (first, last) = lines();
            let register = args.chars().next().filter(|c| c.is_alphanumeric() || *c == '+' || *c == '_');
            let op = if name == "delete" { edit::Op::Delete } else { edit::Op::Yank };
            edit::operator(ed, op, Pos::new(first, 0), Pos::new(last, 0), true, register);
            edit::commit(ed);
        }
        ">" | ">>" | "<" | "<<" => {
            let (first, last) = lines();
            edit::shift_lines(ed, first, last, name.starts_with('>'), name.len());
            edit::commit(ed);
        }
        "normal" => {
            let (first, last) = lines();
            let keys = crate::keys::parse(&args, &ed.keymap.leader.clone())?;
            for line in first..=last.min(ed.doc().text.last_line()) {
                ed.mode = Mode::Normal;
                ed.set_cursor(Pos::new(line, 0));
                ed.vim.replaying += 1;
                for key in &keys {
                    crate::vim::handle_key(ed, *key);
                }
                if matches!(ed.mode, Mode::Insert | Mode::Replace) {
                    crate::vim::handle_key(ed, Key::plain(Code::Esc));
                }
                ed.vim.replaying -= 1;
            }
            edit::commit(ed);
        }
        "read" => {
            let line = range.map_or(ed.cursor().line, |(_, last)| last);
            let text = if let Some(command) = args.strip_prefix('!') {
                crate::jobs::capture(&expand_percent(ed, command), &ed.cwd, None)?
            } else {
                let path = absolute(Path::new(&expand_percent(ed, &args)));
                std::fs::read_to_string(&path).map_err(|error| format!("{}: {error}", path.display()))?
            };
            let body = text.strip_suffix('\n').unwrap_or(&text);
            let end = Pos::new(line, ed.doc().text.line_len(line));
            let cursor = ed.cursor();
            ed.doc_mut().insert(end, &format!("\n{body}"), cursor);
            edit::commit(ed);
            ed.set_cursor(Pos::new(line + 1, 0));
        }
        "!" => {
            let command = expand_percent(ed, &args);
            if let Some((first, last)) = range {
                // `:%!sort`: filter the lines through the command.
                let input = edit::lines_text(ed, first, last);
                let output = crate::jobs::capture(&command, &ed.cwd, Some(&input))?;
                let body = output.strip_suffix('\n').unwrap_or(&output);
                let end = Pos::new(last, ed.doc().text.line_len(last));
                let cursor = ed.cursor();
                ed.doc_mut().replace(Pos::new(first, 0), end, body, cursor);
                edit::commit(ed);
                ed.set_cursor(Pos::new(first, 0));
            } else if command.is_empty() {
                return Err("usage: :!command (or :%!filter)".into());
            } else {
                ed.handoff = Some(crate::jobs::Handoff { command, wait: true });
            }
        }
        "cd" => {
            let target = if args.is_empty() { crate::config::home() } else { absolute(Path::new(&args)) };
            std::env::set_current_dir(&target).map_err(|error| format!("{}: {error}", target.display()))?;
            ed.cwd = target.clone();
            ed.info(format!("cwd: {}", display_path(&target)));
        }
        "pwd" => {
            let cwd = ed.cwd.display().to_string();
            ed.info(cwd);
        }
        "ul" => {
            if args.is_empty() {
                crate::picker::open_ul(ed);
            } else {
                let args = expand_percent(ed, &args);
                crate::ul::run(ed, &args, bang)?;
            }
        }
        "run" => {
            if args.is_empty() {
                crate::jobs::run_current(ed, &[])?;
            } else {
                let command = expand_percent(ed, &args);
                crate::jobs::run_shell(ed, &command, "[run]")?;
                ed.last_run = Some(command);
            }
        }
        "ask" => {
            let selection = range.map(|(first, last)| edit::lines_text(ed, first, last));
            if args.is_empty() {
                crate::commands::run(ed, "ask", &[], None, None)?;
            } else {
                crate::ul::ask(ed, &args, selection)?;
            }
        }
        "ai" => {
            let (first, last) = range.ok_or("select lines first (V … then :ai instruction)")?;
            if args.is_empty() {
                return Err("usage: :'<,'>ai make it shorter".into());
            }
            let text = edit::lines_text(ed, first, last);
            let end = Pos::new(last, ed.doc().text.line_len(last));
            let version = ed.doc().version;
            crate::ul::ai_edit(ed, &args, doc_id, Pos::new(first, 0), end, version, text)?;
        }
        "grep" => crate::picker::open_grep(ed, &args),
        "find" => {
            crate::picker::open_files(ed, false);
            if let Some(picker) = ed.picker.as_mut() {
                picker.input.set(&args);
            }
            crate::picker::refresh(ed);
        }
        "format" => crate::commands::run(ed, "format", &[], None, None)?,
        "lsp" => match args.as_str() {
            "" | "info" => crate::commands::run(ed, "lsp_info", &[], None, None)?,
            "restart" => crate::lsp::restart(ed),
            "stop" => {
                ed.lsp.shutdown();
                ed.info("language servers stopped");
            }
            other => return Err(format!("lsp {other}? use info, restart or stop")),
        },
        "config" => crate::commands::run(ed, "open_config", &[], None, None)?,
        "config-reload" => reload_config(ed),
        "help" => crate::help::open(ed, (!args.is_empty()).then_some(args.as_str())),
        "commands" => crate::picker::open_commands(ed),
        "keys" | "map" | "maps" => crate::picker::open_keymaps(ed),
        "registers" => {
            let mut names: Vec<char> = ed.registers.keys().copied().collect();
            names.sort();
            let text: Vec<String> = names
                .into_iter()
                .map(|name| {
                    let register = &ed.registers[&name];
                    let preview: String = register.text.replace('\n', "⏎").chars().take(70).collect();
                    format!("\"{name}  {preview}")
                })
                .collect();
            ed.popup =
                Some(crate::widgets::Popup::new(crate::widgets::PopupKind::Info, "Registers", &text.join("\n"), false));
        }
        "marks" => {
            let mut marks: Vec<(char, Pos)> = ed.doc().marks.iter().map(|(name, pos)| (*name, *pos)).collect();
            marks.sort();
            let text: Vec<String> = marks
                .iter()
                .map(|(name, pos)| {
                    format!("{name}  {:>5}:{:<3} {}", pos.line + 1, pos.col + 1, ed.doc().text.line(pos.line).trim())
                })
                .collect();
            ed.popup =
                Some(crate::widgets::Popup::new(crate::widgets::PopupKind::Info, "Marks", &text.join("\n"), false));
        }
        "messages" => {
            let text = ed.message.as_ref().map_or_else(|| "no messages".to_string(), |message| message.text.clone());
            ed.popup = Some(crate::widgets::Popup::new(crate::widgets::PopupKind::Info, "Messages", &text, false));
        }
        "lang" => {
            if args.is_empty() {
                crate::picker::open_languages(ed);
            } else {
                let lang = ed.languages.by_name(&args).ok_or(format!("unknown language {args}"))?;
                ed.lsp_close(doc_id);
                ed.doc_mut().set_language(Some(lang));
                ed.lsp_open(doc_id);
                ed.info(format!("language: {}", ed.languages.list[lang].name));
            }
        }
        "explore" => crate::commands::run(ed, "explorer", &[], None, None)?,
        "terminal" => {
            let shell = std::env::var("SHELL").unwrap_or_else(|_| "/bin/zsh".into());
            ed.handoff = Some(crate::jobs::Handoff { command: shell, wait: false });
        }
        "rename" => {
            let path = ed.doc().path.clone().ok_or("this buffer has no file")?;
            if args.is_empty() {
                let start = display_path(&path);
                ed.prompt = Some(Prompt::new(
                    PromptKind::Input { title: "Rename to".into(), action: InputAction::RenameFile(path) },
                    &start,
                ));
            } else {
                rename_file(ed, &path, &args)?;
            }
        }
        "trash" => {
            let path = ed.doc().path.clone().ok_or("this buffer has no file")?;
            ed.prompt = Some(Prompt::new(
                PromptKind::Confirm {
                    question: format!("Move {} to the Trash?", display_path(&path)),
                    action: ConfirmAction::DeleteFile(path),
                },
                "",
            ));
        }
        "copy-path" => {
            let path = ed.doc().path.clone().ok_or("this buffer has no file")?;
            let text = path.to_string_lossy().into_owned();
            crate::clipboard::set(&text);
            ed.info(format!("copied {text}"));
        }
        "retab" => {
            let unit = ed.indent_unit(ed.doc());
            let tab = ed.tab_width(ed.doc());
            let cursor = ed.cursor();
            for line in 0..ed.doc().text.len_lines() {
                let indent = ed.doc().text.indent_of(line).to_string();
                if indent.is_empty() {
                    continue;
                }
                let width = crate::display::col_to_display(&indent, char_len(&indent), tab);
                let wanted = if unit == "\t" {
                    format!("{}{}", "\t".repeat(width / tab), " ".repeat(width % tab))
                } else {
                    " ".repeat(width)
                };
                if wanted != indent {
                    ed.doc_mut().replace(Pos::new(line, 0), Pos::new(line, char_len(&indent)), &wanted, cursor);
                }
            }
            edit::commit(ed);
        }
        other => {
            // Every named command works as `:name args`.
            if crate::commands::names().contains(&other) {
                let words: Vec<String> = args.split_whitespace().map(str::to_string).collect();
                return crate::commands::run(ed, other, &words, None, None);
            }
            return Err(format!("not a command: {raw_name}"));
        }
    }
    Ok(())
}

fn close_or_quit(ed: &mut Editor, force: bool) -> Result<(), String> {
    if ed.close_view() {
        return Ok(());
    }
    let unsaved = ed.modified_docs();
    if !force && !unsaved.is_empty() {
        let current = ed.doc().modified();
        let others = unsaved.len() - usize::from(current);
        return Err(if current {
            "unsaved changes (:w saves, :q! discards)".to_string()
        } else {
            format!("{others} other file(s) unsaved: {} (:wa saves, :qa! discards)", unsaved.join(", "))
        });
    }
    ed.remember_positions();
    ed.quit = true;
    Ok(())
}

pub fn rename_file(ed: &mut Editor, from: &Path, to: &str) -> Result<(), String> {
    let mut target = absolute(Path::new(to));
    if !to.contains('/') {
        target = from.parent().unwrap_or(Path::new("/")).join(to);
    }
    if target.exists() {
        return Err(format!("{} already exists", display_path(&target)));
    }
    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    std::fs::rename(from, &target).map_err(|error| format!("rename: {error}"))?;
    if let Some(id) = ed.find_doc(from) {
        ed.lsp_close(id);
        let doc = ed.docs.get_mut(&id).expect("document");
        doc.path = Some(target.clone());
        doc.name = display_path(&target);
        doc.lang = ed.languages.detect(Some(&target), doc.text.line(0));
        ed.lsp_open(id);
    }
    if let Some(explorer) = ed.explorer.as_mut() {
        explorer.refresh();
    }
    ed.info(format!("renamed to {}", display_path(&target)));
    Ok(())
}

pub fn apply_theme(ed: &mut Editor, name: &str) -> Result<(), String> {
    let theme = ed.themes.load(name)?;
    ed.theme = theme;
    ed.options.theme = name.to_string();
    Ok(())
}

pub fn reload_config(ed: &mut Editor) {
    let config = crate::config::Config::load(&crate::commands::names());
    let mut errors = config.errors.clone();
    let (languages, language_errors) = crate::syntax::Languages::load(config.languages.as_ref());
    errors.extend(language_errors);
    ed.themes = crate::theme::Themes::new(config.themes.as_ref());
    ed.options = config.options.clone();
    match ed.themes.load(&ed.options.theme) {
        Ok(theme) => ed.theme = theme,
        Err(error) => errors.push(error),
    }
    ed.keymap = crate::keymap::Keymap::build(&config);
    errors.extend(ed.keymap.errors.iter().cloned());
    ed.languages = languages;
    let ids: Vec<usize> = ed.docs.keys().copied().collect();
    for id in ids {
        let doc = ed.docs.get_mut(&id).expect("document");
        let lang = ed.languages.detect(doc.path.as_deref(), doc.text.line(0)).or(doc.lang);
        doc.set_language(lang);
    }
    ed.config = config;
    if errors.is_empty() {
        ed.info("ule.toml reloaded");
    } else {
        ed.error(format!("ule.toml: {}", errors.join("; ")));
    }
}

fn set(ed: &mut Editor, args: &str) -> Result<(), String> {
    if args.is_empty() {
        let text: Vec<String> = crate::config::OPTIONS
            .iter()
            .map(|(name, description)| {
                format!("{name:<26} {:<12} {description}", ed.options.get(name).unwrap_or_default())
            })
            .collect();
        ed.popup =
            Some(crate::widgets::Popup::new(crate::widgets::PopupKind::Info, "Options", &text.join("\n"), false));
        return Ok(());
    }
    for item in args.split_whitespace() {
        if let Some((name, value)) = item.split_once(['=', ':']) {
            ed.options.set(name, value)?;
            if name == "theme" {
                apply_theme(ed, value)?;
            }
            if name == "leader" {
                ed.keymap = crate::keymap::Keymap::build(&crate::config::Config {
                    options: ed.options.clone(),
                    ..Default::default()
                });
            }
        } else if let Some(name) = item.strip_suffix('!') {
            ed.options.toggle(name)?;
        } else if let Some(name) = item.strip_suffix('?') {
            let value = ed.options.get(name).ok_or(format!("unknown option {name}"))?;
            ed.info(format!("{name}={value}"));
            return Ok(());
        } else if ed.options.get(item).is_some() {
            match ed.options.get(item).as_deref() {
                Some("true") | Some("false") | Some("auto") => ed.options.set(item, "true")?,
                Some(value) => {
                    let value = value.to_string();
                    ed.info(format!("{item}={value}"));
                    return Ok(());
                }
                None => {}
            }
        } else if let Some(name) = item.strip_prefix("no").filter(|name| ed.options.get(name).is_some()) {
            ed.options.set(name, "false")?;
        } else if let Some(name) = item.strip_prefix("inv").filter(|name| ed.options.get(name).is_some()) {
            ed.options.toggle(name)?;
        } else if item == "filetype" || item == "ft" {
            let name = ed.language_name(ed.doc());
            ed.info(format!("filetype={name}"));
        } else if let Some(lang) = item.strip_prefix("filetype=").or_else(|| item.strip_prefix("ft=")) {
            return execute(ed, &format!("lang {lang}"));
        } else {
            return Err(format!("unknown option {item:?} (:set lists them)"));
        }
    }
    if args.contains("hlsearch") {
        ed.hlsearch_active = ed.options.hlsearch;
    }
    Ok(())
}

/// Translates vim's replacement syntax (`&`, `\1`, `\n`) to the regex crate's (`$0`, `${1}`).
fn replacement(text: &str) -> String {
    let mut out = String::new();
    let mut chars = text.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '\\' => match chars.next() {
                Some(d @ '0'..='9') => out.push_str(&format!("${{{d}}}")),
                Some('n') | Some('r') => out.push('\n'),
                Some('t') => out.push('\t'),
                Some('&') => out.push('&'),
                // `\$` is a literal dollar (the regex crate needs `$$`).
                Some('$') => out.push_str("$$"),
                Some(other) => out.push(other),
                None => out.push('\\'),
            },
            '&' => out.push_str("${0}"),
            // `$1` / `${name}` work too; any other `$` is literal like in vim.
            '$' if chars.peek().is_some_and(|next| next.is_ascii_digit() || *next == '{') => out.push('$'),
            '$' => out.push_str("$$"),
            other => out.push(other),
        }
    }
    out
}

fn split_delimited(args: &str) -> Option<(String, String, String)> {
    let delimiter = args.chars().next()?;
    let mut parts = vec![String::new()];
    let mut escaped = false;
    for c in args.chars().skip(1) {
        if escaped {
            if c != delimiter {
                parts.last_mut()?.push('\\');
            }
            parts.last_mut()?.push(c);
            escaped = false;
        } else if c == '\\' {
            escaped = true;
        } else if c == delimiter && parts.len() < 3 {
            parts.push(String::new());
        } else {
            parts.last_mut()?.push(c);
        }
    }
    if escaped {
        parts.last_mut()?.push('\\');
    }
    while parts.len() < 3 {
        parts.push(String::new());
    }
    Some((parts[0].clone(), parts[1].clone(), parts[2].clone()))
}

fn substitute(ed: &mut Editor, first: usize, last: usize, args: &str) -> Result<(), String> {
    let (pattern, replace, flags) = if args.trim().is_empty() {
        ed.vim.last_substitute.clone().ok_or("no previous substitute")?
    } else {
        let (pattern, replace, flags) = split_delimited(args).ok_or("usage: s/pattern/replacement/flags")?;
        let pattern = if pattern.is_empty() {
            ed.search.as_ref().map(|(pattern, _)| pattern.clone()).unwrap_or_default()
        } else {
            pattern
        };
        (pattern, replace, flags)
    };
    if pattern.is_empty() {
        return Err("empty pattern".into());
    }
    ed.vim.last_substitute = Some((pattern.clone(), replace.clone(), flags.clone()));
    let mut regex_pattern = pattern.clone();
    if flags.contains('i') {
        regex_pattern = format!("{regex_pattern}\\c");
    }
    if flags.contains('I') {
        regex_pattern = format!("{regex_pattern}\\C");
    }
    let regex = ed.compile_search(&regex_pattern)?;
    let replacement = replacement(&replace);
    let global = flags.contains('g');
    let count_only = flags.contains('n');
    let cursor = ed.cursor();
    let mut changed_lines = 0;
    let mut total = 0;
    let mut last_changed = None;
    for line in first..=last.min(ed.doc().text.last_line()) {
        let text = ed.doc().text.line(line).to_string();
        let matches = regex.find_iter(&text).count();
        if matches == 0 {
            continue;
        }
        total += if global { matches } else { 1 };
        if count_only {
            continue;
        }
        let new = if global {
            regex.replace_all(&text, replacement.as_str())
        } else {
            regex.replace(&text, replacement.as_str())
        };
        if new != text {
            let len = char_len(&text);
            ed.doc_mut().replace(Pos::new(line, 0), Pos::new(line, len), &new, cursor);
            changed_lines += 1;
            last_changed = Some(line);
        }
    }
    if total == 0 {
        return Err(format!("pattern not found: {pattern}"));
    }
    if count_only {
        ed.info(format!("{total} match(es) on {} line(s)", last - first + 1));
        return Ok(());
    }
    edit::commit(ed);
    // A replacement with newlines adds lines; the cursor goes to the last changed line.
    if let Some(line) = last_changed {
        let line = line.min(ed.doc().text.last_line());
        let col = ed.doc().text.first_non_blank(line);
        ed.set_cursor(Pos::new(line, col));
    }
    ed.set_search(&pattern, true).ok();
    ed.info(format!("{total} substitution(s) on {changed_lines} line(s)"));
    Ok(())
}

fn global(ed: &mut Editor, first: usize, last: usize, args: &str, invert: bool) -> Result<(), String> {
    let delimiter = args.chars().next().ok_or("usage: g/pattern/d")?;
    let rest: String = args.chars().skip(1).collect();
    let close = rest.find(delimiter).ok_or("usage: g/pattern/d")?;
    let pattern = &rest[..close];
    let command = rest[close + delimiter.len_utf8()..].trim();
    let regex = ed.compile_search(pattern)?;
    let matching: Vec<usize> = (first..=last.min(ed.doc().text.last_line()))
        .filter(|line| regex.is_match(ed.doc().text.line(*line)) != invert)
        .collect();
    if matching.is_empty() {
        return Err(format!("pattern not found: {pattern}"));
    }
    let command = if command.is_empty() { "p" } else { command };
    if command == "d" || command == "delete" {
        let cursor = ed.cursor();
        for line in matching.iter().rev() {
            let text = &ed.doc().text;
            let (from, to) = if *line < text.last_line() {
                (Pos::new(*line, 0), Pos::new(line + 1, 0))
            } else if *line > 0 {
                (Pos::new(line - 1, text.line_len(line - 1)), Pos::new(*line, text.line_len(*line)))
            } else {
                (Pos::new(0, 0), Pos::new(0, text.line_len(0)))
            };
            ed.doc_mut().remove(from, to, cursor);
        }
        edit::commit(ed);
        ed.clamp_cursor();
        ed.info(format!("{} line(s) deleted", matching.len()));
    } else if let Some(keys) = command.strip_prefix("normal ").or_else(|| command.strip_prefix("norm ")) {
        // Lines shift as keys edit them, so go bottom-up.
        let keys = crate::keys::parse(keys, &ed.keymap.leader.clone())?;
        for line in matching.iter().rev() {
            ed.mode = Mode::Normal;
            ed.set_cursor(Pos::new(*line, 0));
            ed.vim.replaying += 1;
            for key in &keys {
                crate::vim::handle_key(ed, *key);
            }
            if matches!(ed.mode, Mode::Insert | Mode::Replace) {
                crate::vim::handle_key(ed, Key::plain(Code::Esc));
            }
            ed.vim.replaying -= 1;
        }
        edit::commit(ed);
    } else if command == "p" || command == "print" {
        let items: Vec<(usize, String)> =
            matching.iter().map(|line| (*line, ed.doc().text.line(*line).to_string())).collect();
        crate::picker::open_lines(ed, &format!("Lines matching {pattern}"), items);
    } else {
        return Err("g supports d, normal <keys> and p".into());
    }
    Ok(())
}

fn sort(ed: &mut Editor, first: usize, last: usize, args: &str, reverse: bool) {
    let mut lines: Vec<String> = (first..=last).map(|line| ed.doc().text.line(line).to_string()).collect();
    let numeric = args.contains('n');
    let ignore_case = args.contains('i');
    if numeric {
        let number = |line: &str| -> f64 {
            let digits: String = line
                .chars()
                .skip_while(|c| !c.is_ascii_digit() && *c != '-')
                .take_while(|c| c.is_ascii_digit() || *c == '.' || *c == '-')
                .collect();
            digits.parse().unwrap_or(f64::MIN)
        };
        lines.sort_by(|a, b| number(a).partial_cmp(&number(b)).unwrap_or(std::cmp::Ordering::Equal));
    } else if ignore_case {
        lines.sort_by_key(|line| line.to_lowercase());
    } else {
        lines.sort();
    }
    if reverse {
        lines.reverse();
    }
    if args.contains('u') {
        lines.dedup();
    }
    let cursor = ed.cursor();
    let end = Pos::new(last, ed.doc().text.line_len(last));
    ed.doc_mut().replace(Pos::new(first, 0), end, &lines.join("\n"), cursor);
    edit::commit(ed);
    ed.clamp_cursor();
}

// --- the prompt ---------------------------------------------------------------------

pub fn prompt_key(ed: &mut Editor, key: Key) {
    let Some(mut prompt) = ed.prompt.take() else {
        return;
    };
    if let PromptKind::Confirm { action, .. } = &prompt.kind {
        if matches!(key.as_char(), Some('y') | Some('Y') | Some('д')) {
            confirm(ed, action.clone());
        }
        return;
    }
    let is_search = matches!(prompt.kind, PromptKind::Search { .. });
    match key.code {
        _ if key.is_esc() => {
            if let PromptKind::Search { origin, scroll, .. } = prompt.kind {
                ed.view_mut().cursor = origin;
                ed.view_mut().scroll = scroll;
            }
            return;
        }
        Code::Enter => {
            submit(ed, prompt);
            return;
        }
        Code::Backspace if prompt.line.text.is_empty() => {
            if let PromptKind::Search { origin, scroll, .. } = prompt.kind {
                ed.view_mut().cursor = origin;
                ed.view_mut().scroll = scroll;
            }
            return;
        }
        Code::Tab | Code::BackTab if prompt.kind == PromptKind::Command => {
            complete(ed, &mut prompt, key.code == Code::Tab);
            ed.prompt = Some(prompt);
            return;
        }
        Code::Up | Code::Down => {
            let history = match prompt.kind {
                PromptKind::Command => ed.persisted.commands.clone(),
                PromptKind::Search { .. } => ed.persisted.searches.clone(),
                _ => Vec::new(),
            };
            if !history.is_empty() {
                if prompt.history.is_none() {
                    prompt.typed = prompt.line.text.clone();
                }
                // Up/down walk only the entries that start with what was typed.
                let typed = prompt.typed.clone();
                let matching: Vec<&String> = history.iter().filter(|item| item.starts_with(&typed)).collect();
                let index = match (prompt.history, key.code) {
                    (None, Code::Up) => matching.len().checked_sub(1),
                    (Some(index), Code::Up) => Some(index.saturating_sub(1)),
                    (Some(index), Code::Down) if index + 1 < matching.len() => Some(index + 1),
                    _ => None,
                };
                match index {
                    Some(index) if !matching.is_empty() => {
                        prompt.line.set(matching[index]);
                        prompt.history = Some(index);
                    }
                    _ => {
                        prompt.line.set(&typed);
                        prompt.history = None;
                    }
                }
            }
            ed.prompt = Some(prompt);
            return;
        }
        Code::Char('r') if key.ctrl => {
            // Ctrl-r Ctrl-w inserts the word under the cursor (one key here: Ctrl-r).
            if let Some((_, _, word)) = crate::motion::word_at(&ed.doc().text, ed.cursor()) {
                prompt.line.insert(&word);
            }
        }
        _ => {
            prompt.line.handle(key);
            prompt.completion = None;
            prompt.history = None;
        }
    }
    if is_search && ed.options.incsearch {
        incremental_search(ed, &prompt);
    }
    ed.prompt = Some(prompt);
}

pub fn paste(ed: &mut Editor, text: &str) {
    if let Some(prompt) = ed.prompt.as_mut() {
        prompt.line.insert(text.lines().next().unwrap_or(""));
    }
}

fn incremental_search(ed: &mut Editor, prompt: &Prompt) {
    let PromptKind::Search { forward, origin, scroll } = prompt.kind else {
        return;
    };
    ed.view_mut().cursor = origin;
    ed.view_mut().scroll = scroll;
    if prompt.line.text.is_empty() {
        ed.search_regex = None;
        return;
    }
    let Ok(regex) = ed.compile_search(&prompt.line.text) else {
        return;
    };
    ed.search_regex = Some(regex);
    ed.hlsearch_active = true;
    if let Some((start, _, _)) = ed.find_match(ed.doc(), origin, forward) {
        ed.view_mut().cursor = start;
        let focus = ed.focus;
        ed.scroll_to_cursor(focus);
    }
}

fn submit(ed: &mut Editor, prompt: Prompt) {
    let text = prompt.line.text.clone();
    match prompt.kind {
        PromptKind::Command => {
            ed.persisted.add_command(&text);
            ed.vim.last_ex = Some(text.clone());
            run(ed, &text);
        }
        PromptKind::Search { forward, origin, .. } => {
            let pattern = if text.is_empty() {
                ed.search.as_ref().map(|(pattern, _)| pattern.clone()).unwrap_or_default()
            } else {
                text
            };
            if pattern.is_empty() {
                return;
            }
            if let Err(error) = ed.set_search(&pattern, forward) {
                ed.error(error);
                return;
            }
            ed.view_mut().cursor = origin;
            ed.search_next(false, 1);
        }
        PromptKind::Input { action, .. } => {
            if let Err(error) = input(ed, action, &text) {
                ed.error(error);
            }
        }
        PromptKind::Confirm { .. } => {}
    }
}

fn input(ed: &mut Editor, action: InputAction, text: &str) -> Result<(), String> {
    let text = text.trim();
    match action {
        InputAction::LspRename => {
            if !text.is_empty() {
                crate::lsp::rename(ed, text)?;
            }
        }
        InputAction::GitCommit => {
            if text.is_empty() {
                return Err("empty commit message".into());
            }
            ed.save_all_quietly();
            crate::ul::run(ed, &format!("git {}", crate::jobs::quote(text)), false)?;
        }
        InputAction::Ask { with_selection } => {
            if !text.is_empty() {
                crate::ul::ask(ed, text, with_selection)?;
            }
        }
        InputAction::AiEdit { doc, start, end, version, text: original } => {
            if !text.is_empty() {
                crate::ul::ai_edit(ed, text, doc, start, end, version, original)?;
            }
        }
        InputAction::UlArgs(command) => {
            crate::ul::run(ed, &format!("{command} {text}"), false)?;
        }
        InputAction::NewFile(dir) => {
            if text.is_empty() {
                return Ok(());
            }
            let path = if text.starts_with('/') || text.starts_with('~') {
                absolute(Path::new(text))
            } else {
                absolute(&ed.cwd.join(text))
            };
            let _ = dir;
            if text.ends_with('/') {
                std::fs::create_dir_all(&path).map_err(|error| error.to_string())?;
                ed.info(format!("created {}/", display_path(&path)));
            } else {
                if let Some(parent) = path.parent() {
                    std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
                }
                if !path.exists() {
                    std::fs::write(&path, "").map_err(|error| error.to_string())?;
                }
                ed.open(&path)?;
            }
            if let Some(explorer) = ed.explorer.as_mut() {
                explorer.refresh();
                explorer.reveal(&path);
            }
        }
        InputAction::RenameFile(from) => {
            if !text.is_empty() {
                rename_file(ed, &from, text)?;
            }
        }
        InputAction::Run => {
            if !text.is_empty() {
                crate::jobs::run_shell(ed, text, "[run]")?;
                ed.last_run = Some(text.to_string());
            }
        }
        InputAction::SaveAs(doc) => {
            if !text.is_empty() {
                let message = ed.save(doc, Some(PathBuf::from(text)), false)?;
                ed.info(message);
            }
        }
        InputAction::GotoLine => {
            let (line, col) = text.split_once(':').map_or((text, None), |(line, col)| (line, Some(col)));
            let line: usize = line.trim().parse().map_err(|_| format!("not a line number: {text}"))?;
            let col = col.and_then(|col| col.trim().parse::<usize>().ok()).unwrap_or(1);
            ed.push_jump();
            ed.set_cursor(Pos::new(line.saturating_sub(1), col.saturating_sub(1)));
            ed.center_cursor_if_offscreen();
        }
        InputAction::Replace { pattern } => {
            let line = format!("%s/{}/{}/g", pattern.replace('/', "\\/"), text.replace('/', "\\/"));
            run(ed, &line);
        }
    }
    Ok(())
}

fn confirm(ed: &mut Editor, action: ConfirmAction) {
    match action {
        ConfirmAction::QuitAll => {
            ed.remember_positions();
            ed.quit = true;
        }
        ConfirmAction::DeleteFile(path) => match crate::explorer::trash(&path) {
            Ok(()) => {
                if let Some(id) = ed.find_doc(&path) {
                    let _ = ed.close_doc(id, true);
                }
                if let Some(explorer) = ed.explorer.as_mut() {
                    explorer.refresh();
                }
                ed.info(format!("moved {} to the Trash", display_path(&path)));
            }
            Err(error) => ed.error(error),
        },
        ConfirmAction::CloseBuffer(id) => {
            let _ = ed.close_doc(id, true);
        }
        ConfirmAction::Reload(id) => {
            let cursor = ed.cursor();
            if let Some(doc) = ed.docs.get_mut(&id) {
                if let Err(error) = doc.reload(cursor) {
                    ed.error(error.to_string());
                }
            }
        }
    }
}

impl Editor {
    pub fn save_all_quietly(&mut self) {
        let ids: Vec<usize> =
            self.docs.values().filter(|doc| doc.modified() && doc.path.is_some()).map(|doc| doc.id).collect();
        for id in ids {
            if let Err(error) = self.save(id, None, false) {
                self.error(error);
            }
        }
    }
}

// --- completion of the command line --------------------------------------------------------

fn complete(ed: &mut Editor, prompt: &mut Prompt, forward: bool) {
    if prompt.completion.is_none() {
        prompt.completion_base = prompt.line.text.clone();
        prompt.completions = candidates(ed, &prompt.completion_base);
        if prompt.completions.is_empty() {
            return;
        }
    }
    let len = prompt.completions.len();
    let next = match prompt.completion {
        None if forward => 0,
        None => len - 1,
        Some(index) if forward => (index + 1) % len,
        Some(index) => (index + len - 1) % len,
    };
    prompt.completion = Some(next);
    let base = prompt.completion_base.clone();
    // Replace the last word of the line with the candidate.
    let cut = base.rfind([' ', '=']).map_or(0, |at| at + 1);
    let head = &base[..cut];
    let (range, _, _, _) = split_command(&base);
    let head = if cut == 0 { range.as_str() } else { head };
    prompt.line.set(&format!("{head}{}", prompt.completions[next]));
}

fn list_dir(partial: &str, cwd: &Path) -> Vec<String> {
    let expanded = if let Some(rest) = partial.strip_prefix("~/") {
        crate::config::home().join(rest).to_string_lossy().into_owned()
    } else {
        partial.to_string()
    };
    let (dir, prefix) = match expanded.rfind('/') {
        Some(at) => (expanded[..=at].to_string(), expanded[at + 1..].to_string()),
        None => (String::new(), expanded.clone()),
    };
    let shown_dir = match partial.rfind('/') {
        Some(at) => partial[..=at].to_string(),
        None => String::new(),
    };
    let base = if dir.is_empty() {
        cwd.to_path_buf()
    } else if Path::new(&dir).is_absolute() {
        PathBuf::from(&dir)
    } else {
        cwd.join(&dir)
    };
    let Ok(entries) = std::fs::read_dir(&base) else {
        return Vec::new();
    };
    let mut out: Vec<String> = entries
        .filter_map(Result::ok)
        .filter_map(|entry| {
            let name = entry.file_name().to_string_lossy().into_owned();
            if !name.starts_with(&prefix) || (name.starts_with('.') && !prefix.starts_with('.')) {
                return None;
            }
            let slash = if entry.path().is_dir() { "/" } else { "" };
            Some(format!("{shown_dir}{name}{slash}"))
        })
        .collect();
    out.sort();
    out
}

fn candidates(ed: &Editor, line: &str) -> Vec<String> {
    let (range, name, bang, args) = split_command(line);
    let _ = (range, bang);
    let has_space = line.trim_start_matches(':').contains(' ');
    if !has_space {
        let mut names: Vec<String> = EX.iter().map(|(name, _)| name.to_string()).collect();
        names.extend(crate::commands::names().into_iter().map(str::to_string));
        names.extend(SHORT.iter().map(|(short, _)| short.to_string()));
        names.sort();
        names.dedup();
        return names.into_iter().filter(|candidate| candidate.starts_with(&name) && *candidate != name).collect();
    }
    let word = args.rsplit(' ').next().unwrap_or("");
    match expand_name(&name).as_str() {
        "edit" | "write" | "split" | "vsplit" | "read" | "cd" | "find" | "wq" | "rename" => list_dir(word, &ed.cwd),
        "set" => {
            if let Some((option, value)) = word.split_once('=') {
                let values: &[&str] = match option {
                    "line_numbers" => &["relative", "absolute", "off"],
                    "format_on_save" => &["auto", "always", "never"],
                    "bufferline" => &["always", "multiple", "never"],
                    "theme" => &[],
                    "wrap" => &["true", "false", "auto"],
                    _ => &["true", "false"],
                };
                let mut values: Vec<String> = values.iter().map(|value| value.to_string()).collect();
                if option == "theme" {
                    values = ed.themes.names();
                }
                values.into_iter().filter(|candidate| candidate.starts_with(value)).collect()
            } else {
                let mut options: Vec<String> =
                    crate::config::OPTIONS.iter().map(|(name, _)| name.to_string()).collect();
                options.extend(crate::config::OPTIONS.iter().map(|(name, _)| format!("no{name}")));
                options.into_iter().filter(|candidate| candidate.starts_with(word)).collect()
            }
        }
        "theme" | "colorscheme" => ed.themes.names().into_iter().filter(|theme| theme.starts_with(word)).collect(),
        "lang" => {
            ed.languages.list.iter().map(|lang| lang.name.clone()).filter(|lang| lang.starts_with(word)).collect()
        }
        "buffer" | "bdelete" => {
            ed.buffers.iter().map(|id| ed.docs[id].title()).filter(|title| title.contains(word)).collect()
        }
        "help" => crate::help::TOPICS
            .iter()
            .map(|(topic, _)| topic.to_string())
            .filter(|topic| topic.starts_with(word))
            .collect(),
        "lsp" => ["info", "restart", "stop"]
            .iter()
            .map(|item| item.to_string())
            .filter(|item| item.starts_with(word))
            .collect(),
        "ul" => {
            if args.contains(' ') {
                list_dir(word, &ed.cwd)
            } else {
                ed.ul_commands.iter().map(|(name, _)| name.clone()).filter(|name| name.starts_with(word)).collect()
            }
        }
        _ => list_dir(word, &ed.cwd),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splits_command_lines() {
        assert_eq!(split_command("%s/a/b/g"), ("%".into(), "s".into(), false, "/a/b/g".into()));
        assert_eq!(split_command("w! out.txt"), ("".into(), "w".into(), true, "out.txt".into()));
        assert_eq!(split_command("'<,'>sort u"), ("'<,'>".into(), "sort".into(), false, "u".into()));
        assert_eq!(split_command("10,20d"), ("10,20".into(), "d".into(), false, "".into()));
        assert_eq!(split_command("%!sort -u"), ("%".into(), "!".into(), false, "sort -u".into()));
        assert_eq!(split_command("g/TODO/d"), ("".into(), "g".into(), false, "/TODO/d".into()));
        assert_eq!(split_command("42"), ("42".into(), "".into(), false, "".into()));
        assert_eq!(split_command("ul todo add milk"), ("".into(), "ul".into(), false, "todo add milk".into()));
    }

    #[test]
    fn vim_replacements() {
        assert_eq!(replacement("[&]"), "[${0}]");
        assert_eq!(replacement("\\1-\\2"), "${1}-${2}");
        assert_eq!(replacement("a\\nb"), "a\nb");
        assert_eq!(split_delimited("/a\\/b/c/g"), Some(("a/b".into(), "c".into(), "g".into())));
    }
}
