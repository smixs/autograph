# autograph

Schema-as-code engine for any Obsidian vault. Discover structure, enforce a taxonomy, manage decay (Ebbinghaus), repair links, generate MOCs, deduplicate — all driven by a single `schema.json`. Zero hardcoded domains or paths.

Ships as a Claude Code **plugin**:

- `skills/autograph/` — the engine (14 stdlib-only Python scripts + references).
- `commands/research.md` — the `/autograph:research` slash command: an interactive bootstrap for empty or chaotic vaults backed by a swarm of exploration agents and `AskUserQuestion` rounds.

## Install

### From a local clone (development)

```bash
git clone https://github.com/shimaozb/autograph.git ~/dev/autograph
claude --plugin-dir ~/dev/autograph
```

### As a marketplace plugin

Add this repo to your marketplace (see `~/.claude/plugins/known_marketplaces.json`) and install via `/plugin install autograph`.

## Requirements

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) for running scripts (`uv run scripts/*.py`)
- Obsidian vault (any structure — the whole point is `autograph` adapts)
- Optional: `OPENROUTER_API_KEY` for `enrich.py` (tag & link enrichment via LLM)

Scripts are stdlib-only. No `pip install` needed.

## Usage

### First time on a chaotic vault

```
/autograph:research /path/to/vault
```

Runs the gate check, asks a handful of questions, spawns up to 5 exploration agents in parallel (haiku-class), drafts a `schema.json`, and lets you approve before writing. Only for vaults with no usable structure — for already-organised vaults, go straight to the bootstrap workflow below.

### Structured / production workflow

Read `skills/autograph/references/bootstrap-workflow.md` — the canonical 10-phase guide (discover → generate → swarm → enforce → link cleanup → tag enrich → dedup → link enrich → MOC → verify).

### Daily maintenance

```bash
uv run skills/autograph/scripts/graph.py health /path/to/vault
uv run skills/autograph/scripts/engine.py decay /path/to/vault
uv run skills/autograph/scripts/moc.py generate /path/to/vault
```

## What is not in the repo

- `schema.json` — your vault's taxonomy. Generate it via `/autograph:research` or `scripts/discover.py` → `scripts/generate_schema.py`. A generic `schema.example.json` ships with the skill as a starting point.
- `.graph/` — intermediate artifacts, reports, caches. Per-vault, gitignored.

## Tests

```bash
cd skills/autograph
uv run scripts/test_autograph.py
```

~193 self-contained tests using temp fixtures. No external dependencies.

## License

MIT — see `LICENSE`.
