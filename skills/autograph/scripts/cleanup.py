#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""
autograph cleanup - bounded-memory repair of bug-bloated descriptions.

A historic write_frontmatter bug could retain a folded description line while
writing its parsed value, doubling the field on every rewrite. Files can grow
large enough to OOM ordinary vault tools. This command streams frontmatter with
a hard line buffer, rewrites only repairable descriptions, and copies the body
byte-for-byte.

Usage:
  cleanup.py <vault-dir> [schema.json]            # dry run
  cleanup.py <vault-dir> [schema.json] --apply    # atomic repair
  cleanup.py <vault-dir> [schema.json] --verbose
"""

import os
import sys
import tempfile
from pathlib import Path

from common import (
    cap_description,
    collapse_repeated_description,
    format_field,
    get_description_max_chars,
    load_schema,
    rel_path,
    walk_vault,
)

CHUNK = 1 << 20
LINE_CAP = 1 << 16
BLOCK_SMALL = 4096
FM_MAX_LINES = 10_000


class LineStream:
    """Newline reader with bounded memory and access to its unread tail."""

    def __init__(self, handle, line_cap=LINE_CAP, chunk=CHUNK):
        self.handle = handle
        self.line_cap = line_cap
        self.chunk = chunk
        self.buf = b''
        self.eof = False

    def next_line(self):
        """Return ``(line_without_newline, truncated)`` or ``None`` at EOF."""
        head = None
        while True:
            newline = self.buf.find(b'\n')
            if newline >= 0:
                if head is not None:
                    line = (head, True)
                elif newline > self.line_cap:
                    line = (self.buf[:self.line_cap], True)
                else:
                    line = (self.buf[:newline], False)
                self.buf = self.buf[newline + 1:]
                return line
            if head is None and len(self.buf) > self.line_cap:
                head, self.buf = self.buf[:self.line_cap], b''
            elif head is not None:
                self.buf = b''
            if self.eof:
                if head is not None:
                    return head, True
                if self.buf:
                    line = (self.buf, False)
                    self.buf = b''
                    return line
                return None
            data = self.handle.read(self.chunk)
            if data:
                self.buf += data
            else:
                self.eof = True


def repeated_unit_from_prefix(sample: str) -> str | None:
    """Recover a substantial repeated unit from a truncated exact prefix."""
    sample = sample.strip()
    if len(sample) <= 40:
        return None
    probe = sample[:min(200, len(sample) // 2)]
    period = sample.find(probe, 1)
    if period <= 20 or period >= len(sample):
        return None
    if any(char != sample[index % period] for index, char in enumerate(sample)):
        return None
    return collapse_repeated_description(sample[:period].strip())


def _review(md: Path, old_size: int, reason: str) -> dict:
    return {
        'status': 'review',
        'path': str(md),
        'old_size': old_size,
        'new_size': old_size,
        'reason': reason,
    }


def clean_file(md: Path, apply: bool, max_chars: int | None = None) -> dict | None:
    """Inspect one card and optionally repair it with bounded memory.

    Returns a ``cleaned`` or ``review`` result, or ``None`` when no action is
    needed. A non-periodic giant description is only repairable when the schema
    cap fits inside the retained sample; otherwise it is reported for review.
    """
    if md.is_symlink():
        return _review(md, md.lstat().st_size, 'symlink is not modified')

    original_stat = md.stat()
    old_size = original_stat.st_size
    with md.open('rb') as handle:
        stream = LineStream(handle)
        first = stream.next_line()
        if first is None or first[1] or first[0].rstrip(b'\r') != b'---':
            return None

        output_lines = []
        changed = False
        description_lines = []
        description_sample = None
        description_header = None
        review_reason = None
        in_description = False
        closed = False

        def flush_description():
            nonlocal changed, review_reason
            if description_sample is not None:
                unit = repeated_unit_from_prefix(description_sample)
                if unit is not None:
                    value = cap_description(unit, max_chars)
                elif max_chars is not None and max_chars <= len(description_sample):
                    value = cap_description(description_sample, max_chars)
                else:
                    review_reason = (
                        'non-periodic oversized description requires an explicit '
                        'description_max_chars no larger than the retained sample'
                    )
                    return
                output_lines.append(format_field('description', value))
                changed = True
                return

            raw = ' '.join(description_lines).strip()
            value = cap_description(collapse_repeated_description(raw), max_chars)
            if value == raw:
                output_lines.append(description_header or 'description:')
                output_lines.extend('  ' + line for line in description_lines)
                return
            output_lines.append(format_field('description', value))
            changed = True

        while True:
            item = stream.next_line()
            if item is None:
                break
            if len(output_lines) + len(description_lines) > FM_MAX_LINES:
                return _review(md, old_size, 'frontmatter exceeds safety line limit')

            raw_line, truncated = item
            line = raw_line.decode('utf-8', errors='ignore')
            stripped = line.strip()
            indented = line.startswith(('  ', '\t'))

            if in_description and (indented or truncated):
                if truncated or len(line) > BLOCK_SMALL:
                    if description_sample is None:
                        prefix = ' '.join(description_lines + [stripped]).strip()
                        description_sample = prefix[:LINE_CAP]
                        description_lines = []
                elif description_sample is None:
                    description_lines.append(stripped)
                continue
            if in_description:
                flush_description()
                in_description = False
                description_lines, description_sample = [], None

            if not indented and line.rstrip('\r') == '---':
                closed = True
                break

            if not indented and stripped.startswith('description:'):
                value = stripped.partition(':')[2].strip()
                description_header = line
                if truncated:
                    description_sample = value.lstrip('\'"')[:LINE_CAP]
                    in_description = True
                    continue
                if value in ('>-', '>', '|-', '|', ''):
                    in_description = True
                    continue
                bare = value.strip('\'"')
                repaired = cap_description(collapse_repeated_description(bare), max_chars)
                if repaired != bare:
                    output_lines.append(format_field('description', repaired))
                    changed = True
                else:
                    output_lines.append(line)
                continue

            if truncated:
                return _review(md, old_size, 'oversized non-description frontmatter line')
            output_lines.append(line)

        if in_description:
            flush_description()
        if not closed:
            return _review(md, old_size, 'frontmatter closing delimiter not found')
        if review_reason is not None:
            return _review(md, old_size, review_reason)
        if not changed:
            return None

        frontmatter_size = sum(len(line.encode('utf-8')) + 1 for line in output_lines) + 8
        body_size = len(stream.buf) + max(0, old_size - handle.tell())
        projected_size = frontmatter_size + body_size
        if not apply:
            return {
                'status': 'cleaned',
                'path': str(md),
                'old_size': old_size,
                'new_size': projected_size,
                'reason': 'description repair',
            }

        current_stat = md.stat()
        if (current_stat.st_size != original_stat.st_size or
                current_stat.st_mtime_ns != original_stat.st_mtime_ns):
            return _review(md, old_size, 'file changed during cleanup')

        descriptor, temporary = tempfile.mkstemp(dir=str(md.parent), suffix='.tmp')
        try:
            os.fchmod(descriptor, original_stat.st_mode & 0o7777)
            with os.fdopen(descriptor, 'wb') as output:
                output.write(b'---\n')
                for output_line in output_lines:
                    output.write(output_line.encode('utf-8') + b'\n')
                output.write(b'---\n')
                output.write(stream.buf)
                while True:
                    chunk = handle.read(CHUNK)
                    if not chunk:
                        break
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, md)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    return {
        'status': 'cleaned',
        'path': str(md),
        'old_size': old_size,
        'new_size': md.stat().st_size,
        'reason': 'description repair',
    }


def main():
    args = sys.argv[1:]
    apply = '--apply' in args
    verbose = '--verbose' in args
    positional = [arg for arg in args if not arg.startswith('--')]
    if not positional or len(positional) > 2:
        print(__doc__)
        sys.exit(1)

    vault_dir = Path(positional[0]).resolve()
    schema_path = (Path(positional[1]) if len(positional) == 2
                   else vault_dir / 'schema.json')
    schema = load_schema(schema_path) if schema_path.exists() else {}
    try:
        max_chars = get_description_max_chars(schema)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(2)

    cleaned = 0
    review = 0
    saved = 0
    for md in walk_vault(vault_dir):
        try:
            result = clean_file(md, apply, max_chars)
        except Exception as error:
            print(f"  REVIEW {rel_path(md, vault_dir)}: {error}")
            review += 1
            continue
        if result is None:
            continue
        if result['status'] == 'review':
            review += 1
            print(f"  REVIEW {rel_path(md, vault_dir)}: {result['reason']}")
            continue
        cleaned += 1
        saved += result['old_size'] - result['new_size']
        if verbose or result['old_size'] > 1_000_000:
            action = 'cleaned' if apply else 'would clean'
            print(f"  {action} {rel_path(md, vault_dir)}: "
                  f"{result['old_size']:,} -> {result['new_size']:,} bytes")

    mode = 'applied' if apply else 'dry-run'
    suffix = '' if apply else ' - run with --apply to fix'
    print(f"cleanup ({mode}): {cleaned} repairable, {review} review, "
          f"{saved:,} bytes removable{suffix}")


if __name__ == '__main__':
    main()
