# Unlaw

Unlaw — быстрая персональная CLI-утилита для macOS. Её главный механизм остаётся
простым: каталог `commands/<name>/main.py` автоматически становится командой
`ul <name>`.

## Установка и обновление

Установка последней версии из GitHub одной командой:

```bash
curl -LsSf https://raw.githubusercontent.com/SDH4114/UnLaw/main/install.sh | sh
```

Ядро Unlaw (dispatcher, конфигурация, системные команды, completion, doctor)
написано на Rust и собирается через `cargo`; установщик поставит Rust через
rustup, если его нет. Команды в `commands/` остаются обычными Python-файлами,
поэтому нужен Python 3.11+ (`brew install python`). Бинарники `ul` и `unlaw`
ставятся в `~/.local/bin`; старая uv-версия Unlaw удаляется автоматически.

Обновление до последней версии с GitHub:

```bash
ul update --check          # сравнить версию и коммит с GitHub, ничего не ставя
ul update                  # переустановить из main (cargo install --locked --force)
ul update --tag v2.2.0     # конкретный релиз; --branch <name> — ветка
```

`ul --version` показывает версию и коммит сборки (`Unlaw 3.0.0 (dd061d1)`), поэтому
обновление видно даже без смены номера версии. `ul update` ставит новый бинарник туда же, где лежит текущий `ul` (по умолчанию
`~/.local/bin`). Конфигурация, данные и изменённые вручную команды не трогаются;
неизменённые стандартные команды обновятся при следующем запуске. Нужны `cargo`
и Python 3.11+, для `--check` — `curl`. `UNLAW_UPDATE_REPOSITORY` задаёт форк.

Из локального checkout (установка и обновление — одна и та же команда):

```bash
cargo install --path . --root ~/.local --force
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
ul commands --describe          # однострочные описания (без запуска команд)
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
ul update --check              # есть ли новая версия на GitHub
```

Глобальные опции:

```bash
ul --dry-run <command> ...
ul --verbose <command> ...
ul --no-color <command> ...
ul --version
```

Неизвестная команда получает подсказку по ближайшему имени. `--dry-run` показывает
точный процесс команды (интерпретатор и путь), не запуская её.

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

Если `.venv` отсутствует, команда создаёт его через `python -m venv` (интерпретатор из
`core.python`), а затем
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
Комментарии, порядок и неизвестные ключи в `config.toml` при записи сохраняются.

Конфигурация по умолчанию:

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
level = "max"                   # 0–9 или store, fastest, fast, normal, max, ultra
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

Команда — это папка с одной точкой входа. Проверяются по порядку:

| Файл | Чем запускается |
|---|---|
| `main.py` | Python 3.11+ из `core.python` (`auto` — самый новый `python3.x` в PATH) |
| `main.sh` | `/bin/sh`, или напрямую по shebang, если файл исполняемый |
| `main.js` | `node` |
| `main` | напрямую; любой исполняемый файл, например собранный Rust/C++ бинарник |

Никакой SDK не нужен: Unlaw передаёт команде переменные окружения.

| Переменная | Значение |
|---|---|
| `UNLAW_COMMAND` | имя команды |
| `UNLAW_COMMAND_DIR` | папка команды |
| `UNLAW_CONFIG_DIR` | папка конфигурации Unlaw (`config.toml`) |
| `UNLAW_STORAGE` | итоговый путь `storage.root` для файлов команды |

```sh
#!/bin/sh
# Show today's notes folder.
mkdir -p "$UNLAW_STORAGE/notes" && open "$UNLAW_STORAGE/notes"
```

Описание для `ul commands --describe` и Zsh completion читается без запуска
команды: первая строка `help.txt` в папке команды, иначе первая строка docstring
`main.py`, иначе первый комментарий `#`/`//` у других скриптов. `--help` внутри
самой команды по-прежнему обязателен.

Свой шаблон новых команд:

```text
~/.config/unlaw/templates/commands/main.py
~/.config/unlaw/templates/commands/rust/      # Cargo.toml + src/, {{command_name}} заменяется
```

### Команды на Rust

```bash
ul create command fast --lang rust
ul fast hello
```

Создаёт Cargo-проект в `~/.config/unlaw/commands/fast/` и сразу собирает его.
Правите `src/main.rs` и просто запускаете `ul fast`: Unlaw сам пересобирает
команду, когда `src/`, `Cargo.toml` или `Cargo.lock` новее бинарника. Описание
для `ul commands --describe` берётся из `description` в `Cargo.toml`. Нужен
`cargo`; зависимости добавляются как в любом Rust-проекте (`cargo add` в папке
команды).

### Встроенные Rust-команды

`ul zip`, `ul game` и `ul lm` встроены в ядро. Порядок поиска: системные команды →
`commands/<name>/` → встроенные, поэтому своя папка `commands/zip` по-прежнему
перекрывает встроенный `zip`. Нетронутые старые `commands/zip/main.py`,
`commands/game/main.py` и `commands/lm/main.py` (клиент LM Studio из 3.0)
удаляются при обновлении автоматически; изменённые вручную остаются и продолжают
работать вместо встроенных.

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
ul yt download "https://youtu.be/VIDEO_ID"                 # скачать MOV
ul yt download "https://youtu.be/VIDEO_ID" --format mp4    # MP4
ul yt download "https://youtu.be/VIDEO_ID" --format raw    # исходный контейнер/кодеки
ul yt download "https://youtu.be/VIDEO_ID" --audio         # MP3
ul yt download "https://youtu.be/VIDEO_ID" --quality 1080  # максимум 1080p
ul yt download "https://youtu.be/VIDEO_ID" --output ~/Downloads
ul yt --help                      # все варианты и примеры
```

Для автоматического запуска результата Spotify терминалу понадобится разрешение
Accessibility.

Стартовая страница `ul browser` настраивается через config:

```bash
ul config set apps.browser_url '"https://duckduckgo.com/"'
```

## Архивы

`ul zip` сжимает файлы и папки и распаковывает почти любой архив. Без действия
команда сама понимает, что делать: архивы распаковываются, остальное сжимается.

```bash
ul zip project                     # project.zip рядом с папкой, максимальное сжатие
ul zip a.png b.png notes/          # несколько путей → ./Archive.zip
ul zip project -f 7z               # сильнее всего (LZMA2)
ul zip project -f rar              # RAR5 с recovery record (нужен rar)
ul zip project -f zst --fast       # tar.zst: быстро и плотно, для бэкапов
ul zip project -f 7z -9            # уровень 0–9 (или --store … --ultra)
ul zip project -p -f 7z            # пароль AES-256, имена файлов тоже скрыты
ul zip project -o ~/Desktop/pack.7z  # формат берётся из расширения
ul zip project.zip                 # распаковать рядом
ul zip x backup.rar -o ~/Downloads # распаковать в папку
ul zip x pack.zip --here           # содержимое прямо в папку назначения
ul zip ls backup.7z                # содержимое
ul zip test backup.7z              # проверка целостности
```

Создаёт `zip` (по умолчанию), `7z`, `rar`, `tar.zst`, `tar.xz`, `tar.gz`; читает
также `rar`, `gz`, `bz2`, `xz`, `zst`, `cab`, `iso`, `cpio`, `xar`. Мусор macOS
(`.DS_Store`, `._*`, `__MACOSX`) не попадает в архивы; `--keep-junk` оставляет его.
Архив из одного элемента распаковывается как этот элемент, иначе — в папку с
именем архива. Ничего не перезаписывается: добавляется суффикс ` 2`. Пароль
запрашивается в терминале и не передаётся в аргументах процесса.

Уровни идут по шкале 7-Zip: `0` store, `1` fastest, `3` fast, `5` normal,
`7` max (по умолчанию), `9` ultra. Каждый уровень переводится в лучшие настройки
формата (`-mx`, `rar -m0…5`, `xz -0…9`, `zstd -1…19` и `--ultra -22`). Замер на
68 МБ кода и бинарников: 7z `1/5/7/9` даёт 16.7/14.1/13.8/13.8 МБ, zip — 20.0/19.0/18.7/18.6 МБ,
Finder — 20.3 МБ. Если уровень не указан и ≥90% входа уже сжатые медиа (jpg,
heic, mp4, zip…), используется уровень 1: на 236 МБ HEIC уровень 9 давал выигрыш
0.01% за 37 с вместо 3 с.

Зависимости: `brew install sevenzip zstd`; для создания `.rar` — `brew install --cask rar`.
Без 7-Zip `zip` создаётся системным `zip`, а распаковка идёт через `bsdtar`.

## Unlaw Arcade

```bash
ul game                       # меню (мышь или клавиатура)
ul game tetris
ul game snake easy
ul game minesweeper normal
ul game invaders hard
```

Игры встроены в Rust-ядро и рассчитаны на клавиатуру и мышь. Внизу каждого экрана —
подсказка управления, `P` ставит паузу, `Esc`/`Q` выходит. После конца игры
Enter или клик — играть заново, Esc — в меню. Лучшие результаты хранятся в
`storage.root/runtime/arcade.toml` и видны в меню.

| Игра | Как в оригинале | Мышь |
|---|---|---|
| Tetris | мешок из 7 фигур, очередь Next, Hold (`C`), тень, вращение с отскоками от стен (`↑`/`X`, `Z`), задержка фиксации, уровень каждые 10 линий, guideline-гравитация, комбо и back-to-back | фигура следует за курсором, клик — сброс, правый клик — поворот |
| Snake | клетки шириной 2 символа, буфер поворотов, ускорение с ростом, бонус ★ на время | клик — поворот в сторону клика |
| Minesweeper | Beginner 9×9/10, Intermediate 16×16/40, Expert 30×16/99, первый клик безопасен, аккорд по цифре, классические цвета, таймер | левый — открыть или аккорд, правый — флажок |
| Space Invaders | строй 5×11, три вида пришельцев, ускорение по мере потерь, стреляют только нижние, одна ваша пуля на экране, укрытия, НЛО, жизни и волны, бонусная жизнь за 1500 | пушка следует за курсором, клик — выстрел |

Сложность: `easy` — медленный старт и подсказки (у Тетриса тень и 3 фигуры в Next,
змейка проходит сквозь стены, 5 жизней в Invaders); `normal` — классика; `hard` —
по-настоящему сложно: Тетрис стартует с 12 уровня без тени и Hold, с растущим снизу
мусором, у змейки препятствия и двойной рост, Сапёр — Expert без гарантированного
открытия, пришельцы стреляют непрерывно и у вас 2 жизни. По умолчанию:
`ul config set games.difficulty hard`.

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

## Локальные модели (MLX)

`ul lm` — свой движок локальных моделей на Apple Silicon вместо LM Studio и
Ollama: скачивает любые модели с Hugging Face и запускает их через MLX —
чат, зрение, эмбеддинги, распознавание и синтез речи, музыку, картинки и видео,
в терминале и через API, совместимый с OpenAI (как LM Studio) и Ollama.

```bash
ul lm search qwen3 --mlx                       # поиск на Hugging Face
ul lm pull prism-ml/Ternary-Bonsai-2-9B-mlx-2bit
ul lm use Bonsai-2-9B                          # модель по умолчанию для своего типа
ul lm                                          # диалог: /model /image /clear /save /think
ul lm "объясни этот код" < main.rs             # разовый ответ потоком
ul lm -i photo.jpg "что на фото?"              # vision-модели
ul lm image "бонсай в утреннем свете" --open   # картинки (mflux, Bonsai Image)
ul lm video "волны на закате" --seconds 2      # видео (mlx-video: Wan 2.x, LTX-2)
ul lm speak "Привет!" -m Qwen3-TTS --play      # синтез речи (mlx-audio)
ul lm music "lo-fi piano" --lyrics song.txt    # музыка (MiniMax Music 3)
ul lm transcribe voice.m4a --srt               # речь в текст; любой формат, даже .mov
ul lm embed "текст для поиска"                 # эмбеддинги (JSON)
ul lm convert Qwen/Qwen3-4B --bits 4           # обычная модель → MLX 4-bit
ul lm list | info <model> | use <model>
ul lm rm [<model>...]                          # стереть модели с Mac (без имени — выбор из списка)
ul lm clean                                    # недокачанное, ничейные файлы, кеш загрузок
ul lm open [<model>|models|generated|converted|engine|logs]   # показать папку в Finder
ul lm where <...>                              # то же, но напечатать путь
ul lm serve [--ollama] [--cors]                # API на 127.0.0.1:1234 до Ctrl-C
ul lm import-lmstudio [--dry-run]              # перенести загрузки LM Studio
ul lm doctor [--repair]
```

Подключение своих приложений после `ul lm serve`:

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:1234/v1", api_key="local")
reply = client.chat.completions.create(model="Bonsai-2-9B",
                                       messages=[{"role": "user", "content": "привет"}])
image = client.images.generate(model="bonsai-image", prompt="лиса в снегу", size="512x512")
speech = client.audio.speech.create(model="Qwen3-TTS", voice="serena", input="Привет!")
```

OpenAI API: `/v1/models`, `/v1/chat/completions` (стриминг, tools, картинки,
`reasoning_content`), `/v1/completions`, `/v1/embeddings`,
`/v1/audio/transcriptions` (json, text, srt, verbose_json), `/v1/audio/speech`,
`/v1/images/generations`, `/v1/videos` (задача; `GET /v1/videos/{id}` и
`/content`). Ollama API: `/api/tags`, `/api/chat`, `/api/generate`,
`/api/embed`, `/api/show`, `/api/ps`; `--ollama` дополнительно слушает `:11434`.
Сервер отвечает только на `127.0.0.1`, отклоняет чужие имена хоста (защита от
DNS rebinding), не отдаёт CORS без `--cors` и не читает локальные файлы по
просьбе API. Поле `model` принимает `owner/repo`, имя репозитория или его часть;
без него используется модель по умолчанию для этого типа (`lm.model`,
`lm.image_model`, `lm.tts_model`...). Если сервер запущен, `ul lm` в терминале
работает через него и использует уже загруженные модели.

Модели хранятся в стандартном кеше Hugging Face (`HF_HUB_CACHE`,
`HF_HOME/hub` или `~/.cache/huggingface/hub`) и видны `hf`, transformers и
другим инструментам. `ul lm rm` и `ul lm clean` удаляют через сам huggingface_hub (как `hf cache rm` / `prune`), поэтому файлы, общие с другими моделями и датасетами, не пострадают; модель, выбранная по умолчанию, при удалении сбрасывается на auto. Тип модели
определяется по карточке и файлам: text, vision, embedding, stt, tts, music,
image, video. GGUF тоже запускается: чат, зрение (с файлом `mmproj`) и
эмбеддинги — через закреплённую официальную сборку llama.cpp (скачивается сама,
16 МБ, проверяется по sha256), распознавание речи (Parakeet, Whisper GGUF) —
через transcribe.cpp. Из нескольких квантований берётся Q4_K_M (иначе Q5_K_M,
Q6_K, Q8_0); `ul lm info` показывает какое. Если есть MLX- и GGUF-версия одной
модели, по короткому имени выбирается MLX. В репозитории с десятком GGUF-файлов
`pull` попросит выбрать один.
Bonsai (1-bit, Ternary, Bonsai-2) работает без их лаунчера; Bonsai Image —
через библиотеку PrismML mflux в отдельном движке.

Движки ставятся сами при первом использовании в `storage.root/runtime/lm-engine`
через uv на Python 3.13: основной (около 1.2 ГБ: mlx, mlx-lm, mlx-vlm,
mlx-embeddings, mlx-audio, mlx-whisper, mlx-video), картинки (mflux) и Bonsai
Image — по 1.5 ГБ, только когда понадобятся. Чат, вспомогательные модели,
картинки и видео работают в разных процессах: эмбеддинги не ждут длинного ответа,
падение одного не задевает остальные. Модель больше 75% RAM отклоняется до
загрузки; модели выгружаются после `lm.idle_minutes` простоя. Параметры
сэмплинга по умолчанию берутся из `generation_config.json` модели (рекомендации
авторов), затем из `lm.temperature`. Облачного запасного варианта нет.

## Самовосстановление

```bash
ul doctor --verbose
ul doctor --json
ul doctor --fix
```

`--fix` дописывает недостающие настройки (комментарии в `config.toml` сохраняются), создаёт каталоги внутри `storage.root`,
переносит старый runtime-log, добавляет папку бинарника `ul` перед `/usr/bin` и
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

Пользовательские команды могут вызывать тот же мост через CLI:

```python
import subprocess

subprocess.run(["ul", "mac", "key", "Spotify", "cmd+k"], check=False)
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

Completion показывает команды с описаниями, затем подкоманды `config`, `create`,
`doctor` и т.д. Его обслуживает Rust-ядро (`ul _complete`), Python при этом не
запускается.

## Разработка

```text
Cargo.toml, rust/      Rust-ядро: dispatcher, config, system commands, doctor
rust/build.rs          встраивает данные из Python через rust/gen_assets.py
src/unlawful/          исходники seeded-команд, их справка и DEFAULT_CONFIG
tests/                 Python-тесты команд и black-box тесты бинарника
```

Seeded-команды, их справка, legacy-хеши и конфигурация по умолчанию определены
один раз в `src/unlawful`; `cargo build` экспортирует их в бинарник, поэтому
сборке нужен Python 3.11+. Версия в `Cargo.toml` обязана совпадать с
`src/unlawful/__init__.py` — иначе сборка остановится.

```bash
cargo test
cargo clippy --all-targets
python3 -m unittest discover -s tests -v   # сам собирает target/debug/ul
cargo build --release
```

Unlaw 3 остаётся local-first: команды не используют shell-строки, `ul lm`
слушает только loopback и не обращается к облачным моделям, а секрет Telegram
хранится в macOS Keychain.
Внешние приложения и разрешения остаются явно видимыми через `ul doctor`.

### Справка команд и скачивание YouTube

Все встроенные команды поддерживают `ul <команда> --help`, `-h` и `ul help <команда>`. Справка описывает назначение, действия, параметры и примеры без запуска команды. Новые команды из `ul create command <name>` также имеют обработчик справки; при изменении команды обновляйте его текст.

Для скачивания установите внешние инструменты: `brew install yt-dlp ffmpeg deno`. Unlaw остаётся пакетом без Python-зависимостей. Видео по умолчанию сохраняется в MOV со звуком; `--format mp4` выбирает MP4, `--format raw` сохраняет исходный контейнер и кодеки YouTube (в том числе WebM), без перекодирования. Это не камерный RAW. Конвертация в MOV/MP4 использует H.264/AAC, когда формат требуется изменить, и может занять время. `--quality` задаёт верхнюю границу высоты (если такого качества нет, выбирается ниже), `--audio` сохраняет MP3 и не совмещается с `--quality` или `--format`. По умолчанию используется `storage.root/youtube`; `--output` задаёт другую папку. Скачивается одно видео, включая ссылки Shorts и видео из плейлиста; ссылки на целые плейлисты и каналы отклоняются. Существующие файлы не перезаписываются.

### Субтитры YouTube и полный комплект

```bash
ul yt download "https://youtu.be/VIDEO_ID" --sub           # только субтитры .md, язык оригинала
ul yt download "https://youtu.be/VIDEO_ID" --sub-lang      # то же самое
ul yt download "https://youtu.be/VIDEO_ID" --sub-lang ru   # выбрать русский
ul yt download "https://youtu.be/VIDEO_ID" --full          # MOV со звуком + отдельный MP3 + .md
ul yt download "https://youtu.be/VIDEO_ID" --full --sub-lang en --format mp4 --quality 1080
```

`--sub-lang` без значения выбирает оригинал; сам этот флаг включает режим субтитров, кроме случая `--full`. Неизвестный код выводит все доступные языки и завершает команду до скачивания медиа. Авторские субтитры приоритетнее автоматических на выбранном языке. Когда язык оригинала определить невозможно, команда явно сообщает о выбранном доступном языке. `.md` начинается со ссылки на видео, далее идут название, язык, источник субтитров и текст. Время, служебная разметка и перекрывающиеся повторы убираются; текст не пересказывается. Автосубтитры могут содержать ошибки распознавания. Для субтитров достаточно `yt-dlp`, `ffmpeg` не нужен.

`--full` сохраняет файлы рядом в `storage.root/youtube` или папке `--output`: видео выбранного формата со звуком, отдельный `.mp3`, субтитры `.<язык>.md`. Видео с YouTube скачивается один раз; аудио извлекается локально. Режимы `--sub`, `--audio`, `--full` взаимоисключающие. Если субтитров нет или их загрузка не удалась, `--full` сохраняет медиа, сообщает о неполном результате и возвращает ненулевой код. Существующие файлы сохраняются, временные файлы удаляются.

## Лицензия

Copyright (C) 2026 Haos

Unlaw — свободная программа: её можно распространять и изменять на условиях
GNU General Public License версии 3 или (по вашему выбору) любой более поздней
версии, опубликованной Free Software Foundation (`GPL-3.0-or-later`). Программа
распространяется без каких-либо гарантий. Полный текст — в файле [LICENSE](LICENSE).
