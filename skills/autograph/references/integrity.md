# Card integrity and safe maintenance

Run entry points with `uv run`: their inline metadata pins PyYAML 6.0.3. The standard library has no YAML parser. The previous line parser split quoted list items at commas, accepted duplicate keys and lost nested fields; JSON-safe serialization and a real YAML parser address those failures. PyYAML is MIT-licensed and has no runtime dependency tree. See the [primary documentation](https://pyyaml.org/wiki/PyYAMLDocumentation).

`parse_frontmatter` uses a safe YAML loader, preserves scalar types, nested mappings and sequences, and retains dates as text. The writer verifies that field names and values survive a full parse roundtrip. Invalid YAML is left as the original document for read-only inspection; mutation paths use strict parsing and refuse invalid or duplicate keys. YAML merge keys require explicit resolution before mutation. Do not treat a parse failure as an empty card. An unknown status is a review item, never a fallback to `active`.

Prepare a batch outside the live vault and validate it before publication:

```bash
uv run scripts/enforce.py /path/to/staged-vault /path/to/schema.json --check --manifest /path/to/manifest.json
```

The manifest has a `files` array of objects with a `path` relative to the vault. Check mode writes no files and returns nonzero for invalid YAML, required fields, types, statuses or list shapes. Check links with `graph.py health` on the staged vault. Include the existing linked cards in that view; a folder containing only new cards is not the full graph.

The graph counts `related`, `parent`, `hub` and `superseded_by` alongside body links. Literal examples in code/comments and self-links do not count. `orphan_list` retains the no-incoming definition; `isolated_list` and `unreachable_list` report distinct problems. These sets overlap. A high scalar health score is not proof of factual accuracy or completeness.

`orchestrate.py health` reports only: it does not implicitly edit cards, merge files, regenerate indexes or apply decay. Review a scoped repair manifest before invoking mutation commands.

MOC generation updates only an explicit `autograph:moc:start` / `autograph:moc:end` body block. Existing MOCs without those markers are preserved for manual review. To migrate one, identify the generated section and preserve handwritten content before placing markers. Never wrap unknown handwritten content in a generated block.

Read-only archival paths remain subject to the vault's policy. Schema aliases and status enums must reflect the owner's actual semantics; validation does not authorize lifecycle transitions, publication or deletion.
