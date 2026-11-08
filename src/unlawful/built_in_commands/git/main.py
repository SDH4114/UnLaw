from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from urllib.parse import quote

from unlawful.command_help import COMMAND_HELP
from unlawful.git_hosts import (
    HOSTS,
    HostError,
    create_repo,
    ensure_ssh_key,
    expand_remote,
    host_of,
    is_host_name,
    pr_url,
    save_token,
    ssh_check,
    web_url,
)

USAGE = (
    "Usage: ul git [message|push [message]|commit [message]|sync [message]|init|"
    "connect SPEC|mirror add|list|remove|token HOST|open|pr|undo [--list|COMMIT]]"
)
# Removed actions: still refused, so the word never becomes a commit message by accident.
_GIT_REMOVED = {"status", "pull"}
_GIT_ACTIONS = {
    "push",
    "commit",
    "sync",
    "init",
    "connect",
    "mirror",
    "token",
    "open",
    "pr",
    "undo",
}
_GIT_MAX_BYTES = 50 * 1024 * 1024
_GIT_ALWAYS_IGNORE = [
    ".DS_Store",
    ".env",
    ".env.*",
    "!.env.example",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
]
_GIT_TYPE_IGNORE = {
    "python": [
        "__pycache__/",
        "*.py[cod]",
        ".venv/",
        "venv/",
        ".pytest_cache/",
        ".ruff_cache/",
        ".mypy_cache/",
        "*.egg-info/",
        "build/",
        "dist/",
        ".coverage",
    ],
    "rust": ["target/"],
    "cpp": [
        "build/",
        "cmake-build-*/",
        "CMakeCache.txt",
        "CMakeFiles/",
        "*.o",
        "*.obj",
        "*.a",
        "*.so",
        "*.dylib",
    ],
    "node": ["node_modules/", "dist/", "npm-debug.log*"],
}
_GIT_TYPE_FILES = {
    "python": ("pyproject.toml", "requirements.txt"),
    "rust": ("Cargo.toml",),
    "cpp": ("CMakeLists.txt",),
    "node": ("package.json",),
}
_GIT_REMOTE_SUFFIX = re.compile(r"[A-Za-z0-9._-]+")


class _GitUsage(Exception):
    """A command-line mistake: printed with the usage line, exit code 2."""


def _run_all(commands: list[list[str]]) -> int:
    try:
        for command in commands:
            code = subprocess.run(command, check=False).returncode
            if code:
                return code
    except OSError as error:
        print(f"unlaw git: {error}", file=sys.stderr)
        return 1
    return 0


def _git_fail(message: str) -> int:
    print(f"unlaw git: {message}", file=sys.stderr)
    return 1


def _git_out(*args: str) -> subprocess.CompletedProcess[str]:
    """Run git quietly and return its text output; a missing git becomes exit code 127."""
    command = ["git", *args]
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            errors="surrogateescape",
        )
    except OSError as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def _git_parse(
    args: list[str], *, values: Sequence[str] = (), flags: Sequence[str] = ()
) -> tuple[dict[str, str], list[str]]:
    options: dict[str, str] = {}
    positional: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in values:
            if index + 1 >= len(args):
                raise _GitUsage(f"{arg} needs a value")
            options[arg] = args[index + 1]
            index += 2
            continue
        if arg in flags:
            options[arg] = "1"
        elif arg.startswith("-") and len(arg) > 1:
            raise _GitUsage(f"unknown option {arg}")
        else:
            positional.append(arg)
        index += 1
    return options, positional


def _git_in_worktree() -> bool:
    result = _git_out("rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip() == "true"


def _git_branch() -> str:
    return _git_out("symbolic-ref", "--short", "-q", "HEAD").stdout.strip()


def _git_has_commits() -> bool:
    return _git_out("rev-parse", "--verify", "-q", "HEAD").returncode == 0


def _git_remote_url(name: str) -> str | None:
    """The URL as written in the config (`remote get-url` would apply insteadOf)."""
    result = _git_out("config", "--get", f"remote.{name}.url")
    return result.stdout.strip() or None if result.returncode == 0 else None


def _git_mirrors() -> list[str]:
    return [
        name for name in _git_out("remote").stdout.split() if name.startswith("mirror-")
    ]


def _git_repo_name() -> str:
    root = _git_out("rev-parse", "--show-toplevel").stdout.strip()
    return os.path.basename(root or os.getcwd())


def _git_open_url(url: str) -> int:
    try:
        return subprocess.run(["open", url], check=False).returncode
    except OSError as error:
        return _git_fail(str(error))


def _git_push_all(*, upstream_branch: str | None = None) -> int:
    """Push origin, then every mirror; a failing mirror only warns."""
    if upstream_branch is None and _git_remote_url("origin"):
        # A branch without an upstream would make a plain `git push` fail: publish it on origin.
        branch = _git_branch()
        if branch and _git_out("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode:
            upstream_branch = branch
    command = (
        ["git", "push"]
        if upstream_branch is None
        else ["git", "push", "-u", "origin", upstream_branch]
    )
    code = _run_all([command])
    if code:
        return code
    for mirror in _git_mirrors():
        if subprocess.run(["git", "push", mirror, "HEAD"], check=False).returncode:
            print(
                f"unlaw git: warning: push to {mirror} failed; origin is up to date.",
                file=sys.stderr,
            )
    return 0


def _commit_message(tokens: list[str]) -> str | None:
    if tokens:
        return " ".join(tokens).strip()
    try:
        message = input("Commit message: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nunlaw git: commit cancelled.", file=sys.stderr)
        return None
    if not message:
        print("unlaw git: commit message cannot be empty.", file=sys.stderr)
        return None
    return message


def _has_staged_changes() -> bool | int:
    """True or False, or git's exit code when it cannot tell (not a repository)."""
    try:
        code = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], check=False
        ).returncode
    except OSError as error:
        print(f"unlaw git: {error}", file=sys.stderr)
        return 1
    if code in (0, 1):
        return code == 1
    return code


def _git_secret_reason(path: str, root: str) -> str | None:
    name = path.rsplit("/", 1)[-1]
    lower = name.lower()
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return "environment file"
    if lower.endswith((".pem", ".key")):
        return "private key or certificate"
    if lower.endswith(".p12"):
        return "key store"
    if name.startswith(("id_rsa", "id_ed25519")) and not name.endswith(".pub"):
        return "private SSH key"
    try:
        if os.path.getsize(os.path.join(root, path)) > _GIT_MAX_BYTES:
            return f"larger than {_GIT_MAX_BYTES // (1024 * 1024)} MB"
    except OSError:
        return None
    return None


def _git_secrets_guard(allow: bool) -> int:
    """Unstage files that must not be committed; 0 when clear, 1 when something was held back."""
    if allow:
        return 0
    # Deletions are excluded: removing a committed secret must always be possible.
    staged = _git_out("diff", "--cached", "--name-only", "--diff-filter=d", "-z")
    if staged.returncode:
        # Keep git's own exit code (128 outside a repository), as the workflow always did.
        _git_fail(staged.stderr.strip() or "cannot list staged files.")
        return staged.returncode
    paths = [path for path in staged.stdout.split("\0") if path]
    if not paths:
        return 0
    root = _git_out("rev-parse", "--show-toplevel").stdout.strip() or "."
    found = [
        (path, reason) for path in paths if (reason := _git_secret_reason(path, root))
    ]
    if not found:
        return 0
    _git_out("reset", "-q", "--", *[path for path, _ in found])
    lines = [
        "not committing, these staged files look like secrets or are too big (now unstaged):"
    ]
    lines.extend(f"  {path}  ({reason})" for path, reason in found)
    lines.append(
        "Add them to .gitignore (`ul git init` merges a safe one) or rerun with --allow-secrets."
    )
    print("unlaw git: " + "\n".join(lines), file=sys.stderr)
    return 1


def _commit_workflow(
    tokens: list[str], *, push: bool, allow_secrets: bool = False
) -> int:
    code = _run_all([["git", "add", "."]])
    if code:
        return code
    code = _git_secrets_guard(allow_secrets)
    if code:
        return code
    staged = _has_staged_changes()
    if staged is False:
        # Earlier commits may still be unpushed, so a clean tree must not stop the push.
        print("unlaw git: nothing to commit.", file=sys.stderr)
        return _git_push_all() if push else 0
    if staged is not True:
        return staged
    message = _commit_message(tokens)
    if message is None:
        return 2
    code = _run_all([["git", "commit", "-m", message]])
    if code or not push:
        return code
    return _git_push_all()


def _git_commit_args(args: list[str]) -> tuple[list[str], bool]:
    allow = "--allow-secrets" in args
    return [arg for arg in args if arg != "--allow-secrets"], allow


def _git_detect_types() -> list[str]:
    return [
        kind
        for kind, names in _GIT_TYPE_FILES.items()
        if any(os.path.exists(name) for name in names)
    ]


def _git_merge_gitignore(kinds: list[str]) -> None:
    """Append the missing ignore lines; existing lines are never changed or removed."""
    try:
        with open(".gitignore", encoding="utf-8") as handle:
            current = handle.read()
    except FileNotFoundError:
        current = ""
    present = {line.strip() for line in current.splitlines()}
    wanted: list[str] = []
    for line in [
        *(line for kind in kinds for line in _GIT_TYPE_IGNORE[kind]),
        *_GIT_ALWAYS_IGNORE,
    ]:
        if line not in present and line not in wanted:
            wanted.append(line)
    if not wanted:
        return
    prefix = "" if not current or current.endswith("\n") else "\n"
    with open(".gitignore", "a", encoding="utf-8") as handle:
        handle.write(prefix + "\n".join(wanted) + "\n")


def _git_init(args: list[str]) -> int:
    options, positional = _git_parse(
        args,
        values=("--connect", "--name", "--url"),
        flags=("--public", "--allow-secrets"),
    )
    if positional:
        raise _GitUsage("init takes no arguments")
    if _git_in_worktree():
        return _git_fail("already inside a Git work tree; nothing to initialize.")
    created = _git_out("init", "-b", "main")
    if created.returncode:
        # Git before 2.28 has no -b.
        created = _git_out("init")
        if created.returncode == 0:
            created = _git_out("symbolic-ref", "HEAD", "refs/heads/main")
        if created.returncode:
            return _git_fail(created.stderr.strip() or "git init failed.")
    print("Initialized a Git repository on branch main.")
    try:
        _git_merge_gitignore(_git_detect_types())
    except (OSError, UnicodeDecodeError) as error:
        return _git_fail(f"cannot update .gitignore: {error}")
    code = _commit_workflow(
        ["Initial commit"], push=False, allow_secrets="--allow-secrets" in options
    )
    if code or "--connect" not in options:
        return code
    forwarded = [options["--connect"]]
    for name in ("--name", "--url"):
        if name in options:
            forwarded.extend([name, options[name]])
    if "--public" in options:
        forwarded.append("--public")
    return _git_connect(forwarded)


def _git_resolve_remote(spec: str, options: dict[str, str]) -> str:
    """The SSH URL for a host name (creating the repository) or the expanded URL for other specs."""
    if is_host_name(spec):
        name = options.get("--name") or _git_repo_name()
        created = create_repo(
            spec, name, private="--public" not in options, base_url=options.get("--url")
        )
        return created.ssh_url
    return expand_remote(spec)


def _git_ssh_gate(url: str) -> int:
    """For SSH remotes of a known host: 0 when SSH works, otherwise offer an SSH key and return 1."""
    host = host_of(url)
    if host is None or not url.startswith(("git@", "ssh://")):
        return 0
    ok, message = ssh_check(host.ssh_host)
    if ok:
        return 0
    print(f"unlaw git: SSH to {host.ssh_host} failed: {message}", file=sys.stderr)
    try:
        answer = input("Create an SSH key and open the key page? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        answer = ""
    if answer.strip().lower() not in {"y", "yes"}:
        return 1
    public = ensure_ssh_key()
    try:
        print(public.read_text(encoding="utf-8").strip())
    except OSError as error:
        print(f"unlaw git: cannot read {public}: {error}", file=sys.stderr)
    if host.keys_page:
        _git_open_url(host.keys_page)
    print("Add the public key above to your account, then run the same command again.")
    return 1


def _git_verify_remote(target: str) -> int:
    result = _git_out("ls-remote", target)
    if result.returncode:
        return _git_fail(
            f"cannot access {target}: {result.stderr.strip() or 'ls-remote failed'}"
        )
    return 0


def _git_connect(args: list[str]) -> int:
    options, positional = _git_parse(
        args, values=("--name", "--url"), flags=("--public", "--force")
    )
    if len(positional) != 1:
        raise _GitUsage("connect needs one SPEC (a host name, gh:owner/repo or a URL)")
    spec = positional[0]
    force = "--force" in options
    if not _git_in_worktree():
        return _git_fail("not a Git repository; run `ul git init` first.")
    existing = _git_remote_url("origin")
    current_host = host_of(existing) if existing else None
    if current_host is not None and is_host_name(spec) and current_host.name == spec.lower() and not force:
        # Already connected to this host (e.g. a rerun after the SSH key step): reuse origin, create nothing.
        url = existing
    elif existing and not force and is_host_name(spec):
        return _git_fail(
            f"origin already points to {existing}; use --force to replace it."
        )
    else:
        url = _git_resolve_remote(spec, options)
    if existing and existing != url and not force:
        return _git_fail(
            f"origin already points to {existing}; use --force to replace it with {url}."
        )
    if existing is None:
        code = _run_all([["git", "remote", "add", "origin", url]])
    elif existing != url:
        code = _run_all([["git", "remote", "set-url", "origin", url]])
    else:
        code = 0
    if code:
        return code
    code = _git_ssh_gate(url)
    if code:
        return code
    code = _git_verify_remote("origin")
    if code or not _git_has_commits():
        return code
    branch = _git_branch()
    if not branch:
        print("unlaw git: detached HEAD; nothing pushed.", file=sys.stderr)
        return 0
    return _git_push_all(upstream_branch=branch)


def _git_mirror(args: list[str]) -> int:
    if not args:
        raise _GitUsage("mirror needs add, list or remove")
    action, rest = args[0], args[1:]
    if action not in {"add", "list", "remove"}:
        raise _GitUsage(f"unknown mirror action {action}")
    if not _git_in_worktree():
        return _git_fail("not a Git repository.")
    if action == "list":
        if rest:
            raise _GitUsage("mirror list takes no arguments")
        mirrors = _git_mirrors()
        if not mirrors:
            print("No mirrors. Add one with: ul git mirror add <host|URL>")
        for name in mirrors:
            print(f"{name}\t{_git_remote_url(name) or ''}")
        return 0
    if action == "remove":
        if len(rest) != 1:
            raise _GitUsage("mirror remove needs a mirror name")
        name = rest[0] if rest[0].startswith("mirror-") else f"mirror-{rest[0]}"
        if name not in _git_mirrors():
            return _git_fail(f"no mirror named {name}; see `ul git mirror list`.")
        return _run_all([["git", "remote", "remove", name]])
    options, positional = _git_parse(
        rest, values=("--name", "--url"), flags=("--public",)
    )
    if len(positional) != 1:
        raise _GitUsage(
            "mirror add needs one SPEC (a host name, gh:owner/repo or a URL)"
        )
    spec = positional[0]
    if is_host_name(spec):
        remote = f"mirror-{spec}"
        if remote in _git_mirrors():
            return _git_fail(f"{remote} already exists; remove it first.")
        url = _git_resolve_remote(spec, options)
    else:
        url = expand_remote(spec)
        host = host_of(url)
        suffix = options.get("--name") or (host.name if host else "")
        if not suffix:
            raise _GitUsage("mirror add needs --name for this URL")
        remote = f"mirror-{suffix}"
        if not _GIT_REMOTE_SUFFIX.fullmatch(suffix):
            raise _GitUsage(
                "the mirror name may use letters, digits, '.', '_' and '-' only"
            )
        if remote in _git_mirrors():
            return _git_fail(f"{remote} already exists; remove it first.")
    code = _git_ssh_gate(url) or _git_verify_remote(url)
    if code:
        return code
    code = _run_all([["git", "remote", "add", remote, url]])
    if not code:
        print(f"Added {remote} -> {url}. `ul git push` now pushes there too.")
    return code


def _git_token(args: list[str]) -> int:
    _, positional = _git_parse(args)
    if len(positional) != 1 or positional[0] not in HOSTS:
        raise _GitUsage(f"token needs a host: {', '.join(HOSTS)}")
    host = positional[0]
    try:
        value = getpass.getpass(f"{host} token (input hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nunlaw git: cancelled.", file=sys.stderr)
        return 2
    if not value:
        print("unlaw git: the token cannot be empty.", file=sys.stderr)
        return 2
    save_token(host, value)
    print(f"Saved the {host} token in the macOS Keychain (service unlaw.git.{host}).")
    return 0


def _git_open(args: list[str]) -> int:
    if args:
        raise _GitUsage("open takes no arguments")
    origin = _git_remote_url("origin")
    if origin is None:
        return _git_fail("no origin remote; run `ul git connect` first.")
    page = web_url(origin)
    if not page:
        return _git_fail(f"cannot work out a web page for {origin}.")
    page = page.rstrip("/")
    branch = _git_branch()
    host = host_of(origin)
    if branch and host is not None:
        page += ("/-/tree/" if host.kind == "gitlab" else "/tree/") + quote(
            branch, safe="/"
        )
    return _git_open_url(page)


def _git_pr(args: list[str]) -> int:
    options, positional = _git_parse(args, values=("--base",))
    if positional:
        raise _GitUsage("pr takes no arguments")
    base = options.get("--base", "main")
    branch = _git_branch()
    if not branch:
        return _git_fail("detached HEAD; check out a branch first.")
    if branch == base:
        return _git_fail(
            f"you are on the base branch {base}; switch to a feature branch first."
        )
    origin = _git_remote_url("origin")
    if origin is None:
        return _git_fail("no origin remote; run `ul git connect` first.")
    code = _git_push_all(upstream_branch=branch)
    if code:
        return code
    host = host_of(origin)
    if host is not None and host.name == "github" and shutil.which("gh"):
        return _run_all([["gh", "pr", "create", "--fill", "--base", base]])
    page = pr_url(origin, branch, base)
    if not page:
        return _git_fail(f"cannot work out a pull request page for {origin}.")
    return _git_open_url(page)


def _git_branch_commits() -> list[tuple[str, str, str]]:
    """(full hash, date, subject) of the current branch, newest first."""
    out = _git_out("log", "--format=%H%x00%ad%x00%s", "--date=short", "HEAD").stdout
    return [tuple(line.split("\0", 2)) for line in out.splitlines() if line.count("\0") == 2]  # type: ignore[misc]


def _git_undo_list() -> int:
    commits = _git_branch_commits()
    if not commits:
        return _git_fail("this branch has no commits yet.")
    local = set(_git_out("rev-list", "HEAD", "--not", "--remotes").stdout.split())
    print(f"Commits on {_git_branch() or 'HEAD'}, newest first; (local) = not pushed, can be undone:")
    for full, date, subject in commits:
        print(f"{full[:7]}  {date}  {subject}{'  (local)' if full in local else ''}")
    print("Go back to one with: ul git undo <hash or part of its message>")
    return 0


def _git_find_commit(text: str) -> str | None:
    """The commit of this branch named by a hash prefix or (part of) its message; None with an explanation."""
    commits = _git_branch_commits()
    if re.fullmatch(r"[0-9a-fA-F]{4,40}", text):
        by_hash = [full for full, _, _ in commits if full.startswith(text.lower())]
        if len(by_hash) == 1:
            return by_hash[0]
    wanted = text.casefold()
    found = [entry for entry in commits if entry[2].casefold() == wanted] or [
        entry for entry in commits if wanted in entry[2].casefold()
    ]
    if len(found) == 1:
        return found[0][0]
    if not found:
        _git_fail(f"no commit in this branch matches `{text}`; see `ul git undo --list`.")
        return None
    lines = "\n".join(f"  {full[:7]}  {subject}" for full, _, subject in found[:10])
    _git_fail(f"several commits match `{text}`; use the hash:\n{lines}")
    return None


def _git_undo(args: list[str]) -> int:
    options, positional = _git_parse(args, flags=("--list",))
    if "--list" in options:
        if positional:
            raise _GitUsage("undo --list takes no commit")
        return _git_undo_list()
    if not _git_has_commits():
        return _git_fail("this branch has no commits yet.")
    if positional:
        # Back to the named commit: it stays, every commit after it is undone.
        target = _git_find_commit(" ".join(positional))
        if target is None:
            return 1
    else:
        parent = _git_out("rev-parse", "--verify", "-q", "HEAD~1")
        if parent.returncode:
            return _git_fail("there is no earlier commit to go back to.")
        target = parent.stdout.strip()
    undone = _git_out("rev-list", f"{target}..HEAD").stdout.split()
    if not undone:
        print("Already at that commit; nothing to undo.")
        return 0
    # The oldest undone commit is in every later one: if a remote has any of them, it has this one.
    if _git_out("branch", "-r", "--contains", undone[-1]).stdout.split():
        return _git_fail(
            "some of these commits are already on a remote branch; undoing them would rewrite shared history.\n"
            f"Use `git revert {'<commit>' if positional else 'HEAD'}` instead."
        )
    subjects = _git_out("log", "--format=%h  %s", f"{target}..HEAD").stdout.rstrip()
    code = _run_all([["git", "reset", "--soft", target]])
    if not code:
        count = len(undone)
        print(f"Undid {count} commit{'s' if count > 1 else ''}:\n{subjects}\nTheir changes are staged.")
    return code


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help", "help"}:
        print(COMMAND_HELP["git"], end="")
        return 0
    action, rest = (args[0], args[1:]) if args else ("", [])
    if action in _GIT_ACTIONS and any(arg in {"-h", "--help"} for arg in rest):
        print(COMMAND_HELP["git"], end="")
        return 0
    if action in _GIT_REMOVED:
        print(f"unlaw git: `ul git {action}` was removed; use `git {action}`.", file=sys.stderr)
        return 2
    try:
        if action in {"push", "commit", "sync"}:
            tokens, allow = _git_commit_args(rest)
            if action == "commit":
                return _commit_workflow(tokens, push=False, allow_secrets=allow)
            if action == "sync":
                code = _run_all([["git", "pull", "--rebase"]])
                return code or _commit_workflow(tokens, push=True, allow_secrets=allow)
            return _commit_workflow(tokens, push=True, allow_secrets=allow)
        handlers = {
            "init": _git_init,
            "connect": _git_connect,
            "mirror": _git_mirror,
            "token": _git_token,
            "open": _git_open,
            "pr": _git_pr,
            "undo": _git_undo,
        }
        if action in handlers:
            return handlers[action](rest)
        tokens, allow = _git_commit_args(args)
        return _commit_workflow(tokens, push=True, allow_secrets=allow)
    except _GitUsage as error:
        print(f"unlaw git: {error}\n{USAGE}", file=sys.stderr)
        return 2
    except HostError as error:
        print(f"unlaw git: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
