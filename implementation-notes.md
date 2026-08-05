# Implementation notes

## Audio embed regression

- Added regression coverage for the audio embed extensions merged in PR #9.
- The negative fixture keeps `note.ogg.md` classified as a Markdown note link rather than an audio embed.
- No runtime behavior or dependencies changed in that branch.

## Safe description repair

- Replaced the unconditional 500-character policy from PR #10 with the optional top-level `description_max_chars` schema key.
- Repeated descriptions are repaired deterministically even when no cap is configured.
- `cleanup.py` streams frontmatter with bounded buffers, performs same-directory atomic replacement, preserves file mode, and copies body bytes exactly.
- Giant non-periodic descriptions remain untouched and are reported unless the schema provides a usable cap.
- `enforce.py` skips files over 10 MiB and excludes them from duplicate inspection so it cannot re-read them through a secondary path.
- Follow-up self-review applies small schema caps consistently and keeps indented YAML block delimiters inside frontmatter.
- CodeRabbit CLI 0.7.1 was attempted after local validation but returned the organization rate limit with a 45-minute wait; the coordinator approved recording the skip and proceeding with strict local checks.
