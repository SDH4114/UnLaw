//! Current-shell integration: the Zsh wrapper, `.venv` creation and saved
//! project launching.

use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::config::Config;
use crate::workspace::{self, Template};

pub const ZSH_BLOCK_START: &str = "# >>> Unlaw shell integration >>>";
pub const ZSH_BLOCK_END: &str = "# <<< Unlaw shell integration <<<";

#[derive(Debug)]
pub struct ShellError(pub String);

impl fmt::Display for ShellError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl From<workspace::TemplateError> for ShellError {
    fn from(error: workspace::TemplateError) -> Self {
        ShellError(error.0)
    }
}

pub type Result<T> = std::result::Result<T, ShellError>;

fn existing_directory(template: &Template) -> Result<&Path> {
    if template.path.is_dir() {
        Ok(&template.path)
    } else {
        Err(ShellError(format!("Saved project directory does not exist: {}", template.path.display())))
    }
}

pub fn template_path(name: &str) -> Result<PathBuf> {
    let template = workspace::load(name)?;
    existing_directory(&template).map(Path::to_path_buf)
}

fn open(args: &[&str]) -> Result<i32> {
    Command::new("open")
        .args(args)
        .status()
        .map(|status| status.code().unwrap_or(1))
        .map_err(|error| ShellError(error.to_string()))
}

pub fn launch(template: &Template, config: Option<&Config>) -> Result<i32> {
    let path = existing_directory(template)?.to_string_lossy().into_owned();
    let app = if template.app == "zed" {
        config.map(|config| config.string("apps.editor")).unwrap_or_else(|| "Zed".into())
    } else {
        "Obsidian".into()
    };
    let code = open(&["-a", &app, &path])?;
    if code != 0 || !template.ai {
        return Ok(code);
    }
    open(&["-a", "ChatGPT"])
}

pub fn ensure_venv(directory: &Path, python: &Path) -> Result<PathBuf> {
    let project = fs::canonicalize(directory).map_err(|error| ShellError(format!("{}: {error}", directory.display())))?;
    let root = project.join(".venv");
    let activation = root.join("bin").join("activate");
    if root.exists() {
        if !root.is_dir() || !activation.is_file() {
            return Err(ShellError(format!("Invalid virtual environment: {}", root.display())));
        }
        return Ok(activation);
    }
    let status = Command::new(python)
        .args(["-m", "venv"])
        .arg(&root)
        .status()
        .map_err(|error| ShellError(format!("Could not create {}: {}: {error}", root.display(), python.display())))?;
    if !status.success() {
        return Err(ShellError(format!(
            "Could not create {}: {} -m venv exited with status {}",
            root.display(),
            python.display(),
            status.code().unwrap_or(1)
        )));
    }
    if !activation.is_file() {
        return Err(ShellError(format!(
            "Virtual environment was created without an activation script: {}",
            activation.display()
        )));
    }
    Ok(activation)
}

pub const ZSH_INTEGRATION: &str = r#"ul() {
  if (( $# > 0 )); then
    if [[ "$2" == "--help" || "$2" == "-h" || "$2" == "help" ]]; then
      command ul "$@"
      return $?
    fi
    if [[ "$1" == "venv" ]]; then
      if (( $# != 1 )); then
        command ul "$@"
        return $?
      fi
      local _unlaw_activation
      _unlaw_activation="$(command ul _venv-path)" || return $?
      source "$_unlaw_activation"
      return $?
    fi
    local _unlaw_path
    _unlaw_path="$(command ul _template-path "$1" 2>/dev/null)"
    local _unlaw_status=$?
    if (( _unlaw_status == 0 )); then
      if (( $# != 1 )); then
        command ul _template-launch "$@"
        return $?
      fi
      builtin cd -- "$_unlaw_path" || return $?
      command ul _template-launch "$1"
      return $?
    fi
  fi
  command ul "$@"
}
"#;

fn managed_block() -> String {
    format!("{ZSH_BLOCK_START}\neval \"$(command ul _shell-init zsh)\"\n{ZSH_BLOCK_END}")
}

/// Insert or replace the managed block; returns whether the file changed.
pub fn install_zsh_integration(zshrc: &Path) -> std::io::Result<bool> {
    let existing = fs::read_to_string(zshrc).unwrap_or_default();
    let block = managed_block();
    let replaced = existing.find(ZSH_BLOCK_START).and_then(|start| {
        let end = existing[start..].find(ZSH_BLOCK_END)? + start + ZSH_BLOCK_END.len();
        Some(format!("{}{block}{}", &existing[..start], &existing[end..]))
    });
    let updated = replaced.unwrap_or_else(|| {
        let separator = if existing.is_empty() {
            ""
        } else if existing.ends_with('\n') {
            "\n"
        } else {
            "\n\n"
        };
        format!("{existing}{separator}{block}\n")
    });
    if updated == existing {
        return Ok(false);
    }
    if let Some(parent) = zshrc.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(zshrc, updated)?;
    Ok(true)
}

/// Completion: `ul _complete <position> <words...>` prints `name:description`.
pub const ZSH_COMPLETION: &str = r#"#compdef ul unlaw
_unlaw() {
  local -a candidates
  candidates=( ${(f)"$(command ul _complete $(( CURRENT - 1 )) "${(@)words[2,-1]}" 2>/dev/null)"} )
  if (( ${#candidates} )); then
    _describe 'unlaw' candidates
  else
    _files
  fi
}
compdef _unlaw ul unlaw
"#;

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(name: &str) -> PathBuf {
        let directory = std::env::temp_dir().join(format!("unlaw-shell-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        fs::create_dir_all(&directory).unwrap();
        directory
    }

    #[test]
    fn zsh_block_separators_follow_existing_content() {
        let directory = scratch("zshrc");
        let cases = [("", ""), ("export A=1\n", "export A=1\n\n"), ("export A=1", "export A=1\n\n")];
        for (index, (before, prefix)) in cases.iter().enumerate() {
            let zshrc = directory.join(format!("zshrc{index}"));
            if !before.is_empty() {
                fs::write(&zshrc, before).unwrap();
            }
            assert!(install_zsh_integration(&zshrc).unwrap());
            assert_eq!(fs::read_to_string(&zshrc).unwrap(), format!("{prefix}{}\n", managed_block()));
            assert!(!install_zsh_integration(&zshrc).unwrap());
        }
        assert!(install_zsh_integration(&directory.join("new/dir/.zshrc")).unwrap());
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn unterminated_managed_block_is_kept_and_a_new_block_appended() {
        let directory = scratch("broken");
        let zshrc = directory.join(".zshrc");
        fs::write(&zshrc, format!("{ZSH_BLOCK_START}\nold\n")).unwrap();
        assert!(install_zsh_integration(&zshrc).unwrap());
        let text = fs::read_to_string(&zshrc).unwrap();
        assert!(text.starts_with(&format!("{ZSH_BLOCK_START}\nold\n\n")));
        assert!(text.ends_with(&format!("{}\n", managed_block())));
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn venv_creation_failures_are_explained() {
        let directory = scratch("venv");
        let error = ensure_venv(&directory, Path::new("/nonexistent/python3")).unwrap_err();
        assert!(error.0.starts_with("Could not create"), "{error}");
        let error = ensure_venv(&directory, Path::new("/usr/bin/true")).unwrap_err();
        assert!(error.0.contains("without an activation script"), "{error}");
        let error = ensure_venv(&directory, Path::new("/usr/bin/false")).unwrap_err();
        assert!(error.0.contains("exited with status 1"), "{error}");
        assert!(ensure_venv(&directory.join("missing"), Path::new("/usr/bin/true")).is_err());
        fs::write(directory.join(".venv"), "file").unwrap();
        let error = ensure_venv(&directory, Path::new("/usr/bin/true")).unwrap_err();
        assert!(error.0.contains("Invalid virtual environment"), "{error}");
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn missing_project_directories_are_not_launched() {
        let template = Template { name: "gone".into(), path: "/nonexistent/project".into(), app: "zed".into(), ai: true };
        assert!(launch(&template, None).unwrap_err().0.contains("does not exist"));
    }
}
