<div align="center">

# autograph

<img src=".github/assets/hero.webp" alt="autograph — typed memory graph for Obsidian vaults" width="560">

**Schema-as-code memory for AI agents that write to an Obsidian vault.**
One `schema.json` keeps the vault typed, linked, deduplicated, and decaying — automatically.

[![skills.sh](https://skills.sh/b/smixs/autograph)](https://skills.sh/smixs/autograph)
[![Claude Code plugin](https://img.shields.io/badge/Claude_Code-plugin-4dc9f6?style=flat&labelColor=0a0e14)](https://code.claude.com/docs/en/plugins)
[![Tests](https://img.shields.io/badge/tests-256%2F256-b0e8ff?style=flat&labelColor=0a0e14)](./skills/autograph/tests)
[![License](https://img.shields.io/badge/license-MIT-ffffff?style=flat&labelColor=0a0e14)](./LICENSE)

English · [Русский](./README.ru.md)

</div>

---

**autograph** is a memory engine for [Obsidian](https://obsidian.md) vaults that AI agents write to. You define the taxonomy once in `schema.json` — card types, folders, allowed statuses, how fast each kind of knowledge decays. From there the engine places new cards, repairs wiki-links, merges duplicate entities, forgets what you stopped touching, and scores the vault's health. It's plain Markdown you own, not a hosted database — the same files stay a human-readable second brain. The scripts are Python stdlib only, zero external dependencies, 256 tests.

The problem it solves: an always-on agent drops notes into your vault every day — voice transcripts, meetings, contacts, ideas. A month later you have 800 files, broken links, three cards for the same person, and no one remembers if `status: ongoing` means `status: active`. autograph is the layer that keeps that in order without you babysitting it.

## Install

One command installs autograph into whichever agent you run — it picks the right directory automatically:

```bash
npx skills add smixs/autograph
```

This uses [skills.sh](https://skills.sh), the open Agent Skills registry. Works with Claude Code, Codex, Cursor, OpenClaw, Hermes, and 70+ others.

**Claude Code as a plugin** (read-only, always current):

```
/plugin marketplace add smixs/autograph
/plugin install autograph@autograph
```

Or from your shell: `claude plugin marketplace add smixs/autograph && claude plugin install autograph@autograph`.

## Quickstart

```bash
# Bootstrap a schema for an empty or messy vault (interactive)
/autograph:research /path/to/vault

# Daily health check
uv run skills/autograph/scripts/graph.py health /path/to/vault
#  health: 94/100 · broken_links: 0 · orphans: 2 · desc_coverage: 88%

# Recompute relevance + tier for every card
uv run skills/autograph/scripts/engine.py decay /path/to/vault

# Regenerate Map-of-Content indexes
uv run skills/autograph/scripts/moc.py generate /path/to/vault
```

Full 10-phase bootstrap (discover → schema → enforce → dedup → link → MOC → verify) lives in [`bootstrap-workflow.md`](./skills/autograph/references/bootstrap-workflow.md).

## What makes it different

- **Your files, your format.** Memory is Markdown in your own vault — no API, no vendor database, no lock-in. Open it in Obsidian, grep it, back it up with git.
- **Updates in place, doesn't duplicate.** New fact contradicts an old one (job changed, project renamed)? autograph rewrites the current value and moves the old one to an append-only `## History` line — it doesn't leave you two conflicting cards. Same entity under two filenames gets merged by identity, not just by exact name match.
- **Forgets on purpose.** An Ebbinghaus decay model demotes cards you stopped touching, so the working set stays small and the important cards stay warm.
- **Schema-as-code, zero hardcoded domains.** Every type, folder, status, and decay rate reads from `schema.json`. The same file drives every agent writing to the vault.

**What it doesn't do:** it won't invent structure you didn't describe, and it doesn't run an embeddings server — search is BM25 + link-graph reranking over the raw Markdown (hybrid dense search is opt-in).

## Built for the scale where idea files break

Andrej Karpathy's [llm-wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) nailed the framing: an LLM should *compile* knowledge into living Markdown pages, not re-derive it from a vector store on every query. autograph is built on the same three layers — raw sources, LLM-written pages, a schema of conventions — with one difference that decides everything as the vault grows: **the conventions are code, not prose.**

The gist draws its own line: index-first navigation "works surprisingly well at moderate scale (~100 sources, ~hundreds of pages)." Past that line, prose conventions drift between sessions, the same entity accretes under two names, contradictions pile up flagged-but-unresolved, and stale pages never leave. autograph is the engine for the other side of that line:

- **There, `lint` is a prompt you remember to run. Here it's cycles the system runs** — enforce, dedup, decay, health score — backed by 256 tests that hold the schema even on the model's off day.
- **Contradictions get resolved, not just noted.** "New data contradicts an old claim" becomes update-in-place supersede with provenance: the current value is rewritten, the old value moves to an append-only `## History` line.
- **The same entity under two filenames merges by identity** — email, handle, phone — not by hoping the model cross-references it.
- **Nothing accumulates forever.** Ebbinghaus decay demotes what you stopped touching, so the working set stays legible at ten thousand notes, not just a few hundred.

Karpathy answered *who* maintains the wiki — the LLM. autograph answers whether that maintenance is *correct*.

## autograph vs hosted agent memory

| | autograph | mem0 / Letta | basic-memory |
|---|---|---|---|
| Storage | Markdown in your Obsidian vault | Hosted DB / vector store | Local Markdown (MCP) |
| Ownership | Files you own, git-friendly | Vendor service | Local files |
| Typed schema + decay | Yes (schema-as-code, Ebbinghaus) | Partial | No |
| Dedup + link repair + health score | Yes | No | No |
| Runtime | Any agent (skills.sh) | SDK / API | MCP clients |
| External deps | None (Python stdlib) | Cloud account | MCP server |

## Use cases

| Scenario | Commands | Why |
|---|---|---|
| **Audit someone's vault** | `discover.py` → `graph.py health` → `graph.py fix --apply` | See the state before touching anything |
| **Bootstrap an empty or chaotic vault** | `/autograph:research <vault>` | Q&A + explorer-agent swarm → schema draft → your approval |
| **Record a card that stays linked** | Workflow 3 in `SKILL.md`: dedup-first → type → `## Related` (hub + 2 siblings) → `touch` | The skill won't finish until the card is linked — orphans are dead knowledge |
| **A fact changed** | dedup-first lookup → SUPERSEDE: rewrite the value, old one → `## History` | One card per subject, with an audit trail, instead of a duplicate |
| **Import from a CRM / export** | `engine.py init` → `enforce.py --apply` → `enrich.py tags --apply` | HubSpot / Notion / Apple Notes exports become native cards |
| **Resurface forgotten notes** | `engine.py creative 5 <vault>` + cron | The oldest cards drift back into `warm` for review |

## How decay works

Ebbinghaus-style memory, all knobs in `schema.decay`.

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
<summary><b>2. Per-type decay rates</b></summary>

| Type | Rate | Half-life | Rationale |
|---|---|---|---|
| `contact` | 0.005 | ~100 days | People don't go stale quickly |
| `crm` | 0.008 | ~62 days | Deals have a medium lifecycle |
| `project` | 0.012 | ~42 days | Projects have deadlines |
| `daily` | 0.020 | ~25 days | Daily notes lose relevance fast |
| default | 0.015 | ~33 days | Everything else |

</details>

<details>
<summary><b>3. Graduated recall</b></summary>

A touch promotes one tier at a time: `archive → cold → warm → active`. `last_accessed` is set to the interval midpoint, so without a re-touch the card drifts back down on its own.

</details>

## Scheduling

Run decay + health nightly, dedup + MOC weekly. Any scheduler works; here's plain cron:

```cron
0 3 * * *  cd /path/to/vault && uv run ~/dev/autograph/skills/autograph/scripts/engine.py decay . && uv run ~/dev/autograph/skills/autograph/scripts/graph.py health .
0 4 * * 0  cd /path/to/vault && uv run ~/dev/autograph/skills/autograph/scripts/dedup.py . --apply && uv run ~/dev/autograph/skills/autograph/scripts/moc.py generate .
```

Targets: health ≥ 90, broken_links = 0, description coverage ≥ 80%, stale (>90d) < 20%.

## What's inside

```
autograph/
├── .claude-plugin/         # plugin.json + marketplace.json (Claude Code, skills.sh)
├── commands/research.md     # /autograph:research slash command
├── llms.txt                 # machine-readable summary for agents
├── skills/autograph/
│   ├── SKILL.md             # workflows for the model (create/update, health, daily→cards)
│   ├── schema.example.json  # starting template — copy and customize
│   ├── references/          # bootstrap, card templates, update-in-place, daily processor
│   ├── scripts/             # 17 engine scripts (Python stdlib only)
│   └── tests/               # 256 self-contained tests
└── LICENSE
```

**Requirements:** Python 3.11+, [`uv`](https://github.com/astral-sh/uv), an Obsidian-style vault (folder of `.md` with YAML frontmatter). Optional `OPENROUTER_API_KEY` for tag/link enrichment. No `pip install` — stdlib only.

```bash
cd skills/autograph && uv run tests/test_autograph.py   # 256/256
```

## FAQ

### What is autograph?
autograph is a schema-as-code memory layer for Obsidian vaults written to by AI agents. One `schema.json` defines card types, folders, statuses, and decay rates; the engine enforces placement, repairs wiki-links, merges duplicate entities, applies Ebbinghaus-style decay, and scores vault health. Python stdlib only, 256 tests, MIT.

### How is it different from mem0, Letta, or basic-memory?
autograph stores memory as plain Markdown in your own Obsidian vault instead of a hosted database — no API, no vendor lock-in, and the files stay a human-readable PKM. It adds typed schema enforcement, entity dedup, link repair, and memory decay that those tools don't.

### Does it work outside Claude Code?
Yes. `npx skills add smixs/autograph` installs it into Codex, Cursor, OpenClaw, Hermes, and 70+ agents via skills.sh. The engine scripts also run standalone from any shell.

### What happens when a fact changes?
autograph updates the existing card in place: it rewrites the current value (Compiled Truth) and moves the old one to an append-only `## History` line — instead of creating a second, conflicting card. Retired cards get `status: superseded` and a pointer to their replacement.

### Do I need an embeddings server?
No. Search is BM25 over the raw Markdown plus link-graph reranking, no vector database. Dense hybrid search is opt-in if you want it.

## Used by

- **[iva](https://github.com/smixs/iva)** — a personal always-on AI agent. autograph is its long-term memory: every day's transcript is distilled into typed cards, deduplicated, and decayed.
- **[agent-second-brain](https://github.com/smixs/agent-second-brain)** — the Telegram second-brain bot autograph grew out of.

## Lineage

autograph grew out of [`agent-second-brain`](https://github.com/smixs/agent-second-brain), a Telegram bot that filed my voice transcripts into an Obsidian vault with a 9pm daily report. The decay engine, health scoring, and graph tools turned out to be the part every agent needed — not just that one bot — so I pulled them into a shared memory layer for any runtime.

---

<div align="center">

Built in Tashkent · [MIT](./LICENSE) · [Issues](https://github.com/smixs/autograph/issues)

</div>
