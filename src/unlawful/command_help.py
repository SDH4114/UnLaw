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
    "capture": '''Screenshots and screen, camera and audio recordings on macOS.
Usage: ul capture                 a menu: pick what to capture (in a terminal)
       ul capture shot [screen|area|window] [options] [PATH]
       ul capture record [screen|camera|audio] [options] [PATH]
       ul capture pause | resume | stop | status
       ul capture list | last | open | reveal | copy | delete | trim | convert | devices
Screenshots (shot):
  screen (default) the whole display; area / window let you select with the mouse
  --display N      which display (1 = main; see `devices`)   --delay S  wait S seconds
  --clipboard      copy instead of saving   --cursor  include the pointer
  --jpg            JPEG instead of PNG      --open    open the file afterwards
Recording (record) runs in the background until `ul capture stop`:
  screen (default) the display with system audio (macOS screencapture) and the
                   microphone; --camera puts the camera in a corner (capture.overlay)
  camera           the camera with the microphone
  audio            the microphone only (m4a, mp3 or wav)
  --mic NAME|N     microphone by name or number; --no-mic records without it
  --cam NAME|N     camera by name or number (default: capture.camera_device)
  --system-audio / --no-system-audio   sound of the Mac (screen only)
  --display N      --rect X,Y,W,H (part of the screen, in points)   --no-clicks
  --format F       mov|mp4 for video, m4a|mp3|wav for audio
  --duration S     record S seconds in the foreground, then save
  --wait           stay in the foreground: Enter stops, p + Enter pauses
  pause / resume   pause and continue; the parts are joined when you stop
  stop             stop and save (adds the camera and microphone; may take a moment)
  status           what is recording, for how long, and where it goes
Library:
  list [N] [--all] the newest captures with kind, length and size
  last [--reveal]  open the newest capture (or show it in Finder)
  open|reveal X    open a capture, or show it in Finder (X: name, path or `last`)
  copy X           put a screenshot on the clipboard
  delete X         move a capture to the Trash (only from the capture folders)
  trim X --from T [--to T]   cut a recording exactly (T: seconds or m:ss); keeps the original
  convert X --to mp4|mov|gif|m4a|mp3|wav   a new file next to the original
  devices          displays, cameras and microphones with their numbers
  wave X [--bars N] the loudness of a recording as bars (like Voice Memos)
  thumb X / preview [--display N]   small JPEGs (used by `ul desk`)
Add --json to any action for machine-readable output.
Files: storage.root/captures/screenshots and /recordings; never overwritten (" 2" is added).
Settings: capture.audio_device and capture.camera_device (`default` = what macOS
  uses, a name, or a number from `devices`), capture.screen_audio (microphone in
  screen recordings, true), capture.system_audio (true), capture.show_clicks (true),
  capture.video_format (mov), capture.audio_format (m4a), capture.overlay
  (bottom-right, bottom-left, top-right, top-left).
Permissions: the terminal (or the app running ul) needs Screen Recording, Camera
  and Microphone in System Settings > Privacy & Security.
Dependencies: macOS screencapture; ffmpeg + ffprobe (brew install ffmpeg) for the
  camera, a non-default microphone, audio, pause, MP4, trim and convert.
`ul desk` has a Studio tab with the same controls, a preview and a player.
Examples: ul capture shot area; ul capture record --camera; ul capture stop
  ul capture record audio --duration 60; ul capture convert last --to gif
''',
    "cpp": '''Create a C++ project from the configured templates.
Usage: ul cpp <project-name> [--std 11|14|17|20|23|26] [--git]
Options: --std selects the C++ standard; --git initializes Git.
Defaults: projects.cpp.standard and projects.cpp.initialize_git.
Example: ul cpp demo --std 23 --git
''',
    "git": '''Stage, commit and push the current Git project, or run a Git action.
Usage: ul git [message]
       ul git push [message] | commit [message] | sync [message]
       ul git init [--connect SPEC] [--public] [--name NAME]
       ul git connect SPEC [--public] [--name NAME] [--url BASE] [--force]
       ul git mirror add SPEC [--name N] | list | remove NAME
       ul git token HOST | open | pr [--base BRANCH] | undo [--list | COMMIT]
Actions:
  no arguments / <message>    git add ., commit, then push (prompts "Commit message:" when
                              missing; with nothing to commit it only pushes)
  push [message]              Same as above. A branch without an upstream is published on
                              origin (-u). `ul git status` and `ul git pull` were removed:
                              use git status / git pull
  commit [message]            Stage and commit without pushing
  sync [message]              Pull with rebase, then stage, commit and push
  init                        Create a repository on branch main (refuses inside one), merge a
                              .gitignore for the detected project types (pyproject.toml or
                              requirements.txt = python, Cargo.toml = rust, CMakeLists.txt = cpp,
                              package.json = node; only missing lines are added, yours are kept
                              and .env, keys and .DS_Store are always ignored), then make the
                              first commit "Initial commit"
  connect SPEC                Set origin and push the current branch with -u
  mirror add|list|remove      Extra remotes named mirror-*; every push also pushes to them
  token HOST [--url BASE]     Save an API token: the Keychain's own hidden prompt asks for it
                              twice, so it never appears in argv (`ps`)
  open                        Open the origin page of the current branch in the browser
  pr                          Push the current branch, then open a pull request (GitHub with
                              gh when installed, otherwise the host's compare page). Commit
                              first: a branch with no commits beyond the base is refused
  undo                        Undo the last commit, keeping its changes staged
  undo --list                 Show the commits of this branch, newest first; (local) marks the
                              ones not pushed yet
  undo COMMIT                 Go back to COMMIT (a hash, or its message or a unique part of it):
                              it stays, every later commit is undone and their changes stay
                              staged. Refused when any undone commit is already on a remote
                              branch (use git revert)
Options:
  --connect SPEC     (init) run connect afterwards
  --public           Create the repository public (default: private)
  --name NAME        Repository name to create (default: the folder name); for mirror add with a
                     URL it is the mirror name (remote mirror-NAME)
  --url BASE         Server for gitea or a self-hosted gitlab, for example https://git.example.com
                     (also for token: the token is saved for that server only)
  --force            Replace an origin that points somewhere else
  --base BRANCH      (pr) target branch, default main
  --allow-secrets    Commit even when secrets or files over 50 MB are staged
  -h, --help         Show this help
SPEC is a host name (github, gitlab, codeberg, gitea: creates the repository through its API),
  a short form (gh:owner/repo, gl:..., cb:...) or a full URL or path. Short forms become SSH URLs.
Secrets guard: every commit path unstages .env and .env.* (not .env.example), .netrc, .pypirc,
  *.pem, *.key, *.p8, *.p12, *.pfx, *.jks, *.keystore, id_rsa*, id_ed25519*, id_ecdsa*, id_dsa*
  (not .pub; names compared ignoring case) and files over 50 MB, explains why and stops with
  exit 1. Fix it with .gitignore, or pass --allow-secrets. Deleting such a file is always allowed.
  init never writes through a .gitignore that is a symlink.
Mirrors: they exist only as Git remotes named mirror-* in the repository. A failing mirror is
  reported as a warning and does not fail the push when origin succeeded.
SSH: for SSH remotes of a known host connect checks the login. When it fails it offers to
  create ~/.ssh/id_ed25519, prints the public key and opens the host's key page; add the key
  and run the command again. An unknown host key is never accepted silently: check the
  fingerprint and accept it once with `ssh -T git@HOST`.
Tokens: stored in the macOS Keychain per server, service unlaw.git.<server> (for example
  unlaw.git.gitlab.com), and only ever sent to that server. Scopes: gitlab and gitea or
  codeberg need an access token that can create repositories (gitlab: api; gitea/codeberg:
  write:repository and write:user). GitHub uses `gh auth login` instead of a token.
Dependencies: git; ssh; gh (optional, for GitHub pull requests); the macOS `open` command.
Examples: ul git "Fix downloader"
  ul git init --connect github
  ul git connect gh:me/project --force
  ul git mirror add codeberg
  ul git token codeberg
  ul git token gitea --url https://git.example.com
  ul git pr --base develop
  ul git undo --list
  ul git undo "add parser"
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
    "desk": '''Kanban board, TODO list and pomodoro timer in the browser, on your Obsidian board file.
Usage: ul desk [board.md|name] [--reminders] [--port N] [--no-open]
       ul desk new <board.md|name> | path [board.md|name] | stats [board.md|name]
       ul desk pomodoro [status|start [minutes] [--card <text>]|pause|resume|stop|skip]
Actions:
  no arguments     Serve the todo board (todo.vault_path + todo.file) on 127.0.0.1
                   and open it in the browser; Ctrl+C stops the server
  board.md         Serve another Kanban Markdown file instead
  name             A bare name (no folder, no .md) is a board in desk.boards_dir
  --reminders      Start on the Apple Reminders layer (see Reminders below)
  --port N         Use exactly this port (0 = any free one); default desk.port,
                   or the next free port after it
  --no-open        Print the address without opening the browser
  new <board.md>   Create a board with To do / Doing / Done columns
  new <name>       The same in desk.boards_dir (created when missing)
  path [board.md]  Print the board's path
  stats [board.md] Focus sessions, finished tasks, streak and busiest cards
  pomodoro         Show or control the timer from the terminal; the page shows
                   the same timer, and a macOS notification marks each phase end
Page: Board (drag cards between columns, double-click to edit), Today (overdue,
  due today, in progress, next 7 days), Stats, Games, Studio, Canvas. Keys: n new
  card, / search, space start/pause timer, 1-6 views, Esc clear filters, ? keys.
Games: Tetris, Snake, Minesweeper, Space Invaders, Chomp, Dash and Ping Pong from
  `ul game`, played in the page with keyboard and mouse at easy/normal/hard.
  The page runs `ul game --stream` (the same Rust games), so best scores are
  the ones in storage.root/runtime/arcade.toml that the terminal arcade shows
  too. The page also sends key releases, so two Ping Pong players can hold
  keys at once. Leaving the tab pauses a game; closing the page ends it.
Canvas: a whiteboard in the page. Files are JSON Canvas (.canvas, jsoncanvas.org),
  so Obsidian Canvas opens them: text, file, link and group nodes plus edges.
  Freehand drawings and shapes (rectangle, ellipse, diamond, line, arrow, text)
  are stored in the same file under the extra top-level key "unlaw", which
  Obsidian ignores; every key Unlaw does not know is kept as it was. A bare
  name opens or creates <desk.canvas_dir>/<name>.canvas; any other path must
  end in .canvas. Saving replaces the file atomically and is refused (the page
  reloads) when the file changed meanwhile. A new canvas is an empty
  {"nodes": [], "edges": []}; an existing file is never overwritten on create.
  Tools: v select, h hand (or Space/middle mouse), t card, r rectangle,
  o ellipse, d diamond, l line, a arrow, p pen, x text, e eraser, g group,
  f fit; drag a card's side dot onto another card to connect them; wheel pans,
  Ctrl+wheel/pinch zooms; Cmd+Z/Shift+Cmd+Z, Cmd+C/V/D; PNG export button.
Boards: the board menu lists Apple Reminders, recent boards and the boards in
  desk.boards_dir; "New board…" asks for a name and creates it there.
Reminders: a separate layer, never mixed into your .md boards. Each Reminders
  list is a column, each open reminder a card (its notes as details). Changes
  go straight to Reminders (and iCloud): add, edit, @date sets the due date,
  drag to another column moves it to that list, done completes it, delete
  removes it, a new column creates a list. Order inside a list stays the
  Reminders app's own. Uses EventKit through osascript; the first use asks to
  allow your terminal in System Settings > Privacy & Security > Reminders.
Cards: #tag filters, @{2026-11-01} due dates (quick add: @today @tomorrow
  @сегодня @завтра @+3 @2026-11-01), [[note]] opens the note in Obsidian.
  Done cards move to todo.completed_column (or the board's Done column).
The file stays the source of truth: ul todo, the agent and Obsidian see every
  change, and edits made elsewhere appear on the page within two seconds.
Security: listens on 127.0.0.1 only and needs the random token in the printed
  address; it reads and writes only the open board, Reminders (when that
  layer is open), canvas files you open and storage.root/desk.
Settings: desk.port (8765), desk.open_browser (true), desk.sound (true),
  desk.reminders (true; false hides the layer), desk.boards_dir ("boards":
  a relative path is inside the Unlaw config directory, ~ works),
  desk.canvas_dir ("canvas", the same rules),
  desk.pomodoro.work (25), short_break (5), long_break (15), cycles (4) in minutes;
  todo.vault_path, todo.file, todo.completed_column, apps.lofi_url,
  games.difficulty (default level on the Games tab).
Storage: storage.root/desk (timer state, pomodoro.jsonl log, recent boards,
  recent-canvas.json with the last 8 canvases).
Dependencies: Python standard library; osascript for notifications and the
  Reminders layer; the Games tab needs ul built with the `game` feature.
Examples: ul desk
          ul desk ~/notes/Project.md --no-open
          ul desk new Work            (~/.config/unlaw/boards/Work.md by default)
          ul desk --reminders
          ul desk pomodoro start 50 --card "Write chapter 3"
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
