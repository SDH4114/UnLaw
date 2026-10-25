//! The macOS clipboard through pbcopy/pbpaste (no-ops when they are missing or disabled).

use std::io::Write;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};

static DISABLED: AtomicBool = AtomicBool::new(false);

/// Tests and `ULE_NO_CLIPBOARD=1` keep the real clipboard untouched.
pub fn disable() {
    DISABLED.store(true, Ordering::Relaxed);
}

fn enabled() -> bool {
    !DISABLED.load(Ordering::Relaxed) && std::env::var_os("ULE_NO_CLIPBOARD").is_none()
}

pub fn set(text: &str) {
    if !enabled() {
        return;
    }
    let Ok(mut child) = Command::new("pbcopy").stdin(Stdio::piped()).stdout(Stdio::null()).stderr(Stdio::null()).spawn()
    else {
        return;
    };
    if let Some(mut stdin) = child.stdin.take() {
        let _ = stdin.write_all(text.as_bytes());
    }
    let _ = child.wait();
}

pub fn get() -> Option<String> {
    if !enabled() {
        return None;
    }
    let output = Command::new("pbpaste").stderr(Stdio::null()).output().ok()?;
    output.status.success().then(|| String::from_utf8_lossy(&output.stdout).into_owned())
}
