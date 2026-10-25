//! Key bindings: the defaults (leader menus, LSP, windows, ul) merged with `[keys.*]` from ule.toml.
//!
//! Vim's own grammar (operators, motions, text objects) lives in vim.rs;
//! bindings here are checked first, so a user can rebind anything.

use crate::config::{parse_action, Action, Config};
use crate::keys::{self, notation, Key};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum KeyMode {
    Normal,
    Insert,
    Visual,
}

#[derive(Clone, Debug)]
pub struct Binding {
    pub keys: Vec<Key>,
    pub actions: Vec<Action>,
    pub description: String,
}

pub enum Lookup<'a> {
    None,
    Prefix,
    Exact(&'a Binding),
    ExactAndPrefix(&'a Binding),
}

#[derive(Debug, Default)]
pub struct Keymap {
    pub normal: Vec<Binding>,
    pub insert: Vec<Binding>,
    pub visual: Vec<Binding>,
    pub leader: Vec<Key>,
    pub groups: Vec<(Vec<Key>, String)>,
    pub errors: Vec<String>,
}

/// (mode, keys, action, description). Modes: n normal, i insert, v visual, nv both.
const DEFAULTS: &[(&str, &str, &str, &str)] = &[
    ("ni", "<C-s>", "save", "save the file"),
    ("n", "<leader>w", "save", "save"),
    ("n", "<leader>q", "quit", "close window (quit when last)"),
    ("n", "<leader>Q", "quit_all", "quit ule"),
    ("nv", "<leader><space>", "file_picker", "find file"),
    ("n", "<C-p>", "file_picker", "find file"),
    ("n", "<leader>/", "grep", "search in project"),
    ("v", "<leader>/", "grep_selection", "search selection in project"),
    ("n", "<leader>,", "buffer_picker", "open buffers"),
    ("n", "<leader>.", "recent_files", "recent files"),
    ("n", "<leader>'", "last_picker", "reopen the last picker"),
    ("n", "<leader>e", "explorer", "file explorer"),
    ("n", "<leader>E", "explorer_reveal", "show this file in the explorer"),
    ("n", "<leader>o", "panel", "output panel"),
    ("nv", "<leader>:", "command_palette", "all commands"),
    ("n", "<leader>?", "keymap_picker", "search key bindings"),
    ("n", "<leader>-", "split", "split below"),
    ("n", "<leader>|", "vsplit", "split right"),
    ("n", "<leader>r", "run", "run this file"),
    ("n", "<leader>R", "run_again", "run the last command again"),
    ("n", "<F5>", "run", "run this file"),
    // find
    ("n", "<leader>ff", "file_picker", "files"),
    ("n", "<leader>fr", "recent_files", "recent files"),
    ("n", "<leader>fb", "buffer_picker", "buffers"),
    ("n", "<leader>fg", "grep", "grep the project"),
    ("n", "<leader>fw", "grep_word", "grep the word under the cursor"),
    ("n", "<leader>fs", "symbols", "symbols in this file (LSP)"),
    ("n", "<leader>fS", "workspace_symbols", "symbols in the project (LSP)"),
    ("n", "<leader>fd", "diagnostics", "diagnostics"),
    ("n", "<leader>fc", "open_config", "ule settings (ule.toml)"),
    ("n", "<leader>ft", "theme_picker", "themes"),
    ("n", "<leader>fk", "keymap_picker", "key bindings"),
    ("n", "<leader>fh", "help", "help"),
    ("n", "<leader>fl", "language_picker", "set the language"),
    ("n", "<leader>fu", "ul_picker", "ul commands"),
    ("n", "<leader>fn", "new_file", "new file"),
    ("n", "<leader>fo", "reveal_in_finder", "show in Finder"),
    // code
    ("nv", "<leader>ca", "code_action", "code actions"),
    ("n", "<leader>cr", "rename", "rename symbol"),
    ("n", "<F2>", "rename", "rename symbol"),
    ("nv", "<leader>cf", "format", "format file"),
    ("n", "<leader>cd", "line_diagnostics", "diagnostics on this line"),
    ("n", "<leader>cD", "diagnostics", "all diagnostics"),
    ("n", "<leader>ch", "hover", "documentation"),
    ("n", "<leader>cs", "symbols", "symbols"),
    ("n", "<leader>cl", "lsp_info", "language server info"),
    ("n", "<leader>cR", "lsp_restart", "restart language server"),
    ("n", "gd", "goto_definition", "go to definition"),
    ("n", "gD", "goto_declaration", "go to declaration"),
    ("n", "gy", "goto_type_definition", "go to type definition"),
    ("n", "gI", "goto_implementation", "go to implementation"),
    ("n", "gr", "references", "references"),
    ("n", "K", "hover", "documentation"),
    ("n", "gl", "line_diagnostics", "diagnostics on this line"),
    ("n", "gf", "goto_file", "open the file under the cursor"),
    ("n", "gx", "open_external", "open URL/file with macOS"),
    ("n", "]d", "diagnostic_next", "next diagnostic"),
    ("n", "[d", "diagnostic_prev", "previous diagnostic"),
    ("n", "]e", "error_next", "next error"),
    ("n", "[e", "error_prev", "previous error"),
    ("n", "]b", "buffer_next", "next buffer"),
    ("n", "[b", "buffer_prev", "previous buffer"),
    ("n", "]q", "location_next", "next location in the output"),
    ("n", "[q", "location_prev", "previous location in the output"),
    // git
    ("n", "<leader>gs", "git_status", "status"),
    ("n", "<leader>gd", "git_diff", "diff"),
    ("n", "<leader>gD", "git_diff_file", "diff of this file"),
    ("n", "<leader>gl", "git_log", "log"),
    ("n", "<leader>gb", "git_blame", "blame this line"),
    ("n", "<leader>gc", "git_commit", "commit and push (ul git)"),
    ("n", "<leader>gf", "git_files", "changed files"),
    // ul
    ("n", "<leader>uu", "ul_picker", "run a ul command"),
    ("n", "<leader>ut", "ul_todo", "TODO board"),
    ("n", "<leader>ud", "ul_doctor", "ul doctor"),
    ("n", "<leader>uc", "ul_config", "Unlaw config.toml"),
    ("n", "<leader>ug", "git_commit", "ul git: commit and push"),
    ("n", "<leader>ua", "ul_agent", "local agent (ula)"),
    ("n", "<leader>ul", "ul_lm", "local model chat"),
    // ai (local models through ul lm)
    ("nv", "<leader>aa", "ask", "ask the local model"),
    ("n", "<leader>af", "ask_file", "ask about this file"),
    ("v", "<leader>ae", "ai_edit", "rewrite the selection"),
    ("v", "<leader>ax", "ai_explain", "explain the selection"),
    ("n", "<leader>ax", "ai_explain", "explain this file"),
    // toggles
    ("n", "<leader>tw", "toggle wrap", "line wrap"),
    ("n", "<leader>tn", "line_numbers", "line numbers"),
    ("n", "<leader>ti", "toggle indent_guides", "indent guides"),
    ("n", "<leader>td", "toggle inline_diagnostics", "inline diagnostics"),
    ("n", "<leader>tl", "toggle show_whitespace", "whitespace"),
    ("n", "<leader>tc", "toggle cursorline", "cursor line"),
    ("n", "<leader>th", "toggle hlsearch", "search highlight"),
    ("n", "<leader>ta", "toggle auto_pairs", "auto pairs"),
    ("n", "<leader>tm", "toggle mouse", "mouse"),
    ("n", "<leader>tt", "theme_picker", "theme"),
    // buffers
    ("n", "<leader>bd", "buffer_close", "close buffer"),
    ("n", "<leader>bD", "buffer_close_force", "close buffer, discard changes"),
    ("n", "<leader>bo", "buffer_only", "close other buffers"),
    ("n", "<leader>bn", "buffer_next", "next buffer"),
    ("n", "<leader>bp", "buffer_prev", "previous buffer"),
    ("n", "<leader>bs", "scratch", "new scratch buffer"),
    ("n", "<leader>bb", "alternate_buffer", "previous file"),
    ("n", "<C-^>", "alternate_buffer", "previous file"),
    ("n", "<C-6>", "alternate_buffer", "previous file"),
    // windows
    ("n", "<C-w>v", "vsplit", "split right"),
    ("n", "<C-w>s", "split", "split below"),
    ("n", "<C-w>h", "focus_left", "window left"),
    ("n", "<C-w>j", "focus_down", "window below"),
    ("n", "<C-w>k", "focus_up", "window above"),
    ("n", "<C-w>l", "focus_right", "window right"),
    ("n", "<C-w>w", "focus_next", "next window"),
    ("n", "<C-w><C-w>", "focus_next", "next window"),
    ("n", "<C-w>q", "quit", "close window"),
    ("n", "<C-w>c", "close_window", "close window"),
    ("n", "<C-w>o", "only", "only this window"),
    ("n", "<C-h>", "focus_left", "window left"),
    ("n", "<C-j>", "focus_down", "window below"),
    ("n", "<C-k>", "focus_up", "window above"),
    ("n", "<C-l>", "focus_right", "window right"),
    // editing helpers
    ("n", "<esc>", "clear", "clear search highlight and popups"),
    ("ni", "<A-j>", "move_line_down", "move line down"),
    ("ni", "<A-k>", "move_line_up", "move line up"),
    ("v", "<A-j>", "move_selection_down", "move lines down"),
    ("v", "<A-k>", "move_selection_up", "move lines up"),
    ("n", "<C-_>", "comment_line", "toggle comment"),
    ("n", "<C-/>", "comment_line", "toggle comment"),
    ("i", "<C-space>", "complete", "completion"),
    ("n", "<C-z>", "suspend", "back to the shell (fg returns)"),
    ("n", "Q", "macro_replay", "replay the last recorded macro"),
];

const GROUPS: &[(&str, &str)] = &[
    ("<leader>f", "find"),
    ("<leader>c", "code"),
    ("<leader>g", "git"),
    ("<leader>u", "ul"),
    ("<leader>a", "ai (ul lm)"),
    ("<leader>t", "toggle"),
    ("<leader>b", "buffer"),
    ("<C-w>", "window"),
    ("g", "go to / more"),
    ("z", "view"),
    ("]", "next"),
    ("[", "previous"),
];

impl Keymap {
    pub fn build(config: &Config) -> Keymap {
        let commands = crate::commands::names();
        let mut keymap = Keymap::default();
        keymap.leader = keys::parse(&config.options.leader, &[]).unwrap_or_else(|error| {
            keymap.errors.push(format!("leader: {error}"));
            vec![Key::char(' ')]
        });
        let leader = keymap.leader.clone();
        for (modes, text, action, description) in DEFAULTS {
            let parsed = keys::parse(text, &leader).expect("default binding");
            let action = parse_action(action, &commands);
            for (flag, list) in [('n', &mut keymap.normal), ('i', &mut keymap.insert), ('v', &mut keymap.visual)] {
                if modes.contains(flag) {
                    list.push(Binding {
                        keys: parsed.clone(),
                        actions: vec![action.clone()],
                        description: description.to_string(),
                    });
                }
            }
        }
        for (prefix, name) in GROUPS {
            if let Ok(parsed) = keys::parse(prefix, &leader) {
                keymap.groups.push((parsed, name.to_string()));
            }
        }
        for (mode, text, actions, description) in &config.keys.bindings {
            let parsed = match keys::parse(text, &leader) {
                Ok(parsed) => parsed,
                Err(error) => {
                    keymap.errors.push(format!("keys.{mode}: {error}"));
                    continue;
                }
            };
            for action in actions {
                if let Action::Command(name, _) = action {
                    if !commands.contains(&name.as_str()) {
                        keymap.errors.push(format!("keys.{mode}.{text}: unknown command {name:?}"));
                    }
                }
            }
            let targets: Vec<&mut Vec<Binding>> = match mode.as_str() {
                "normal" => vec![&mut keymap.normal],
                "insert" => vec![&mut keymap.insert],
                "visual" => vec![&mut keymap.visual],
                _ => vec![&mut keymap.normal, &mut keymap.visual],
            };
            for list in targets {
                list.retain(|binding| binding.keys != parsed);
                if actions.iter().all(|action| *action == Action::Nop) {
                    continue;
                }
                list.push(Binding { keys: parsed.clone(), actions: actions.clone(), description: description.clone() });
            }
        }
        keymap
    }

    pub fn list(&self, mode: KeyMode) -> &[Binding] {
        match mode {
            KeyMode::Normal => &self.normal,
            KeyMode::Insert => &self.insert,
            KeyMode::Visual => &self.visual,
        }
    }

    pub fn lookup(&self, mode: KeyMode, keys: &[Key]) -> Lookup<'_> {
        let list = self.list(mode);
        let exact = list.iter().find(|binding| binding.keys == keys);
        let prefix = list.iter().any(|binding| binding.keys.len() > keys.len() && binding.keys.starts_with(keys));
        match (exact, prefix) {
            (Some(binding), true) => Lookup::ExactAndPrefix(binding),
            (Some(binding), false) => Lookup::Exact(binding),
            (None, true) => Lookup::Prefix,
            (None, false) => Lookup::None,
        }
    }

    /// What may follow `prefix`: (key, description, is a group).
    pub fn continuations(&self, mode: KeyMode, prefix: &[Key]) -> Vec<(String, String, bool)> {
        let mut out: Vec<(String, String, bool)> = Vec::new();
        for binding in self.list(mode) {
            if binding.keys.len() <= prefix.len() || !binding.keys.starts_with(prefix) {
                continue;
            }
            let next = binding.keys[prefix.len()];
            let label = next.notation();
            if out.iter().any(|(existing, _, _)| *existing == label) {
                continue;
            }
            if binding.keys.len() == prefix.len() + 1 {
                out.push((label, binding.description.clone(), false));
            } else {
                let mut group = prefix.to_vec();
                group.push(next);
                let name = self
                    .groups
                    .iter()
                    .find(|(keys, _)| *keys == group)
                    .map_or_else(|| "+more".to_string(), |(_, name)| format!("+{name}"));
                out.push((label, name, true));
            }
        }
        out.sort_by(|a, b| a.0.to_lowercase().cmp(&b.0.to_lowercase()).then(a.0.cmp(&b.0)));
        out
    }

    /// Every binding as (mode, keys, description) for help and the keymap picker.
    pub fn all(&self) -> Vec<(&'static str, String, String)> {
        let mut out = Vec::new();
        for (name, list) in [("normal", &self.normal), ("insert", &self.insert), ("visual", &self.visual)] {
            for binding in list {
                let keys = notation(&binding.keys).replace(&notation(&self.leader), "<leader>");
                out.push((name, keys, binding.description.clone()));
            }
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_parse_and_user_bindings_override() {
        let config = Config::parse(
            "[keys.normal]\n\"<leader>w\" = \":wq\"\n\"<leader>q\" = \"nop\"\n\"<leader>x\" = \"bogus_command arg\"\n",
            &crate::commands::names(),
        );
        let keymap = Keymap::build(&config);
        assert!(keymap.errors.is_empty(), "{:?}", keymap.errors);
        let leader_w = keys::parse("<leader>w", &keymap.leader).unwrap();
        match keymap.lookup(KeyMode::Normal, &leader_w) {
            Lookup::Exact(binding) => assert_eq!(binding.actions, vec![Action::Ex("wq".into())]),
            _ => panic!("expected the user's binding"),
        }
        let leader_q = keys::parse("<leader>q", &keymap.leader).unwrap();
        assert!(matches!(keymap.lookup(KeyMode::Normal, &leader_q), Lookup::None));
        // A word that is not a command is taken as keys.
        let leader_x = keys::parse("<leader>x", &keymap.leader).unwrap();
        assert!(matches!(keymap.lookup(KeyMode::Normal, &leader_x), Lookup::Exact(_)));
        assert!(matches!(keymap.lookup(KeyMode::Normal, &[Key::char(' ')]), Lookup::Prefix));
        let next = keymap.continuations(KeyMode::Normal, &[Key::char(' ')]);
        assert!(next.iter().any(|(key, name, group)| key == "f" && name == "+find" && *group));
    }

    #[test]
    fn every_default_command_exists() {
        let names = crate::commands::names();
        for (_, keys, action, _) in DEFAULTS {
            let name = action.split_whitespace().next().unwrap();
            assert!(names.contains(&name), "{keys}: unknown command {name}");
        }
    }
}
