# Unlaw: план развития

Текущая версия: 3.4.0. `ul re` убран из плана.

## Порядок

| # | Что | Объём | Статус |
|---|-----|-------|--------|
| 1 | `ul skills` — skills для внешних агентов | 1–2 дня | готово (3.3.0) |
| 2 | `ul agent` — локальный агент (harness): терминал + Telegram, файлы, расписание, дела | по фазам | фазы 1–4 готовы (3.3.0), фаза 5 дальше |
| 3 | `ule` — свой редактор на Rust | неделя на MVP, 2–3 на LSP/tree-sitter | дальше |
| 4 | `ul lm laya` — Laya как быстрый слой решений | 2–3 дня | последним |

Skills первыми: дёшево, и их реестр команд становится набором tools агента. Laya — надстройка над агентом. Редактор независим, можно параллельно.

---

## 1. `ul skills`

Цель: любой агент (Claude Code, Codex, другие) легко пользуется `ul`.

- `ul skills install [--project] [--claude] [--path <dir>]`, `ul skills list|show|remove`.
- По умолчанию ставится в `~/.agents/skills/unlaw/`; `--project` — в `./.agents/skills/unlaw/`. Codex читает `.agents/skills` (по сторонним источникам, сверить с официальной документацией).
- Claude Code читает только `~/.claude/skills`; `--claude` создаёт symlink `~/.claude/skills/unlaw → ~/.agents/skills/unlaw`. Одна копия, видят все.
- Формат: папка с `SKILL.md` (YAML frontmatter `name`, `description` + Markdown).
- **Устойчивость к росту функционала:** `SKILL.md` не перечисляет команды жёстко, а учит агента находить их на лету: `ul commands --describe` → `ul <cmd> --help`. Новые команды и флаги работают без переустановки. `reference/<cmd>.md` — кэш-снимок help, помечен версией и хэшем списка команд, пересобирается при `ul update`, `ul create command` и `ul skills install`.
- Описания команд берутся без их запуска (`help.txt`, docstring), как в `ul commands --describe`.
- `remove` удаляет только то, что создал `install`; в skill не попадают личные данные (chat id, пути vault).

---

## 2. `ul agent` (harness)

Цель: локальная модель из `ul lm` как личный агент. Говоришь с ней в терминале и Telegram; она читает файлы, меняет и удаляет их (только с разрешения), запускает задачи по расписанию и ведёт дела на сегодня.

**Устройство:** seeded Python-команда `agent` (stdlib). Python, потому что Telegram/HTTPS уже есть на Python, а в Rust нет TLS. Модель — OpenAI API `ul lm serve` на 127.0.0.1 (tool calling уже поддерживается). Если сервер не запущен, агент поднимает его сам.

**Запуск (3.4.0):** три команды. `ula` — консоль в стиле pi (стрим, вызовы инструментов, Esc, /команды, `!cmd`, `@file`, `-p/-c/-m`), `ula server` — Telegram и расписание, `ula setup` — мастер (модель с проверкой инструментов, токен в `~/.config/unlaw/.env`, id: добавить/`-id`/Enter, сводка, папки, фоновый режим вкл/выкл).

**Режимы:**
- `ula` — консоль; `ula -p "задача"` — один ответ; `ula -c` — продолжить разговор.
- `ula server` — Telegram и расписание в этом терминале; фоновый режим включается в `ula setup` (launchd).
- Дела и план — словами в чате или `/today`, `/plan`, `/unschedule <id>` в консоли.

**Tools:**
- без подтверждения: `list_dir`, `read_file`, `search`, `stat` — только внутри `agent.roots`;
- с подтверждением: `write_file`, `edit_file` (с diff), `move`, `delete` (в Корзину macOS, не `rm`), `run` (shell);
- `ul_command` — команды ul по allowlist;
- `todo_list` / `todo_add` / `todo_done` — через существующий `ul todo` (Obsidian `TODO.md`, одна точка правды);
- `schedule` / `unschedule` / `list_schedule`.

**Подтверждение:** терминал `[y/N]`; Telegram — inline-кнопки владельцу с точной командой или diff. Таймаут = отказ. Задачи по расписанию тоже ждут кнопку.

**Расписание:** `storage.root/agent/schedule.json`: `once`, `daily`, `weekly`, `every <N>m|h|d`. Демон в срок запускает промпт и шлёт результат в Telegram.

**Дела:** `/today` (и инструмент `today`) = открытые пункты `ul todo` + задачи расписания на сегодня. Утренняя сводка в Telegram во время `agent.digest_time` (пусто = выключено).

**Доступ и безопасность:**
- `agent.allowed_ids` — только им бот отвечает, остальным молчит.
- Владелец — `telegram.chat_id`, полный доступ. Остальные id по умолчанию только чат; `agent.users.<id>` = `chat|read|full` расширяет права.
- Всегда deny: `~/.ssh`, `~/Library/Keychains`, `.env*`, конфиг unlaw.
- `storage.root/agent/audit.log` — каждое действие с id отправителя.
- Содержимое файлов — данные, а не инструкции; ничто из файла или ответа модели не отключает подтверждения.
- `ul lm` остаётся на 127.0.0.1, агент портов не открывает.

**Фазы:**
1. Терминал + read-only tools.
2. Telegram + allowlist, отправка файлов, голосовые → транскрипция.
3. Write/delete/run с подтверждением.
4. Расписание, дела, демон launchd, утренняя сводка.
5. Память о пользователе и поиск по vault.

**Gotchas:** маленькие модели плохо держат длинные цепочки tool calling — лимит шагов `agent.max_steps` и список проверенных моделей. Несколько id одновременно → очередь, модель одна. Тесты без сети: фейковый Telegram-сервер и фейковый worker.

---

## 3. `ule` — редактор

Цель: заменить nvim. Просто, удобно, но не менее функционально. И учёба, и инструмент. Ориентир — Helix (всё встроено, без системы плагинов) с vim-движениями.

- **Имя:** `ule` (ul + edit): три буквы, набирается как `ul`, свободно в PATH и Homebrew. Плюс `ul edit <file>`.
- **Где:** отдельный пакет в workspace (`ule/`), чтобы тяжёлые deps (ropey, tree-sitter) не попадали в ядро `ul`. `ul update` и `install.sh` ставят оба пакета.
- **Конфиги через него:** общая функция открытия редактора. Порядок: `core.editor` → `ule` → `$VISUAL`/`$EDITOR` → `open -t`. Через неё работают `ul config edit`, `ul todo edit`, `ul create command`.
- **Неделя 1 (MVP):** rope-буфер; normal/insert/visual/command; операторы + motions, счётчики, `.`; undo/redo; поиск/замена; несколько буферов; атомарное сохранение + swap-файл; headless-тесты.
- **Недели 2–3:** tree-sitter (Rust, Python, TOML, Markdown, C++), LSP по stdio, fuzzy finder, сплиты, keymaps в TOML.
- **Потом:** выделение → `ul <cmd>`, `ul lm` в редакторе, проверка `config.toml` при сохранении, просмотр diff агента, функции своего nvim-плагина.
- **Готово, когда:** неделя работы над реальными проектами без nvim.

---

## 4. `ul lm laya`

[Laya](https://huggingface.co/convaiinnovations/laya) (ConvAI, Apache 2.0) — encoder-классификатор, не чат: текст + типизированные вопросы (`choice`, да/нет, `score`) → калиброванные вероятности за ~33 мс. В ul — быстрый роутер и guardrail перед LLM в агенте.

- `ul lm laya` без установки показывает размер и спрашивает `[y/N]`; без согласия ничего не качается (`--yes` для скриптов).
- Размеры (по файлам HF-репо), качается только выбранный чекпоинт:
  - multilingual (по умолчанию, русский): ~678 MB;
  - english: ~846 MB;
  - typed-decisions: ~846 MB;
  - плюс отдельный venv с torch — замерить при первой сборке.
- `ul lm laya "<текст>" --choice name=a,b,c --yes name --score name=low,mid,high [--json]`, `ul lm laya rm`, `POST /v1/decide`.
- В агенте: `agent.router = "laya"`, если установлена.
- Оговорки: zero-shot точность скромная (0.362 базовая, 0.766 после fine-tune на их бенчмарке) — пороги уверенности, сложное отдаём LLM. torch, а не MLX. Проект молодой — пиннить версию.

---

## Общее

- Каждая новая команда: `--help`/`-h` до побочных эффектов, doctor-проверки, тесты без сети.
- Валидация конфига одинаковая в `rust/src/config.rs` и `src/unlawful/config.py`.
- Обновлять AGENTS.md при появлении `skills`, `agent`, `ule`, движка Laya.
