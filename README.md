# Unlaw

Unlaw is a fast personal CLI utility for macOS. Its core mechanism stays simple:
a `commands/<name>/main.py` folder automatically becomes the `ul <name>` command.

## Install and update

Install the latest version from GitHub with one command:

```bash
curl -LsSf https://raw.githubusercontent.com/SDH4114/UnLaw/main/install.sh | sh
```

The Unlaw core (dispatcher, configuration, system commands, completion, doctor)
is written in Rust and built with `cargo`; the installer sets up Rust through
rustup if it is missing. Commands in `commands/` remain plain Python files, so
Python 3.11+ is required (`brew install python`). The `ul` and `unlaw` binaries
are installed into `~/.local/bin`; the old uv-based Unlaw is removed automatically.

Update to the latest version from GitHub:

```bash
ul update --check          # compare version and commit with GitHub without installing
ul update                  # reinstall from main (cargo install --locked --force)
ul update --tag v2.2.0     # a specific release; --branch <name> for a branch
```

`ul --version` shows the version and build commit (`Unlaw 3.0.0 (dd061d1)`), so an
update is visible even when the version number doesn't change. `ul update` installs
the new binary where the current `ul` lives (`~/.local/bin` by default).
Configuration, data and manually edited commands are left untouched; unmodified
standard commands are updated on the next run. Requires `cargo` and Python 3.11+;
`--check` also needs `curl`. `UNLAW_UPDATE_REPOSITORY` points to a fork.

From a local checkout (install and update are the same command):

```bash
cargo install --path . --root ~/.local --force
```

`unlaw` and `ul` are fully equivalent. Building from source and the first run
automatically create the user structure:

```text
~/.config/unlaw/
├── config.toml
├── commands/                   # all non-system commands
│   ├── game/main.py
│   ├── todo/main.py
│   └── ...
├── data/                       # single default storage
│   ├── captures/
│   ├── runtime/
│   └── telegram/
└── templates/
    ├── commands/
    ├── python/
    ├── rust/
    ├── cpp/
    └── projects/                  # saved paths and launch settings
```

Existing configs, commands and templates are never overwritten. Old official
import wrappers are automatically replaced with full code, while manually edited
commands are kept. System commands cover configuration, diagnostics, listings,
project templates and shell integration; all other commands are created in
`commands/<name>/main.py` and are yours to edit. Each such file contains only its
own command's code and the minimal settings it needs — code from other commands is
never mixed in.

## Main commands

```bash
ul                              # help and initialization
ul init                         # show user paths
ul commands                     # all commands and aliases
ul commands --verbose           # sources and real paths
ul commands --describe          # one-line descriptions (without running commands)
ul commands --json              # machine-readable JSON
ul templates                    # saved project templates
ul list                         # templates first, then commands
ul which git                    # where a command comes from
ul create command anime         # new command
ul create template hearme       # save the current project
ul venv                         # create/activate .venv in the current shell
ul doctor --verbose             # full diagnostics
ul doctor --fix                 # safe automatic fixes
ul doctor --json                # diagnostics for scripts
ul completion zsh               # zsh completion
ul version
ul update --check              # is there a new version on GitHub
ul skills install --claude      # teach coding agents to use ul
ula                             # local AI agent: files, TODO, schedule, Telegram
```

Global options:

```bash
ul --dry-run <command> ...
ul --verbose <command> ...
ul --no-color <command> ...
ul --version
```

An unknown command gets a suggestion with the closest name. `--dry-run` shows the
exact process for a command (interpreter and path) without running it.

## Saved projects

A project template saves an existing folder and its launch settings. Project
files are not copied.

```bash
cd ~/giti/HearMe
ul create template hearme
```

Unlaw asks whether to open the project with `zed` or `obsidian`, then whether to
open ChatGPT. If no name is given, it is prompted for too:

```text
Name of template > hearme
Open with (zed/obsidian) > zed
Add AI? (y/n) > y
```

Once saved, the project can be launched from any folder:

```bash
ul hearme
```

The command changes directory in the current Zsh, opens it in the chosen app and
launches ChatGPT if requested. No new terminal is created. Saved projects are
listed by `ul templates`, and the combined list by `ul list`. The manifest is
stored in `~/.config/unlaw/templates/projects/<name>.toml` and contains only the
absolute path, the app and the AI flag.

To change directory in the current shell, install the integration once and
restart Zsh:

```bash
ul doctor --fix
exec zsh
```

## Virtual environment

```bash
cd ~/giti/HearMe
ul venv
```

If `.venv` is missing, the command creates it with `python -m venv` (interpreter
from `core.python`) and then activates it in the current Zsh. An existing valid
`.venv` is simply activated. Project templates neither save nor activate a
virtual environment.

## Configuration

```bash
ul config path
ul config show
ul config get core.command_timeout
ul config set core.command_timeout 15
ul config set aliases.g '["git"]'
ul config check
ul config edit
ul config reset --yes
```

`reset --yes` creates a timestamped backup first. Writes are atomic.
`config set` accepts TOML values; unquoted text is stored as a string.
Comments, ordering and unknown keys in `config.toml` are preserved on write.

Default configuration:

```toml
[core]
color = true
verbose = false
command_timeout = 0
show_timing = false
python = "auto"

[aliases]

[storage]
root = "data"

[git]
auto_push = true

[projects.python]
environment = "auto"
initialize_git = false

[projects.rust]
initialize_git = false

[projects.cpp]
standard = 20
initialize_git = false

[mac]
executable = "macos-harness"
timeout = 30

[todo]
vault_path = "~/aiwork/data-obsidian"
file = "TODO.md"
completed_column = "Completed"

[capture]
camera_device = "0"
audio_device = "0"
screen_audio = true
show_clicks = true

[games]
difficulty = "normal"

[zip]
format = "zip"                  # zip, 7z, rar, tar.zst, tar.xz, tar.gz
level = "max"                   # 0–9 or store, fastest, fast, normal, max, ultra
keep_junk = false

[apps]
spotify = "Spotify"
editor = "Zed"
spotify_autoplay_delay = 2.0
browser_url = "https://duckduckgo.com/"
lofi_url = "https://lofi-engine.vercel.app/"
youtube_url = "https://www.youtube.com/"

[telegram]
chat_id = ""
api_base = "https://api.telegram.org"
keychain_service = "unlaw.telegram"

[lm]
model = "auto"
embedding_model = "auto"
stt_model = "auto"
tts_model = "auto"
image_model = "auto"
video_model = "auto"
music_model = "auto"
port = 1234
idle_minutes = 10
system_prompt = "You are a concise and practical local assistant."
temperature = 0.7
max_tokens = 4096
```

`command_timeout = 0` disables the limit. The Python environment accepts `auto`,
`uv`, `venv` or `none`. In `auto` mode uv is tried first, then the standard venv.
A relative `storage.root` is resolved against `~/.config/unlaw`; an absolute path
or a path with `~` moves the whole storage elsewhere:

```bash
ul config set storage.root '"~/Documents/UnlawData"'
```

## Aliases

An alias is an array of arguments, not a shell string. It is therefore never run
with `shell=True` and can safely be extended with user arguments:

```toml
[aliases]
g = ["git"]
gs = ["git", "status"]
newpy = ["py"]
```

```bash
ul gs
ul newpy experiment --uv --git
```

Cyclic aliases are detected and not run. System commands cannot be overridden by
an alias.

## User commands

```bash
ul create command anime
```

This creates `~/.config/unlaw/commands/anime/main.py`. Arguments are in
`sys.argv[1:]`, and the script's exit code is returned to the shell. A user
command can be fully rewritten by hand. Automatic updates never overwrite an
existing `main.py`.

A command is a folder with a single entry point. These are checked in order:

| File | Run with |
|---|---|
| `main.py` | Python 3.11+ from `core.python` (`auto` — the newest `python3.x` on PATH) |
| `main.sh` | `/bin/sh`, or directly via shebang if the file is executable |
| `main.js` | `node` |
| `main` | directly; any executable, e.g. a compiled Rust/C++ binary |

No SDK is needed: Unlaw passes environment variables to the command.

| Variable | Value |
|---|---|
| `UNLAW_COMMAND` | command name |
| `UNLAW_COMMAND_DIR` | command folder |
| `UNLAW_CONFIG_DIR` | Unlaw config folder (`config.toml`) |
| `UNLAW_STORAGE` | resolved `storage.root` path for the command's files |
| `UNLAW_BIN` | absolute path of the running `ul`, for calling other commands |

```sh
#!/bin/sh
# Show today's notes folder.
mkdir -p "$UNLAW_STORAGE/notes" && open "$UNLAW_STORAGE/notes"
```

The description for `ul commands --describe` and Zsh completion is read without
running the command: the first line of `help.txt` in the command folder, otherwise
the first line of the `main.py` docstring, otherwise the first `#`/`//` comment in
other scripts. `--help` inside the command itself is still required.

Your own template for new commands:

```text
~/.config/unlaw/templates/commands/main.py
~/.config/unlaw/templates/commands/rust/      # Cargo.toml + src/, {{command_name}} is substituted
```

### Rust commands

```bash
ul create command fast --lang rust
ul fast hello
```

Creates a Cargo project in `~/.config/unlaw/commands/fast/` and builds it right
away. Edit `src/main.rs` and just run `ul fast`: Unlaw rebuilds the command itself
when `src/`, `Cargo.toml` or `Cargo.lock` is newer than the binary. The description
for `ul commands --describe` comes from `description` in `Cargo.toml`. Requires
`cargo`; dependencies are added as in any Rust project (`cargo add` in the command
folder).

### Built-in Rust commands

`ul zip`, `ul game` and `ul lm` are built into the core. Lookup order: system
commands → `commands/<name>/` → built-ins, so your own `commands/zip` folder still
overrides the built-in `zip`. Untouched old `commands/zip/main.py`,
`commands/game/main.py` and `commands/lm/main.py` (the LM Studio client from 3.0)
are removed automatically on update; manually edited ones stay and keep running
instead of the built-ins.

## Commands in config

All commands below live at `~/.config/unlaw/commands/<name>/main.py`. They are
complete standalone sources: at runtime they don't import `unlawful` and don't
depend on the package's internal structure. The system dispatcher looks for
commands only in this folder.

### Apps

```bash
ul app Zed
ul app "Visual Studio Code"
```

### Git

```bash
ul git "fix parser"       # add, commit, push
ul git                    # add, ask for a message in the terminal, commit -m, push
ul git status
ul git pull
ul git push
ul git commit "message"  # add + commit, no push
ul git sync "message"    # pull --rebase + add + commit + push
```

Without an argument, `ul git` shows a plain one-line `Commit message:` prompt in
the current terminal and never opens a Git editor. The standard workflow always
ends with `git push` and stops at the first error.

### Python

```bash
ul py experiment
ul py experiment --uv
ul py experiment --venv
ul py experiment --no-venv
ul py experiment --uv --git
```

### Rust

```bash
ul rust amber
ul rust amber --lib
ul rust amber --bin --git
```

The project is created with Cargo. Without `--git`, Cargo gets `--vcs none`
unless `projects.rust.initialize_git` is enabled.

### C++

```bash
ul cpp engine
ul cpp engine --std 23
ul cpp engine --git
```

Creates a CMake project. Standards 11, 14, 17, 20, 23 and 26 are supported.

No generator overwrites an existing directory.

## Obsidian Kanban

`ul todo` works with an existing `TODO.md` inside the configured Obsidian vault
and keeps the Kanban plugin's service block intact. Task numbers are shown by the
command without arguments:

```bash
ul todo
ul todo add "Finish Unlaw"
ul todo add "Check tests" --column "For today"
ul todo search "Unlaw"
ul todo move 3 "In progress"
ul todo done 3
ul todo open
ul todo path
```

Changes are written atomically. Multi-line descriptions move together with the
task.

## Screen, video and audio capture

```bash
ul capture screenshot
ul capture area
ul capture window
ul capture screen                 # background screen + microphone recording
ul capture camera                 # camera + microphone via ffmpeg
ul capture audio                  # microphone via ffmpeg
ul capture screen --duration 30
ul capture devices
ul capture stop
ul capture last
```

The first run may ask for Screen Recording, Camera, Microphone and Accessibility
permissions. `camera_device` and `audio_device` can be picked from the output of
`ul capture devices`. By default all media goes into `storage.root/captures`;
Telegram saves downloads to `storage.root/telegram/downloads`, and runtime files
go to `storage.root/runtime`.

## Quick apps

```bash
ul lofi                           # open Lofi Engine
ul zed                            # open the current folder in Zed
ul netflix                        # open Netflix
ul tg                             # open Telegram
ul obsidian                       # open Obsidian
ul gpt                            # open ChatGPT
ul browser                        # open the configured start page
ul steam                          # open Steam
ul minecraft                      # open Prism Launcher
ul music
ul music "Killer Queen"           # search and play the first result in Spotify
ul work                            # Lofi Engine + current folder in Zed
ul yt                              # open the YouTube home page
ul yt "omarchy linux"             # YouTube search in the browser
ul yt download "https://youtu.be/VIDEO_ID"                 # download MOV
ul yt download "https://youtu.be/VIDEO_ID" --format mp4    # MP4
ul yt download "https://youtu.be/VIDEO_ID" --format raw    # source container/codecs
ul yt download "https://youtu.be/VIDEO_ID" --audio         # MP3
ul yt download "https://youtu.be/VIDEO_ID" --quality 1080  # up to 1080p
ul yt download "https://youtu.be/VIDEO_ID" --output ~/Downloads
ul yt --help                      # all options and examples
```

Auto-playing a Spotify result requires the Accessibility permission for the
terminal.

The `ul browser` start page is set in the config:

```bash
ul config set apps.browser_url '"https://duckduckgo.com/"'
```

## Archives

`ul zip` compresses files and folders and extracts almost any archive. Without an
action, the command figures out what to do: archives are extracted, everything
else is compressed.

```bash
ul zip project                     # project.zip next to the folder, max compression
ul zip a.png b.png notes/          # several paths → ./Archive.zip
ul zip project -f 7z               # strongest (LZMA2)
ul zip project -f rar              # RAR5 with recovery record (needs rar)
ul zip project -f zst --fast       # tar.zst: fast and dense, for backups
ul zip project -f 7z -9            # level 0–9 (or --store … --ultra)
ul zip project -p -f 7z            # AES-256 password, file names hidden too
ul zip project -o ~/Desktop/pack.7z  # format taken from the extension
ul zip project.zip                 # extract next to it
ul zip x backup.rar -o ~/Downloads # extract into a folder
ul zip x pack.zip --here           # contents directly into the destination
ul zip ls backup.7z                # list contents
ul zip test backup.7z              # integrity check
```

Creates `zip` (default), `7z`, `rar`, `tar.zst`, `tar.xz`, `tar.gz`; also reads
`rar`, `gz`, `bz2`, `xz`, `zst`, `cab`, `iso`, `cpio`, `xar`. macOS junk
(`.DS_Store`, `._*`, `__MACOSX`) is kept out of archives; `--keep-junk` keeps it.
A single-item archive extracts as that item, otherwise into a folder named after
the archive. Nothing is overwritten: a ` 2` suffix is added. The password is
prompted in the terminal and never passed in process arguments.

Levels follow the 7-Zip scale: `0` store, `1` fastest, `3` fast, `5` normal,
`7` max (default), `9` ultra. Each level maps to the format's best settings
(`-mx`, `rar -m0…5`, `xz -0…9`, `zstd -1…19` and `--ultra -22`). Measured on
68 MB of code and binaries: 7z `1/5/7/9` gives 16.7/14.1/13.8/13.8 MB, zip —
20.0/19.0/18.7/18.6 MB, Finder — 20.3 MB. If no level is given and ≥90% of the
input is already-compressed media (jpg, heic, mp4, zip…), level 1 is used: on
236 MB of HEIC, level 9 saved 0.01% in 37 s instead of 3 s.

Dependencies: `brew install sevenzip zstd`; to create `.rar` — `brew install --cask rar`.
Without 7-Zip, `zip` archives are created with the system `zip`, and extraction
goes through `bsdtar`.

## Unlaw Arcade

```bash
ul game                       # menu (mouse or keyboard)
ul game tetris
ul game snake easy
ul game minesweeper normal
ul game invaders hard
```

The games are built into the Rust core and support keyboard and mouse. Each screen
shows a controls hint at the bottom, `P` pauses, `Esc`/`Q` quits. After game over,
Enter or a click plays again, Esc returns to the menu. Best scores are stored in
`storage.root/runtime/arcade.toml` and shown in the menu.

| Game | Like the original | Mouse |
|---|---|---|
| Tetris | 7-piece bag, Next queue, Hold (`C`), ghost piece, rotation with wall kicks (`↑`/`X`, `Z`), lock delay, level up every 10 lines, guideline gravity, combos and back-to-back | piece follows the cursor, click — hard drop, right click — rotate |
| Snake | 2-character-wide cells, turn buffer, speeds up as it grows, timed ★ bonus | click — turn toward the click |
| Minesweeper | Beginner 9×9/10, Intermediate 16×16/40, Expert 30×16/99, safe first click, chording on numbers, classic colors, timer | left — reveal or chord, right — flag |
| Space Invaders | 5×11 formation, three alien types, speeds up as they fall, only the bottom row shoots, one player bullet on screen, bunkers, UFO, lives and waves, extra life at 1500 | cannon follows the cursor, click — fire |

Difficulty: `easy` — slow start and assists (Tetris has a ghost piece and 3 pieces
in Next, the snake passes through walls, 5 lives in Invaders); `normal` — classic;
`hard` — genuinely hard: Tetris starts at level 12 without ghost or Hold, with
garbage rising from below, the snake gets obstacles and double growth, Minesweeper
is Expert without a guaranteed opening, aliens fire nonstop and you have 2 lives.
Set the default with `ul config set games.difficulty hard`.

## Telegram

```bash
ul tg                              # open the Telegram app
ul tg setup                        # token is stored in the macOS Keychain
ul tg "Message from the terminal"
ul tg send report.pdf
ul tg photo screenshot.png
ul tg video demo.mov
ul tg capture                       # latest Unlaw screenshot or recording
cat notes.txt | ul tg
ul tg last
ul tg download
ul tg status
```

The bot token is never written to `config.toml` or Git. For a private chat, first
message the bot, then enter its `chat_id` during `setup`.

## Local agent

`ula` (also `unlawagent` and `ul agent`) is a personal agent on a local `ul lm`
model. It reads and searches your files, works with the TODO board, schedules
jobs and, with your approval, changes things on the Mac. Three commands:

```bash
ula                     # console: streamed answers, tool calls, approvals
ula server              # Telegram bot + schedule in this terminal (Ctrl+C stops)
ula setup               # model, Telegram, allowed ids, folders, background mode
```

The console works like [pi](https://github.com/badlogic/pi-mono) and other CLI
agents: an input box with a status line, streamed answers with Markdown, tool
calls as they run.

```text
/            command menu (↑↓ choose, Enter or Tab picks, Esc closes);
             /model and /unschedule open a second menu with models or jobs
@            file menu; the picked file or image is attached to the message
!git status  run a shell command and share its output (!! keeps it to you)
Enter        send · Alt+Enter or Ctrl+J: new line · ↑↓: history
Esc          stop the agent · Ctrl+C: clear the input (twice: quit) · Ctrl+D: quit
```

Approvals are a picker: Yes, Yes for this kind of action until you quit, or No
(←→ and Enter, or `y` / `a` / `n`).

```bash
ula -p "what is in ~/Downloads that is older than a month?"   # answer once, print it
git diff | ula -p "review this change"                         # piped stdin is the message
ula -c                                                         # continue the last conversation
ula -m prism-ml/Ternary-Bonsai-2-27B-mlx-2bit                 # another model for this run
```

- Only local models: `ul lm serve` on 127.0.0.1, started when needed. Small
  models (2-4B, 2-bit) often answer without calling tools; `ula setup` and
  `/model` check whether a model calls them.
- Reading, listing and searching work only inside `agent.roots` (default `~`).
  SSH keys, `.env` files, the keychain and Unlaw's config are always blocked.
- Writing, editing, moving, deleting (to the Trash), shell commands and `ul`
  commands from `agent.commands` need approval: a picker in the console, Yes/No
  buttons in Telegram. No answer within `agent.confirm_timeout` seconds means no.
- Telegram: only `telegram.chat_id` (you, full access) and `agent.allowed_ids`
  get answers; others may only chat unless `agent.users.<id>` is `"read"` or
  `"full"`. In `ula setup`, typing ids adds them, `-id` removes one, Enter keeps
  the list. Voice messages are transcribed, photos go to a vision model, Markdown
  answers arrive formatted.
- Background mode (asked in `ula setup`) keeps `ula server` running through
  launchd, also after login; a second server for the same bot is refused.
- Schedule and today's list: ask in plain words ("remind me at 9:00 to …");
  jobs run while a server runs. `agent.digest_time = "08:30"` sends today's list
  every morning.

```bash
ul config set agent.roots '["~/giti", "~/Documents", "~/Downloads"]'
ul config set agent.users.123456789 read
```

## Agent skills

`ul skills install` writes an Agent Skill (`SKILL.md`) that teaches
coding agents (Codex, Claude Code and others) to use `ul`.

```bash
ul skills install               # ~/.agents/skills/unlaw
ul skills install --claude      # plus a link in ~/.claude/skills
ul skills install --project     # ./.agents/skills/unlaw in the current project
ul skills list
ul skills show todo             # one command's reference page
ul skills remove
```

`SKILL.md` tells agents to discover commands live (`ul commands --describe`,
`ul <command> --help`), so new commands work right away. The `reference/`
snapshot is regenerated automatically after `ul update` and whenever commands
are added, changed or removed. Folders the skill did not create are never
overwritten.

## Local models (MLX)

`ul lm` is its own local model engine for Apple Silicon, replacing LM Studio and
Ollama: it downloads any model from Hugging Face and runs it with MLX — chat,
vision, embeddings, speech recognition and synthesis, music, images and video, in
the terminal and through an API compatible with OpenAI (like LM Studio) and Ollama.

```bash
ul lm search qwen3 --mlx                       # search Hugging Face
ul lm pull prism-ml/Ternary-Bonsai-2-9B-mlx-2bit
ul lm use Bonsai-2-9B                          # default model for its type
ul lm                                          # chat: /model /image /clear /save /think
ul lm "explain this code" < main.rs            # one-off streamed answer
ul lm -i photo.jpg "what's in the photo?"      # vision models
ul lm image "bonsai in morning light" --open   # images (mflux, Bonsai Image)
ul lm video "waves at sunset" --seconds 2      # video (mlx-video: Wan 2.x, LTX-2)
ul lm speak "Hello!" -m Qwen3-TTS --play       # speech synthesis (mlx-audio)
ul lm music "lo-fi piano" --lyrics song.txt    # music (MiniMax Music 3)
ul lm transcribe voice.m4a --srt               # speech to text; any format, even .mov
ul lm embed "text to search"                   # embeddings (JSON)
ul lm convert Qwen/Qwen3-4B --bits 4           # regular model → MLX 4-bit
ul lm list | info <model> | use <model>
ul lm rm [<model>...]                          # delete models from the Mac (no name — pick from a list)
ul lm clean                                    # partial downloads, orphaned files, download cache
ul lm open [<model>|models|generated|converted|engine|logs]   # show the folder in Finder
ul lm where <...>                              # same, but print the path
ul lm serve [--ollama] [--cors]                # API on 127.0.0.1:1234 until Ctrl-C
ul lm import-lmstudio [--dry-run]              # move LM Studio downloads over
ul lm doctor [--repair]
```

Connecting your own apps after `ul lm serve`:

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:1234/v1", api_key="local")
reply = client.chat.completions.create(model="Bonsai-2-9B",
                                       messages=[{"role": "user", "content": "hello"}])
image = client.images.generate(model="bonsai-image", prompt="a fox in the snow", size="512x512")
speech = client.audio.speech.create(model="Qwen3-TTS", voice="serena", input="Hello!")
```

OpenAI API: `/v1/models`, `/v1/chat/completions` (streaming, tools, images,
`reasoning_content`), `/v1/completions`, `/v1/embeddings`,
`/v1/audio/transcriptions` (json, text, srt, verbose_json), `/v1/audio/speech`,
`/v1/images/generations`, `/v1/videos` (a job; `GET /v1/videos/{id}` and
`/content`). Ollama API: `/api/tags`, `/api/chat`, `/api/generate`,
`/api/embed`, `/api/show`, `/api/ps`; `--ollama` additionally listens on `:11434`.
The server answers only on `127.0.0.1`, rejects foreign host names (DNS rebinding
protection), sends no CORS headers without `--cors` and never reads local files on
an API request. The `model` field accepts `owner/repo`, the repository name or
part of it; without it, the default model for that type is used (`lm.model`,
`lm.image_model`, `lm.tts_model`...). If the server is running, `ul lm` in the
terminal goes through it and reuses already loaded models.

Models are stored in the standard Hugging Face cache (`HF_HUB_CACHE`,
`HF_HOME/hub` or `~/.cache/huggingface/hub`) and are visible to `hf`, transformers
and other tools. `ul lm rm` and `ul lm clean` delete through huggingface_hub itself
(like `hf cache rm` / `prune`), so files shared with other models and datasets are
not affected; a default model that gets deleted is reset to auto. The model type is
detected from the model card and files: text, vision, embedding, stt, tts, music,
image, video. GGUF runs too: chat, vision (with an `mmproj` file) and embeddings
through a pinned official llama.cpp build (downloaded automatically, 16 MB,
sha256-verified), speech recognition (Parakeet, Whisper GGUF) through
transcribe.cpp. Among several quantizations, Q4_K_M is picked (otherwise Q5_K_M,
Q6_K, Q8_0); `ul lm info` shows which one. If both MLX and GGUF versions of a model
exist, the short name picks MLX. In a repository with a dozen GGUF files, `pull`
asks you to choose one.
Bonsai (1-bit, Ternary, Bonsai-2) runs without its own launcher; Bonsai Image runs
through PrismML's mflux library in a separate engine.

Engines install themselves on first use into `storage.root/runtime/lm-engine`
via uv on Python 3.13: the core one (about 1.2 GB: mlx, mlx-lm, mlx-vlm,
mlx-embeddings, mlx-audio, mlx-whisper, mlx-video), images (mflux) and Bonsai
Image — 1.5 GB each, only when needed. Chat, helper models, images and video run
in separate processes: embeddings don't wait for a long reply, and one crashing
doesn't affect the others. A model larger than 75% of RAM is rejected before
loading; models are unloaded after `lm.idle_minutes` of inactivity. Default
sampling parameters come from the model's `generation_config.json` (the authors'
recommendations), then from `lm.temperature`. There is no cloud fallback.

## Self-repair

```bash
ul doctor --verbose
ul doctor --json
ul doctor --fix
```

`--fix` adds missing settings (comments in `config.toml` are preserved), creates
directories inside `storage.root`, moves the old runtime log, puts the `ul`
binary's folder before `/usr/bin` and installs a managed Zsh function in
`~/.zshrc`. It is needed for `ul <template>` and `ul venv`, because only a
function in the current shell can do a persistent `cd` or `source`. Run
`exec zsh` after the fix.

## Project file templates

Files from `~/.config/unlaw/templates/python`, `rust` and `cpp` are layered over
the standard project. UTF-8 files support placeholders:

```text
{{project_name}}
{{cpp_standard}}
```

Binary files are copied unchanged. Placeholders also work in file and directory
names.

## macOS Harness

Harness remains an optional backend:

```bash
ul mac see Spotify
ul mac key Spotify cmd+k
ul mac type Telegram "hello"
ul mac click Spotify 500 300
```

User commands can call the same bridge through the CLI:

```python
import subprocess

subprocess.run(["ul", "mac", "key", "Spotify", "cmd+k"], check=False)
```

The executable and timeout are set in the `[mac]` section. `doctor` checks
Harness without requesting new macOS permissions.

## Zsh completion

```bash
mkdir -p ~/.zfunc
ul completion zsh > ~/.zfunc/_ul
```

Add before `compinit` in `~/.zshrc`:

```zsh
fpath=(~/.zfunc $fpath)
autoload -Uz compinit && compinit
```

Completion shows commands with descriptions, then subcommands of `config`,
`create`, `doctor` and so on. It is served by the Rust core (`ul _complete`);
Python is not started.

## Development

```text
Cargo.toml, rust/      Rust core: dispatcher, config, system commands, doctor
rust/build.rs          embeds data from Python via rust/gen_assets.py
src/unlawful/          seeded command sources, their help and DEFAULT_CONFIG
tests/                 Python command tests and black-box binary tests
```

Seeded commands, their help, legacy hashes and the default configuration are
defined once in `src/unlawful`; `cargo build` exports them into the binary, so the
build needs Python 3.11+. The version in `Cargo.toml` must match
`src/unlawful/__init__.py`, otherwise the build stops.

```bash
cargo test
cargo clippy --all-targets
python3 -m unittest discover -s tests -v   # builds target/debug/ul itself
cargo build --release
```

Unlaw 3 stays local-first: commands don't use shell strings, `ul lm` listens only
on loopback and never calls cloud models, and the Telegram token is stored in the
macOS Keychain (a `TELEGRAM_BOT_TOKEN=` line in `.env` next to `config.toml` is read
only when the Keychain has none). External apps and permissions stay explicitly
visible through `ul doctor`.

### Command help and YouTube downloads

All built-in commands support `ul <command> --help`, `-h` and `ul help <command>`. Help describes the purpose, actions, options and examples without running the command. New commands from `ul create command <name>` also get a help handler; update its text when you change the command.

For downloads, install the external tools: `brew install yt-dlp ffmpeg deno`. Unlaw stays a package without Python dependencies. By default video is saved as MOV with audio; `--format mp4` picks MP4, `--format raw` keeps YouTube's source container and codecs (including WebM) without re-encoding. This is not camera RAW. Converting to MOV/MP4 uses H.264/AAC when the format has to change and may take a while. `--quality` sets an upper bound on height (if that quality isn't available, a lower one is picked); `--audio` saves MP3 and can't be combined with `--quality` or `--format`. The default location is `storage.root/youtube`; `--output` sets another folder. A single video is downloaded, including Shorts links and videos from a playlist; links to entire playlists and channels are rejected. Existing files are never overwritten.

### YouTube subtitles and full bundle

```bash
ul yt download "https://youtu.be/VIDEO_ID" --sub           # subtitles only as .md, original language
ul yt download "https://youtu.be/VIDEO_ID" --sub-lang      # same thing
ul yt download "https://youtu.be/VIDEO_ID" --sub-lang ru   # pick Russian
ul yt download "https://youtu.be/VIDEO_ID" --full          # MOV with audio + separate MP3 + .md
ul yt download "https://youtu.be/VIDEO_ID" --full --sub-lang en --format mp4 --quality 1080
```

`--sub-lang` without a value picks the original; the flag itself enables subtitle mode, except with `--full`. An unknown code lists all available languages and exits before any media is downloaded. Authored subtitles take priority over automatic ones in the chosen language. When the original language can't be determined, the command says explicitly which available language it chose. The `.md` starts with the video link, followed by the title, language, subtitle source and text. Timestamps, markup and overlapping repeats are removed; the text is not paraphrased. Automatic captions may contain recognition errors. Subtitles need only `yt-dlp`, not `ffmpeg`.

`--full` saves files side by side in `storage.root/youtube` or the `--output` folder: the video in the chosen format with audio, a separate `.mp3`, and subtitles as `.<lang>.md`. The video is downloaded from YouTube once; audio is extracted locally. The `--sub`, `--audio` and `--full` modes are mutually exclusive. If there are no subtitles or downloading them fails, `--full` keeps the media, reports an incomplete result and returns a non-zero exit code. Existing files are kept, temporary files are removed.

## License

Copyright (C) 2026 Haos

Unlaw is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version
(`GPL-3.0-or-later`). This program is distributed WITHOUT ANY WARRANTY. See
[LICENSE](LICENSE) for the full text.
