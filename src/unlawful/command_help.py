"""Help for seeded commands; generated sources embed only their own entry.

System and built-in Rust commands (zip, game) keep their help in rust/src.
"""

COMMAND_HELP = {
    "agent": '''Talk to a local AI agent that can work with your files, TODO board and schedule.
Shortcuts: `ula ...` and `unlawagent ...` are the same as `ul agent ...`.
Usage:
  ul agent                           Chat in the terminal (/new, /today, /plan, /exit)
  ul agent "<task>"                  Do one task and exit (or pipe the task on stdin)
  ul agent today | plan              Today's open tasks and jobs / everything scheduled
  ul agent schedule <when> <prompt> [--repeat once|daily|weekly|"every 2h"]
  ul agent unschedule <id>           Cancel a scheduled job
  ul agent setup                     Pick the local model, connect Telegram, folders, start
  ul agent start | stop | status     Background agent (Telegram + schedule) via launchd
  ul agent serve                     Run the Telegram bot and schedule in the foreground
  ul agent log [n]                   Last n actions from the audit log (default 20)
when: "in 30m", "18:00", "tomorrow 9:00" or "2026-11-01 09:00".
The model runs in `ul lm serve` (127.0.0.1, started on demand; agent.model, default
the lm default). It reads, searches and lists files only inside agent.roots; writing,
editing, moving, deleting (to the Trash), shell commands and `ul` commands from
agent.commands need your approval ([y/N] in the terminal, Yes/No buttons in
Telegram; no answer within agent.confirm_timeout seconds means no). Keys, .env
files, the keychain and Unlaw's config are always blocked.
Telegram: needs a bot token (`ul agent setup` or `ul tg setup`, stored in .env next to
config.toml with mode 600); only telegram.chat_id (you, full access) and
agent.allowed_ids get answers. Other ids may only chat unless agent.users.<id> is
"read" or "full"; approvals always go to you. Voice messages are transcribed,
photos go to a vision model, files are saved to storage.root/telegram/downloads.
Messages sent while the agent was off are skipped.
Today: open tasks from `ul todo` plus today's jobs; agent.digest_time (HH:MM) sends
it to Telegram every morning. Data and audit log: storage.root/agent.
Settings: agent.model, agent.roots, agent.allowed_ids, agent.users, agent.commands,
agent.max_steps, agent.confirm_timeout, agent.digest_time, agent.system_prompt.
Dependencies: ul lm with a downloaded chat model (MLX on Apple silicon); no cloud models.
Examples:
  ul agent setup
  ula "what is in ~/Downloads that is older than a month?"
  ul agent schedule 9:00 "summarize my TODO board" --repeat daily
  ul config set agent.allowed_ids \'["123456789"]\'
  ul agent start
''',
    "app": '''Open a macOS application by name.
Usage: ul app <application>
Example: ul app "Visual Studio Code"
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
Token: .env next to config.toml (mode 600); tokens saved before 3.3 are read from
the macOS Keychain. Default downloads: storage.root/telegram/downloads.
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
}
