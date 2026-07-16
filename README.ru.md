<div align="center">

# autograph

<img src=".github/assets/banner.webp" alt="autograph — типизированный граф памяти для Obsidian" width="100%">

**Память как код для AI-агентов, пишущих в Obsidian-vault.**
Одна `schema.json` держит vault типизированным, связанным, без дублей и с забыванием — сама.

[![skills.sh](https://skills.sh/b/smixs/autograph)](https://skills.sh/smixs/autograph)
[![Claude Code plugin](https://img.shields.io/badge/Claude_Code-plugin-4dc9f6?style=flat&labelColor=0a0e14)](https://code.claude.com/docs/en/plugins)
[![Tests](https://img.shields.io/badge/tests-256%2F256-b0e8ff?style=flat&labelColor=0a0e14)](./skills/autograph/tests)
[![License](https://img.shields.io/badge/license-MIT-ffffff?style=flat&labelColor=0a0e14)](./LICENSE)

[English](./README.md) · Русский

</div>

---

**autograph** — движок памяти для [Obsidian](https://obsidian.md)-vault, в который пишут AI-агенты. Таксономию задаёшь один раз в `schema.json`: типы карточек, папки, допустимые статусы, скорость забывания для каждого вида знаний. Дальше движок сам раскладывает новые карточки, чинит wiki-ссылки, сливает дубли сущностей, забывает то, что перестал трогать, и считает health-скор. Это обычный Markdown, который принадлежит тебе, а не хостинговая база — те же файлы остаются человекочитаемым вторым мозгом. Скрипты на голом Python stdlib, ноль внешних зависимостей, 256 тестов.

Проблема, которую он решает: always-on агент каждый день сыпет заметки в vault — голос, встречи, контакты, идеи. Через месяц там 800 файлов, битые ссылки, три карточки на одного человека и непонятно, `status: ongoing` — это то же, что `status: active`, или нет. autograph держит это в порядке без ручного досмотра.

## Установка

Одна команда ставит autograph в того агента, которым ты пользуешься, — папку он выберет сам:

```bash
npx skills add smixs/autograph
```

Это [skills.sh](https://skills.sh) — открытый реестр Agent Skills. Работает с Claude Code, Codex, Cursor, OpenClaw, Hermes и 70+ другими.

**Claude Code как плагин** (read-only, всегда актуальный):

```
/plugin marketplace add smixs/autograph
/plugin install autograph@autograph
```

Или из шелла: `claude plugin marketplace add smixs/autograph && claude plugin install autograph@autograph`.

## Быстрый старт

```bash
# Собрать схему для пустого или хаотичного vault (интерактивно)
/autograph:research /path/to/vault

# Ежедневный health-чек
uv run skills/autograph/scripts/graph.py health /path/to/vault
#  health: 94/100 · broken_links: 0 · orphans: 2 · desc_coverage: 88%

# Пересчитать relevance + tier для всех карточек
uv run skills/autograph/scripts/engine.py decay /path/to/vault

# Перегенерировать Map-of-Content индексы
uv run skills/autograph/scripts/moc.py generate /path/to/vault
```

Полный 10-фазный bootstrap (discover → schema → enforce → dedup → link → MOC → verify) — в [`bootstrap-workflow.md`](./skills/autograph/references/bootstrap-workflow.md).

## Чем отличается

- **Твои файлы, твой формат.** Память — это Markdown в твоём vault: без API, без чужой базы, без лок-ина. Открывается в Obsidian, ищется grep'ом, бэкапится через git.
- **Обновляет на месте, а не плодит дубли.** Новый факт противоречит старому (сменил работу, проект переименован)? autograph переписывает текущее значение, а старое уносит в append-only секцию `## History` — двух конфликтующих карточек не остаётся. Одна сущность под двумя именами файлов сливается по идентичности, не только по точному совпадению имени.
- **Забывает осознанно.** Модель забывания Эббингауза понижает карточки, которые ты перестал трогать, — рабочий набор остаётся маленьким, важное — «тёплым».
- **Схема как код, ноль захардкоженных доменов.** Каждый тип, папка, статус и скорость распада читаются из `schema.json`. Один файл управляет всеми агентами, пишущими в vault.

**Чего он не делает:** не выдумывает структуру, которую ты не описал, и не поднимает embeddings-сервер — поиск это BM25 + реранк по графу ссылок поверх сырого Markdown (плотный гибридный поиск — опционально).

## Сделан для масштаба, на котором idea-файлы ломаются

[llm-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) Андрея Карпаты попал в точку с рамкой: LLM должна *компилировать* знание в живые Markdown-страницы, а не выводить его заново из вектор-стора на каждый запрос. autograph стоит на тех же трёх слоях — сырые источники, страницы, написанные LLM, схема-конвенции, — с одним отличием, которое решает всё по мере роста vault: **конвенции здесь код, а не проза.**

Гист сам проводит границу: навигация от индекса «работает на удивление хорошо на умеренном масштабе (~100 источников, ~сотни страниц)». За этой границей прозаические конвенции расходятся между сессиями, одна сущность обрастает двумя именами, противоречия копятся отмеченными-но-нерешёнными, а устаревшие страницы не уходят. autograph — движок для той стороны границы:

- **Там `lint` — это промпт, который надо не забыть запустить. Здесь это циклы, которые крутит система** — enforce, dedup, decay, health-скор — с 256 тестами, которые держат схему даже в неудачный день модели.
- **Противоречия разрешаются, а не просто отмечаются.** «Новые данные противоречат старому утверждению» превращается в update-in-place supersede с провенансом: текущее значение переписывается, старое уходит в append-only строку `## History`.
- **Одна сущность под двумя именами файлов сливается по идентичности** — email, handle, телефон, — а не в надежде, что модель вспомнит про перекрёстную ссылку.
- **Ничего не копится вечно.** Распад по Эббингаузу понижает то, что ты перестал трогать, — рабочий набор остаётся читаемым и на десяти тысячах заметок, а не только на паре сотен.

Карпаты ответил на вопрос, *кто* поддерживает вики, — LLM. autograph отвечает на вопрос, *правильно* ли это делается.

## autograph против хостинговой памяти агентов

| | autograph | mem0 / Letta | basic-memory |
|---|---|---|---|
| Хранилище | Markdown в твоём Obsidian-vault | Хостинг-БД / вектор-стор | Локальный Markdown (MCP) |
| Владение | Твои файлы, дружат с git | Сервис вендора | Локальные файлы |
| Типизированная схема + распад | Да (схема-как-код, Эббингауз) | Частично | Нет |
| Дедуп + починка ссылок + health | Да | Нет | Нет |
| Раннтайм | Любой агент (skills.sh) | SDK / API | MCP-клиенты |
| Внешние зависимости | Нет (Python stdlib) | Облачный аккаунт | MCP-сервер |

## Сценарии

| Сценарий | Команды | Зачем |
|---|---|---|
| **Аудит чужого vault** | `discover.py` → `graph.py health` → `graph.py fix --apply` | Понять состояние до того, как что-то трогать |
| **Bootstrap пустого/хаотичного vault** | `/autograph:research <vault>` | Q&A + рой агентов-исследователей → черновик схемы → твоё одобрение |
| **Карточка, которая останется связанной** | Workflow 3 в `SKILL.md`: dedup-first → тип → `## Related` (hub + 2 соседа) → `touch` | Скилл не закончит, пока карточка не связана — сироты это мёртвое знание |
| **Факт изменился** | dedup-first поиск → SUPERSEDE: переписать значение, старое → `## History` | Одна карточка на субъект с историей, а не дубль |
| **Импорт из CRM / экспорта** | `engine.py init` → `enforce.py --apply` → `enrich.py tags --apply` | Экспорты HubSpot / Notion / Apple Notes становятся родными карточками |
| **Вернуть забытое** | `engine.py creative 5 <vault>` + cron | Самые старые карточки всплывают в `warm` на повтор |

## Как работает распад

Память в стиле Эббингауза, все ручки — в `schema.decay`.

<details>
<summary><b>1. Счётчик обращений (spacing effect)</b></summary>

Каждый `touch` увеличивает `access_count`. Больше обращений — медленнее забывание:

```
strength = 1 + ln(access_count)
effective_rate = base_rate / strength
relevance = max(floor, 1.0 − effective_rate × days_since_access)
```

Карточка с 5 обращениями распадается в ~2.6× медленнее, чем с одним.

</details>

<details>
<summary><b>2. Скорость распада по типу</b></summary>

| Тип | Rate | Период полураспада | Почему |
|---|---|---|---|
| `contact` | 0.005 | ~100 дней | Люди не устаревают быстро |
| `crm` | 0.008 | ~62 дня | У сделок средний цикл |
| `project` | 0.012 | ~42 дня | У проектов есть дедлайны |
| `daily` | 0.020 | ~25 дней | Ежедневные заметки теряют смысл быстро |
| default | 0.015 | ~33 дня | Всё остальное |

</details>

<details>
<summary><b>3. Ступенчатое возвращение</b></summary>

`touch` повышает на один tier за раз: `archive → cold → warm → active`. `last_accessed` ставится в середину интервала — без повторного `touch` карточка сама сползает обратно.

</details>

## Расписание

Распад + health ночью, дедуп + MOC по воскресеньям. Подойдёт любой планировщик; вот обычный cron:

```cron
0 3 * * *  cd /path/to/vault && uv run ~/dev/autograph/skills/autograph/scripts/engine.py decay . && uv run ~/dev/autograph/skills/autograph/scripts/graph.py health .
0 4 * * 0  cd /path/to/vault && uv run ~/dev/autograph/skills/autograph/scripts/dedup.py . --apply && uv run ~/dev/autograph/skills/autograph/scripts/moc.py generate .
```

Цели: health ≥ 90, broken_links = 0, покрытие описаний ≥ 80%, устаревшие (>90д) < 20%.

## Что внутри

```
autograph/
├── .claude-plugin/         # plugin.json + marketplace.json (Claude Code, skills.sh)
├── commands/research.md     # слэш-команда /autograph:research
├── llms.txt                 # машиночитаемая сводка для агентов
├── skills/autograph/
│   ├── SKILL.md             # воркфлоу для модели (create/update, health, daily→cards)
│   ├── schema.example.json  # стартовый шаблон — копируй и правь
│   ├── references/          # bootstrap, шаблоны карточек, update-in-place, daily processor
│   ├── scripts/             # 17 скриптов движка (только Python stdlib)
│   └── tests/               # 256 автономных тестов
└── LICENSE
```

**Требования:** Python 3.11+, [`uv`](https://github.com/astral-sh/uv), vault в стиле Obsidian (папка `.md` с YAML-фронтматтером). Опционально `OPENROUTER_API_KEY` для обогащения тегов/ссылок. Без `pip install` — только stdlib.

```bash
cd skills/autograph && uv run tests/test_autograph.py   # 256/256
```

## FAQ

### Что такое autograph?
autograph — слой памяти как код для Obsidian-vault, в которые пишут AI-агенты. Одна `schema.json` задаёт типы карточек, папки, статусы и скорость распада; движок раскладывает карточки, чинит wiki-ссылки, сливает дубли сущностей, применяет забывание по Эббингаузу и считает health. Только Python stdlib, 256 тестов, MIT.

### Чем отличается от mem0, Letta, basic-memory?
autograph хранит память как обычный Markdown в твоём Obsidian-vault, а не в хостинговой базе — без API, без лок-ина, файлы остаются человекочитаемым PKM. И добавляет типизацию схемы, дедуп сущностей, починку ссылок и распад памяти, которых у тех инструментов нет.

### Работает вне Claude Code?
Да. `npx skills add smixs/autograph` ставит его в Codex, Cursor, OpenClaw, Hermes и 70+ агентов через skills.sh. Скрипты движка запускаются и standalone из любого шелла.

### Что происходит, когда факт меняется?
autograph обновляет существующую карточку на месте: переписывает текущее значение (Compiled Truth), а старое уносит в append-only `## History` — вместо второй, конфликтующей карточки. Отслужившие карточки получают `status: superseded` и ссылку на замену.

### Нужен ли embeddings-сервер?
Нет. Поиск — это BM25 по сырому Markdown плюс реранк по графу ссылок, без вектор-базы. Плотный гибридный поиск — опционально, если захочешь.

## Где используется

- **[iva](https://github.com/smixs/iva)** — персональный always-on AI-агент. autograph — его долговременная память: транскрипт каждого дня перегоняется в типизированные карточки, дедуплицируется и распадается.
- **[agent-second-brain](https://github.com/smixs/agent-second-brain)** — Telegram-бот «второй мозг», из которого autograph вырос.

## Происхождение

autograph вырос из [`agent-second-brain`](https://github.com/smixs/agent-second-brain) — Telegram-бота, который раскладывал мои голосовые расшифровки по Obsidian-vault с отчётом в 21:00. Движок распада, health-скоринг и графовые инструменты оказались той частью, которая нужна каждому агенту, а не только тому боту, — так они переехали в общий слой памяти для любого раннтайма.

---

<div align="center">

Сделано в Ташкенте · [MIT](./LICENSE) · [Issues](https://github.com/smixs/autograph/issues)

</div>
