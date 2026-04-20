#!/usr/bin/env python3
"""
autograph dedup — find duplicate entities, pick canonical (richest content wins),
merge unique data, redirect links, move extras to .trash/.

Usage:
  python3 dedup.py <vault-dir>                    # report only
  python3 dedup.py <vault-dir> --apply             # merge + redirect
  python3 dedup.py <vault-dir> --apply --verbose

Safety:
  - NEVER deletes files. Moves extras to <vault>/.trash/dedup-YYYY-MM-DD/
  - Merges unique content from extras INTO canonical before moving
  - Logs every action to <vault>/.graph/dedup-log.jsonl
"""

import re
import sys
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

from common import (
    parse_frontmatter, walk_vault, rel_path, IGNORE_DIRS,
    load_schema, get_richness_fields, collect_duplicate_groups, write_frontmatter
)


def content_richness(content: str, bonus_fields: list | None = None) -> int:
    """Score content by information density. PRIMARY signal for canonical pick."""
    fm, body, _ = parse_frontmatter(content)
    if fm is None:
        fm = {}
    score = 0
    # Body length (main signal)
    score += len(body.strip())
    # Description quality
    desc = fm.get('description', '')
    if isinstance(desc, str):
        score += len(desc) * 2
    # Tags
    tags = fm.get('tags', [])
    if isinstance(tags, list):
        score += len(tags) * 10
    # Status presence
    if fm.get('status'):
        score += 20
    # Rich fields from schema
    for field in (bonus_fields or []):
        if fm.get(field):
            score += 15
    return score


def pick_canonical(paths: list[str], vault_dir: Path, bonus_fields: list | None = None) -> tuple[str, list[str]]:
    """Pick richest file as canonical. Content richness = primary, folder depth = tiebreaker."""
    scored = []
    for p in paths:
        try:
            content = (vault_dir / p).read_text(errors='replace')
        except Exception:
            content = ''
        richness = content_richness(content, bonus_fields)
        # Tiebreaker: shallower paths preferred (fewer '/' = more canonical location)
        depth_score = -p.count('/')
        scored.append((richness, depth_score, p))

    scored.sort(key=lambda x: (-x[0], -x[1]))
    canonical = scored[0][2]
    extras = [s[2] for s in scored[1:]]
    return canonical, extras


def merge_content(canonical_path: Path, extra_paths: list[Path]) -> bool:
    """Merge unique info from extras into canonical. Returns True if changed."""
    canon_content = canonical_path.read_text(errors='replace')
    canon_fm, canon_body, canon_lines = parse_frontmatter(canon_content)
    if canon_fm is None:
        canon_fm = {}
    changed = False

    for extra_path in extra_paths:
        try:
            extra_content = extra_path.read_text(errors='replace')
        except Exception:
            continue
        extra_fm, extra_body, _ = parse_frontmatter(extra_content)
        if extra_fm is None:
            extra_fm = {}

        # Merge frontmatter: take richer/non-empty values
        for key, val in extra_fm.items():
            canon_val = canon_fm.get(key, '')
            if not canon_val and val:
                canon_fm[key] = val
                changed = True
            elif isinstance(val, str) and isinstance(canon_val, str) and len(val) > len(canon_val) * 1.5:
                canon_fm[key] = val
                changed = True
            elif isinstance(val, list) and isinstance(canon_val, list) and len(val) > len(canon_val):
                merged = list(dict.fromkeys(canon_val + val))
                if merged != canon_val:
                    canon_fm[key] = merged
                    changed = True

        # Merge unique body sections
        extra_sections = set(re.findall(r'^## (.+)$', extra_body, re.MULTILINE))
        canon_sections = set(re.findall(r'^## (.+)$', canon_body, re.MULTILINE))
        for section_name in extra_sections - canon_sections:
            pattern = rf'^## {re.escape(section_name)}\n(.*?)(?=\n## |\Z)'
            m = re.search(pattern, extra_body, re.MULTILINE | re.DOTALL)
            if m:
                canon_body = canon_body.rstrip() + '\n\n' + m.group(0).strip() + '\n'
                changed = True

    if changed:
        new_fm = write_frontmatter(canon_fm, canon_lines)
        canonical_path.write_text(f"---\n{new_fm}\n---\n{canon_body}")

    return changed


def redirect_links(vault_dir: Path, old_paths: list[str], canonical: str) -> int:
    """Update wikilinks pointing to old paths → canonical."""
    canonical_noext = canonical.replace('.md', '')

    old_refs = set()
    for old in old_paths:
        old_noext = old.replace('.md', '')
        old_refs.add(old_noext)
        old_refs.add(Path(old).stem)
        parts = old_noext.split('/')
        for i in range(len(parts)):
            old_refs.add('/'.join(parts[i:]))

    # Don't redirect canonical references
    canon_parts = canonical_noext.split('/')
    for i in range(len(canon_parts)):
        old_refs.discard('/'.join(canon_parts[i:]))
    old_refs.discard(Path(canonical).stem)

    if not old_refs:
        return 0

    count = 0
    for md in walk_vault(vault_dir):
        try:
            content = md.read_text(errors='replace')
        except Exception:
            continue

        new_content = content
        for old_ref in old_refs:
            pattern = re.compile(r'\[\[' + re.escape(old_ref) + r'(\|[^\]]+)?\]\]')
            if pattern.search(new_content):
                new_content = pattern.sub(
                    lambda m: f'[[{canonical_noext}{m.group(1) or ""}]]',
                    new_content
                )
                count += 1

        if new_content != content:
            md.write_text(new_content)

    return count


def dedup(vault_dir: Path, apply=False, verbose=False):
    today = datetime.now().strftime('%Y-%m-%d')
    trash_dir = vault_dir / '.trash' / f'dedup-{today}'
    log_path = vault_dir / '.graph' / 'dedup-log.jsonl'

    # Load schema for richness fields
    try:
        schema = load_schema()
    except FileNotFoundError:
        schema = {}
    bonus_fields = get_richness_fields(schema)

    # Find only safe duplicates: same stem + domain + type
    dupes = collect_duplicate_groups(vault_dir, schema)

    if not dupes:
        print("No duplicates found.")
        return

    total_extra = sum(len(paths) - 1 for paths in dupes.values())

    print(f"\n{'='*55}")
    print(f"  AUTOGRAPH DEDUP — {'APPLY' if apply else 'DRY RUN'}")
    print(f"{'='*55}")
    print(f"  Duplicate groups: {len(dupes)}")
    print(f"  Extra files:      {total_extra}")

    log_file = None
    if apply:
        trash_dir.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(exist_ok=True)
        log_file = open(log_path, 'a')

    merged_count = 0
    content_merged = 0
    links_redirected = 0
    moved_count = 0

    for (slug, domain, card_type), paths in sorted(dupes.items(), key=lambda x: (-len(x[1]), x[0])):
        canonical, extras = pick_canonical(paths, vault_dir, bonus_fields)

        if verbose:
            canon_rich = content_richness((vault_dir / canonical).read_text(errors='replace'), bonus_fields)
            print(f"\n  {slug} [{domain}/{card_type}] ({len(paths)}x):")
            print(f"    KEEP: {canonical} (richness={canon_rich})")
            for e in extras:
                e_rich = content_richness((vault_dir / e).read_text(errors='replace'), bonus_fields)
                print(f"    MOVE: {e} (richness={e_rich})")

        if apply:
            extra_full = [vault_dir / e for e in extras]
            did_merge = merge_content(vault_dir / canonical, extra_full)
            if did_merge:
                content_merged += 1

            lr = redirect_links(vault_dir, extras, canonical)
            links_redirected += lr

            for extra in extras:
                src = vault_dir / extra
                dest = trash_dir / extra
                dest.parent.mkdir(parents=True, exist_ok=True)
                src.rename(dest)
                moved_count += 1

            if log_file:
                log_file.write(json.dumps({
                    'ts': datetime.now().isoformat(), 'slug': slug,
                    'domain': domain, 'type': card_type,
                    'canonical': canonical, 'moved': extras,
                    'content_merged': did_merge, 'links_redirected': lr,
                }, ensure_ascii=False) + '\n')

        merged_count += 1

    if log_file:
        log_file.close()

    print(f"\n  Results:")
    print(f"    Slugs processed:    {merged_count}")
    if apply:
        print(f"    Content merged:     {content_merged}")
        print(f"    Links redirected:   {links_redirected}")
        print(f"    Files moved:        {moved_count} → {trash_dir}")
        print(f"    Log:                {log_path}")
    else:
        print(f"    Would move:         {total_extra} files to .trash/")

    out = vault_dir / '.graph' / 'dedup-report.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        'date': today, 'duplicates': len(dupes), 'extra_files': total_extra,
        'merged': merged_count, 'moved': moved_count if apply else 0,
        'content_merged': content_merged if apply else 0,
    }, indent=2, ensure_ascii=False))
    print(f"    Report:             {out}")


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        print("Usage: dedup.py <vault-dir> [--apply] [--verbose]", file=sys.stderr)
        sys.exit(1)
    dedup(Path(args[0]), '--apply' in args, '--verbose' in args)
