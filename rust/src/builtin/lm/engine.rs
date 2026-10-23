//! Engines: private venvs with pinned MLX libraries plus the worker script,
//! created on first use and rebuilt when their pins change. Libraries whose
//! dependencies clash live in separate engines: the core (chat, vision,
//! embeddings, speech, music, video), mflux for images, and PrismML's mflux
//! fork for Bonsai Image. Nothing is installed into the user's Python.
//! `UNLAW_LM_PYTHON` + `UNLAW_LM_WORKER` replace all of them (tests use a fake
//! worker this way).

use std::env;
use std::fs::{self, File};
use std::io;
use std::os::unix::io::AsRawFd;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use sha2::{Digest, Sha256};

use super::worker::Launch;
use crate::config::Config;
use crate::util::{atomic_write, which};

pub const WORKER_PY: &str = include_str!("worker.py");
const PYTHON_VERSION: &str = "3.13";
const STAMP: &str = ".unlaw-engine";

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Engine {
    Core,
    Image,
    Bonsai,
}

impl Engine {
    pub const ALL: [Engine; 3] = [Engine::Core, Engine::Image, Engine::Bonsai];

    pub fn name(self) -> &'static str {
        match self {
            Engine::Core => "core",
            Engine::Image => "image",
            Engine::Bonsai => "bonsai-image",
        }
    }

    fn folder(self) -> &'static str {
        match self {
            Engine::Core => "venv",
            Engine::Image => "image-venv",
            Engine::Bonsai => "bonsai-venv",
        }
    }

    pub fn requirements(self) -> &'static str {
        match self {
            Engine::Core => include_str!("requirements.txt"),
            Engine::Image => include_str!("requirements-image.txt"),
            Engine::Bonsai => include_str!("requirements-bonsai.txt"),
        }
    }

    /// Installed without dependencies; see requirements.txt.
    fn no_deps(self) -> &'static [&'static str] {
        match self {
            Engine::Core => &["mlx-whisper==0.4.3"],
            Engine::Image | Engine::Bonsai => &[],
        }
    }

    pub fn size_hint(self) -> &'static str {
        match self {
            Engine::Core => "about 1.2 GB",
            Engine::Image | Engine::Bonsai => "about 1.5 GB",
        }
    }
}

pub fn engine_dir(storage: &Path) -> PathBuf {
    storage.join("runtime").join("lm-engine")
}

fn venv(storage: &Path, engine: Engine) -> PathBuf {
    engine_dir(storage).join(engine.folder())
}

fn stamp(engine: Engine) -> String {
    let mut digest = Sha256::new();
    digest.update(engine.requirements().as_bytes());
    for package in engine.no_deps() {
        digest.update(package.as_bytes());
    }
    digest.update(PYTHON_VERSION.as_bytes());
    digest.finalize().iter().map(|byte| format!("{byte:02x}")).collect()
}

fn log_path(storage: &Path, engine: Engine) -> PathBuf {
    match engine {
        Engine::Core => engine_dir(storage).join("worker.log"),
        other => engine_dir(storage).join(format!("worker-{}.log", other.name())),
    }
}

fn override_launch(storage: &Path, engine: Engine) -> Option<Launch> {
    let python = env::var_os("UNLAW_LM_PYTHON").filter(|value| !value.is_empty())?;
    let script = env::var_os("UNLAW_LM_WORKER").filter(|value| !value.is_empty())?;
    Some(Launch { python: python.into(), script: script.into(), log: log_path(storage, engine) })
}

/// Ready means the venv was completed with the current pins.
pub fn is_ready(storage: &Path, engine: Engine) -> bool {
    if override_launch(storage, engine).is_some() {
        return true;
    }
    let venv = venv(storage, engine);
    venv.join("bin").join("python").exists() && fs::read_to_string(venv.join(STAMP)).is_ok_and(|text| text.trim() == stamp(engine))
}

/// An exclusive lock so two `ul lm` processes never build a venv at once.
struct Lock {
    _file: File,
}

impl Lock {
    fn take(path: &Path) -> io::Result<Lock> {
        let file = File::create(path)?;
        // SAFETY: flock on a descriptor we own; released when the file closes.
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX) } != 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(Lock { _file: file })
    }
}

fn run(command: &mut Command, what: &str) -> Result<(), String> {
    let status = command.stdin(Stdio::null()).status().map_err(|error| format!("{what}: {error}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("{what} failed ({status})"))
    }
}

/// Python that can host MLX without uv: 3.11+ (mlx-lm's minimum).
fn usable_python(config: &Config) -> Option<PathBuf> {
    let python = crate::commands::python(Some(config))?;
    let output = Command::new(&python).args(["-c", "import sys; print(sys.version_info >= (3, 11))"]).output().ok()?;
    (String::from_utf8_lossy(&output.stdout).trim() == "True").then_some(python)
}

fn build(storage: &Path, config: &Config, engine: Engine) -> Result<(), String> {
    let venv = venv(storage, engine);
    let requirements = engine_dir(storage).join(format!("requirements-{}.txt", engine.name()));
    atomic_write(&requirements, engine.requirements(), ".req.").map_err(|error| error.to_string())?;
    if venv.exists() {
        fs::remove_dir_all(&venv).map_err(|error| format!("Cannot replace {}: {error}", venv.display()))?;
    }
    eprintln!("Setting up the {} engine (one time, {}) in {}", engine.name(), engine.size_hint(), venv.display());
    let python = venv.join("bin").join("python");
    if let Some(uv) = which("uv") {
        // uv's own Python build: system ones may be old patch releases.
        run(
            Command::new(&uv).args(["venv", "--quiet", "--managed-python", "--python", PYTHON_VERSION]).arg(&venv),
            "Creating the engine venv with uv",
        )?;
        run(Command::new(&uv).args(["pip", "install", "--python"]).arg(&python).arg("-r").arg(&requirements), "Installing the engine")?;
        for package in engine.no_deps() {
            run(Command::new(&uv).args(["pip", "install", "--no-deps", "--python"]).arg(&python).arg(package), "Installing the engine")?;
        }
    } else {
        let base = usable_python(config).ok_or("The engine needs uv (brew install uv) or Python 3.11+ (set core.python)")?;
        run(Command::new(&base).args(["-m", "venv"]).arg(&venv), "Creating the engine venv")?;
        let pip = |args: &[&str]| {
            run(
                Command::new(&python).args(["-m", "pip", "install", "--quiet", "--disable-pip-version-check"]).args(args),
                "Installing the engine",
            )
        };
        pip(&["-r", &requirements.to_string_lossy()])?;
        for package in engine.no_deps() {
            pip(&["--no-deps", package])?;
        }
    }
    fs::write(venv.join(STAMP), stamp(engine)).map_err(|error| error.to_string())?;
    eprintln!("The {} engine is ready.", engine.name());
    Ok(())
}

/// Return how to start the worker, building or repairing the engine first.
pub fn ensure(storage: &Path, config: &Config, engine: Engine) -> Result<Launch, String> {
    if let Some(launch) = override_launch(storage, engine) {
        return Ok(launch);
    }
    if !cfg!(target_arch = "aarch64") || !cfg!(target_os = "macos") {
        return Err("MLX runs only on Apple Silicon Macs".into());
    }
    let directory = engine_dir(storage);
    fs::create_dir_all(&directory).map_err(|error| format!("Cannot create {}: {error}", directory.display()))?;
    let _lock = Lock::take(&directory.join(".lock")).map_err(|error| format!("Cannot lock the engine: {error}"))?;
    if !is_ready(storage, engine) {
        build(storage, config, engine)?;
    }
    let script = directory.join("worker.py");
    if fs::read_to_string(&script).ok().as_deref() != Some(WORKER_PY) {
        atomic_write(&script, WORKER_PY, ".worker.").map_err(|error| error.to_string())?;
    }
    Ok(Launch { python: venv(storage, engine).join("bin").join("python"), script, log: log_path(storage, engine) })
}

/// Delete a venv so the next use rebuilds it (`ul lm doctor --repair`).
pub fn reset(storage: &Path, engine: Engine) -> io::Result<()> {
    let venv = venv(storage, engine);
    if venv.exists() {
        fs::remove_dir_all(venv)?;
    }
    Ok(())
}

/// Run a hub helper (`worker.py hub <action> <json>`): progress goes straight
/// to the terminal, the JSON result line is returned.
pub fn hub(launch: &Launch, action: &str, args: &serde_json::Value) -> Result<serde_json::Value, i32> {
    let output = Command::new(&launch.python)
        .arg("-u")
        .arg(&launch.script)
        .arg("hub")
        .arg(action)
        .arg(args.to_string())
        .env("TOKENIZERS_PARALLELISM", "false")
        .stdin(Stdio::inherit())
        .stderr(Stdio::inherit())
        .output()
        .map_err(|error| {
            eprintln!("unlaw lm: cannot run the engine: {error}");
            1
        })?;
    if !output.status.success() {
        return Err(output.status.code().unwrap_or(1));
    }
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .rev()
        .find_map(|line| serde_json::from_str::<serde_json::Value>(line).ok()?.get("result").cloned())
        .ok_or_else(|| {
            eprintln!("unlaw lm: the engine returned no result");
            1
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embedded_worker_and_pins_are_consistent() {
        assert!(WORKER_PY.contains("def serve()"));
        for engine in Engine::ALL {
            let pins = engine.requirements().lines().filter(|l| !l.starts_with('#') && !l.trim().is_empty());
            for line in pins {
                assert!(line.contains("==") || line.contains("git+https://") && line.contains('@'), "{line} is not pinned");
            }
            assert_eq!(stamp(engine).len(), 64);
        }
        assert_ne!(stamp(Engine::Core), stamp(Engine::Image));
    }

    #[test]
    fn readiness_needs_the_current_stamp() {
        let storage = super::super::store::tests::scratch("engine");
        for engine in Engine::ALL {
            assert!(!is_ready(&storage, engine));
            let venv = venv(&storage, engine);
            fs::create_dir_all(venv.join("bin")).unwrap();
            fs::write(venv.join("bin").join("python"), "").unwrap();
            fs::write(venv.join(STAMP), "old").unwrap();
            assert!(!is_ready(&storage, engine));
            fs::write(venv.join(STAMP), stamp(engine)).unwrap();
            assert!(is_ready(&storage, engine));
            reset(&storage, engine).unwrap();
            assert!(!is_ready(&storage, engine));
        }
        assert_ne!(log_path(&storage, Engine::Core), log_path(&storage, Engine::Image));
        fs::remove_dir_all(storage).unwrap();
    }
}
