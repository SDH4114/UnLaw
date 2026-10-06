"""Command documentation; generated sources embed only their own entry."""

COMMAND_HELP = {
    "app": '''Open a macOS application by name.
Usage: ul app <application>
Example: ul app "LM Studio"
''',
    "browser": '''Open the configured browser homepage in your default browser.
Usage: ul browser
Setting: apps.browser_url
Example: ul config set apps.browser_url "https://duckduckgo.com/"
''',
    "capture": '''Capture screenshots or record screen, camera and microphone.
Usage: ul capture <action> [output] [--duration <seconds>]
Actions:
  screenshot / area / window   Full screen, selected area or selected window PNG
  screen / camera / audio     Start a recording (camera/audio require ffmpeg)
  devices                     List camera and microphone devices
  stop                        Stop the active recording
  last                        Open the latest capture
Defaults: storage.root/captures; --duration must be positive.
Examples: ul capture area; ul capture screen --duration 30
''',
    "cpp": '''Create a C++ project from the configured templates.
Usage: ul cpp <project-name> [--std 11|14|17|20|23|26] [--git]
Options: --std selects the C++ standard; --git initializes Git.
Defaults: projects.cpp.standard and projects.cpp.initialize_git.
Example: ul cpp demo --std 23 --git
''',
    "game": '''Play a terminal arcade game; no arguments opens the game menu.
Usage: ul game [tetris|snake|minesweeper|invaders] [easy|normal|hard]
Default difficulty: games.difficulty. Use the on-screen controls; q quits.
Example: ul game snake hard
''',
    "git": '''Stage, commit and push the current Git project, or run a Git action.
Usage: ul git [message|status|pull|push|commit [message]|sync [message]]
Actions:
  no arguments / <message>    git add ., commit, then push (prompts for missing message)
  status / pull / push       Run the corresponding Git command
  commit [message]           Stage and commit without pushing
  sync [message]             Pull with rebase, then stage, commit and push
Example: ul git commit "Fix downloader"
''',
    "gpt": '''Open the ChatGPT macOS application.
Usage: ul gpt
Example: ul gpt
''',
    "lm": '''Use a local model through LM Studio (localhost only).
Usage: ul lm [prompt|open|start|stop|status|models]
Actions:
  no arguments     Interactive chat, or read a prompt from stdin
  <prompt>         Ask the loaded local model
  open             Open LM Studio
  start/stop/status Manage the local server through lms
  models           List loaded models
Settings: lm.base_url, model, system_prompt, temperature, timeout.
Example: ul lm "Explain this Python error"
''',
    "lofi": '''Open the configured lofi website in your default browser.
Usage: ul lofi
Setting: apps.lofi_url
Example: ul lofi
''',
    "mac": '''Control macOS applications through optional macos-harness.
Usage:
  ul mac see <application>                 Inspect an application
  ul mac key <application> <shortcut>      Send a keyboard shortcut
  ul mac type <application> <text>         Type text
  ul mac click <application> <x> <y>       Click coordinates
Example: ul mac see Zed
''',
    "minecraft": '''Open the Prism Launcher macOS application for Minecraft.
Usage: ul minecraft
Example: ul minecraft
''',
    "music": '''Open Spotify, or search for a track and attempt to play it.
Usage: ul music [track]
Settings: apps.spotify, apps.spotify_autoplay_delay.
Autoplay requires Accessibility permission for your terminal.
Example: ul music "Nujabes Feather"
''',
    "netflix": '''Open Netflix in your default browser.
Usage: ul netflix
Example: ul netflix
''',
    "obsidian": '''Open the Obsidian macOS application.
Usage: ul obsidian
Example: ul obsidian
''',
    "py": '''Create a Python project from the configured templates.
Usage: ul py <project-name> [--uv|--venv|--no-venv] [--git]
Options: --uv uses uv; --venv uses Python venv; --no-venv skips environment creation.
--git initializes Git. Defaults come from projects.python.
Example: ul py demo --venv --git
''',
    "rust": '''Create a Rust project using Cargo and the configured templates.
Usage: ul rust <project-name> [--bin|--lib] [--git]
Options: --bin creates an executable (default); --lib creates a library.
--git initializes Git; default comes from projects.rust.initialize_git.
Example: ul rust demo --lib --git
''',
    "steam": '''Open the Steam macOS application.
Usage: ul steam
Example: ul steam
''',
    "tg": '''Open Telegram, or send and download messages/files through your bot.
Usage:
  ul tg                                  Open Telegram
  ul tg <message>|send <message-or-file>   Send text or a file
  ul tg photo|video|file <path>            Send a file with an explicit type
  ul tg capture                          Send the latest capture
  ul tg setup                            Configure bot token and chat ID
  ul tg status                           Check bot configuration
  ul tg last                             Print recent bot updates
  ul tg download [directory]              Download files from recent updates
Token: macOS Keychain. Default downloads: storage.root/telegram/downloads.
Example: ul tg send "Hello"
''',
    "todo": '''Read and update the configured Obsidian TODO board.
Usage: ul todo [open|path|search <text>|add <text> [--column <name>]|move <id> <column>|done <id>]
Actions:
  no arguments   List tasks with numeric IDs
  open / path    Open the board in Obsidian / print its path
  search <text>  Find matching tasks
  add <text>     Add a task; --column selects its section
  move <id> <column> Move a task to another section
  done <id>      Mark complete and move to todo.completed_column
Settings: todo.vault_path, todo.file, todo.completed_column.
Example: ul todo add "Study Python" --column "To do"
''',
    "work": '''Open the configured lofi website and the current directory in your editor.
Usage: ul work
Settings: apps.lofi_url, apps.editor.
Example: ul work
''',
    "yt": '''Open YouTube, search, or download one YouTube video.
Usage:
  ul yt                                 Open YouTube homepage
  ul yt <query>                         Search YouTube in your default browser
  ul yt download <URL> [options]         Download one video (not its playlist)
Options:
  --format mov|mp4|raw Video format (default: mov); raw keeps the source container
  --audio              Save only MP3 (cannot combine with --quality or --format)
  --sub                Save only subtitles as .md, original language by default
  --sub-lang [code]    Choose ru/en/etc.; no value selects original. Implies --sub
                       unless --full is used; unknown codes list available languages
  --full               Save video with sound, separate MP3 and .md subtitles
  --quality <height>   Maximum video height, e.g. 720, 1080, 2160
  --output <directory> Save into this directory (created if needed)
  -h, --help           Show this help, also after download
Modes --audio, --sub and --full cannot be combined.
Subtitle-only mode cannot use --quality or --format; --full supports both.
Markdown starts with the video link, then title, language/source and cleaned text.
Authored captions are preferred; automatic captions may contain recognition errors.
--full downloads media once and extracts MP3 locally. Missing/failed subtitles
produce a clear warning and a nonzero exit code while retaining saved media.
Defaults: MOV video with audio; storage.root/youtube.
MOV/MP4 conversion uses H.264/AAC when conversion is needed; it can take time.
Raw preserves the source codecs/container (possibly WebM); it is not camera RAW.
Dependencies: yt-dlp; video/audio also need ffmpeg/ffprobe. Deno supports YouTube.
Install: brew install yt-dlp ffmpeg deno
Existing files are not overwritten. Download progress appears in the terminal.
Examples:
  ul yt "omarchy linux"
  ul yt download "https://www.youtube.com/watch?v=VIDEO_ID"
  ul yt download "https://youtu.be/VIDEO_ID" --format mp4
  ul yt download "https://youtu.be/VIDEO_ID" --format raw
  ul yt download "https://youtu.be/VIDEO_ID" --audio
  ul yt download "https://youtu.be/VIDEO_ID" --sub
  ul yt download "https://youtu.be/VIDEO_ID" --sub-lang
  ul yt download "https://youtu.be/VIDEO_ID" --sub-lang ru
  ul yt download "https://youtu.be/VIDEO_ID" --full --sub-lang en --format mp4
  ul yt download "https://youtu.be/VIDEO_ID" --quality 1080 --output ~/Downloads
''',
    "zed": '''Open the current directory in the configured editor (default: Zed).
Usage: ul zed
Setting: apps.editor
Example: ul zed
''',
    "commands": '''List available system commands, installed commands and aliases.
Usage: ul commands [--verbose|--json]
Options: --verbose includes source/path; --json prints structured records.
Example: ul commands --verbose
''',
    "completion": '''Print Zsh completion code for ul and unlaw.
Usage: ul completion zsh
Example: eval "$(ul completion zsh)"
''',
    "config": '''Inspect or edit the Unlaw TOML configuration.
Usage:
  ul config path|show|edit|check     Print path/content, edit, or validate
  ul config get <key>               Read a dotted configuration key
  ul config set <key> <value>       Set and validate a value atomically
  ul config reset --yes             Reset defaults, preserving a backup
Example: ul config set storage.root ~/Downloads/unlaw
''',
    "create": '''Create an editable command or save the current project as a template.
Usage:
  ul create command <name>          Create commands/<name>/main.py
  ul create template [name]         Prompt for project name, app and AI preference
Existing commands/templates are not overwritten.
Example: ul create command hello
''',
    "doctor": '''Check Unlaw configuration, tools and shell integration.
Usage: ul doctor [--verbose|--json|--fix]
Options: --verbose adds details; --json prints a report; --fix repairs supported issues.
Example: ul doctor --verbose
''',
    "init": '''Initialize the Unlaw configuration and editable command sources.
Usage: ul init
Example: ul init
''',
    "list": '''List saved project templates and available commands.
Usage: ul list
Example: ul list
''',
    "templates": '''List saved project templates.
Usage: ul templates
Example: ul templates
''',
    "venv": '''Create and activate .venv in the current project's Zsh shell.
Usage: ul venv
Requires current-shell integration: ul doctor --fix, then restart Zsh.
Example: ul venv
''',
    "version": '''Show the installed Unlaw version.
Usage: ul version
Example: ul version
''',
    "which": '''Print the source path of an installed command.
Usage: ul which <command>
Example: ul which yt
''',
}
