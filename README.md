# autograph

**A typed memory layer for always-on agents. One schema, one graph, any Obsidian vault.**

Agents that run continuously — OpenClaw, Hermes, Claude Code, Codex — accumulate thousands of notes, decisions, contacts, and meetings. Without a taxonomy that memory rots: duplicate cards, broken links, fields no two notes agree on, no way to tell what is still relevant. `autograph` puts a single `schema.json` in front of the vault and enforces it. The schema describes node types, domains, decay behaviour, field rules. Scripts discover your existing structure, generate the schema, repair what drifts from it, forget what is stale, and keep the graph healthy across sessions and agents.

Zero hardcoded domains, types, or paths. The engine is stdlib Python and runs on any vault — personal knowledge base, work CRM, research archive, or an empty folder waiting to be bootstrapped.

---

## What you get

- **Schema as code** — one `schema.json` per vault. Node types, domain inference from paths, status enums, decay rates, field fixes. Everything else reads from it.
- **Ebbinghaus decay with graduated recall** — `active → warm → cold → archive`. Access count slows forgetting, touches promote one tier at a time instead of jumping straight to active, creative recall resurfaces forgotten cards for spaced repetition.
- **Vault health scoring (0–100)** — broken links, orphans, description coverage, tag coverage, tier distribution. One number you can put on a dashboard.
- **Interactive bootstrap** — the `/autograph:research` slash command gates the vault (empty / chaos / structured), spawns up to five exploration agents in parallel, asks you a handful of questions, drafts a schema, waits for approval before writing.
- **Catalog-based link enrichment** — LLM picks wikilinks only from a materialised catalog of the vault. Prevents hallucinated link targets (81.6% match rate vs. 0.3% with fuzzy matching).
- **Safe deduplication** — merges richer cards, redirects wikilinks, moves losers to `.trash/dedup-YYYY-MM-DD/`. Nothing is deleted.
- **Map-of-Content generation** — one MOC per domain, grouped by type/industry/status, regenerates from the graph.

220 self-contained regression tests across the engine. stdlib only. API calls via `urllib`. No pip install.

---

## Why

`autograph` grew out of [`smixs/agent-second-brain`](https://github.com/smixs/agent-second-brain) — a Telegram-first "second brain" that classified voice notes, wrote them to an Obsidian vault, and decayed old cards over time. The decay engine, vault-health scoring, and graph tools were the parts worth keeping once multiple agents started writing to the same vault.

The problem those agents all share: they are good at capture, bad at curation. They add cards forever, never prune, never verify links, never agree on what "status" means. Within a month the vault is chaos. `autograph` gives any agent — yours, mine, or a third-party — the same enforcement layer.

---

## Install

### Claude Code (plugin marketplace)

```
/plugin marketplace add smixs/autograph
/plugin install autograph@autograph
```

Direct install without registering the marketplace:

```
/plugin install github:smixs/autograph
```

Update and uninstall:

```
/plugin marketplace update autograph
/plugin uninstall autograph
```

### OpenClaw

OpenClaw autodetects `.claude-plugin/plugin.json`, so the repo installs as a bundle plugin:

```bash
git clone https://github.com/smixs/autograph.git ~/dev/autograph
openclaw plugins install ~/dev/autograph
openclaw gateway restart
```

The skill becomes available at `~/.openclaw/skills/autograph/` and the `/autograph:research` command is registered globally. To install for one workspace only, put the clone under `<workspace>/.agents/skills/autograph/`.

### Hermes (NousResearch)

Hermes doesn't read `.claude-plugin/plugin.json` directly but the skill format is compatible:

```bash
hermes skills install github:smixs/autograph/skills/autograph
```

The skill lands in `~/.hermes/skills/autograph/`. To run the research workflow, invoke the skill name in chat — Hermes doesn't have slash-commands in the Claude Code sense, so the command file is ignored but the skill does the same job. For cron-based maintenance see below.

Already on OpenClaw and switching? `hermes claw migrate` imports the skill to `~/.hermes/skills/openclaw-imports/autograph/`.

### Codex

Codex reads `.codex-plugin/plugin.json`. The quickest path today is to symlink:

```bash
git clone https://github.com/smixs/autograph.git ~/dev/autograph
ln -s ~/dev/autograph/.claude-plugin ~/dev/autograph/.codex-plugin
```

Point Codex at `~/dev/autograph` in your agents config.

### Local development

```bash
git clone https://github.com/smixs/autograph.git ~/dev/autograph
claude --plugin-dir ~/dev/autograph
```

---

## Quickstart

```bash
# 1. Point at a vault — empty, chaotic, or existing
/autograph:research /path/to/vault

# 2. Daily health check (see "Scheduling" for cron)
uv run skills/autograph/scripts/graph.py health /path/to/vault

# 3. Decay cycle — recompute relevance + tier for every card
uv run skills/autograph/scripts/engine.py decay /path/to/vault

# 4. Regenerate Map-of-Content indexes
uv run skills/autograph/scripts/moc.py generate /path/to/vault
```

Full bootstrap workflow (10 phases — discover, generate, swarm, enforce, cleanup, tag, dedup, link, MOC, verify) lives in `skills/autograph/references/bootstrap-workflow.md`.

---

## Use cases

### Audit an existing vault

You have 800 notes across three folders, mixed frontmatter, no idea which links still resolve. Run `discover.py` to dump every field and value, then `graph.py health` for the score, then `graph.py fix --apply` to repair broken wikilinks. No schema needed for the audit — only for enforcement.

### Bootstrap an empty or chaotic vault

`/autograph:research /path/to/vault` gates the vault, spawns explorer agents, runs two rounds of `AskUserQuestion`, drafts a schema, writes it only on your approval. Use this on a fresh vault, a post-import mess, or a workspace inherited from someone else.

### Create a knowledge card with guaranteed linking

Workflow 3 in the skill: pick a type from `node_types`, reverse-lookup the target folder from `domain_inference`, write frontmatter with a non-trivial description and 2–5 tags, add a `## Related` section with a hub link plus two siblings, run `engine.py touch` to initialise recall metadata. Orphan cards are wasted knowledge — the skill refuses to consider a card "created" until it is linked.

### Import from CRM / external source

Dump whatever source (HubSpot export, Notion CSV, OneNote, Apple Notes) into a folder under the vault. Run `engine.py init` to add baseline frontmatter, then `enforce.py --apply` to type-infer and fix statuses, then `enrich.py tags --apply` and `enrich.py swarm-links --apply` for tags and wikilinks. Cards end up indistinguishable from hand-written ones.

### Spaced repetition of forgotten knowledge

`engine.py creative 5 <vault>` picks the five oldest / lowest-relevance cards and promotes them back to `warm` tier for review. Pair with a cron entry and you get daily surfacing without a separate Anki deck.

---

## Scheduling

Run decay and health nightly. Pick the scheduler your runtime provides.

### OpenClaw cron

```bash
openclaw cron add --name "autograph-decay" \
  --cron "0 3 * * *" --tz "Europe/Amsterdam" \
  --session isolated --tools exec,read \
  --message "uv run ~/.openclaw/skills/autograph/scripts/engine.py decay /path/to/vault && uv run ~/.openclaw/skills/autograph/scripts/graph.py health /path/to/vault"
```

Second entry for weekly dedup + MOC regeneration:

```bash
openclaw cron add --name "autograph-weekly" \
  --cron "0 4 * * 0" --tz "Europe/Amsterdam" \
  --session isolated --tools exec,read \
  --message "uv run ~/.openclaw/skills/autograph/scripts/dedup.py /path/to/vault --apply && uv run ~/.openclaw/skills/autograph/scripts/moc.py generate /path/to/vault"
```

### Hermes cron

```bash
hermes cron create "0 3 * * *" "Run autograph decay + health on /path/to/vault" --skill autograph
hermes cron create "0 4 * * 0" "Run autograph dedup + MOC regeneration on /path/to/vault" --skill autograph
```

Job output goes to `~/.hermes/cron/output/{job_id}/{ts}.md`.

### Plain system cron

```cron
0 3 * * *  cd /path/to/vault && uv run ~/dev/autograph/skills/autograph/scripts/engine.py decay . >/tmp/autograph-decay.log 2>&1
5 3 * * *  cd /path/to/vault && uv run ~/dev/autograph/skills/autograph/scripts/graph.py health . >/tmp/autograph-health.log 2>&1
0 4 * * 0  cd /path/to/vault && uv run ~/dev/autograph/skills/autograph/scripts/moc.py generate . >/tmp/autograph-moc.log 2>&1
```

Target: health score ≥90, broken links = 0, description coverage ≥80%, stale cards (>90d) <20%.

---

## How the decay engine works

Three mechanisms, all configurable in `schema.decay`:

**Access count (spacing effect).** Each `touch` increments `access_count`. More retrievals slow forgetting:

```
strength = 1 + ln(access_count)
effective_rate = base_rate / strength
relevance = max(floor, 1.0 - effective_rate * days_since_access)
```

A card touched five times decays ~2.6× slower than a card touched once.

**Domain-specific rates.** Different kinds of knowledge fade at different rates. Defaults (override in schema):

| Type       | Rate  | Half-life | Rationale                          |
|------------|-------|-----------|------------------------------------|
| `contact`  | 0.005 | ~100 days | People don't become stale quickly  |
| `crm`      | 0.008 | ~62 days  | Deals have medium lifecycle        |
| `learning` | 0.010 | ~50 days  | Knowledge fades moderately         |
| `project`  | 0.012 | ~42 days  | Projects have defined timelines    |
| `daily`    | 0.020 | ~25 days  | Daily notes lose relevance fast    |
| default    | 0.015 | ~33 days  | Fallback for unlisted types        |

**Graduated recall.** A touch promotes one tier at a time — `archive → cold → warm → active` — and sets `last_accessed` to a midpoint so the card naturally drifts back down if you never touch it again.

---

## Requirements

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) for running scripts
- An Obsidian-style vault (any folder of Markdown with YAML frontmatter)
- Optional: `OPENROUTER_API_KEY` for tag and link enrichment via LLM

---

## Repository layout

```
autograph/
├── .claude-plugin/
│   ├── plugin.json         # Plugin manifest (read by Claude Code, OpenClaw)
│   └── marketplace.json    # Marketplace entry (single-plugin repo)
├── commands/
│   └── research.md         # /autograph:research slash command
├── skills/autograph/
│   ├── SKILL.md            # Skill instructions for the model
│   ├── schema.example.json # Generic starting template
│   ├── references/         # Bootstrap workflow, card templates, schema docs
│   ├── scripts/            # 14 engine scripts (stdlib only)
│   ├── tests/              # 220 self-contained regression tests
│   └── evals/evals.json    # Skill-creator eval cases
├── README.md
├── LICENSE
└── .gitignore
```

## Scripts

| Script                  | Purpose                                                           |
|-------------------------|-------------------------------------------------------------------|
| `common.py`             | Shared: parse FM, walk, domain inference, decay, wikilinks         |
| `discover.py`            | Phase 1: scan vault, output enum candidates                       |
| `generate_schema.py`     | Phase 2A: discovery JSON → draft schema                           |
| `swarm_prepare.py`       | Phase 2B: bin-pack vault into agent batches                       |
| `swarm_reduce.py`        | Phase 2B: consolidate + validate schema from agent output         |
| `research.py`            | `/research` helper: gate + small manifests + schema reduce        |
| `enforce.py`             | Phase 4: validate + auto-fix against schema                       |
| `link_cleanup.py`        | Phase 5: remove phantom wikilinks from `## Related`               |
| `enrich.py`              | Phase 6/8: tags + catalog-based swarm-links via LLM               |
| `dedup.py`               | Phase 7: safe merge + `.trash/`                                   |
| `graph.py`               | Health score, link repair, backlinks, orphans                     |
| `moc.py`                 | Map-of-Content generation per domain                              |
| `engine.py`              | Decay, touch, creative recall, stats, bootstrap init              |
| `daily.py`               | Entity extraction from memory/daily files                         |

---

## Tests

```bash
cd skills/autograph
uv run tests/test_autograph.py
```

220 assertions. Temp fixtures, no real vault needed, no external services.

---

## License

MIT — see `LICENSE`. Lineage: evolved from [`smixs/agent-second-brain`](https://github.com/smixs/agent-second-brain). Inspiration for the packaging style: [`MemPalace`](https://github.com/MemPalace/mempalace).
