<div align="center">

<!-- TODO: replace with your hero image (recommended 800×320) -->
<!-- <img src=".github/assets/hero.png" alt="autograph" width="720"> -->

# 🧠 autograph

**Типизированный слой памяти для always-on агентов. Одна схема, один граф, любой Obsidian-vault.**

[![Version](https://img.shields.io/badge/version-1.0.0-4dc9f6?style=flat-square&labelColor=0a0e14)](https://github.com/smixs/autograph)
[![Python](https://img.shields.io/badge/python-3.11+-7dd8f8?style=flat-square&labelColor=0a0e14)](https://www.python.org)
[![Tests](https://img.shields.io/badge/tests-220%2F220-b0e8ff?style=flat-square&labelColor=0a0e14)](https://github.com/smixs/autograph)
[![License](https://img.shields.io/badge/license-MIT-ffffff?style=flat-square&labelColor=0a0e14)](./LICENSE)

[🇷🇺 Русский](#-по-русски) · [🇬🇧 English](#-english)

</div>

---

## 🇷🇺 По-русски

Агент каждый день пишет тебе заметки в Obsidian — голосовые расшифровки, встречи, идеи, контакты. Через месяц там 800 файлов, битые wiki-ссылки, дубликаты, и никто не помнит, что значит поле `status: ongoing` против `status: active`. **`autograph` — это слой, который всё это держит в порядке автоматически.**

Ты описываешь один раз в `schema.json`: какие бывают типы карточек (заметка, контакт, проект, CRM-сделка), в какой папке что лежит, как быстро стареет знание, какие статусы допустимы. Дальше движок сам: раскладывает новые файлы, чинит ссылки, забывает то, что не трогал полгода, сливает дубликаты, считает health-score. Один `schema.json` понимают и Claude Code, и OpenClaw, и Hermes, и Codex — любой агент, который пишет в твой vault.

<details>
<summary><b>📋 Оглавление</b></summary>

- [⚡ Установка](#-установка)
- [🚀 Быстрый старт](#-быстрый-старт)
- [💡 Сценарии использования](#-сценарии-использования)
- [⏰ Расписание (cron)](#-расписание-cron)
- [🧬 Как работает decay](#-как-работает-decay)
- [📦 Что внутри](#-что-внутри)
- [🔗 Откуда проект](#-откуда-проект)

</details>

### ⚡ Установка

<details>
<summary><b>Claude Code</b> — marketplace или прямая установка</summary>

```
/plugin marketplace add smixs/autograph
/plugin install autograph@autograph
```

Без регистрации marketplace:

```
/plugin install github:smixs/autograph
```

Обновить / удалить:

```
/plugin marketplace update autograph
/plugin uninstall autograph
```

</details>

<details>
<summary><b>OpenClaw</b> — через bundle-детект <code>.claude-plugin/plugin.json</code></summary>

```bash
git clone https://github.com/smixs/autograph.git ~/dev/autograph
openclaw plugins install ~/dev/autograph
openclaw gateway restart
```

Skill встанет в `~/.openclaw/skills/autograph/`, команда `/autograph:research` доступна глобально. Для одного workspace — клонируй в `<workspace>/.agents/skills/autograph/`.

</details>

<details>
<summary><b>Hermes</b> (NousResearch) — github source</summary>

```bash
hermes skills install github:smixs/autograph/skills/autograph
```

Skill окажется в `~/.hermes/skills/autograph/`. Hermes не поддерживает slash-команды в формате Claude Code — `commands/research.md` игнорируется, но вся логика живёт в skill, вызови его по имени в чате.

Переезжаешь с OpenClaw на Hermes? `hermes claw migrate` перенесёт autograph в `~/.hermes/skills/openclaw-imports/`.

</details>

<details>
<summary><b>Codex</b> — через symlink</summary>

```bash
git clone https://github.com/smixs/autograph.git ~/dev/autograph
ln -s ~/dev/autograph/.claude-plugin ~/dev/autograph/.codex-plugin
```

Добавь `~/dev/autograph` в agents-конфиг Codex.

</details>

### 🚀 Быстрый старт

```bash
# 1. На любом vault — пустом, хаотичном, или уже наполненном
/autograph:research /путь/к/vault

# 2. Ежедневный health check
uv run skills/autograph/scripts/graph.py health /путь/к/vault

# 3. Прогон decay: пересчёт relevance и tier для всех карточек
uv run skills/autograph/scripts/engine.py decay /путь/к/vault

# 4. Перегенерация Map-of-Content индексов
uv run skills/autograph/scripts/moc.py generate /путь/к/vault
```

Полный bootstrap (10 фаз: discover → generate → swarm → enforce → cleanup → tag → dedup → link → MOC → verify) — в `skills/autograph/references/bootstrap-workflow.md`.

### 💡 Сценарии использования

| Сценарий | Команды | Зачем |
|---|---|---|
| **Аудит чужого vault** | `discover.py` → `graph.py health` → `graph.py fix --apply` | Понять состояние перед любыми изменениями |
| **Bootstrap пустого или хаотичного** | `/autograph:research <vault>` | Интерактивный Q&A + рой explorer-агентов → draft схемы → твоё approve |
| **Создание карточки с линками** | Workflow 3 в SKILL.md: тип → путь → frontmatter → `## Related` (hub + 2 siblings) → `engine.py touch` | Orphan-карточки — мёртвое знание. Skill отказывается "закрывать" задачу пока линки не проставлены |
| **Импорт из CRM / внешнего источника** | `engine.py init` → `enforce.py --apply` → `enrich.py tags --apply` → `enrich.py swarm-links --apply` | Экспорт из HubSpot / Notion / OneNote / Apple Notes становится неотличим от ручных карточек |
| **Spaced repetition забытого** | `engine.py creative 5 <vault>` + cron | 5 самых старых карточек поднимаются в `warm` tier для повторного просмотра |

### ⏰ Расписание (cron)

Ночью — decay + health. По воскресеньям — dedup + MOC.

<details>
<summary><b>OpenClaw cron</b></summary>

```bash
openclaw cron add --name "autograph-daily" \
  --cron "0 3 * * *" --tz "Europe/Amsterdam" \
  --session isolated --tools exec,read \
  --message "uv run ~/.openclaw/skills/autograph/scripts/engine.py decay /path/to/vault && uv run ~/.openclaw/skills/autograph/scripts/graph.py health /path/to/vault"

openclaw cron add --name "autograph-weekly" \
  --cron "0 4 * * 0" --tz "Europe/Amsterdam" \
  --session isolated --tools exec,read \
  --message "uv run ~/.openclaw/skills/autograph/scripts/dedup.py /path/to/vault --apply && uv run ~/.openclaw/skills/autograph/scripts/moc.py generate /path/to/vault"
```

</details>

<details>
<summary><b>Hermes cron</b></summary>

```bash
hermes cron create "0 3 * * *" "autograph decay + health on /path/to/vault" --skill autograph
hermes cron create "0 4 * * 0" "autograph dedup + MOC on /path/to/vault" --skill autograph
```

Вывод джобов — в `~/.hermes/cron/output/{job_id}/{ts}.md`.

</details>

<details>
<summary><b>Системный cron</b></summary>

```cron
0 3 * * *  cd /path/to/vault && uv run ~/dev/autograph/skills/autograph/scripts/engine.py decay . >/tmp/autograph-decay.log 2>&1
5 3 * * *  cd /path/to/vault && uv run ~/dev/autograph/skills/autograph/scripts/graph.py health . >/tmp/autograph-health.log 2>&1
0 4 * * 0  cd /path/to/vault && uv run ~/dev/autograph/skills/autograph/scripts/moc.py generate . >/tmp/autograph-moc.log 2>&1
```

</details>

**Целевые метрики:** health ≥ 90, broken_links = 0, description coverage ≥ 80%, stale (>90d) < 20%.

### 🧬 Как работает decay

Память моделируется по Эббингаузу — три механизма, всё настраивается в `schema.decay`:

<details>
<summary><b>1. Access count (spacing effect)</b></summary>

Каждый `touch` инкрементит `access_count`. Чем чаще обращение — тем медленнее забывание:

```
strength = 1 + ln(access_count)
effective_rate = base_rate / strength
relevance = max(floor, 1.0 − effective_rate × days_since_access)
```

Карточка с 5 touches затухает в ~2.6× медленнее, чем с одним.

</details>

<details>
<summary><b>2. Domain-specific rates</b></summary>

| Тип | Rate | Период полураспада | Почему |
|---|---|---|---|
| `contact` | 0.005 | ~100 дней | Люди не устаревают быстро |
| `crm` | 0.008 | ~62 дня | У сделок средний цикл |
| `learning` | 0.010 | ~50 дней | Знание блекнет умеренно |
| `project` | 0.012 | ~42 дня | Проекты имеют дедлайны |
| `daily` | 0.020 | ~25 дней | Дневник быстро теряет актуальность |
| default | 0.015 | ~33 дня | Fallback для прочего |

</details>

<details>
<summary><b>3. Graduated recall</b></summary>

Touch поднимает на один tier за раз: `archive → cold → warm → active`. `last_accessed` ставится в середину интервала — если карточку не трогать, она плавно уйдёт обратно вниз.

</details>

### 📦 Что внутри

```
autograph/
├── .claude-plugin/
│   ├── plugin.json         # Манифест (Claude Code, OpenClaw)
│   └── marketplace.json    # Marketplace entry
├── commands/research.md    # Slash-команда /autograph:research
├── skills/autograph/
│   ├── SKILL.md            # Инструкции для модели
│   ├── schema.example.json # Generic-шаблон
│   ├── references/         # Bootstrap workflow, card templates, schema docs
│   ├── scripts/            # 14 движковых скриптов (stdlib only)
│   ├── tests/              # 220 self-contained тестов
│   └── evals/evals.json    # Eval-кейсы для skill-creator
└── LICENSE
```

<details>
<summary><b>Скрипты движка</b> — 14 штук</summary>

| Script | Назначение |
|---|---|
| `common.py` | FM-парсер, walk, domain inference, decay-формула |
| `discover.py` | Phase 1: скан vault, enum-кандидаты |
| `generate_schema.py` | Phase 2A: discovery → draft schema |
| `swarm_prepare.py` | Phase 2B: bin-pack vault в батчи для агентов |
| `swarm_reduce.py` | Phase 2B: консолидация + валидация схемы |
| `research.py` | Helper для `/research`: gate + manifests + reduce |
| `enforce.py` | Phase 4: валидация + auto-fix по схеме |
| `link_cleanup.py` | Phase 5: удаление фантомных wikilinks |
| `enrich.py` | Phase 6/8: tags + catalog-based swarm-links через LLM |
| `dedup.py` | Phase 7: merge + `.trash/` |
| `graph.py` | Health score, repair, backlinks, orphans |
| `moc.py` | Map-of-Content генерация |
| `engine.py` | Decay, touch, creative recall, stats, init |
| `daily.py` | Entity extraction из daily/memory файлов |

</details>

**Требования:** Python 3.11+, [`uv`](https://github.com/astral-sh/uv), Obsidian-vault (папка `.md`-файлов с YAML frontmatter). Опционально — `OPENROUTER_API_KEY` для enrich.py. `pip install` не нужен — stdlib only.

**Тесты:**
```bash
cd skills/autograph && uv run tests/test_autograph.py
```

### 🔗 Откуда проект

Вырос из [`smixs/agent-second-brain`](https://github.com/smixs/agent-second-brain) — Telegram-бота "второй мозг", где голосовые расшифровки классифицировались и писались в Obsidian с ежевечерним daily-репортом. Decay-движок, vault-health scoring, graph-tools оказались частью, которая нужна всем агентам, а не только одному боту. `autograph` выделяет эти инструменты в общий слой памяти для любого рантайма.

Оформление README — в духе [`MemPalace`](https://github.com/MemPalace/mempalace).

---

## 🇬🇧 English

An always-on agent writes notes into your Obsidian vault every day — voice transcripts, meetings, ideas, contacts. A month later you have 800 files, broken wiki-links, duplicates, and no one remembers whether `status: ongoing` is the same as `status: active`. **`autograph` is the layer that keeps all of that in order automatically.**

You describe the taxonomy once in `schema.json`: what card types exist (note, contact, project, CRM deal), which folder holds which domain, how fast each kind of knowledge decays, which statuses are allowed. From there the engine takes over — it places new files, repairs links, forgets cards you haven't touched for months, merges duplicates, computes a health score. One `schema.json` is read by Claude Code, OpenClaw, Hermes, Codex — any agent writing to your vault.

<details>
<summary><b>📋 Table of contents</b></summary>

- [⚡ Install](#-install)
- [🚀 Quickstart](#-quickstart)
- [💡 Use cases](#-use-cases)
- [⏰ Scheduling](#-scheduling)
- [🧬 How decay works](#-how-decay-works)
- [📦 What's inside](#-whats-inside)
- [🔗 Lineage](#-lineage)

</details>

### ⚡ Install

<details>
<summary><b>Claude Code</b> — marketplace or direct</summary>

```
/plugin marketplace add smixs/autograph
/plugin install autograph@autograph
```

Direct install without registering the marketplace:

```
/plugin install github:smixs/autograph
```

Update / uninstall:

```
/plugin marketplace update autograph
/plugin uninstall autograph
```

</details>

<details>
<summary><b>OpenClaw</b> — via <code>.claude-plugin/plugin.json</code> bundle autodetect</summary>

```bash
git clone https://github.com/smixs/autograph.git ~/dev/autograph
openclaw plugins install ~/dev/autograph
openclaw gateway restart
```

The skill lands in `~/.openclaw/skills/autograph/` and `/autograph:research` becomes available globally. For one workspace only, clone into `<workspace>/.agents/skills/autograph/`.

</details>

<details>
<summary><b>Hermes</b> (NousResearch) — github source</summary>

```bash
hermes skills install github:smixs/autograph/skills/autograph
```

The skill lands in `~/.hermes/skills/autograph/`. Hermes doesn't support Claude Code slash-commands — `commands/research.md` is ignored, but the whole workflow lives in the skill, so just invoke the skill by name in chat.

Moving from OpenClaw to Hermes? `hermes claw migrate` imports autograph to `~/.hermes/skills/openclaw-imports/`.

</details>

<details>
<summary><b>Codex</b> — via symlink</summary>

```bash
git clone https://github.com/smixs/autograph.git ~/dev/autograph
ln -s ~/dev/autograph/.claude-plugin ~/dev/autograph/.codex-plugin
```

Point Codex at `~/dev/autograph` in your agents config.

</details>

### 🚀 Quickstart

```bash
# 1. Point at a vault — empty, chaotic, or already populated
/autograph:research /path/to/vault

# 2. Daily health check
uv run skills/autograph/scripts/graph.py health /path/to/vault

# 3. Decay pass: recompute relevance + tier for every card
uv run skills/autograph/scripts/engine.py decay /path/to/vault

# 4. Regenerate Map-of-Content indexes
uv run skills/autograph/scripts/moc.py generate /path/to/vault
```

The 10-phase bootstrap (discover → generate → swarm → enforce → cleanup → tag → dedup → link → MOC → verify) is in `skills/autograph/references/bootstrap-workflow.md`.

### 💡 Use cases

| Scenario | Commands | Why |
|---|---|---|
| **Audit someone else's vault** | `discover.py` → `graph.py health` → `graph.py fix --apply` | Understand state before changing anything |
| **Bootstrap empty or chaotic vault** | `/autograph:research <vault>` | Interactive Q&A + explorer agent swarm → schema draft → approval |
| **Create a card with guaranteed links** | Workflow 3 in SKILL.md: type → path → frontmatter → `## Related` (hub + 2 siblings) → `engine.py touch` | Orphan cards are dead knowledge — the skill won't close the task until links are in place |
| **Import from CRM / external source** | `engine.py init` → `enforce.py --apply` → `enrich.py tags --apply` → `enrich.py swarm-links --apply` | Exports from HubSpot / Notion / OneNote / Apple Notes become indistinguishable from hand-written cards |
| **Spaced repetition of forgotten knowledge** | `engine.py creative 5 <vault>` + cron | The 5 oldest cards surface back in `warm` tier for review |

### ⏰ Scheduling

Decay + health at night. Dedup + MOC on Sundays.

<details>
<summary><b>OpenClaw cron</b></summary>

```bash
openclaw cron add --name "autograph-daily" \
  --cron "0 3 * * *" --tz "Europe/Amsterdam" \
  --session isolated --tools exec,read \
  --message "uv run ~/.openclaw/skills/autograph/scripts/engine.py decay /path/to/vault && uv run ~/.openclaw/skills/autograph/scripts/graph.py health /path/to/vault"

openclaw cron add --name "autograph-weekly" \
  --cron "0 4 * * 0" --tz "Europe/Amsterdam" \
  --session isolated --tools exec,read \
  --message "uv run ~/.openclaw/skills/autograph/scripts/dedup.py /path/to/vault --apply && uv run ~/.openclaw/skills/autograph/scripts/moc.py generate /path/to/vault"
```

</details>

<details>
<summary><b>Hermes cron</b></summary>

```bash
hermes cron create "0 3 * * *" "autograph decay + health on /path/to/vault" --skill autograph
hermes cron create "0 4 * * 0" "autograph dedup + MOC on /path/to/vault" --skill autograph
```

Job output: `~/.hermes/cron/output/{job_id}/{ts}.md`.

</details>

<details>
<summary><b>System cron</b></summary>

```cron
0 3 * * *  cd /path/to/vault && uv run ~/dev/autograph/skills/autograph/scripts/engine.py decay . >/tmp/autograph-decay.log 2>&1
5 3 * * *  cd /path/to/vault && uv run ~/dev/autograph/skills/autograph/scripts/graph.py health . >/tmp/autograph-health.log 2>&1
0 4 * * 0  cd /path/to/vault && uv run ~/dev/autograph/skills/autograph/scripts/moc.py generate . >/tmp/autograph-moc.log 2>&1
```

</details>

**Targets:** health ≥ 90, broken_links = 0, description coverage ≥ 80%, stale (>90d) < 20%.

### 🧬 How decay works

Ebbinghaus-style memory with three mechanisms, all configurable in `schema.decay`:

<details>
<summary><b>1. Access count (spacing effect)</b></summary>

Each `touch` increments `access_count`. More retrievals slow forgetting:

```
strength = 1 + ln(access_count)
effective_rate = base_rate / strength
relevance = max(floor, 1.0 − effective_rate × days_since_access)
```

A card touched 5 times decays ~2.6× slower than one touched once.

</details>

<details>
<summary><b>2. Domain-specific rates</b></summary>

| Type | Rate | Half-life | Rationale |
|---|---|---|---|
| `contact` | 0.005 | ~100 days | People don't go stale quickly |
| `crm` | 0.008 | ~62 days | Deals have medium lifecycle |
| `learning` | 0.010 | ~50 days | Knowledge fades moderately |
| `project` | 0.012 | ~42 days | Projects have deadlines |
| `daily` | 0.020 | ~25 days | Daily notes lose relevance fast |
| default | 0.015 | ~33 days | Fallback for everything else |

</details>

<details>
<summary><b>3. Graduated recall</b></summary>

A touch promotes one tier at a time: `archive → cold → warm → active`. `last_accessed` is set to the midpoint of the interval — so without a re-touch the card naturally drifts back down.

</details>

### 📦 What's inside

```
autograph/
├── .claude-plugin/
│   ├── plugin.json         # Manifest (Claude Code, OpenClaw)
│   └── marketplace.json    # Marketplace entry
├── commands/research.md    # /autograph:research slash command
├── skills/autograph/
│   ├── SKILL.md            # Skill instructions for the model
│   ├── schema.example.json # Generic starting template
│   ├── references/         # Bootstrap workflow, card templates, schema docs
│   ├── scripts/            # 14 engine scripts (stdlib only)
│   ├── tests/              # 220 self-contained tests
│   └── evals/evals.json    # Skill-creator eval cases
└── LICENSE
```

<details>
<summary><b>Engine scripts</b> — 14 total</summary>

| Script | Purpose |
|---|---|
| `common.py` | FM parser, walk, domain inference, decay formula |
| `discover.py` | Phase 1: scan vault, enum candidates |
| `generate_schema.py` | Phase 2A: discovery → draft schema |
| `swarm_prepare.py` | Phase 2B: bin-pack vault into agent batches |
| `swarm_reduce.py` | Phase 2B: consolidate + validate schema |
| `research.py` | `/research` helper: gate + manifests + reduce |
| `enforce.py` | Phase 4: validate + auto-fix against schema |
| `link_cleanup.py` | Phase 5: remove phantom wikilinks |
| `enrich.py` | Phase 6/8: tags + catalog-based swarm-links via LLM |
| `dedup.py` | Phase 7: safe merge + `.trash/` |
| `graph.py` | Health score, repair, backlinks, orphans |
| `moc.py` | Map-of-Content generation |
| `engine.py` | Decay, touch, creative recall, stats, init |
| `daily.py` | Entity extraction from daily/memory files |

</details>

**Requirements:** Python 3.11+, [`uv`](https://github.com/astral-sh/uv), Obsidian-style vault (folder of `.md` with YAML frontmatter). Optional: `OPENROUTER_API_KEY` for enrich.py. No `pip install` needed — stdlib only.

**Tests:**
```bash
cd skills/autograph && uv run tests/test_autograph.py
```

### 🔗 Lineage

Grew out of [`smixs/agent-second-brain`](https://github.com/smixs/agent-second-brain) — a Telegram-first "second brain" bot that classified voice transcripts into an Obsidian vault with a 9pm daily report. The decay engine, vault-health scoring, and graph tools turned out to be the part every agent needed, not just that one bot. `autograph` extracts them into a shared memory layer for any runtime.

README styling inspired by [`MemPalace`](https://github.com/MemPalace/mempalace).

---

<div align="center">

Made with care in Tashkent · [MIT License](./LICENSE) · [Issues](https://github.com/smixs/autograph/issues)

</div>
