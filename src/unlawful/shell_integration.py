from __future__ import annotations

import re
import subprocess
import venv
from pathlib import Path

from .config import ConfigError, load_config
from .workspace_templates import WorkspaceTemplate, load_workspace_template

ZSH_BLOCK_START = "# >>> Unlaw shell integration >>>"
ZSH_BLOCK_END = "# <<< Unlaw shell integration <<<"


class ShellIntegrationError(RuntimeError):
    """Raised when a current-shell operation cannot be completed."""


def template_path(name: str) -> Path:
    template = load_workspace_template(name)
    if not template.path.is_dir():
        raise ShellIntegrationError(
            f"Saved project directory does not exist: {template.path}"
        )
    return template.path


def launch_workspace_template(template: WorkspaceTemplate) -> int:
    if not template.path.is_dir():
        raise ShellIntegrationError(
            f"Saved project directory does not exist: {template.path}"
        )
    try:
        app = (
            str(load_config()["apps"]["editor"])
            if template.app == "zed"
            else "Obsidian"
        )
        code = subprocess.run(
            ["open", "-a", app, str(template.path)], check=False
        ).returncode
        if code or not template.ai:
            return code
        return subprocess.run(["open", "-a", "ChatGPT"], check=False).returncode
    except (ConfigError, OSError) as error:
        raise ShellIntegrationError(str(error)) from error


def ensure_venv(directory: Path) -> Path:
    project = directory.expanduser().resolve()
    root = project / ".venv"
    activation = root / "bin" / "activate"
    if root.exists():
        if not root.is_dir() or not activation.is_file():
            raise ShellIntegrationError(f"Invalid virtual environment: {root}")
        return activation
    try:
        venv.EnvBuilder(with_pip=True).create(root)
    except (OSError, subprocess.SubprocessError) as error:
        raise ShellIntegrationError(f"Could not create {root}: {error}") from error
    if not activation.is_file():
        raise ShellIntegrationError(
            f"Virtual environment was created without an activation script: {activation}"
        )
    return activation


def render_zsh_integration() -> str:
    return '''ul() {
  if (( $# > 0 )); then
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
'''


def _managed_zsh_block() -> str:
    return (
        f"{ZSH_BLOCK_START}\n"
        'eval "$(command ul _shell-init zsh)"\n'
        f"{ZSH_BLOCK_END}"
    )


def install_zsh_integration(zshrc: Path | None = None) -> bool:
    destination = zshrc or Path.home() / ".zshrc"
    existing = destination.read_text(encoding="utf-8") if destination.exists() else ""
    block = _managed_zsh_block()
    pattern = re.compile(
        re.escape(ZSH_BLOCK_START) + r".*?" + re.escape(ZSH_BLOCK_END),
        re.DOTALL,
    )
    match = pattern.search(existing)
    if match:
        updated = existing[: match.start()] + block + existing[match.end() :]
    else:
        separator = "" if not existing else ("\n" if existing.endswith("\n") else "\n\n")
        updated = existing + separator + block + "\n"
    if updated == existing:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(updated, encoding="utf-8")
    return True
