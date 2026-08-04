#!/usr/bin/env python3
"""
autograph enforce — validate and fix vault cards against schema.

Usage:
  python3 enforce.py <vault-dir> <schema.json>              # dry run
  python3 enforce.py <vault-dir> <schema.json> --apply       # apply fixes
  python3 enforce.py <vault-dir> <schema.json> --verbose
"""

import json
import re
import sys
from pathlib import Path
from datetime import date
from collections import defaultdict

from common import (
    load_schema, parse_frontmatter, write_frontmatter, format_field,
    walk_vault, rel_path, infer_domain, infer_type, IGNORE_DIRS,
    get_type_aliases, get_field_fixes, get_node_types, get_status_defaults,
    collect_duplicate_groups, collapse_repeated_description, cap_description, DESC_CAP
)

# ─── CARD BODY CLEANUP ─────────────────────────────────────
# The nightly LLM pass sometimes appends a fresh section instead of updating the
# existing one, leaving cards with layered '## Related' blocks and bare dated
# headings. Cards only — daily/ and the rollups are append-only by design.
RELATED_HEADING = '## Related'
SECTION_BREAK = re.compile(r'^#{1,2} ')
DATED_HEADING = re.compile(r'^## .*\d{4}-\d{2}-\d{2}\s*$')
BULLET_TARGET = re.compile(r'\[\[([^\]|#]+)')


def _sections(lines: list[str]) -> list[tuple[int, int]]:
    """Heading spans as (heading_index, end_index_exclusive), split on ^# / ^##."""
    starts = [i for i, l in enumerate(lines) if SECTION_BREAK.match(l)]
    return [(s, starts[j + 1] if j + 1 < len(starts) else len(lines))
            for j, s in enumerate(starts)]


def _bullet_key(line: str) -> str:
    """Dedup key for a Related bullet: the wikilink target, alias ignored."""
    m = BULLET_TARGET.search(line)
    return m.group(1).strip() if m else line.strip()


def _dedup_bullets(section: list[str], seen: set) -> tuple[list[str], bool]:
    """Drop bullets whose target is already seen; first occurrence wins."""
    out, dropped = [], False
    for l in section:
        if l.startswith('- '):
            key = _bullet_key(l)
            if key in seen:
                dropped = True
                continue
            seen.add(key)
        out.append(l)
    return out, dropped


def merge_related(lines: list[str]) -> tuple[list[str], bool]:
    """Fold repeated '## Related' sections into the first one, dedup by target."""
    spans = [(s, e) for s, e in _sections(lines) if lines[s].strip() == RELATED_HEADING]
    if not spans:
        return lines, False

    first_s, first_e = spans[0]
    seen = set()
    section, deduped = _dedup_bullets(lines[first_s + 1:first_e], seen)
    extra, drop = [], []
    for s, e in spans[1:]:
        dupe = lines[s + 1:e]
        # A duplicate section holding prose is not ours to throw away.
        if any(l.strip() and not l.startswith('- ') for l in dupe):
            continue
        for l in dupe:
            if l.startswith('- ') and _bullet_key(l) not in seen:
                seen.add(_bullet_key(l))
                extra.append(l)
        drop.append((s, e))
    if not deduped and not drop:
        return lines, False

    last_bullet = max((i for i, l in enumerate(section) if l.startswith('- ')), default=-1)
    section = section[:last_bullet + 1] + extra + section[last_bullet + 1:]
    out = lines[:first_s + 1] + section + lines[first_e:]
    shift = len(out) - len(lines)  # every dropped span sits after the first section
    for s, e in reversed(drop):
        del out[s + shift:e + shift]
    return out, True


def drop_empty_dated_headings(lines: list[str]) -> tuple[list[str], int]:
    """Remove '## <text> YYYY-MM-DD' headings whose section holds no content."""
    removed = 0
    for s, e in reversed(_sections(lines)):
        if DATED_HEADING.match(lines[s]) and not any(l.strip() for l in lines[s + 1:e]):
            del lines[s:e]
            removed += 1
    return lines, removed


def clean_card_body(body: str) -> tuple[str, dict]:
    """Undo nightly append artifacts in a card body. Returns (body, fix_counts)."""
    lines = body.split('\n')
    fixes = {}
    lines, merged = merge_related(lines)
    if merged:
        fixes['related_merged'] = 1
    lines, removed = drop_empty_dated_headings(lines)
    if removed:
        fixes['empty_headers_removed'] = removed
    return '\n'.join(lines), fixes


def enforce(vault_dir: Path, schema: dict, apply=False, verbose=False):
    node_types = schema['node_types']
    type_aliases = get_type_aliases(schema)
    field_fixes = get_field_fixes(schema)
    region_fixes = schema.get('region_fixes', {})

    stats = {
        'total': 0, 'valid': 0, 'fixed': 0, 'needs_review': 0,
        'no_fm': 0, 'fixes': defaultdict(int), 'review_items': []
    }
    for md in walk_vault(vault_dir):
        rp = rel_path(md, vault_dir)
        stats['total'] += 1

        try:
            content = md.read_text(errors='replace')
        except Exception:
            continue

        fields, body, orig_lines = parse_frontmatter(content)
        if fields is None:
            stats['no_fm'] += 1
            continue

        changed = False
        issues = []

        # --- TYPE ---
        t = fields.get('type', '')
        if t in type_aliases:
            fields['type'] = type_aliases[t]
            changed = True
            stats['fixes']['type_alias'] += 1
        t = fields.get('type', '')
        if not t or t not in node_types:
            fields['type'] = infer_type(rp, schema)
            changed = True
            stats['fixes']['type_inferred'] += 1
        t = fields['type']
        tdef = node_types.get(t, {})

        # --- STATUS ---
        valid_s = tdef.get('status', [])
        cur_s = fields.get('status', '')
        # Apply field_fixes for status
        status_fixes = field_fixes.get('status', {})
        if cur_s and cur_s.lower() in status_fixes:
            fields['status'] = status_fixes[cur_s.lower()]
            changed = True
            stats['fixes']['status_fix'] += 1
            cur_s = fields['status']
        # Validate
        if valid_s and cur_s and cur_s not in valid_s:
            # Fall back to first valid status for this type
            fields['status'] = valid_s[0]
            changed = True
            stats['fixes']['status_remap'] += 1
        if not cur_s and valid_s:
            # Use status_defaults from schema, or first valid status
            defaults = get_status_defaults(schema)
            fields['status'] = defaults.get(t, defaults.get('default', valid_s[0]))
            changed = True
            stats['fixes']['status_default'] += 1

        # --- PRIORITY ---
        pri = fields.get('priority', '')
        priority_fixes = field_fixes.get('priority', {})
        if pri and pri.lower() in priority_fixes:
            fields['priority'] = priority_fixes[pri.lower()]
            changed = True
            stats['fixes']['priority_fix'] += 1

        # --- POTENTIAL ---
        pot = fields.get('potential', '')
        potential_fixes = field_fixes.get('potential', {})
        if pot and pot.lower() in potential_fixes:
            fields['potential'] = potential_fixes[pot.lower()]
            changed = True
            stats['fixes']['potential_fix'] += 1

        # --- REGION ---
        reg = fields.get('region', '')
        if isinstance(reg, str) and reg in region_fixes:
            fields['region'] = region_fixes[reg]
            changed = True
            stats['fixes']['region_fix'] += 1

        # --- DOMAIN ---
        if 'domain' not in fields or not fields['domain']:
            fields['domain'] = infer_domain(rp, schema)
            changed = True
            stats['fixes']['domain_add'] += 1

        # --- DESCRIPTION ---
        desc = fields.get('description', '')
        if not desc:
            first = body.strip().split('\n')[0].strip().lstrip('#').strip() if body.strip() else ''
            if first and 10 < len(first) < 200:
                fields['description'] = first
                changed = True
                stats['fixes']['desc_inferred'] += 1
            else:
                issues.append('missing description')
        elif isinstance(desc, str) and len(desc) > 20:
            collapsed = collapse_repeated_description(desc)
            if len(collapsed) < len(desc.strip()):
                fields['description'] = collapsed
                changed = True
                stats['fixes']['desc_dedup'] += 1
            # Hard cap — even a non-periodic bloated description must not survive.
            if len(fields['description']) > DESC_CAP:
                fields['description'] = cap_description(fields['description'])
                changed = True
                stats['fixes']['desc_truncated'] += 1

        # --- TAGS ---
        tags = fields.get('tags', '')
        if not tags or (isinstance(tags, list) and len(tags) == 0):
            issues.append('missing tags')

        # --- SYSTEM FIELDS ---
        today_str = date.today().isoformat()
        for sf, default in [('last_accessed', today_str), ('tier', 'warm'), ('relevance', 0.5)]:
            if sf not in fields or not fields[sf]:
                fields[sf] = default
                changed = True
                stats['fixes'][f'{sf}_add'] += 1

        # --- BODY (cards only) ---
        if rp.startswith('cards/'):
            new_body, body_fixes = clean_card_body(body)
            if body_fixes:
                body = new_body
                changed = True
                for k, v in body_fixes.items():
                    stats['fixes'][k] += v

        # --- WRITE ---
        if changed and apply:
            new_fm = write_frontmatter(fields, orig_lines)
            md.write_text(f"---\n{new_fm}\n---\n{body}")

        if changed:
            stats['fixed'] += 1
        if issues:
            stats['needs_review'] += 1
            if verbose:
                for i in issues:
                    stats['review_items'].append(f"{rp}: {i}")
        if not changed and not issues:
            stats['valid'] += 1

    dupes = collect_duplicate_groups(vault_dir, schema)
    return stats, dupes


def health_score(stats, dupes):
    total = max(stats['total'], 1)
    fm_ok = 1 - stats['no_fm'] / total
    valid_rate = (stats['valid'] + stats['fixed']) / total
    desc_miss = stats['fixes'].get('desc_inferred', 0) + len([r for r in stats.get('review_items', []) if 'description' in r])
    tags_miss = len([r for r in stats.get('review_items', []) if 'tags' in r])
    dup_count = sum(len(p) - 1 for p in dupes.values())

    score = 100.0
    score -= (1 - fm_ok) * 10
    score -= (1 - valid_rate) * 25
    score -= (desc_miss / total) * 20
    score -= (tags_miss / total) * 15
    score -= min(dup_count, 50) * 0.3
    score -= stats['needs_review'] / total * 10
    return max(0, round(score, 1))


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: enforce.py <vault-dir> <schema.json> [--apply] [--verbose]", file=sys.stderr)
        sys.exit(1)

    vault_dir = Path(args[0])
    schema_path = Path(args[1])
    apply = '--apply' in args
    verbose = '--verbose' in args

    schema = load_schema(schema_path)
    stats, dupes = enforce(vault_dir, schema, apply=apply, verbose=verbose)
    score = health_score(stats, dupes)

    mode = "APPLIED" if apply else "DRY RUN"
    print(f"\n{'='*55}")
    print(f"  AUTOGRAPH ENFORCE — {mode}")
    print(f"{'='*55}")
    print(f"  Total:          {stats['total']}")
    print(f"  Valid:           {stats['valid']}")
    print(f"  Auto-fixed:      {stats['fixed']}")
    print(f"  Needs review:    {stats['needs_review']}")
    print(f"  No frontmatter:  {stats['no_fm']}")
    print(f"\n  Fixes:")
    for k, v in sorted(stats['fixes'].items(), key=lambda x: -x[1]):
        print(f"    {k}: {v}")
    if dupes:
        dup_total = sum(len(p) - 1 for p in dupes.values())
        print(f"\n  Duplicates: {len(dupes)} slugs ({dup_total} extra files)")
        for (slug, domain, card_type), paths in sorted(dupes.items(), key=lambda x: -len(x[1]))[:15]:
            print(f"    {slug} [{domain}/{card_type}] ({len(paths)}x)")
    if verbose and stats.get('review_items'):
        print(f"\n  Review ({len(stats['review_items'])}):")
        for r in stats['review_items'][:20]:
            print(f"    {r}")

    print(f"\n  {'='*40}")
    print(f"  SCHEMA COMPLIANCE: {score}/100")
    print(f"  {'='*40}")

    out = vault_dir / '.graph' / 'enforce-report.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        'score': score, 'total': stats['total'], 'valid': stats['valid'],
        'fixed': stats['fixed'], 'review': stats['needs_review'],
        'duplicates': len(dupes), 'mode': mode,
        'fixes': dict(stats['fixes']),
    }, indent=2))
    print(f"  Report: {out}")


if __name__ == '__main__':
    main()
