//! ule: Unlaw's modal code editor.
//!
//! Vim keys (vim.rs) and key bindings (keymap.rs) drive an Editor (editor.rs)
//! of documents (document.rs, text.rs) shown in views; ui.rs draws it into a
//! Surface that render.rs diffs onto the terminal; app.rs runs the loop.
//! Language servers (lsp.rs), jobs (jobs.rs), pickers (picker.rs) and ul
//! (ul.rs) report back through Editor::rx.

pub mod app;
pub mod clipboard;
pub mod commands;
pub mod complete;
pub mod config;
pub mod display;
pub mod document;
pub mod edit;
pub mod editor;
pub mod ex;
pub mod explorer;
pub mod format;
pub mod fuzzy;
pub mod help;
pub mod jobs;
pub mod keymap;
pub mod keys;
pub mod lsp;
pub mod motion;
pub mod picker;
pub mod render;
pub mod standard;
pub mod state;
pub mod syntax;
pub mod text;
pub mod theme;
pub mod ui;
pub mod ul;
pub mod vim;
pub mod widgets;

#[cfg(test)]
mod tests;
