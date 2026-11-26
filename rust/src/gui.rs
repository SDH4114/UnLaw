//! `ul gui`: Unlaw.app, the menu bar half of Unlaw (package `unlaw-app`,
//! binary `ul-app`). It builds the app bundle from the installed `ul-app`,
//! starts it at login through the LaunchAgent `com.unlaw.gui` and removes both.
//! Only a bundle carrying our marker is ever replaced or deleted.

use std::env;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use crate::config::{self, config_dir};
use crate::help::print_if_requested;
use crate::update;
use crate::util::{home, is_executable};

pub const LABEL: &str = "com.unlaw.gui";
pub const BINARY: &str = "ul-app";
pub const PACKAGE: &str = "unlaw-app";
/// The feature that brings Unlaw.app (`gui` itself is the system command).
pub const FEATURE: &str = "menubar";
const BUNDLE: &str = "Unlaw.app";
const MARKER: &str = ".unlaw-gui";
const LOGO: &str = include_str!("../../assets/logo.svg");
const USAGE: &str = "Usage: ul gui [status|install [--no-start]|start|stop|config|check|uninstall]";

/// `ul-app` next to this ul, else in the install root, else the one inside an
/// installed Unlaw.app (a downloaded app carries it, with no cargo build).
pub fn app_binary() -> Option<PathBuf> {
    let beside = env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|folder| folder.join(BINARY)));
    let bundled = installed_bundle().map(|bundle| bundle.join("Contents").join("MacOS").join(BINARY));
    beside
        .into_iter()
        .chain([update::install_root().join("bin").join(BINARY)])
        .chain(bundled)
        .find(|path| is_executable(path))
}

/// `ul features remove menubar`: the built ul-app goes too, so adding the
/// feature again builds the current one instead of reinstalling a stale binary.
/// Only the install root's copy: a ul-app next to a development build
/// (target/debug) is the build's own and stays.
pub fn remove_built_app() {
    let path = update::install_root().join("bin").join(BINARY);
    if path.is_file() {
        let _ = fs::remove_file(&path);
    }
}

/// Whether this user may create files in `folder`, asked without writing
/// anything (doctor and `ul gui status` must stay read-only).
fn writable(folder: &Path) -> bool {
    use std::os::unix::ffi::OsStrExt;
    let Ok(path) = std::ffi::CString::new(folder.as_os_str().as_bytes()) else { return false };
    // SAFETY: access(2) only reads the NUL-terminated path.
    unsafe { libc::access(path.as_ptr(), libc::W_OK) == 0 }
}

/// /Applications when it can be written, else ~/Applications; UNLAW_GUI_APPS in tests.
fn apps_dir() -> PathBuf {
    if let Some(folder) = env::var_os("UNLAW_GUI_APPS") {
        return PathBuf::from(folder);
    }
    let system = PathBuf::from("/Applications");
    if writable(&system) {
        system
    } else {
        home().join("Applications")
    }
}

/// Every Unlaw.app of ours: /Applications and ~/Applications can both hold one.
fn our_bundles() -> Vec<PathBuf> {
    let mut places = vec![apps_dir().join(BUNDLE)];
    if env::var_os("UNLAW_GUI_APPS").is_none() {
        places.extend([
            PathBuf::from("/Applications").join(BUNDLE),
            home().join("Applications").join(BUNDLE),
        ]);
    }
    let mut found: Vec<PathBuf> = Vec::new();
    for bundle in places {
        if ours(&bundle) && !found.contains(&bundle) {
            found.push(bundle);
        }
    }
    found
}

/// Where an installed Unlaw.app is: ours in /Applications or ~/Applications.
pub fn installed_bundle() -> Option<PathBuf> {
    our_bundles().into_iter().next()
}

fn ours(bundle: &Path) -> bool {
    bundle
        .join("Contents")
        .join("Resources")
        .join(MARKER)
        .is_file()
}

pub fn plist_path() -> PathBuf {
    home()
        .join("Library")
        .join("LaunchAgents")
        .join(format!("{LABEL}.plist"))
}

fn xml(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

fn info_plist() -> String {
    let version = xml(crate::VERSION);
    format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleName</key><string>Unlaw</string>
	<key>CFBundleDisplayName</key><string>Unlaw</string>
	<key>CFBundleIdentifier</key><string>{LABEL}</string>
	<key>CFBundleExecutable</key><string>{BINARY}</string>
	<key>CFBundleIconFile</key><string>AppIcon</string>
	<key>CFBundlePackageType</key><string>APPL</string>
	<key>CFBundleShortVersionString</key><string>{version}</string>
	<key>CFBundleVersion</key><string>{version}</string>
	<key>LSMinimumSystemVersion</key><string>13.0</string>
	<key>LSUIElement</key><true/>
	<key>NSHighResolutionCapable</key><true/>
	<key>NSAppleEventsUsageDescription</key><string>Unlaw's commands control apps you ask them to (Terminal, Spotify, Telegram) and show notifications.</string>
	<key>NSMicrophoneUsageDescription</key><string>ul capture records your voice when you record the screen or audio.</string>
	<key>NSCameraUsageDescription</key><string>ul capture records your camera when you record the screen with it.</string>
	<key>NSRemindersUsageDescription</key><string>ul desk shows your Apple Reminders lists as a board.</string>
	<key>NSRemindersFullAccessUsageDescription</key><string>ul desk shows your Apple Reminders lists as a board and saves the changes you make there.</string>
	<key>NSCalendarsUsageDescription</key><string>Commands you run from Unlaw may read your calendars.</string>
	<key>NSCalendarsFullAccessUsageDescription</key><string>Commands you run from Unlaw may read your calendars.</string>
	<key>NSDesktopFolderUsageDescription</key><string>Commands you run from Unlaw read and save files you name on the Desktop.</string>
	<key>NSDocumentsFolderUsageDescription</key><string>Commands you run from Unlaw read and save files you name in Documents.</string>
	<key>NSDownloadsFolderUsageDescription</key><string>Commands you run from Unlaw save downloads (YouTube, Telegram) to Downloads.</string>
</dict>
</plist>
"#
    )
}

/// The job's environment: what ul needs to find Python, ffmpeg and the config
/// from the user's shell (launchd starts with a bare PATH).
fn job_environment() -> Vec<(String, String)> {
    let mut environment: Vec<(String, String)> =
        ["PATH", "HOME", "XDG_CONFIG_HOME", "UNLAW_PYTHON"]
            .iter()
            .filter_map(|key| {
                env::var(key)
                    .ok()
                    .filter(|value| !value.is_empty())
                    .map(|value| (key.to_string(), value))
            })
            .collect();
    if !environment.iter().any(|(key, _)| key == "PATH") {
        environment.push((
            "PATH".into(),
            "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin".into(),
        ));
    }
    let ul = update::install_root().join("bin").join("ul");
    let ul = if is_executable(&ul) {
        ul
    } else {
        env::current_exe().unwrap_or(ul)
    };
    environment.push(("UNLAW_BIN".into(), ul.to_string_lossy().into_owned()));
    environment
}

fn log_file() -> PathBuf {
    let storage = config::load()
        .map(|config| config.storage_root())
        .unwrap_or_else(|_| config_dir().join("data"));
    storage.join("runtime").join("gui.log")
}

fn job_plist(bundle: &Path) -> String {
    let program = bundle.join("Contents").join("MacOS").join(BINARY);
    let variables: String = job_environment()
        .iter()
        .map(|(key, value)| {
            format!(
                "\t\t<key>{}</key><string>{}</string>\n",
                xml(key),
                xml(value)
            )
        })
        .collect();
    let log = xml(&log_file().to_string_lossy());
    format!(
        r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key><string>{LABEL}</string>
	<key>ProgramArguments</key>
	<array>
		<string>{}</string>
	</array>
	<key>EnvironmentVariables</key>
	<dict>
{variables}	</dict>
	<key>RunAtLoad</key><true/>
	<key>KeepAlive</key>
	<dict>
		<key>SuccessfulExit</key><false/>
	</dict>
	<key>ThrottleInterval</key><integer>30</integer>
	<key>LimitLoadToSessionType</key><string>Aqua</string>
	<key>ProcessType</key><string>Interactive</string>
	<key>StandardOutPath</key><string>{log}</string>
	<key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"#,
        xml(&program.to_string_lossy())
    )
}

fn quiet(command: &mut Command) -> bool {
    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .is_ok_and(|status| status.success())
}

/// AppIcon.icns from the Unlaw logo: Quick Look renders the SVG, sips scales it,
/// iconutil packs it. Any missing tool only means the generic app icon.
fn make_icon(resources: &Path) -> bool {
    let work = env::temp_dir().join(format!("unlaw-icon-{}", std::process::id()));
    let _ = fs::remove_dir_all(&work);
    let made = (|| -> Option<()> {
        fs::create_dir_all(&work).ok()?;
        let svg = work.join("logo.svg");
        fs::write(&svg, LOGO).ok()?;
        quiet(
            Command::new("qlmanage")
                .args(["-t", "-s", "1024", "-o"])
                .arg(&work)
                .arg(&svg),
        )
        .then_some(())?;
        let png = work.join("logo.svg.png");
        png.is_file().then_some(())?;
        let set = work.join("AppIcon.iconset");
        fs::create_dir_all(&set).ok()?;
        for size in [16u32, 32, 128, 256, 512] {
            for (scale, suffix) in [(1, ""), (2, "@2x")] {
                let out = set.join(format!("icon_{size}x{size}{suffix}.png"));
                let pixels = (size * scale).to_string();
                quiet(
                    Command::new("sips")
                        .args(["-z", &pixels, &pixels])
                        .arg(&png)
                        .arg("--out")
                        .arg(&out),
                )
                .then_some(())?;
            }
        }
        quiet(
            Command::new("iconutil")
                .args(["-c", "icns"])
                .arg(&set)
                .arg("-o")
                .arg(resources.join("AppIcon.icns")),
        )
        .then_some(())
    })()
    .is_some();
    let _ = fs::remove_dir_all(&work);
    made
}

const SIGNING_NAME: &str = "Unlaw Local Signing";

/// A self-signed code signing identity of this Mac's own, in a keychain file of
/// Unlaw's (`<config>/signing/`, never the login keychain), made once. Why: macOS
/// ties Screen Recording, camera and microphone grants to an app's designated
/// requirement; an ad-hoc signature's requirement is its cdhash, which changes
/// with every build, so after each update macOS asked again although the switch
/// in System Settings still showed on. With this identity the requirement is
/// "identifier com.unlaw.gui and certificate leaf = <this certificate>", the
/// same for every build. None (ad-hoc then) when any tool is missing or fails.
fn signing_keychain() -> Option<PathBuf> {
    use std::os::unix::fs::{DirBuilderExt, OpenOptionsExt};
    let folder = config_dir().join("signing");
    let keychain = folder.join("unlaw-signing.keychain-db");
    let secret = folder.join("password");
    let has_identity = |password: &str| {
        quiet(Command::new("security").args(["unlock-keychain", "-p", password]).arg(&keychain))
            && Command::new("security")
                .args(["find-identity", "-p", "codesigning"])
                .arg(&keychain)
                .stdin(Stdio::null())
                .stderr(Stdio::null())
                .output()
                .is_ok_and(|output| String::from_utf8_lossy(&output.stdout).contains(SIGNING_NAME))
    };
    if let Ok(password) = fs::read_to_string(&secret) {
        if keychain.exists() && has_identity(password.trim()) {
            return Some(keychain);
        }
    }
    // Make it (again: a half-made one from an earlier failure is replaced).
    std::fs::DirBuilder::new().recursive(true).mode(0o700).create(&folder).ok()?;
    let _ = quiet(Command::new("security").arg("delete-keychain").arg(&keychain));
    let _ = fs::remove_file(&keychain);
    let mut bytes = [0u8; 16];
    io::Read::read_exact(&mut fs::File::open("/dev/urandom").ok()?, &mut bytes).ok()?;
    let password: String = bytes.iter().map(|byte| format!("{byte:02x}")).collect();
    let work = folder.join(format!(".make-{}", std::process::id()));
    let _ = fs::remove_dir_all(&work);
    std::fs::DirBuilder::new().mode(0o700).create(&work).ok()?;
    let made = (|| {
        fs::write(
            work.join("cert.cnf"),
            format!(
                "[req]\ndistinguished_name = dn\nx509_extensions = ext\nprompt = no\n[dn]\nCN = {SIGNING_NAME}\n\
                 [ext]\nbasicConstraints = critical,CA:false\nkeyUsage = critical,digitalSignature\n\
                 extendedKeyUsage = critical,codeSigning\n"
            ),
        )
        .ok()?;
        let openssl = |args: &[&str]| quiet(Command::new("/usr/bin/openssl").current_dir(&work).args(args));
        // 20 years; LibreSSL's legacy PKCS#12 algorithms are the ones `security import` reads.
        let ok = openssl(&["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "key.pem", "-out", "cert.pem",
            "-days", "7300", "-config", "cert.cnf"])
            && openssl(&["pkcs12", "-export", "-inkey", "key.pem", "-in", "cert.pem", "-out", "id.p12",
                "-passout", &format!("pass:{password}"), "-name", SIGNING_NAME,
                "-keypbe", "PBE-SHA1-3DES", "-certpbe", "PBE-SHA1-3DES", "-macalg", "sha1"])
            && quiet(Command::new("security").args(["create-keychain", "-p", &password]).arg(&keychain))
            // No auto-lock, so later builds sign without asking.
            && quiet(Command::new("security").arg("set-keychain-settings").arg(&keychain))
            && quiet(Command::new("security").args(["unlock-keychain", "-p", &password]).arg(&keychain))
            && quiet(Command::new("security").arg("import").arg(work.join("id.p12"))
                .args(["-P", &password, "-T", "/usr/bin/codesign", "-k"]).arg(&keychain));
        ok.then_some(())
    })();
    let _ = fs::remove_dir_all(&work);
    made?;
    let mut file = fs::OpenOptions::new().write(true).create(true).truncate(true).mode(0o600).open(&secret).ok()?;
    io::Write::write_all(&mut file, password.as_bytes()).ok()?;
    has_identity(&password).then_some(keychain)
}

fn build_bundle(binary: &Path, bundle: &Path) -> io::Result<()> {
    let parent = bundle.parent().unwrap_or(Path::new("/"));
    fs::create_dir_all(parent)?;
    let staging = parent.join(format!(".{BUNDLE}.new-{}", std::process::id()));
    let _ = fs::remove_dir_all(&staging);
    let result = (|| {
        let contents = staging.join("Contents");
        let (macos, resources) = (contents.join("MacOS"), contents.join("Resources"));
        fs::create_dir_all(&macos)?;
        fs::create_dir_all(&resources)?;
        fs::write(contents.join("Info.plist"), info_plist())?;
        fs::copy(binary, macos.join(BINARY))?;
        fs::write(
            resources.join(MARKER),
            "Made by `ul gui install`; `ul gui uninstall` deletes it.\n",
        )?;
        make_icon(&resources);
        // Apple Silicon runs only signed code and there is no Developer ID: a
        // local identity when one can be made, else an ad-hoc signature.
        let signed = signing_keychain().is_some_and(|keychain| {
            quiet(
                Command::new("codesign")
                    .args(["--force", "--sign", SIGNING_NAME, "--keychain"])
                    .arg(&keychain)
                    .arg(&staging),
            )
        });
        if !signed && !quiet(Command::new("codesign").args(["--force", "--sign", "-"]).arg(&staging)) {
            eprintln!("unlaw gui: codesign failed; macOS may refuse to start Unlaw.app (xcode-select --install adds codesign).");
        }
        // The old bundle moves aside first and is deleted only once the new one
        // is in place, so a failed rename never leaves no app at all.
        let old = parent.join(format!(".{BUNDLE}.old-{}", std::process::id()));
        let had_old = bundle.exists() || bundle.is_symlink();
        if had_old {
            let _ = fs::remove_dir_all(&old);
            fs::rename(bundle, &old)?;
        }
        match fs::rename(&staging, bundle) {
            Ok(()) => {
                if had_old {
                    let _ = fs::remove_dir_all(&old);
                }
                Ok(())
            }
            Err(error) => {
                if had_old {
                    let _ = fs::rename(&old, bundle);
                }
                Err(error)
            }
        }
    })();
    if result.is_err() {
        let _ = fs::remove_dir_all(&staging);
    }
    result
}

fn domain() -> String {
    // SAFETY: getuid has no failure mode.
    format!("gui/{}", unsafe { libc::getuid() })
}

fn launchctl(args: &[&str]) -> bool {
    quiet(Command::new("launchctl").args(args))
}

/// Ask every running copy of our bundle's app to quit (SIGTERM, which the app
/// turns into its normal Quit) and wait up to 6 s. launchctl bootout only stops
/// the copy the login job started; one opened from the Dock or Finder kept
/// running the old binary after `ul gui install`, holding the single-instance
/// lock so the new one exited at once.
fn quit_running(bundles: &[PathBuf]) {
    let executables: Vec<String> = bundles
        .iter()
        .map(|bundle| bundle.join("Contents").join("MacOS").join(BINARY).to_string_lossy().into_owned())
        .collect();
    let Ok(output) = std::process::Command::new("/bin/ps").args(["-axo", "pid=,comm="]).output() else { return };
    let me = std::process::id() as i32;
    let pids: Vec<i32> = String::from_utf8_lossy(&output.stdout)
        .lines()
        .filter_map(|line| {
            let (pid, command) = line.trim_start().split_once(' ')?;
            let pid = pid.parse::<i32>().ok()?;
            (pid != me && executables.iter().any(|path| path == command.trim())).then_some(pid)
        })
        .collect();
    for pid in &pids {
        // SAFETY: plain kill(2) on a pid ps just listed as our app.
        unsafe { libc::kill(*pid, libc::SIGTERM) };
    }
    for _ in 0..60 {
        // SAFETY: signal 0 only asks whether the process still exists.
        if pids.iter().all(|pid| unsafe { libc::kill(*pid, 0) } != 0) {
            return;
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
}

fn load_job(bundle: &Path) -> io::Result<()> {
    let plist = plist_path();
    if let Some(folder) = plist.parent() {
        fs::create_dir_all(folder)?;
    }
    if let Some(folder) = log_file().parent() {
        fs::create_dir_all(folder)?;
    }
    crate::util::atomic_write(&plist, &job_plist(bundle), ".gui.")?;
    launchctl(&["bootout", &format!("{}/{LABEL}", domain())]);
    quit_running(&[bundle.to_path_buf()]);
    // bootout returns before the running app has quit, and bootstrap fails
    // ("Input/output error") until it has. Quitting may take up to ~5 s (the
    // app stops the page servers it runs), so try again for 15 s.
    for attempt in 0..60 {
        if launchctl(&["bootstrap", &domain(), &plist.to_string_lossy()]) {
            return Ok(());
        }
        if attempt < 59 {
            std::thread::sleep(std::time::Duration::from_millis(250));
        }
    }
    Err(io::Error::other("launchctl bootstrap failed"))
}

/// Build Unlaw.app from the installed ul-app and start it (unless `start` is false).
pub fn install(start: bool) -> i32 {
    let Some(binary) = app_binary() else {
        eprintln!("unlaw gui: {BINARY} is not installed. Build it with: ul features add menubar (or ul update)");
        return 1;
    };
    // An existing bundle of ours is rebuilt where it is (/Applications may have
    // become read-only since), so there are never two.
    let bundle = installed_bundle().unwrap_or_else(|| apps_dir().join(BUNDLE));
    if (bundle.exists() || bundle.is_symlink()) && !ours(&bundle) {
        eprintln!(
            "unlaw gui: {} exists and was not made by Unlaw; nothing was changed.",
            bundle.display()
        );
        return 1;
    }
    if let Err(error) = build_bundle(&binary, &bundle) {
        eprintln!("unlaw gui: Could not write {}: {error}", bundle.display());
        return 1;
    }
    println!("Installed {}", bundle.display());
    if !start {
        return 0;
    }
    match load_job(&bundle) {
        Ok(()) => {
            println!(
                "Unlaw.app is running and starts at login ({LABEL}). Command palette: Ctrl+Space."
            );
            0
        }
        Err(error) => {
            eprintln!(
                "unlaw gui: Could not start it: {error}. Open {} by hand.",
                bundle.display()
            );
            1
        }
    }
}

/// Stop the app, delete its login job and the bundle we made; true when
/// anything was removed. Used by `ul remove` and `ul features remove gui`.
pub fn uninstall() -> io::Result<bool> {
    // Stop it first, so the app is not left running from a deleted bundle; then
    // every step is tried, and the first error is reported at the end.
    launchctl(&["bootout", &format!("{}/{LABEL}", domain())]);
    quit_running(&our_bundles());
    let mut removed = false;
    let mut first_error = None;
    let plist = plist_path();
    if plist.exists() || plist.is_symlink() {
        match fs::remove_file(&plist) {
            Ok(()) => removed = true,
            Err(error) => first_error = Some(error),
        }
    }
    for bundle in our_bundles() {
        match fs::remove_dir_all(&bundle) {
            Ok(()) => removed = true,
            Err(error) => {
                first_error.get_or_insert(error);
            }
        }
    }
    match first_error {
        Some(error) => Err(error),
        None => Ok(removed),
    }
}

/// What `ul gui status` and `ul doctor` say: (installed and running, detail).
pub fn status() -> (bool, String) {
    let Some(bundle) = installed_bundle() else {
        return (
            false,
            if app_binary().is_some() {
                "not installed: ul gui install".into()
            } else {
                "not built: ul features add menubar".into()
            },
        );
    };
    let output = Command::new("launchctl")
        .args(["print", &format!("{}/{LABEL}", domain())])
        .stdin(Stdio::null())
        .stderr(Stdio::null())
        .output();
    let text = output
        .ok()
        .filter(|output| output.status.success())
        .map(|output| String::from_utf8_lossy(&output.stdout).into_owned());
    let pid = text.as_deref().and_then(|text| {
        text.lines().find_map(|line| {
            line.trim()
                .strip_prefix("pid = ")
                .map(|pid| pid.trim().to_string())
        })
    });
    match (text.is_some(), pid) {
        (true, Some(pid)) => (true, format!("{} running (pid {pid})", bundle.display())),
        (true, None) => (
            false,
            format!("{} loaded but not running; ul gui start", bundle.display()),
        ),
        (false, _) => (
            false,
            format!("{} installed, not started: ul gui start", bundle.display()),
        ),
    }
}

fn run_app(args: &[&str]) -> i32 {
    let Some(binary) = app_binary() else {
        eprintln!("unlaw gui: {BINARY} is not installed. Build it with: ul features add menubar (or ul update)");
        return 1;
    };
    Command::new(binary)
        .args(args)
        .status()
        .map(crate::commands::exit_code)
        .unwrap_or(1)
}

fn settings_file() -> PathBuf {
    config_dir().join("app.toml")
}

pub fn run(args: &[String]) -> i32 {
    if print_if_requested("gui", args) {
        return 0;
    }
    let words: Vec<&str> = args.iter().map(String::as_str).collect();
    match words.as_slice() {
        [] | ["status"] => {
            let (running, detail) = status();
            println!("Unlaw.app: {detail}");
            println!("Settings: {}", settings_file().display());
            i32::from(!running)
        }
        ["install"] => install(true),
        ["install", "--no-start"] => install(false),
        ["start"] => match installed_bundle() {
            None => install(true),
            Some(bundle) => match load_job(&bundle) {
                Ok(()) => {
                    println!("Unlaw.app started.");
                    0
                }
                Err(error) => {
                    eprintln!("unlaw gui: {error}");
                    1
                }
            },
        },
        ["stop"] => {
            if installed_bundle().is_none() && !plist_path().exists() {
                println!("Unlaw.app is not installed.");
                return 0;
            }
            launchctl(&["bootout", &format!("{}/{LABEL}", domain())]);
            quit_running(&our_bundles());
            println!("Unlaw.app stopped; it starts again at login (ul gui uninstall removes it).");
            0
        }
        ["config"] => {
            let path = settings_file();
            if !path.exists() {
                let code = run_app(&["--write-settings"]);
                if code != 0 {
                    return code;
                }
            }
            crate::editor::open(&[path], config::load().ok().as_ref())
        }
        ["check"] => run_app(&["--check"]),
        ["uninstall"] => match uninstall() {
            Ok(true) => {
                println!("Removed Unlaw.app and its login job.");
                0
            }
            Ok(false) => {
                println!("Unlaw.app is not installed.");
                0
            }
            Err(error) => {
                eprintln!("unlaw gui: {error}");
                1
            }
        },
        _ => {
            eprintln!("{USAGE}");
            2
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plists_escape_text() {
        assert_eq!(xml("a<b>&\"c\""), "a&lt;b&gt;&amp;&quot;c&quot;");
        let plist = job_plist(Path::new("/Apps/Un & law.app"));
        assert!(plist.contains("<string>/Apps/Un &amp; law.app/Contents/MacOS/ul-app</string>"));
        assert!(plist.contains("<key>UNLAW_BIN</key>"));
        assert!(info_plist().contains("<key>LSUIElement</key><true/>"));
    }

    /// macOS kills a process whose responsible app (Unlaw.app for everything it
    /// starts) touches the microphone, camera or Reminders without these keys:
    /// `ul capture record` from the app died as "ul-rec did not start".
    #[test]
    fn the_bundle_explains_every_privacy_access_its_commands_use() {
        let plist = info_plist();
        for key in ["NSMicrophoneUsageDescription", "NSCameraUsageDescription", "NSRemindersFullAccessUsageDescription",
            "NSRemindersUsageDescription", "NSAppleEventsUsageDescription"]
        {
            assert!(plist.contains(&format!("<key>{key}</key><string>")), "{key}");
        }
    }
}
