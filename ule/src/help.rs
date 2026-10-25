//! `:help`: a Markdown buffer generated from the real key bindings and commands.

use crate::document::DocKind;
use crate::editor::Editor;

pub const TOPICS: &[(&str, &str)] = &[
    ("start", "the first five minutes"),
    ("keys", "every key binding"),
    ("vim", "vim keys ule understands"),
    ("standard", "Ctrl-Z/C/V, Shift-select and other keys of ordinary editors"),
    ("commands", ":commands"),
    ("options", "settings for ule.toml and :set"),
    ("languages", "language settings, LSP, formatters, run commands"),
    ("themes", "themes and your own colors"),
    ("ul", "Unlaw integration"),
    ("ai", "local models through ul lm"),
];

/// Vim keys implemented by the grammar in vim.rs (shown in help and the key picker).
pub const VIM_KEYS: &[(&str, &str)] = &[
    ("h j k l", "left, down, up, right (arrows too)"),
    ("w b e ge", "word forward / back / end / end back (W B E: WORDs)"),
    ("0 ^ $ g_", "line start, first char, end, last char"),
    ("gg G 42G", "first line, last line, line 42 (also :42)"),
    ("{ } ( )", "paragraph / sentence back and forward"),
    ("f t F T ; ,", "find a char on the line, repeat"),
    ("%", "matching bracket (50% = middle of the file)"),
    ("H M L", "top, middle, bottom of the window"),
    ("/ ? n N * #", "search, next, previous, word under the cursor"),
    ("Ctrl-d Ctrl-u", "half page down / up (Ctrl-f Ctrl-b full page)"),
    ("Ctrl-e Ctrl-y", "scroll a line"),
    ("zz zt zb", "cursor line to the middle / top / bottom"),
    ("Ctrl-o Ctrl-i", "jump back / forward"),
    ("m{a-z} '{a-z}", "set a mark, go to it ('' last jump, '. last edit)"),
    ("i a I A o O", "insert before/after, at line start/end, new line below/above"),
    ("gi gI", "insert where you last stopped / at column 0"),
    ("x X s S r R", "delete char, before, substitute, line, replace char, replace mode"),
    ("d c y", "delete, change, yank + motion or text object (dd cc yy for lines)"),
    ("D C Y", "to the end of the line (Y yanks the line)"),
    ("> < gc", "indent, dedent, comment toggle + motion (>> << gcc)"),
    ("gu gU g~ ~", "lower, upper, toggle case + motion; ~ one char"),
    ("iw aw iW", "text objects: word (with the space)"),
    ("i( a( ib i{ iB i[ i<", "inside / around brackets"),
    ("i\" i' i`", "inside / around quotes"),
    ("ip ap it ia il ie", "paragraph, tag, argument, line, entire file"),
    ("p P gp gP", "paste after / before (gp leaves the cursor after)"),
    ("u Ctrl-r", "undo, redo"),
    (".", "repeat the last change (with a new count: 3.)"),
    ("J gJ", "join lines (gJ without spaces)"),
    ("Ctrl-a Ctrl-x", "add to / subtract from the number under the cursor"),
    ("v V Ctrl-v", "visual char / line / block; o swaps ends; gv reselects"),
    ("visual I A", "block insert on every line"),
    ("q{a-z} @{a-z} @@ Q", "record a macro, play it, play again, replay the last recorded"),
    ("\"{a-z}", "use a register (\"+ the clipboard, \"_ discard)"),
    ("ZZ ZQ", "save and quit, quit without saving"),
    (":", "command line (Tab completes, Up/Down history)"),
];

fn keys_section(ed: &Editor) -> String {
    let mut out = String::new();
    let leader = crate::keys::notation(&ed.keymap.leader);
    out.push_str(&format!("Leader: `{leader}`. Every binding can be changed in `[keys.normal]` / `[keys.insert]` / `[keys.visual]` of ule.toml.\n\n"));
    for mode in ["normal", "insert", "visual"] {
        out.push_str(&format!("## {mode} mode\n\n"));
        for (binding_mode, keys, description) in ed.keymap.all() {
            if binding_mode == mode {
                out.push_str(&format!("- `{keys}` {description}\n"));
            }
        }
        out.push('\n');
    }
    out
}

fn text(ed: &Editor, topic: &str) -> String {
    match topic {
        "keys" => format!("# Key bindings\n\n{}", keys_section(ed)),
        "standard" => {
            let mut out = String::from(
                "# Keys of ordinary editors\n\nOn by default (`standard_keys = true`); they work next to vim keys. `standard_keys = false` in `[editor]` of ule.toml gives pure vim back. Your own `[keys.*]` bindings always win.\n\nIn Ghostty, Cmd-Left/Right send Ctrl-A/Ctrl-E (line start/end) and Cmd-Backspace sends Ctrl-U; Option+arrows move by word.\n\n",
            );
            for (keys, description) in crate::standard::KEYS {
                out.push_str(&format!("- `{keys}` {description}\n"));
            }
            out
        }
        "vim" => {
            let mut out = String::from("# Vim keys\n\nCounts work everywhere (`3dd`, `d2w`, `5j`). Registers prefix any command (`\"ayy`, `\"ap`).\n\n");
            for (keys, description) in VIM_KEYS {
                out.push_str(&format!("- `{keys}` {description}\n"));
            }
            out
        }
        "commands" => {
            let mut out = String::from("# Commands\n\nEx commands take ranges: `:%s/a/b/g`, `:'<,'>sort`, `:10,20d`, `:.,+3normal A;`.\n\n");
            for (name, description) in crate::ex::EX {
                out.push_str(&format!("- `:{name}` {description}\n"));
            }
            out.push_str("\nNamed commands (also `:name`, bindable in ule.toml, listed by `<space>:`):\n\n");
            for (name, description) in crate::commands::COMMANDS {
                out.push_str(&format!("- `{name}` {description}\n"));
            }
            out
        }
        "options" => {
            let mut out = String::from(
                "# Options\n\nSet them in `[editor]` of ule.toml (`<space>fc` opens it) or for this session with `:set name=value`, `:set name`, `:set noname`, `:set name!`.\n\n",
            );
            for (name, description) in crate::config::OPTIONS {
                let value = ed.options.get(name).unwrap_or_default();
                out.push_str(&format!("- `{name}` = `{value}`: {description}\n"));
            }
            out
        }
        "languages" => {
            let mut out = String::from(
                "# Languages\n\nEach language can set `run`, `lsp`, `formatter`, `indent`, `tab_width`, `wrap`, comments and highlighting in `[languages.<name>]` of ule.toml; new languages work the same way. `ule --health` shows which tools are installed.\n\n| language | extensions | language server | formatter | run |\n|---|---|---|---|---|\n",
            );
            for lang in &ed.languages.list {
                let lsp = lang.lsp.iter().map(|command| command[0].clone()).collect::<Vec<_>>().join(", ");
                let formatter = lang.formatter.first().cloned().unwrap_or_default();
                let run = lang.run.clone().unwrap_or_default();
                out.push_str(&format!("| {} | {} | {} | {} | {} |\n", lang.name, lang.extensions.join(" "), lsp, formatter, run));
            }
            out
        }
        "themes" => {
            let mut names = ed.themes.names();
            names.sort();
            format!(
                "# Themes\n\nBuilt in: {}. `unlaw` uses your terminal's colors.\n\nPick one with `<space>tt` (previews while you move) and keep it with `theme = \"name\"` in ule.toml.\n\nYour own theme:\n\n```toml\n[themes.mine]\ninherits = \"onedark\"\npalette = {{ accent = \"#ff79c6\" }}\n\"syntax.keyword\" = {{ fg = \"accent\", modifiers = [\"bold\"] }}\n\"ui.selection\" = {{ bg = \"#44475a\" }}\n```\n\nKeys: `ui.*` (text, cursorline, selection, linenr, statusline, mode.normal/insert/visual, popup, search, bracket, indent_guide, ruler, bufferline, separator, virtual), `diag.*` (error, warning, info, hint), `syntax.*` (comment, keyword, type, function, macro, string, escape, number, constant, operator, punctuation, attribute, property, label, tag, heading, bold, italic, link, code, list, quote).\n",
                names.join(", ")
            )
        }
        "ul" => "# Unlaw integration\n\n- `<space>uu` or `:ul` picks a ul command; arguments are asked for, the output goes to the panel (`<space>o`).\n- `:ul todo add milk` runs directly; `:ul! game` hands the terminal over for interactive commands.\n- `%` in `:ul`, `:run`, `:!` is the current file: `:ul tg send %`.\n- `<space>gc` commits and pushes with `ul git \"message\"`.\n- `<space>ut` TODO board, `<space>ud` doctor, `<space>uc` Unlaw's config.toml (checked with `ul config check` when saved), `<space>ua` the agent, `<space>ul` local model chat.\n- `ul edit <file>` and `ul config edit` open ule.\n".to_string(),
        "ai" => "# Local AI (ul lm)\n\nNothing leaves the Mac: ule runs `ul lm` with the default local model.\n\n- `<space>aa` asks a question (in visual mode the selection is included); the answer streams into the panel.\n- `<space>af` asks about the whole file.\n- `<space>ax` explains the selection or file.\n- Visual + `<space>ae` rewrites the selection: describe the change, the answer replaces the selection as one undo step (`u` restores it).\n- `:ask question`, `:'<,'>ai make it shorter` do the same from the command line.\n".to_string(),
        _ => {
            let leader = crate::keys::notation(&ed.keymap.leader);
            format!(
                "# ule\n\nUnlaw's editor: vim keys, a `{leader}` menu for everything else, language servers, fuzzy pickers and ul built in.\n\n## First five minutes\n\n- `i` types, `Esc` stops typing, `:w` saves (`Ctrl-s` too), `:q` quits.\n- `{leader}` opens a menu that shows what comes next. `{leader}{leader}` finds a file, `{leader}/` searches the project, `{leader}e` is the file explorer.\n- `gd` goes to a definition, `K` shows documentation, `gr` references, `{leader}ca` fixes, `{leader}cr` renames.\n- `{leader}r` runs the file, `{leader}o` shows the output panel.\n- `{leader}?` searches every key binding; `{leader}:` every command.\n- Ordinary editor keys work too: Ctrl-Z/Y, Ctrl-C/X/V, Shift+arrows to select, Ctrl+Backspace (`:help standard`).\n- Settings: `{leader}fc` opens ule.toml (every option is in it, commented).\n\n## Topics\n\n{}\n\nOpen one with `:help <topic>` or `gf` on a name below.\n",
                TOPICS.iter().map(|(topic, description)| format!("- `:help {topic}` {description}")).collect::<Vec<_>>().join("\n")
            )
        }
    }
}

pub fn open(ed: &mut Editor, topic: Option<&str>) {
    let topic = topic.unwrap_or("start");
    let topic = TOPICS.iter().find(|(name, _)| name.starts_with(topic)).map_or("start", |(name, _)| name);
    let name = format!("[help {topic}]");
    let id = match ed.docs.values().find(|doc| doc.kind == DocKind::Help && doc.name == name) {
        Some(doc) => doc.id,
        None => ed.scratch(&name, DocKind::Help),
    };
    let content = text(ed, topic);
    let markdown = ed.languages.by_name("markdown");
    let doc = ed.docs.get_mut(&id).expect("help document");
    doc.set_content(&content);
    doc.set_language(markdown);
    doc.readonly = true;
    if !ed.buffers.contains(&id) {
        ed.buffers.push(id);
    }
    ed.show_doc(id);
}
