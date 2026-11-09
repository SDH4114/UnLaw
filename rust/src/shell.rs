//! Current-shell integration: the Zsh wrapper, `.venv` creation and saved
//! project launching.

use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::util::{atomic_write, read_to_string_or_empty};
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
      local _unlaw_arg _unlaw_cd=1
      for _unlaw_arg in "${@:2}"; do
        case "$_unlaw_arg" in
          --focus|--no-focus) ;;
          *) _unlaw_cd=0 ;;
        esac
      done
      if (( _unlaw_cd )); then
        builtin cd -- "$_unlaw_path" || return $?
      fi
      command ul _template-launch "$@"
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
    let existing = read_to_string_or_empty(zshrc)?;
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
    atomic_write(zshrc, &updated, ".zshrc.")?;
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
    fn an_unreadable_zshrc_is_never_overwritten() {
        let directory = scratch("badzshrc");
        let zshrc = directory.join(".zshrc");
        fs::write(&zshrc, [b'a', 0xff, 0xfe, b'\n']).unwrap();
        assert!(install_zsh_integration(&zshrc).is_err());
        assert_eq!(fs::read(&zshrc).unwrap(), vec![b'a', 0xff, 0xfe, b'\n']);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn a_symlinked_zshrc_stays_a_symlink() {
        let directory = scratch("linkzshrc");
        let real = directory.join("dotfiles/zshrc");
        fs::create_dir_all(real.parent().unwrap()).unwrap();
        fs::write(&real, "export A=1\n").unwrap();
        let link = directory.join(".zshrc");
        std::os::unix::fs::symlink(&real, &link).unwrap();
        assert!(install_zsh_integration(&link).unwrap());
        assert!(fs::symlink_metadata(&link).unwrap().file_type().is_symlink());
        assert!(fs::read_to_string(&real).unwrap().contains(ZSH_BLOCK_START));
        fs::remove_dir_all(directory).unwrap();
    }
}
