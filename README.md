# Unlaw

Unlaw — быстрая персональная CLI-утилита для macOS. Её главный механизм остаётся
простым: каталог `commands/<name>/main.py` автоматически становится командой
`ul <name>`.

## Установка и обновление

Установка последней версии из GitHub одной командой:

```bash
curl -LsSf https://raw.githubusercontent.com/SDH4114/UnLaw/main/install.sh | sh
```

Установщик использует [uv](https://docs.astral.sh/uv/) и автоматически установит
его, если команды `uv` ещё нет. Нужен Python 3.11+.

Для установки из локального checkout:

```bash
uv tool install .
```

Обновление уже установленной версии:

```bash
uv tool install --force .
```

Для разработки с мгновенным применением изменений:

```bash
uv tool install --force --editable .
```

`unlaw` и `ul` полностью эквивалентны. Сборка из исходников и первый запуск
автоматически создают пользовательскую структуру:

```text
~/.config/unlaw/
├── config.toml
├── commands/                   # все несистемные команды
│   ├── game/main.py
│   ├── todo/main.py
│   └── ...
├── data/                       # единое хранилище по умолчанию
│   ├── captures/
│   ├── runtime/
│   └── telegram/
└── templates/
    ├── commands/
    ├── python/
    ├── rust/
    ├── cpp/
    └── projects/                  # сохранённые пути и настройки запуска
```

Существующие конфиги, команды и шаблоны не перезаписываются. Старые официальные
import-обёртки автоматически заменяются полноценным кодом, а вручную изменённые
команды сохраняются. К системным относятся управление конфигурацией, диагностикой,
списками, project templates и shell-интеграцией; остальные команды создаются в
`commands/<name>/main.py` и доступны для редактирования. Каждый такой файл содержит
только код своей команды и минимальные необходимые ей настройки — код других
команд в него не подмешивается.

## Основные команды

```bash
ul                              # помощь и инициализация
ul init                         # показать пользовательские пути
ul commands                     # все команды и алиасы
ul commands --verbose           # источники и реальные пути
ul commands --json              # машинный JSON
ul templates                    # сохранённые project templates
ul list                         # сначала templates, затем commands
ul which git                    # откуда взята команда
ul create command anime         # новая команда
ul create template hearme       # сохранить текущий проект
ul venv                         # создать/активировать .venv в текущем shell
ul doctor --verbose             # полная диагностика
ul doctor --fix                 # безопасные автоматические исправления
ul doctor --json                # диагностика для скриптов
ul completion zsh               # zsh completion
ul version
```

Глобальные опции:

```bash
ul --dry-run <command> ...
ul --verbose <command> ...
ul --no-color <command> ...
ul --version
```

Неизвестная команда получает подсказку по ближайшему имени. `--dry-run` показывает
точный Python-процесс, не выполняя `main.py` из config.

## Сохранённые проекты

Project template сохраняет существующую папку и настройки её запуска. Файлы
проекта не копируются.

```bash
cd ~/giti/HearMe
ul create template hearme
```

Unlaw спросит, открыть проект через `zed` или `obsidian`, затем нужно ли открыть
ChatGPT. Если имя не передано, оно тоже запрашивается:

```text
Name of template > hearme
Open with (zed/obsidian) > zed
Add AI? (y/n) > y
```

После сохранения проект запускается из любой папки:

```bash
ul hearme
```

Команда меняет папку в текущем Zsh, открывает её в выбранном приложении и при
необходимости запускает ChatGPT. Новый терминал не создаётся. Список сохранённых
проектов доступен через `ul templates`, а объединённый список — через `ul list`.
Manifest хранится в `~/.config/unlaw/templates/projects/<name>.toml` и содержит
только абсолютный путь, приложение и флаг AI.

Для смены папки в текущем shell один раз установите интеграцию и перезапустите
Zsh:

```bash
ul doctor --fix
exec zsh
```

## Виртуальное окружение

```bash
cd ~/giti/HearMe
ul venv
```

Если `.venv` отсутствует, команда создаёт его стандартным Python `venv`, а затем
активирует в текущем Zsh. Существующее корректное `.venv` просто активируется.
Project templates не сохраняют и не активируют виртуальное окружение.

## Конфигурация

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

`reset --yes` сначала создаёт timestamped backup. Запись выполняется атомарно.
`config set` принимает TOML-значения; некавыченный текст сохраняется как строка.

Конфигурация по умолчанию:

```toml
[core]
color = true
verbose = false
command_timeout = 0
show_timing = false

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
base_url = "http://127.0.0.1:1234/v1"
model = "auto"
system_prompt = "You are a concise and practical local assistant."
temperature = 0.7
timeout = 120
```

`command_timeout = 0` отключает лимит. Python environment принимает `auto`, `uv`,
`venv` или `none`. В режиме `auto` сначала используется uv, затем стандартный
venv. Относительный `storage.root` считается от `~/.config/unlaw`; абсолютный путь
или путь с `~` позволяет перенести всё хранилище в другое место:

```bash
ul config set storage.root '"~/Documents/UnlawData"'
```

## Алиасы

Алиас — массив аргументов, а не shell-строка. Поэтому он не выполняется через
`shell=True` и безопасно дополняется пользовательскими аргументами:

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

Циклические алиасы диагностируются и не запускаются. Системные команды нельзя
перекрыть алиасом.

## Пользовательские команды

```bash
ul create command anime
```

Создаст `~/.config/unlaw/commands/anime/main.py`. Аргументы находятся в
`sys.argv[1:]`, а exit code скрипта возвращается shell. Пользовательская команда
может быть полностью изменена вручную. Автоматическое обновление никогда не
перезаписывает существующий `main.py`.

Свой шаблон новых команд:

```text
~/.config/unlaw/templates/commands/main.py
```

## Команды в config

Все команды ниже имеют вид `~/.config/unlaw/commands/<name>/main.py`. Это полные
самостоятельные исходники: во время запуска они не импортируют `unlawful` и не
зависят от внутренней структуры пакета. Системный dispatcher ищет команды только
в этой папке.

### Приложения

```bash
ul app Zed
ul app "Visual Studio Code"
```

### Git

```bash
ul git "fix parser"       # add, commit, push
ul git                    # add, спросить сообщение в терминале, commit -m, push
ul git status
ul git pull
ul git push
ul git commit "message"  # add + commit, без push
ul git sync "message"    # pull --rebase + add + commit + push
```

Без аргумента `ul git` показывает обычный однострочный prompt `Commit message:` в
текущем терминале и никогда не открывает Git-редактор. Стандартный workflow всегда
завершается `git push` и останавливается на первой ошибке.

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

Проект создаётся через Cargo. Без `--git` Cargo получает `--vcs none`, если
`projects.rust.initialize_git` не включён.

### C++

```bash
ul cpp engine
ul cpp engine --std 23
ul cpp engine --git
```

Создаётся CMake-проект. Поддерживаются стандарты 11, 14, 17, 20, 23 и 26.

Существующий каталог ни один генератор не перезаписывает.

## Obsidian Kanban

`ul todo` работает с существующим `TODO.md` внутри настроенного Obsidian vault и
сохраняет служебный блок Kanban-плагина. Номера задач отображаются командой без
аргументов:

```bash
ul todo
ul todo add "Доделать Unlaw"
ul todo add "Проверить тесты" --column "For today"
ul todo search "Unlaw"
ul todo move 3 "In progress"
ul todo done 3
ul todo open
ul todo path
```

Изменения записываются атомарно. Многострочные описания перемещаются вместе с
задачей.

## Захват экрана, видео и звука

```bash
ul capture screenshot
ul capture area
ul capture window
ul capture screen                 # фоновая запись экрана и микрофона
ul capture camera                 # камера + микрофон через ffmpeg
ul capture audio                  # микрофон через ffmpeg
ul capture screen --duration 30
ul capture devices
ul capture stop
ul capture last
```

Первый запуск может запросить системные разрешения Screen Recording, Camera,
Microphone и Accessibility. `camera_device` и `audio_device` можно подобрать по
выводу `ul capture devices`. По умолчанию все медиа находятся внутри
`storage.root/captures`; Telegram сохраняет загрузки в
`storage.root/telegram/downloads`, а runtime-файлы — в `storage.root/runtime`.

## Быстрые приложения

```bash
ul lofi                           # открыть Lofi Engine
ul zed                            # открыть текущую папку в Zed
ul netflix                        # открыть Netflix
ul tg                             # открыть Telegram
ul obsidian                       # открыть Obsidian
ul gpt                            # открыть ChatGPT
ul browser                        # открыть настроенную стартовую страницу
ul steam                          # открыть Steam
ul minecraft                      # открыть Prism Launcher
ul music
ul music "Killer Queen"           # поиск и запуск первого результата в Spotify
ul work                            # Lofi Engine + текущая папка в Zed
ul yt                              # открыть главную страницу YouTube
ul yt "omarchy linux"             # поиск YouTube в браузере
```

Для автоматического запуска результата Spotify терминалу понадобится разрешение
Accessibility.

Стартовая страница `ul browser` настраивается через config:

```bash
ul config set apps.browser_url '"https://duckduckgo.com/"'
```

## Unlaw Arcade

```bash
ul game
ul game tetris
ul game snake easy
ul game minesweeper normal
ul game invaders hard
```

Меню и все четыре игры занимают терминальное окно целиком. После выбора игры меню
предлагает `easy`, `normal` или `hard`; для прямого запуска сложность передаётся
вторым аргументом. Значение по умолчанию меняется через
`ul config set games.difficulty '"hard"'`. Используются стрелки или WASD,
`Space` для действия и `q` для выхода.

## Telegram

```bash
ul tg                              # открыть приложение Telegram
ul tg setup                        # токен скрыто сохраняется в macOS Keychain
ul tg "Сообщение из терминала"
ul tg send report.pdf
ul tg photo screenshot.png
ul tg video demo.mov
ul tg capture                       # последний screenshot или recording Unlaw
cat notes.txt | ul tg
ul tg last
ul tg download
ul tg status
```

Bot token никогда не записывается в `config.toml` или Git. Для личного чата
сначала напишите боту, затем укажите его `chat_id` во время `setup`.

## Локальный чат LM Studio

Загрузите модель в LM Studio и включите Local Server. После этого:

```bash
ul lm                              # диалог с сохранением контекста сессии
ul lm "объясни этот код"
cat error.log | ul lm
ul lm models
ul lm open
ul lm start                         # управление Local Server через LM Studio CLI
ul lm status
ul lm stop
```

Unlaw принимает только loopback-адрес LM Studio (`localhost`, `127.0.0.1` или
`::1`) и не переключается на облачные модели. Если Local Server выключен,
`ul lm` попытается запустить его через официальный `lms` CLI и повторит запрос.

## Самовосстановление

```bash
ul doctor --verbose
ul doctor --json
ul doctor --fix
```

`--fix` материализует новые настройки, создаёт каталоги внутри `storage.root`,
переносит старый runtime-log, добавляет `~/.local/bin` перед `/usr/bin` и
устанавливает управляемую Zsh-функцию в `~/.zshrc`. Она нужна для `ul <template>`
и `ul venv`, потому что только функция текущего shell может выполнить постоянный
`cd` или `source`. После исправления запустите `exec zsh`.

## Файловые шаблоны проектов

Файлы из `~/.config/unlaw/templates/python`, `rust` и `cpp` накладываются на
стандартный проект. UTF-8-файлы поддерживают placeholders:

```text
{{project_name}}
{{cpp_standard}}
```

Бинарные файлы копируются без изменений. Placeholder работает и в имени файла
или каталога.

## macOS Harness

Harness остаётся необязательным backend:

```bash
ul mac see Spotify
ul mac key Spotify cmd+k
ul mac type Telegram "hello"
ul mac click Spotify 500 300
```

Пользовательские команды могут использовать тот же мост:

```python
from unlawful import harness

harness.see("Spotify")
harness.key("Spotify", "cmd+k")
harness.type_text("Telegram", "hello")
harness.click("Spotify", 500, 300)
```

Исполняемый файл и timeout задаются в секции `[mac]`. `doctor` проверяет Harness
без запроса новых macOS-разрешений.

## Zsh completion

```bash
mkdir -p ~/.zfunc
ul completion zsh > ~/.zfunc/_ul
```

Добавьте до `compinit` в `~/.zshrc`:

```zsh
fpath=(~/.zfunc $fpath)
autoload -Uz compinit && compinit
```

## Разработка

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests
uv build
```

Unlaw 2.1.3 остаётся local-first: команды не используют shell-строки, LM Studio
принимает только loopback endpoint, а секрет Telegram хранится в macOS Keychain.
Внешние приложения и разрешения остаются явно видимыми через `ul doctor`.
