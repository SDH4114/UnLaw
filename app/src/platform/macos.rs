//! macOS: SF Symbols in the menu bar, notifications through osascript (text as
//! arguments, never inside the script), Terminal/Ghostty, `open`.

use std::path::Path;
use std::process::{Command, Stdio};

use objc2::MainThreadMarker;
use objc2_app_kit::{NSCellImagePosition, NSImage};
use objc2_foundation::NSString;
use tray_icon::TrayIcon;

/// App icon names (spec::ICONS) to SF Symbols.
fn symbol(icon: &str) -> &'static str {
    match icon {
        "cup" => "cup.and.saucer",
        // A full cup with steam: awake is keeping the Mac up.
        "cup-hot" => "cup.and.heat.waves.fill",
        "cpu" => "cpu",
        "board" => "rectangle.split.3x1",
        "clock" => "timer",
        "clipboard" => "doc.on.clipboard",
        "cloud" => "cloud.sun",
        "music" => "music.note",
        "play" => "play.rectangle",
        "camera" => "camera",
        "record" => "record.circle",
        "download" => "arrow.down.circle",
        "git" => "arrow.triangle.branch",
        "terminal" => "terminal",
        "folder" => "folder",
        "code" => "chevron.left.forwardslash.chevron.right",
        "chat" => "bubble.left",
        "spark" => "sparkles",
        "game" => "gamecontroller",
        "archive" => "archivebox",
        "globe" => "globe",
        "app" => "square.grid.2x2",
        "bolt" => "bolt",
        "gear" => "gearshape",
        _ => "command",
    }
}

/// Put an SF Symbol on a menu bar item (left of its title).
pub fn set_symbol(tray: &TrayIcon, icon: &str) {
    let Some(mtm) = MainThreadMarker::new() else { return };
    let Some(item) = tray.ns_status_item() else { return };
    let Some(button) = item.button(mtm) else { return };
    let name = NSString::from_str(symbol(icon));
    let label = NSString::from_str(icon);
    if let Some(image) = NSImage::imageWithSystemSymbolName_accessibilityDescription(&name, Some(&label)) {
        image.setTemplate(true);
        button.setImage(Some(&image));
        button.setImagePosition(NSCellImagePosition::ImageLeft);
        // tray-icon catches clicks in a view sized to the button when its title or
        // icon changes through tray-icon. An image set here widens the button but
        // not that view: an item with no title (the desk, an idle awake) had a
        // zero-wide click area and ignored every click. Setting the same title
        // again makes tray-icon size the view to the button.
        let title = button.title().to_string();
        tray.set_title(Some(title));
    }
}

/// In the Dock (a regular app with its window) or only in the menu bar. The
/// window's close button takes Unlaw out of the Dock; it keeps running above.
pub fn set_in_dock(visible: bool) {
    use objc2_app_kit::{NSApplication, NSApplicationActivationPolicy};
    let Some(mtm) = MainThreadMarker::new() else { return };
    let app = NSApplication::sharedApplication(mtm);
    let policy =
        if visible { NSApplicationActivationPolicy::Regular } else { NSApplicationActivationPolicy::Accessory };
    if app.activationPolicy() != policy {
        app.setActivationPolicy(policy);
    }
    if visible {
        #[allow(deprecated)]
        app.activateIgnoringOtherApps(true);
    }
}

const NOTIFY: &str = "on run argv
display notification (item 2 of argv) with title (item 1 of argv)
end run";

/// A notification; the texts are arguments of the script, never part of it.
pub fn notify(title: &str, text: &str) {
    let text = if text.trim().is_empty() { "Done." } else { text };
    detached(Command::new("/usr/bin/osascript").args(["-e", NOTIFY, "--", title, text]));
}

/// Start a helper without waiting for it; a thread reaps it, so a long-running
/// menu bar app collects no zombies.
fn detached(command: &mut Command) {
    let child = command.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null()).spawn();
    if let Ok(mut child) = child {
        std::thread::spawn(move || child.wait());
    }
}

const TERMINAL: &str = "on run argv
tell application \"Terminal\"
activate
do script (item 1 of argv)
end tell
end run";

fn ghostty() -> Option<&'static str> {
    ["/Applications/Ghostty.app", "/System/Volumes/Data/Applications/Ghostty.app"]
        .into_iter()
        .find(|path| Path::new(path).is_dir())
}

/// Run `ul <args>` in a new terminal window: Ghostty when installed (`-e`),
/// else Terminal.app. The command line stays open as a shell afterwards only in
/// Terminal; Ghostty closes the window when the command ends, so it is wrapped
/// to wait for Return.
pub fn open_terminal(ul: &Path, args: &[String]) -> Result<(), String> {
    // Terminal.app types the line into an interactive shell, whose line editor
    // acts on control characters even inside quotes.
    if args.iter().any(|arg| arg.chars().any(char::is_control)) {
        return Err("a value contains control characters".into());
    }
    let line: Vec<String> = std::iter::once(ul.to_string_lossy().into_owned())
        .chain(args.iter().cloned())
        .map(|w| super::shell_quote(&w))
        .collect();
    let line = line.join(" ");
    if let Some(app) = ghostty() {
        let wrapped = format!("{line}; printf '\\n[exit %s] Press Return to close.' $?; read _");
        let status = Command::new("/usr/bin/open")
            .args(["-na", app, "--args", "-e", "/bin/zsh", "-lc", &wrapped])
            .stdin(Stdio::null())
            .status();
        if status.is_ok_and(|status| status.success()) {
            return Ok(());
        }
    }
    let status = Command::new("/usr/bin/osascript")
        .args(["-e", TERMINAL, "--", &line])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .status()
        .map_err(|error| error.to_string())?;
    if status.success() {
        Ok(())
    } else {
        Err("Terminal did not open (System Settings > Privacy > Automation)".into())
    }
}

/// A web link in the default browser (http and https only).
pub fn open_link(url: &str) {
    if url.starts_with("https://") || url.starts_with("http://") {
        detached(Command::new("/usr/bin/open").arg(url));
    }
}

/// A text file in the default text editor.
pub fn open_text(path: &Path) {
    detached(Command::new("/usr/bin/open").arg("-t").arg(path));
}
