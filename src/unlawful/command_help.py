"""Help for seeded commands; generated sources embed only their own entry.

System and built-in Rust commands (zip, game) keep their help in rust/src.
"""

COMMAND_HELP = {
    "agent": '''Your local AI agent: files, TODO board and schedule, in the console or Telegram.
Usage:
  ula [options] [message...]   Open the console (a message, if given, is sent first)
  ula server                   Telegram bot and schedule in this terminal (Ctrl+C stops)
  ula setup                    Model, Telegram, allowed ids, folders, background mode
`ula` and `unlawagent` are the same as `ul agent`.
Options:
  -p, --print            Answer once, print only the answer, exit (automatic when
                         stdin or stdout is redirected; piped stdin becomes the message)
  -c, --continue         Continue the last console conversation
  -m, --model <name>     Use another downloaded model for this run
Console:
  / opens a command menu and @ a file menu: up/down choose, Enter or Tab picks,
  Esc closes it. /model and /unschedule open a second menu with models or jobs.
  Enter sends; Alt+Enter or Ctrl+J adds a line (pasting keeps lines); up/down
  browse history. Esc stops the agent; Ctrl+C clears the input, twice quits;
  Ctrl+D quits. Approvals: left/right and Enter, or y (yes), a (yes for this kind
  of action until you quit), n (no).
  /help /new /model /today /plan /schedule /unschedule /status /log /thinking /copy /exit
  /schedule <when> <text> sets a reminder without the model: /schedule in 10m tea,
  /schedule завтра 9:00 позвонить, /schedule 18:00 run --repeat daily.
  !cmd runs a shell command and shares its output; !!cmd keeps the output to you.
  @path attaches a file or an image to the message.
What it may do: read, list and search files inside agent.roots without asking;
writing, editing, moving, deleting (to the Trash), shell commands and `ul`
commands from agent.commands need your approval (a picker in the console, Yes/No
buttons in Telegram; no answer within agent.confirm_timeout seconds means no).
Keys, .env files, the keychain and Unlaw's config are always blocked.
Schedule and today: /schedule, or ask in plain words ("remind me at 9:00 to ...",
"напомни через 10 мин ..."). Reminders arrive in Telegram as they are; tasks are
run by the agent at that time. Both need `ula server` (or background mode).
/today and /plan show them; columns named Done/Completed/Готово count as finished.
Telegram: the bot token lives in the macOS Keychain (`ula setup` saves it there;
a TELEGRAM_BOT_TOKEN= line in .env next to config.toml is read only if the
Keychain has none). Only telegram.chat_id (you, full access) and
agent.allowed_ids get answers; others
may only chat unless agent.users.<id> is "read" or "full"; approvals always come
to you. Voice messages are transcribed, photos go to a vision model, files are
saved to storage.root/telegram/downloads. Messages sent while no server ran are
skipped. agent.digest_time (HH:MM) sends today's list every morning.
Models: only local ones from `ul lm` (started on demand). Small models (2-4B,
2-bit) often answer without calling tools: /model and `ula setup` check this and
keep the old model unless you insist, `ula server` warns at start, and an answer
that claims a change without any tool call gets a warning.
Settings: agent.model, agent.roots, agent.allowed_ids, agent.users, agent.commands,
agent.max_steps, agent.confirm_timeout, agent.digest_time, agent.system_prompt.
Data and audit log: storage.root/agent.
Examples:
  ula
  ula -p "what is in ~/Downloads that is older than a month?"
  git diff | ula -p "review this change"
  ula -c
  ula server
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
Token: the macOS Keychain (service telegram.keychain_service); if it has none, a
TELEGRAM_BOT_TOKEN= line in .env next to config.toml is used. Default downloads:
storage.root/telegram/downloads.
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
  --podcast            Save a small mono MP3 (64 kbps, title/channel/cover tags)
                       into yt.podcast_dir, by default iCloud Drive/Podcasts
  --quality <height>   Maximum video height, e.g. 720, 1080, 2160
  --output <directory> Save into this directory (created if needed)
  -h, --help           Show this help, also after download
Modes --audio, --podcast, --sub and --full cannot be combined.
Subtitle-only mode cannot use --quality or --format; --full supports both.
Markdown starts with the video link, then title, language/source and cleaned text.
Authored captions are preferred; automatic captions may contain recognition errors.
--full downloads media once and extracts MP3 locally. Missing/failed subtitles
produce a clear warning and a nonzero exit code while retaining saved media.
Defaults: MOV video with audio; storage.root/youtube.
--podcast saves into yt.podcast_dir (setting; --output overrides it). Its parent
folder must exist, so a disabled iCloud Drive is reported instead of filled locally.
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
  ul yt download "https://youtu.be/VIDEO_ID" --podcast
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
