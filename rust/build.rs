//! Embeds the Python-defined seeded commands, defaults and version.

use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

const PYTHONS: [&str; 5] = ["python3.14", "python3.13", "python3.12", "python3.11", "python3"];

fn python() -> String {
    if let Ok(explicit) = env::var("UNLAW_PYTHON") {
        return explicit;
    }
    let path = env::var_os("PATH").unwrap_or_default();
    for name in PYTHONS {
        if env::split_paths(&path).any(|dir| dir.join(name).is_file()) {
            return name.to_string();
        }
    }
    "python3".to_string()
}

fn main() {
    let root = PathBuf::from(env::var("CARGO_MANIFEST_DIR").unwrap());
    let out = PathBuf::from(env::var("OUT_DIR").unwrap());
    println!("cargo:rerun-if-changed=src/unlawful");
    println!("cargo:rerun-if-changed=rust/gen_assets.py");
    println!("cargo:rerun-if-env-changed=UNLAW_PYTHON");

    let interpreter = python();
    let status = Command::new(&interpreter)
        .arg("-I")
        .arg(root.join("rust/gen_assets.py"))
        .arg(root.join("src"))
        .arg(&out)
        .status()
        .unwrap_or_else(|error| panic!("Unlaw build needs Python 3.11+ ({interpreter}): {error}"));
    assert!(status.success(), "rust/gen_assets.py failed with {interpreter}; Python 3.11+ is required");

    let assets = std::fs::read_to_string(Path::new(&out).join("assets.rs")).unwrap();
    let version = env::var("CARGO_PKG_VERSION").unwrap();
    assert!(
        assets.contains(&format!("PY_VERSION: &str = \"{version}\"")),
        "Cargo.toml version {version} differs from src/unlawful/__init__.py"
    );
}
