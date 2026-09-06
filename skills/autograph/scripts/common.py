# /// script
# requires-python = ">=3.10"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""
autograph common — shared utilities for all scripts.
Single source of truth. NO hardcoded domains, types, statuses, paths.
Everything reads from schema.json.
"""

import re
import posixpath
import unicodedata
import yaml
import json
from pathlib import Path
from datetime import date, datetime
from collections import defaultdict

# ─── CONSTANTS ─────────────────────────────────────────────
IGNORE_DIRS = frozenset({
    '.obsidian', 'attachments', '.git', '.graph',
    '.claude', '.trash', 'backup', 'archive', '__pycache__'
})

SCHEMA_FILENAME = 'schema.json'

# Scalar facts where a NEW differing value supersedes the old (recency wins);
# the losing value is recorded to ## History. Overridable via schema conflict_fields.
DEFAULT_CONFLICT_FIELDS = ["company", "role", "status", "handle",
                          "platform", "phone", "email", "title"]

# Same-entity detection for dedup/supersede grouping. Strong keys (exact normalized
# match on match_fields) union cards across different filenames. Name-only never
# groups (fuzzy off) — a false merge is worse than a duplicate.
DEFAULT_IDENTITY = {
    "match_fields": ["email", "telegram", "handle", "phone"],
    "same_domain_only": True,
    "same_type_only": True,
    "fuzzy_name": False,
    "ignore_values": ["", "n/a", "-", "none", "unknown"],
    "max_shared": 8,
}


# ─── SCHEMA ────────────────────────────────────────────────
_schema_cache = {}

def load_schema(schema_path: Path | str | None = None) -> dict:
    """Load schema.json. Caches after first load by resolved path.
    If no path given, looks in: CWD/schema.json → skill dir/schema.local.json → schema.json → schema.example.json"""
    if schema_path is not None:
        schema_path = Path(schema_path)
        key = str(schema_path.resolve())
        if key in _schema_cache:
            return _schema_cache[key]
    else:
        skill_dir = Path(__file__).parent.parent
        candidates = [
            Path.cwd() / SCHEMA_FILENAME,          # user's schema in CWD
            skill_dir / 'schema.local.json',        # local override FIRST
            skill_dir / SCHEMA_FILENAME,            # schema.json in skill dir
            skill_dir / 'schema.example.json',      # fallback example
        ]
        for c in candidates:
            if c.exists():
                schema_path = c
                break
        if schema_path is None:
            schema_path = skill_dir / SCHEMA_FILENAME  # will raise FileNotFoundError
        key = str(schema_path.resolve())
        if key in _schema_cache:
            return _schema_cache[key]

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")

    schema = json.loads(schema_path.read_text())
    _schema_cache[key] = schema
    return schema


def get_node_types(schema: dict) -> list[str]:
    """All valid node types."""
    return list(schema.get('node_types', {}).keys())


def get_valid_statuses(schema: dict, node_type: str) -> list[str]:
    """Valid statuses for a node type."""
    return schema.get('node_types', {}).get(node_type, {}).get('status', [])


def get_type_aliases(schema: dict) -> dict:
    """Type alias map (old → new)."""
    return schema.get('type_aliases', {})


def get_domain_map(schema: dict) -> dict:
    """Folder → domain mapping."""
    return schema.get('domain_inference', {})


def get_decay_config(schema: dict) -> dict:
    """Decay rate, floor, tier thresholds."""
    return schema.get('decay', {
        'rate': 0.015, 'floor': 0.1,
        'tiers': {'active': 7, 'warm': 21, 'cold': 60}
    })


def get_ignore_tags(schema: dict) -> set:
    """Tags to ignore (e.g. bulk import artifacts)."""
    return set(schema.get('ignore_tags', []))


def get_field_fixes(schema: dict) -> dict:
    """Field value normalizations."""
    return schema.get('field_fixes', {})


def get_path_type_hints(schema: dict) -> dict:
    """Folder substring → type name mapping for type inference."""
    hints = schema.get('path_type_hints', {})
    return {k: v for k, v in hints.items() if k != '_comment'}


def get_status_order(schema: dict) -> dict:
    """Status sort order for MOC generation."""
    order = schema.get('status_order', {})
    return {k: v for k, v in order.items() if k != '_comment'}


def get_status_defaults(schema: dict) -> dict:
    """Default status by type when status is missing."""
    defaults = schema.get('status_defaults', {})
    return {k: v for k, v in defaults.items() if k != '_comment'}


def get_richness_fields(schema: dict) -> list:
    """Frontmatter fields that indicate content richness (for dedup)."""
    cfg = schema.get('richness_fields', {})
    return cfg.get('bonus_fields', [])


def get_description_max_chars(schema: dict) -> int | None:
    """Return the optional schema-owned description limit.

    Missing means no truncation. Booleans are rejected explicitly because
    ``bool`` is an ``int`` subclass in Python and accepting ``true`` as a
    one-character limit would destroy descriptions.
    """
    value = schema.get('description_max_chars')
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError('description_max_chars must be a positive integer')
    return value


def get_raw_dirs(schema: dict) -> list[str]:
    """Return validated, boundary-safe raw-source directory prefixes.

    Values are relative POSIX directory paths. A trailing slash is normalized
    so callers can use exact prefix matching without treating ``daily-old/``
    as a child of ``daily/``.
    """
    values = schema.get('raw_dirs', [])
    if not isinstance(values, list):
        raise ValueError('raw_dirs must be an array of relative directory strings')

    normalized = []
    seen = set()
    for value in values:
        if not isinstance(value, str) or not value or value != value.strip():
            raise ValueError('raw_dirs entries must be non-empty trimmed strings')
        if ('\\' in value or value.startswith('/') or value.endswith('//') or
                re.match(r'^[A-Za-z]:', value)):
            raise ValueError(f'raw_dirs entry must be a relative POSIX directory: {value!r}')
        bare = value[:-1] if value.endswith('/') else value
        parts = bare.split('/')
        if not bare or any(part in ('', '.', '..') for part in parts):
            raise ValueError(f'raw_dirs entry contains an unsafe path segment: {value!r}')
        prefix = bare + '/'
        if prefix in seen:
            raise ValueError(f'raw_dirs contains a duplicate directory: {value!r}')
        seen.add(prefix)
        normalized.append(prefix)
    return normalized


def get_conflict_fields(schema: dict) -> list:
    """Scalar fields where differing values = temporal conflict (recency wins)."""
    cfg = schema.get('conflict_fields', {}) or {}
    return cfg.get('fields', DEFAULT_CONFLICT_FIELDS)


def get_identity_config(schema: dict) -> dict:
    """Same-entity detection config, defaults filled for any missing key."""
    cfg = {k: v for k, v in (schema.get('identity') or {}).items() if k != '_comment'}
    merged = dict(DEFAULT_IDENTITY)
    merged.update(cfg)
    return merged


def card_recency_date(fields: dict) -> str:
    """Recency key for a card: updated > created > last_accessed > ''."""
    fields = fields or {}
    return str(fields.get('updated') or fields.get('created')
               or fields.get('last_accessed') or '')


def normalize_identity_value(field: str, val) -> str:
    """Normalize an identity value for cross-card matching."""
    s = str(val).strip().lower()
    if field in ('telegram', 'handle'):
        s = s.lstrip('@')
    elif field == 'phone':
        s = re.sub(r'\D', '', s)
    else:
        s = re.sub(r'\s+', ' ', s)
    return s


def get_entity_extraction_config(schema: dict) -> dict:
    """Entity extraction settings for daily.py."""
    cfg = schema.get('entity_extraction', {})
    return {k: v for k, v in cfg.items() if k != '_comment'}


# ─── FRONTMATTER ───────────────────────────────────────────
class FrontmatterError(ValueError):
    """Invalid metadata; error messages deliberately omit document contents."""


class FrontmatterLoader(yaml.SafeLoader):
    # Keep dates textual while preserving actual YAML scalar/list/map types.
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            if key_node.tag == 'tag:yaml.org,2002:merge':
                raise FrontmatterError('YAML merge keys require explicit resolution before mutation')
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise FrontmatterError(f"Invalid or duplicate YAML key at line {key_node.start_mark.line + 1}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


FrontmatterLoader.add_constructor('tag:yaml.org,2002:timestamp',
                                  FrontmatterLoader.construct_scalar)


def load_frontmatter_yaml(raw: str) -> dict:
    try:
        fields = yaml.load(raw, Loader=FrontmatterLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, 'problem_mark', None)
        location = f" at line {mark.line + 1}" if mark else ""
        raise FrontmatterError("Invalid YAML frontmatter" + location) from None
    if fields is None or fields == '':
        return {}
    if not isinstance(fields, dict):
        raise FrontmatterError("Frontmatter must be a mapping")
    return {key: '' if value is None else value for key, value in fields.items()}


def parse_frontmatter(content: str, strict: bool = False) -> tuple[dict, str, list[str]]:
    """Read actual YAML; strict mutations reject malformed metadata.

    Read-only callers retain the original document as body when YAML is invalid.
    They must not interpret that result as permission to replace its metadata.
    """
    normalized = content.replace('\r\n', '\n').replace('\r', '\n')
    m = re.match(r'^---\n(.*?)\n---(?:\n|$)(.*)', normalized, re.DOTALL)
    if not m:
        if strict and normalized.startswith('---\n'):
            raise FrontmatterError("Unclosed frontmatter")
        return None, content, []
    try:
        fields = load_frontmatter_yaml(m.group(1))
    except FrontmatterError:
        if strict:
            raise
        return None, content, []
    return fields, m.group(2), m.group(1).split('\n')


def write_frontmatter(fields: dict, original_lines: list[str]) -> str:
    """Serialize complete metadata without losing nested values or list items."""
    original = load_frontmatter_yaml('\n'.join(original_lines)) if original_lines else {}
    values = {**original, **fields}
    comments = [line for line in original_lines if line.startswith('#')]
    result = '\n'.join(comments + [format_field(key, val) for key, val in values.items()])
    recovered = load_frontmatter_yaml(result)
    if recovered != values:
        raise FrontmatterError("Metadata serialization changed field names or values")
    return result


def collapse_repeated_description(desc: str) -> str:
    """Collapse a description made of the same substantial text N times.

    The old frontmatter writer could retain a folded continuation line while
    writing its parsed value, doubling descriptions on every rewrite. Halving
    repairs the common 2^N case, then a linear periodicity check catches odd
    repeat counts. Units of 20 characters or less are preserved because short
    repetition can be legitimate prose.
    """
    value = desc.strip()
    while len(value) > 40:
        half = len(value) // 2
        first = value[:half].strip()
        second = value[half:].strip()
        if first and first == second:
            value = first
        else:
            break

    probe = value + ' '
    period = (probe + probe).find(probe, 1)
    if 20 < period < len(probe) and len(probe) % period == 0:
        value = probe[:period].strip()
    return value


def cap_description(desc: str, max_chars: int | None) -> str:
    """Truncate a description only when the schema provides a limit."""
    if max_chars is None or len(desc) <= max_chars:
        return desc
    if max_chars == 1:
        return '…'
    head = desc[:max_chars - 1].rstrip()
    if ' ' in head:
        head = head.rsplit(' ', 1)[0].rstrip()
    return head + '…'


YAML_SPECIAL = re.compile(r"[\s:#\[\]{}\"',|>!&*?@\\\x00-\x1f]")


def format_field(key: str, val) -> str:
    """JSON quoting is valid YAML and preserves URLs, commas and newlines."""
    encoded_key = key if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9-]*', key) and isinstance(yaml.safe_load(key), str) else json.dumps(key, ensure_ascii=False)
    if key == 'description' and isinstance(val, str) and len(val) > 80 and '\n' not in val:
        return f'{encoded_key}: >-\n  {val}'
    def scalar(value):
        if isinstance(value, str) and value and not YAML_SPECIAL.search(value):
            if not value.startswith(('-', chr(96), '%')) and isinstance(yaml.safe_load(value), str):
                return value
        return json.dumps(value, ensure_ascii=False)
    if isinstance(val, list):
        return f"{encoded_key}: [{', '.join(scalar(v) for v in val)}]"
    return f"{encoded_key}: {scalar(val)}"


# ─── FILE OPERATIONS ───────────────────────────────────────
def walk_vault(vault_dir: Path) -> list[Path]:
    """Walk vault, yield all .md files, skipping IGNORE_DIRS."""
    results = []
    for md in sorted(vault_dir.rglob('*.md')):
        parts = set(md.relative_to(vault_dir).parts)
        if parts & IGNORE_DIRS:
            continue
        results.append(md)
    return results


def rel_path(md_file: Path, vault_dir: Path) -> str:
    """Relative path as string."""
    return str(md_file.relative_to(vault_dir))


def is_hub_path(path: str) -> bool:
    """Return True for hub notes like _index or MEMORY at any depth."""
    return Path(path).name in {'_index', '.index', 'MEMORY', '_projects-map', 'MOC'} or path.startswith('MOC/')


def build_link_index(vault_dir: Path, files: list[Path] | None = None) -> dict:
    """Build deterministic indexes for wikilink resolution."""
    files = files or walk_vault(vault_dir)
    exact = {}
    suffix_map = defaultdict(set)
    stem_map = defaultdict(set)

    for md in files:
        rp = rel_path(md, vault_dir)
        rp_noext = rp[:-3] if rp.endswith('.md') else rp
        exact[unicodedata.normalize('NFC', rp_noext)] = rp_noext
        stem_map[unicodedata.normalize('NFC', md.stem)].add(rp_noext)

        parts = rp_noext.split('/')
        for i in range(1, len(parts) - 1):
            suffix_map[unicodedata.normalize('NFC', '/'.join(parts[i:]))].add(rp_noext)

    return {
        'exact': exact,
        'unique_suffix': {k: next(iter(v)) for k, v in suffix_map.items() if len(v) == 1},
        'ambiguous_suffix': {k: sorted(v) for k, v in suffix_map.items() if len(v) > 1},
        'unique_stem': {k: next(iter(v)) for k, v in stem_map.items() if len(v) == 1},
        'ambiguous_stem': {k: sorted(v) for k, v in stem_map.items() if len(v) > 1},
    }


def normalize_link_target(target: str) -> str:
    """Normalize a wikilink target before resolution."""
    target = unicodedata.normalize('NFC', target.replace('\\', '').strip())
    if '#' in target:
        target = target.split('#', 1)[0].strip()
    if target.endswith('.md'):
        target = target[:-3]
    if target.startswith('vault/'):
        target = target[6:]
    return target


def resolve_link_target(target: str, link_index: dict, source: str = '') -> tuple[str | None, str]:
    """Resolve a target using exact path, unique suffix, then unique stem."""
    target = normalize_link_target(target)
    if not target:
        return None, 'empty'

    exact = link_index.get('exact', {})
    unique_suffix = link_index.get('unique_suffix', {})
    ambiguous_suffix = link_index.get('ambiguous_suffix', {})
    unique_stem = link_index.get('unique_stem', {})
    ambiguous_stem = link_index.get('ambiguous_stem', {})

    if source:
        relative = unicodedata.normalize('NFC', posixpath.normpath(posixpath.join(posixpath.dirname(source), target)))
        if target.startswith(('./', '../')):
            return (exact[relative], 'relative') if relative in exact else (None, 'missing')
    if target in exact:
        return exact[target], 'exact'
    if source and relative in exact:
        return exact[relative], 'relative'
    if target in unique_suffix:
        return unique_suffix[target], 'unique_suffix'
    if target in ambiguous_suffix:
        return None, 'ambiguous_suffix'

    stem = target.split('/')[-1]
    if '/' in target:
        return None, 'missing'
    if stem in unique_stem:
        return unique_stem[stem], 'unique_stem'
    if stem in ambiguous_stem:
        return None, 'ambiguous_stem'
    return None, 'missing'


# ─── DOMAIN INFERENCE ──────────────────────────────────────
def infer_domain(file_rel_path: str, schema: dict) -> str:
    """Infer domain from file path using schema's domain_inference map."""
    domain_map = get_domain_map(schema)
    for pattern, domain in domain_map.items():
        if file_rel_path.startswith(pattern):
            return domain
    return 'personal'  # default


# ─── TYPE INFERENCE ────────────────────────────────────────
def infer_type(file_rel_path: str, schema: dict) -> str:
    """Infer card type from file path using schema's node_types + path_type_hints.
    No hardcoded values — uses schema data only."""
    valid_types = set(get_node_types(schema))
    rp = file_rel_path.lower()

    # Try to match path keywords against known type names
    for type_name in valid_types:
        if f'{type_name}/' in rp or rp.startswith(f'{type_name}/'):
            return type_name

    # Check path_type_hints from schema
    for pattern, hint_type in get_path_type_hints(schema).items():
        if f'/{pattern}' in rp or rp.startswith(pattern):
            return hint_type if hint_type in valid_types else 'note'

    # Default to first type or 'note'
    return 'note' if 'note' in valid_types else (list(valid_types)[0] if valid_types else 'note')


def collect_duplicate_groups(vault_dir: Path, schema: dict | None = None,
                             files: list[Path] | None = None,
                             ignored_stems: set[str] | None = None) -> dict[tuple[str, str, str], list[str]]:
    """Group compatible duplicates.

    Base: same stem, domain, and type (backward-compatible with earlier behavior).
    When the schema defines an `identity` block, cards that share a strong identity
    key (same normalized email/telegram/handle/phone) are additionally unioned across
    different filenames — same-entity detection. Name-only never groups. Safety-first:
    when in doubt, do NOT group (a false merge is worse than a duplicate).
    """
    schema = schema or {}
    files = files or walk_vault(vault_dir)
    ignored_stems = ignored_stems or {'_index', 'MEMORY'}

    records = []
    for md in files:
        if md.stem in ignored_stems:
            continue
        rp = rel_path(md, vault_dir)
        try:
            content = md.read_text(errors='replace')
        except Exception:
            content = ''
        fm, _, _ = parse_frontmatter(content)
        if fm is None:
            fm = {}
        records.append({
            'rp': rp, 'stem': md.stem,
            'domain': str(fm.get('domain') or infer_domain(rp, schema)),
            'type': str(fm.get('type') or infer_type(rp, schema)),
            'fm': fm,
        })

    # union-find over record indices
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # seed: exact (stem, domain, type)
    exact = defaultdict(list)
    for i, r in enumerate(records):
        exact[(r['stem'], r['domain'], r['type'])].append(i)
    for idxs in exact.values():
        for j in idxs[1:]:
            union(idxs[0], j)

    # entity-identity: opt-in via schema `identity` block
    if schema.get('identity'):
        ident = get_identity_config(schema)
        ignore = set(ident['ignore_values'])
        by_key = defaultdict(list)
        for i, r in enumerate(records):
            for f in ident['match_fields']:
                v = r['fm'].get(f)
                if v is None or isinstance(v, (list, dict)):
                    continue
                nv = normalize_identity_value(f, v)
                if not nv or nv in ignore:
                    continue
                by_key[(f, nv)].append(i)
        for idxs in by_key.values():
            # generic/shared value (too many cards) → don't group
            if len(idxs) < 2 or len(idxs) > ident['max_shared']:
                continue
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    ia, ib = idxs[a], idxs[b]
                    if ident['same_type_only'] and records[ia]['type'] != records[ib]['type']:
                        continue
                    if ident['same_domain_only'] and records[ia]['domain'] != records[ib]['domain']:
                        continue
                    union(ia, ib)

    # assemble components with >1 member; key = first member's (stem, domain, type),
    # which is unique per component (a given tuple lives in exactly one component).
    comps = defaultdict(list)
    for i in range(len(records)):
        comps[find(i)].append(i)

    result = {}
    for idxs in comps.values():
        if len(idxs) < 2:
            continue
        rep = records[idxs[0]]
        result[(rep['stem'], rep['domain'], rep['type'])] = [records[i]['rp'] for i in idxs]
    return result


# ─── WIKILINKS ─────────────────────────────────────────────
def extract_wikilinks(text: str) -> list[tuple[str, str]]:
    """Extract wikilinks as [(target, display_name), ...].
    Handles [[target]], [[target|display]], and [[target#heading]]."""
    # Literal examples are not graph edges.
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    lines = []
    fence = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^\s{0,3}(\x60{3,}|~{3,})', line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not line[marker.end():].strip():
                fence = None
            continue
        if fence is None:
            lines.append(line)
    text = re.sub(r'(\x60+)(.+?)\1', '', ''.join(lines), flags=re.DOTALL)
    results = []
    for m in re.finditer(r'\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]', text):
        target = m.group(1).strip()
        # Strip #anchor — file target only
        if '#' in target:
            target = target.split('#')[0].strip()
        if not target:
            continue
        display = m.group(2) or target
        results.append((target, display.strip()))
    return results


# ─── DECAY ─────────────────────────────────────────────────
def calc_relevance(days_since_access: int, schema: dict,
                   access_count: int = 1, file_type: str = '') -> float:
    """Ebbinghaus-inspired: more retrievals = slower forgetting.
    strength = 1 + ln(access_count) → effective_rate = rate / strength
    """
    from math import log
    config = get_decay_config(schema)
    # Domain-specific rate or default (filter _comment keys)
    domain_rates = {k: v for k, v in config.get('domain_rates', {}).items()
                    if k != '_comment'}
    rate = domain_rates.get(file_type, config.get('rate', 0.015))
    floor = config.get('floor', 0.1)
    # Ebbinghaus spacing effect
    strength = 1.0 + log(max(access_count, 1))
    effective_rate = rate / strength
    return max(floor, round(1.0 - effective_rate * days_since_access, 3))


def calc_tier(days_since_access: int, schema: dict, current_tier: str = '') -> str:
    """Calculate tier based on days since last access."""
    if current_tier == 'core':
        return 'core'  # never auto-demoted
    config = get_decay_config(schema)
    tiers = config.get('tiers', {'active': 7, 'warm': 21, 'cold': 60})
    if days_since_access <= tiers.get('active', 7):
        return 'active'
    if days_since_access <= tiers.get('warm', 21):
        return 'warm'
    if days_since_access <= tiers.get('cold', 60):
        return 'cold'
    return 'archive'


def days_since(date_str: str) -> int:
    """Days between a date string and today."""
    if not date_str:
        return 999
    try:
        dt = datetime.strptime(date_str[:10], '%Y-%m-%d').date()
        return (date.today() - dt).days
    except (ValueError, TypeError):
        return 999
