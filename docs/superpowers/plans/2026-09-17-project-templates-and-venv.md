# Project Templates and Venv Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add saved project templates that switch the current Zsh directory and open configured apps, plus `ul venv` for creating and activating `.venv` in the current shell.

**Architecture:** Store strict TOML manifests under `templates/projects`, isolate manifest operations in `workspace_templates.py`, and route public list/create operations through system commands. Generate a small Zsh wrapper that intercepts template names and `venv`, while hidden CLI helpers perform validation, project app launches, and venv creation.

**Tech Stack:** Python 3.11+ standard library, TOML via `tomllib`, macOS `open`, Zsh shell function, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-17-project-templates-and-venv-design.md`

## Global Constraints

- Keep Python 3.11+ and standard-library-only runtime dependencies.
- Do not change or repurpose existing `templates/commands`, `templates/python`, `templates/rust`, or `templates/cpp` overlays.
- A saved template contains only `path`, `app`, and `ai`; never store or activate a Python environment from it.
- Never open a new terminal.
- Preserve manually edited seeded command files and existing command discovery behavior.
- Reject all template-name conflicts with system commands, installed commands, aliases, and other templates.
- Use atomic manifest writes and do not overwrite an existing template.

---

### Task 1: Saved-template registry

**Files:**
- Create: `src/unlawful/workspace_templates.py`
- Modify: `src/unlawful/config.py`
- Create: `tests/test_workspace_templates.py`

**Interfaces:**
- Consumes: `config.templates_dir()` and existing `ConfigError` conventions.
- Produces: `WorkspaceTemplate`, `workspace_templates_dir()`, `discover_workspace_templates()`, `load_workspace_template(name)`, and `create_workspace_template(name, path, app, ai)`.

- [ ] **Step 1: Write failing registry tests**

```python
def test_create_and_load_template(self):
    created = create_workspace_template("hearme", self.project, "zed", True)
    self.assertEqual(created.path, self.project.resolve())
    self.assertEqual(load_workspace_template("hearme"), created)

def test_manifest_rejects_unknown_keys(self):
    manifest.write_text('path = "/tmp/demo"\napp = "zed"\nai = true\nextra = 1\n')
    with self.assertRaises(WorkspaceTemplateError):
        load_workspace_template("demo")
```

- [ ] **Step 2: Run the focused tests and confirm imports fail**

Run: `python -m unittest tests.test_workspace_templates -v`
Expected: FAIL because `unlawful.workspace_templates` does not exist.

- [ ] **Step 3: Implement strict manifest storage**

```python
@dataclass(frozen=True)
class WorkspaceTemplate:
    name: str
    path: Path
    app: str
    ai: bool

def create_workspace_template(name: str, path: Path, app: str, ai: bool) -> WorkspaceTemplate:
    # Validate name/app/path, write path/app/ai to a same-directory temp file,
    # fsync, and os.replace it into templates/projects/<name>.toml.
```

Add `projects` to the template layout created by `ensure_layout()` without changing overlay behavior.

- [ ] **Step 4: Run registry and config tests**

Run: `python -m unittest tests.test_workspace_templates tests.test_config -v`
Expected: PASS.

- [ ] **Step 5: Commit the registry**

```bash
git add src/unlawful/workspace_templates.py src/unlawful/config.py tests/test_workspace_templates.py
git commit -m "feat: add saved project template registry"
```

### Task 2: Create and listing commands

**Files:**
- Modify: `src/unlawful/system_commands.py`
- Modify: `src/unlawful/cli.py`
- Modify: `tests/test_system_commands.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1 registry functions and existing `discover_commands()`/alias loading.
- Produces: `create template [name]`, `templates`, `list`, and deterministic routing of template names.

- [ ] **Step 1: Add failing public-command tests**

```python
def test_create_template_prompts_and_saves_current_directory(self):
    with patch("builtins.input", side_effect=["hearme", "zed", "y"]):
        self.assertEqual(create_command(["template"]), 0)
    self.assertEqual(load_workspace_template("hearme").path, Path.cwd().resolve())

def test_list_prints_templates_then_commands(self):
    self.assertEqual(list_all([]), 0)
    self.assertTrue(output.getvalue().startswith("Templates\n"))
    self.assertIn("\n\nCommands\n", output.getvalue())
```

Cover named creation, invalid answers that reprompt, EOF cancellation, all collision classes, sorted empty/non-empty lists, and `ul commands` exclusion.

- [ ] **Step 2: Run focused tests and confirm failures**

Run: `python -m unittest tests.test_system_commands tests.test_cli -v`
Expected: FAIL because the new system commands and create mode are absent.

- [ ] **Step 3: Implement public create/list behavior**

```python
SYSTEM_COMMAND_NAMES = {
    "commands", "completion", "config", "create", "doctor", "init",
    "list", "templates", "venv", "version", "which",
}

def list_templates(argv: Sequence[str] = ()) -> int:
    # Print sorted saved-template names only.

def list_all(argv: Sequence[str] = ()) -> int:
    # Print exact Templates/Commands grouped format.
```

Extend `create_command()` to dispatch `command` and `template` modes and use
small prompt helpers that accept only specified values.

- [ ] **Step 4: Run system and CLI tests**

Run: `python -m unittest tests.test_system_commands tests.test_cli -v`
Expected: PASS.

- [ ] **Step 5: Commit commands and routing**

```bash
git add src/unlawful/system_commands.py src/unlawful/cli.py tests/test_system_commands.py tests/test_cli.py
git commit -m "feat: create and list project templates"
```

### Task 3: Project launching and current-shell Zsh integration

**Files:**
- Create: `src/unlawful/shell_integration.py`
- Modify: `src/unlawful/system_commands.py`
- Modify: `src/unlawful/cli.py`
- Modify: `tests/test_system_commands.py`
- Create: `tests/test_shell_integration.py`

**Interfaces:**
- Consumes: `load_workspace_template(name)` and `apps.editor` configuration.
- Produces: `render_zsh_integration()`, hidden `_template-path` and `_template-launch` CLI routes, template fallback routing, and managed `.zshrc` installation.

- [ ] **Step 1: Write failing launch and shell tests**

```python
def test_launch_opens_editor_then_chatgpt(self):
    template = WorkspaceTemplate("hearme", project, "zed", True)
    self.assertEqual(launch_workspace_template(template), 0)
    run.assert_has_calls([
        call(["open", "-a", "Zed", str(project)], check=False),
        call(["open", "-a", "ChatGPT"], check=False),
    ])

def test_zsh_wrapper_changes_directory_before_launch(self):
    script = render_zsh_integration()
    self.assertIn("builtin cd --", script)
    self.assertIn("command ul _template-launch", script)
```

Cover Obsidian, missing path, editor failure stopping AI, no extra template
arguments, hidden helper exclusion, direct invocation guidance, `.zshrc`
preservation, replacement, and idempotence.

- [ ] **Step 2: Run focused tests and confirm failures**

Run: `python -m unittest tests.test_shell_integration tests.test_system_commands -v`
Expected: FAIL because shell integration and hidden helpers are absent.

- [ ] **Step 3: Implement launcher and Zsh wrapper**

```python
def launch_workspace_template(template: WorkspaceTemplate) -> int:
    app = configured_editor() if template.app == "zed" else "Obsidian"
    code = subprocess.run(["open", "-a", app, str(template.path)], check=False).returncode
    if code or not template.ai:
        return code
    return subprocess.run(["open", "-a", "ChatGPT"], check=False).returncode
```

The wrapper asks `_template-path` whether `$1` is a saved template, performs
`builtin cd -- "$path"`, then calls `_template-launch`. Non-template commands
delegate unchanged to `command ul "$@"`.

- [ ] **Step 4: Validate Python tests and generated Zsh syntax**

Run: `python -m unittest tests.test_shell_integration tests.test_system_commands tests.test_cli -v`
Expected: PASS.

Run: `PYTHONPATH=src python -c 'from unlawful.shell_integration import render_zsh_integration; print(render_zsh_integration())' | zsh -n`
Expected: exit status 0.

- [ ] **Step 5: Commit launch integration**

```bash
git add src/unlawful/shell_integration.py src/unlawful/system_commands.py src/unlawful/cli.py tests/test_shell_integration.py tests/test_system_commands.py
git commit -m "feat: launch project templates in current shell"
```

### Task 4: Current-shell `ul venv`

**Files:**
- Modify: `src/unlawful/shell_integration.py`
- Modify: `src/unlawful/system_commands.py`
- Modify: `tests/test_shell_integration.py`
- Modify: `tests/test_system_commands.py`

**Interfaces:**
- Consumes: generated Zsh wrapper from Task 3 and `venv.EnvBuilder`.
- Produces: `ensure_venv(directory) -> Path`, hidden `_venv-path`, and public `venv` guidance when shell integration is absent.

- [ ] **Step 1: Add failing venv tests**

```python
def test_ensure_venv_creates_missing_environment(self):
    activation = ensure_venv(project)
    create.assert_called_once_with(project / ".venv")
    self.assertEqual(activation, project / ".venv/bin/activate")

def test_wrapper_sources_returned_activation_path(self):
    self.assertIn('source "$activation"', render_zsh_integration())
```

Cover existing valid `.venv`, invalid `.venv`, creation failure, extra args,
and source only after successful helper completion.

- [ ] **Step 2: Run focused tests and confirm failures**

Run: `python -m unittest tests.test_shell_integration tests.test_system_commands -v`
Expected: FAIL for absent venv behavior.

- [ ] **Step 3: Implement venv creation and activation handoff**

```python
def ensure_venv(directory: Path) -> Path:
    root = directory / ".venv"
    activation = root / "bin" / "activate"
    if root.exists() and not activation.is_file():
        raise ShellIntegrationError(f"Invalid virtual environment: {root}")
    if not root.exists():
        venv.EnvBuilder(with_pip=True).create(root)
    return activation
```

The Zsh wrapper handles `ul venv` before template resolution, captures the
absolute activation path from `_venv-path`, and sources it in the current shell.

- [ ] **Step 4: Run focused tests and Zsh syntax validation**

Run: `python -m unittest tests.test_shell_integration tests.test_system_commands -v`
Expected: PASS.

Run: `PYTHONPATH=src python -c 'from unlawful.shell_integration import render_zsh_integration; print(render_zsh_integration())' | zsh -n`
Expected: exit status 0.

- [ ] **Step 5: Commit venv support**

```bash
git add src/unlawful/shell_integration.py src/unlawful/system_commands.py tests/test_shell_integration.py tests/test_system_commands.py
git commit -m "feat: add current-shell venv activation"
```

### Task 5: Documentation and release verification

**Files:**
- Modify: `README.md`
- Modify: `src/unlawful/command_sources.py` only if seeded command hashes or support source change during implementation.
- Modify: `tests/test_config.py` only if bootstrap expectations require the new projects directory.

**Interfaces:**
- Consumes: all public behavior from Tasks 1-4.
- Produces: user documentation and verified source/build/install behavior.

- [ ] **Step 1: Add documentation examples**

```markdown
ul create template hearme
ul templates
ul list
ul hearme
ul venv
ul doctor --fix
```

Document that project templates save paths rather than copy files, and that a
new shell session is required after first installing the managed Zsh function.

- [ ] **Step 2: Run formatting and full tests**

Run: `python -m unittest discover -s tests -v`
Expected: all tests PASS.

Run: `ruff check src tests hatch_build.py`
Expected: no findings.

Run: `git diff --check`
Expected: no output.

- [ ] **Step 3: Verify build and generated standalone sources**

Run: `uv build`
Expected: wheel and sdist build successfully.

Run: `find "$XDG_CONFIG_HOME/unlaw/commands" -name main.py -print0 | xargs -0 python -m py_compile`
Expected: exit status 0.

Run: `rg -n '(^from unlawful|^import unlawful|from \.)' "$XDG_CONFIG_HOME/unlaw/commands"`
Expected: no matches.

- [ ] **Step 4: Verify installed CLI in an isolated config**

```bash
uv tool install --force .
XDG_CONFIG_HOME="$(mktemp -d)" ul commands
XDG_CONFIG_HOME="$(mktemp -d)" ul templates
```

Expected: `commands` includes `templates`, `list`, and `venv`; `templates`
exits successfully with no project names.

- [ ] **Step 5: Commit docs and final adjustments**

```bash
git add README.md src tests hatch_build.py pyproject.toml
git commit -m "docs: document project templates and venv"
```
