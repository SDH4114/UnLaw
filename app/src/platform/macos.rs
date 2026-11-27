//! macOS: SF Symbols in the menu bar, notes shown without focus, terminals through osascript (text as
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
        // The weather's own states (`|weather` in a status icon).
        "sun" => "sun.max",
        "cloudsun" => "cloud.sun",
        "overcast" => "cloud",
        "rain" => "cloud.rain",
        "snow" => "cloud.snow",
        "fog" => "cloud.fog",
        "storm" => "cloud.bolt.rain",
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

/// Where an application named like `ul app` takes it is installed (`Safari`,
/// `Prism Launcher`): the usual folders, the first `<name>.app` found.
pub fn app_path(name: &str) -> Option<std::path::PathBuf> {
    let home = std::env::var_os("HOME").map(std::path::PathBuf::from).unwrap_or_default();
    let folders = [
        std::path::PathBuf::from("/Applications"),
        std::path::PathBuf::from("/Applications/Utilities"),
        std::path::PathBuf::from("/System/Applications"),
        std::path::PathBuf::from("/System/Applications/Utilities"),
        home.join("Applications"),
        std::path::PathBuf::from("/System/Library/CoreServices"),
    ];
    let file = format!("{name}.app");
    folders.iter().map(|folder| folder.join(&file)).find(|path| path.is_dir())
}

/// An application's own icon (the one Finder and the Dock show), drawn at `points`.
fn app_image(path: &Path, points: f64) -> Option<objc2::rc::Retained<NSImage>> {
    use objc2::AllocAnyThread;
    use objc2_app_kit::NSWorkspace;
    use objc2_foundation::{NSPoint, NSRect, NSSize};
    let icon = NSWorkspace::sharedWorkspace().iconForFile(&NSString::from_str(path.to_str()?));
    let size = NSSize::new(points, points);
    let canvas = NSImage::initWithSize(NSImage::alloc(), size);
    // Drawn once into a small image: the icon file holds sizes up to 1024 px.
    #[allow(deprecated)]
    {
        canvas.lockFocus();
        icon.drawInRect(NSRect::new(NSPoint::new(0.0, 0.0), size));
        canvas.unlockFocus();
    }
    Some(canvas)
}

/// The icon of an installed application as PNG bytes, for the app's pages.
pub fn app_icon_png(name: &str, points: f64) -> Option<Vec<u8>> {
    use objc2_app_kit::{NSBitmapImageFileType, NSBitmapImageRep};
    use objc2_foundation::NSDictionary;
    let image = app_image(&app_path(name)?, points)?;
    let tiff = image.TIFFRepresentation()?;
    let bitmap = NSBitmapImageRep::imageRepWithData(&tiff)?;
    // SAFETY: an empty properties dictionary is what the method takes for defaults.
    let png = unsafe { bitmap.representationUsingType_properties(NSBitmapImageFileType::PNG, &NSDictionary::new()) }?;
    Some(png.to_vec())
}

/// A menu bar item showing an application's icon in colour (a pinned `app:` item).
pub fn set_app_icon(tray: &TrayIcon, name: &str) -> bool {
    let Some(mtm) = MainThreadMarker::new() else { return false };
    let Some(item) = tray.ns_status_item() else { return false };
    let Some(button) = item.button(mtm) else { return false };
    let Some(image) = app_path(name).and_then(|path| app_image(&path, 18.0)) else { return false };
    button.setImage(Some(&image));
    button.setImagePosition(NSCellImagePosition::ImageLeft);
    // Same as set_symbol: setting the title again sizes tray-icon's click view.
    let title = button.title().to_string();
    tray.set_title(Some(title));
    true
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

/// Show a window above the others without making it the key window or activating
/// the app: a note must not take the keyboard from what the user is typing in.
pub fn show_without_focus(window: &tao::window::Window) {
    use objc2_app_kit::NSWindow;
    use tao::platform::macos::WindowExtMacOS;
    let pointer = window.ns_window() as *const NSWindow;
    if pointer.is_null() {
        return;
    }
    // SAFETY: tao's NSWindow, alive as long as `window`; called on the main thread.
    unsafe { (*pointer).orderFrontRegardless() };
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
