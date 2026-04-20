# autograph

Schema-as-code engine for any Obsidian vault. Discover structure, enforce a taxonomy, manage decay (Ebbinghaus), repair links, generate MOCs, deduplicate — all driven by a single `schema.json`. Zero hardcoded domains or paths.

Ships as a Claude Code **plugin**:

- `skills/autograph/` — the engine (14 stdlib-only Python scripts + references).
- `commands/research.md` — the `/autograph:research` slash command: interactive bootstrap for empty or chaotic vaults, backed by a swarm of exploration agents and `AskUserQuestion` rounds.

## Install

### Via Claude Code marketplace (recommended)

Inside Claude Code:

```
/plugin marketplace add smixs/autograph
/plugin install autograph@autograph
```

Claude Code fetches the repo, reads `.claude-plugin/marketplace.json`, and activates the plugin. To update later:

```
/plugin marketplace update autograph
```

To uninstall:

```
/plugin uninstall autograph
/plugin marketplace remove autograph
```

### Direct install from GitHub (no marketplace)

```
/plugin install github:smixs/autograph
```

### Local development

```bash
git clone https://github.com/smixs/autograph.git ~/dev/autograph
claude --plugin-dir ~/dev/autograph
```

## Requirements

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) for running scripts (`uv run scripts/*.py`)
- An Obsidian vault (any structure — the whole point is `autograph` adapts)
- Optional: `OPENROUTER_API_KEY` for `enrich.py` (tag & link enrichment via LLM)

Scripts are stdlib-only. No `pip install` needed.

## Usage

### First time on a chaotic or empty vault

```
/autograph:research /path/to/vault
```

Gates the vault (empty / chaos / structured), asks up to 4 questions, spawns up to 5 exploration agents in parallel, drafts a `schema.json`, and requests approval before writing.

### Structured / production workflow

See `skills/autograph/references/bootstrap-workflow.md` — the canonical 10-phase guide:
`discover → generate → swarm → enforce → link cleanup → tag enrich → dedup → link enrich → MOC → verify`.

### Daily maintenance

```bash
uv run skills/autograph/scripts/graph.py health /path/to/vault
uv run skills/autograph/scripts/engine.py decay /path/to/vault
uv run skills/autograph/scripts/moc.py generate /path/to/vault
```

## Repository layout

```
autograph/
├── .claude-plugin/
│   ├── plugin.json         # Plugin manifest
│   └── marketplace.json    # Marketplace entry (single-plugin repo)
├── commands/
│   └── research.md         # /autograph:research slash command
├── skills/autograph/
│   ├── SKILL.md            # Skill instructions for the model
│   ├── schema.example.json # Generic starting template
│   ├── references/         # Bootstrap workflow, card templates, schema docs
│   ├── scripts/            # 14 engine scripts (stdlib only)
│   ├── tests/              # Self-contained regression tests
│   └── evals/evals.json    # skill-creator eval cases
├── README.md
├── LICENSE
└── .gitignore
```

## What is not in the repo

- `schema.json` — your vault's taxonomy (generated per vault, gitignored). Produce via `/autograph:research` or `discover.py → generate_schema.py`.
- `.graph/` — intermediate artifacts, reports, caches. Per-vault, gitignored.

## Tests

```bash
cd skills/autograph
uv run tests/test_autograph.py
```

220 self-contained assertions across the engine — common utilities, all 14 script CLIs, edge cases. No external dependencies, uses `tempfile` fixtures.

## License

MIT — see `LICENSE`.
