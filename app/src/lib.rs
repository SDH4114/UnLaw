//! Unlaw.app: the parts with no window code, tested on their own. The window
//! shell (`gui`, built only for the `ul-app` binary) uses them.

pub mod args;
pub mod edit;
pub mod files;
pub mod hotkey;
pub mod runner;
pub mod settings;
pub mod setup;
pub mod spec;
pub mod template;
pub mod term;
pub mod views;
