---
description: Bootstrap a schema for an empty or chaotic Obsidian vault via a swarm of exploration agents + interactive Q&A. Only use on vaults with no schema and no coherent structure — structured vaults should run the regular autograph bootstrap workflow.
argument-hint: <vault-dir>
allowed-tools: Bash, Read, Glob, Grep, Write, Edit, Agent, AskUserQuestion
---

# /autograph:research — interactive bootstrap

You are orchestrating an **interactive bootstrap** of a chaotic or empty Obsidian vault. The user invoked `/autograph:research $ARGUMENTS`. Treat `$ARGUMENTS` as the vault path. If empty, ask for it with `AskUserQuestion`.

This command only runs when the vault lacks a usable schema and structure. For structured vaults, redirect the user to the normal bootstrap workflow (`references/bootstrap-workflow.md` in the autograph skill).

## Workflow

### Phase 1 — Gate (is /research the right tool?)

Run discovery to see what we have:

```bash
uv run <skill-dir>/scripts/discover.py "$VAULT" --verbose > /tmp/autograph-discovery.json
uv run <skill-dir>/scripts/research.py plan "$VAULT" > /tmp/autograph-plan.json
```

Read `/tmp/autograph-plan.json`. It contains `gate` with fields:

- `files_total`, `folders_total`
- `has_schema_json` (bool)
- `frontmatter_coverage` (0–1)
- `verdict`: `"chaos"` | `"structured"` | `"empty"`

**If `verdict == "structured"`**: stop. Tell the user:
> This vault already has a workable structure (N files, X% with frontmatter, schema.json present). `/research` is for empty or chaotic vaults. Use `discover.py` → `generate_schema.py` → `swarm_prepare.py` from the autograph skill instead.

Do not proceed to Phase 2 unless the user overrides.

**If `verdict == "empty"` (≤ ~20 files)**: skip Phase 3 swarm — go straight to Q&A (Phase 2) + manual schema draft.

**If `verdict == "chaos"`**: continue to Phase 2.

### Phase 2 — First-wave Q&A

Use `AskUserQuestion` to establish intent. Ask up to 4 at once:

1. **Purpose** — personal / work / research / mixed
2. **Expected domains** — free-form list, show 3–5 folder names already present as hints
3. **Content language** — ru / en / mixed / other
4. **Schema ambition** — minimal (3–5 types) / standard (6–10) / full taxonomy (10–15)

Store answers in memory — you will feed them to Phase 4.

### Phase 3 — Swarm exploration (only for chaos)

`/tmp/autograph-plan.json` contains a `manifests` array. Each manifest has a non-overlapping subset of files (≤ 20 each) bin-packed by folder. Spawn parallel `Agent` calls — **one per manifest, up to 5 in a single message** — with `subagent_type: "general-purpose"`.

Each agent prompt must say (self-contained — agents see none of this conversation):

> You are a vault exploration agent. Read the files listed below and return a single JSON object with: `observed_themes` (5–10 short tags), `entity_types` (list of content types you see: person, project, note, meeting, etc.), `frontmatter_fields` (fields actually used), `language` (ru/en/mixed), `folder_semantics` (map folder → one-line purpose), `sample_titles` (5 titles). Do NOT classify individual files — focus on patterns. Under 400 words. Files: [list from manifest].

Collect all returned JSONs into a single file `/tmp/autograph-observations.json` — an array of per-agent reports.

### Phase 4 — Clarifying Q&A

Based on observations + first-wave answers, ask up to 4 more via `AskUserQuestion`:

- **Status values** — offer 3 candidate sets from observed frontmatter (e.g. `active/draft/done` vs `todo/in-progress/done` vs custom)
- **Decay profile** — fast (daily notes dominate) / balanced (mixed) / slow (mostly reference)
- **Knowledge vs personal split** — for each top-level folder observed, confirm the domain (provide a small table)
- **Hub files** — do `_index.md` / `MOC.md` / `MEMORY.md` exist? which should be hubs?

### Phase 5 — Consolidate → draft schema

```bash
uv run <skill-dir>/scripts/research.py reduce "$VAULT" \
    /tmp/autograph-observations.json \
    /tmp/autograph-user-answers.json \
    > "$VAULT/schema.draft.json"
```

Show the draft to the user. Summarize the key decisions (node_types, domains, decay rates). Ask for approval before writing `schema.json`.

### Phase 6 — Finalize

On approval:

```bash
mv "$VAULT/schema.draft.json" "$VAULT/schema.json"
uv run <skill-dir>/scripts/enforce.py "$VAULT" "$VAULT/schema.json"          # dry run
uv run <skill-dir>/scripts/enforce.py "$VAULT" "$VAULT/schema.json" --apply  # apply
uv run <skill-dir>/scripts/graph.py health "$VAULT"
```

Report the health score and next steps (tag enrichment, MOC generation) — pointing at the standard autograph workflow.

## Rules

- **Never write to the vault without explicit user approval** between Phase 5 and Phase 6.
- **Never spawn more than 5 exploration agents in one message** — batch if manifests exceed 5.
- **Never invent node types** — only propose what observations or user answers support.
- **User answers beat observations** — if the user says "I don't have projects here", drop `project` even if the swarm saw it.
- **Save intermediate artifacts to `/tmp/autograph-*.json`** so the user can inspect them.

## Writing user-facing notes

Between phases, give one short progress line (≤ 25 words). Don't dump raw JSON — summarize.

## Failure modes

- Discovery fails → the vault path is wrong. Re-ask.
- Swarm agent returns malformed JSON → ignore that agent's output, continue with the rest; if >50% fail, fall back to manual schema from user answers only.
- `enforce.py --apply` drops health below 70 → rollback the draft (the dry run would have surfaced this; stop before `--apply` if the dry run is bad).
