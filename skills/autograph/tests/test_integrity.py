# /// script
# requires-python = ">=3.10"
# dependencies = ["PyYAML==6.0.3"]
# ///
import sys
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from common import parse_frontmatter, write_frontmatter, extract_wikilinks
from enforce import enforce
from graph import build_graph
from enforce import validate_cards
from dedup import merge_content
from moc import save_moc
from unittest.mock import patch

SCHEMA = {'node_types': {'note': {'required': ['description', 'tags'], 'status': ['active', 'archived']},
                         'index': {'required': ['description'], 'status': ['active']}},
          'domain_inference': {'notes/': 'knowledge'}, 'status_defaults': {'default': 'active'}}


class IntegrityTests(unittest.TestCase):
    def test_optional_empty_related_is_not_a_broken_list(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); p = root / 'a.md'
            for value in ('null', "''", '[]'):
                p.write_text(f'---\ntype: note\nstatus: active\ndescription: Good\ntags: [tag]\nrelated: {value}\n---\n')
                self.assertEqual(validate_cards(root, SCHEMA), [])
                required = {**SCHEMA, 'node_types': {'note': {**SCHEMA['node_types']['note'], 'required': ['related']}}}
                self.assertIn('missing related', {e['issue'] for e in validate_cards(root, required)})
            p.write_text('---\ntype: note\nstatus: active\ndescription: Good\ntags: [tag]\nrelated: not-a-list\n---\n')
            self.assertIn('related must be a list of strings', {e['issue'] for e in validate_cards(root, SCHEMA)})

    def test_quoted_keys_survive_roundtrip(self):
        fields = {'#note': 'Keep this fact', 'on': 'yes', '42': 'text', 'a: b': [1, 'two']}
        recovered, _, _ = parse_frontmatter('---\n' + write_frontmatter(fields, []) + '\n---\n', strict=True)
        self.assertEqual(recovered, fields)

    def test_merge_keys_require_explicit_resolution(self):
        with self.assertRaises(ValueError):
            parse_frontmatter('---\nbase: &base {type: note}\n<<: *base\n---\n', strict=True)

    def test_tag_writer_skips_malformed_card(self):
        from enrich import apply_tags
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); results = root / 'results'; results.mkdir()
            p = root / 'a.md'; p.write_text('---\nhandle: @invalid\n---\nKeep me')
            before = p.read_bytes()
            (results / 'batch-1-results.json').write_text(json.dumps({'results': [{'path': 'a.md', 'tags': ['tag']}]}))
            self.assertEqual(apply_tags(root, results), 0)
            self.assertEqual(p.read_bytes(), before)

    def test_supersede_skips_invalid_source_and_target(self):
        from supersede import apply_supersede
        for invalid in ('old', 'new'):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                for name, date in (('old', '2026-01-01'), ('new', '2026-02-01')):
                    (root / f'{name}.md').write_text(f'---\ntype: note\nupdated: {date}\n' + ('handle: @invalid\n' if name == invalid else '') + '---\nBody')
                before = [(root / f'{name}.md').read_bytes() for name in ('old', 'new')]
                self.assertEqual(apply_supersede(root, [{'current': 'new.md', 'superseded_candidates': ['old.md']}]), 0)
                self.assertEqual(before, [(root / f'{name}.md').read_bytes() for name in ('old', 'new')])

    def test_validator_rejects_yaml_scalar_and_list_type_mismatches(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); p = root / 'a.md'
            p.write_text('---\ntype: note\nstatus: false\ndescription: [not, text]\ntags: [true, 42]\n---\n')
            issues = {e['issue'] for e in validate_cards(root, SCHEMA)}
            self.assertTrue({'status must be a string', 'description must be a string', 'tags must be a list of strings'} <= issues)

    def test_optional_description_does_not_crash_enforce(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'a.md').write_text('---\ntype: daily\nstatus: active\n---\nBody')
            schema = {**SCHEMA, 'node_types': {'daily': {'required': [], 'status': ['active']}}}
            stats, _ = enforce(root, schema)
            self.assertEqual(stats['needs_review'], 0)

    def test_fence_with_trailing_text_does_not_close_code(self):
        self.assertEqual(extract_wikilinks('```md\n[[inside]]\n```not-a-close\n[[still-inside]]\n```\n[[outside]]'), [('outside', 'outside')])

    def test_relative_link_in_decomposed_unicode_directory(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); folder = root / 'cafe\u0301'; folder.mkdir()
            (folder / '_index.md').write_text('[[./child]]')
            (folder / 'child.md').write_text('# Child')
            report = build_graph(root, SCHEMA)
            self.assertEqual(report['broken_link_list'], [])
            self.assertEqual(report['nodes']['cafe\u0301/child']['incoming'], ['cafe\u0301/_index'])

    def test_invalid_merge_does_not_change_canonical(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / 'a.md', Path(d) / 'b.md'
            a.write_text('---\ntype: note\n---\nKeep me')
            b.write_text('---\nhandle: @invalid\n---\nImported')
            original = a.read_bytes()
            with self.assertRaises(ValueError):
                merge_content(a, [b])
            self.assertEqual(a.read_bytes(), original)

    def test_validator_checks_shape_without_writing_reports(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); p = root / 'a.md'
            p.write_text('---\ntype: note\nstatus: active\ndescription: Good\ntags: [tag]\nrelated: [[nested]]\n---\n')
            before = p.read_bytes()
            self.assertTrue(validate_cards(root, SCHEMA))
            self.assertEqual(p.read_bytes(), before)
            self.assertFalse((root / '.graph').exists())

    def test_moc_preserves_legacy_and_manual_sections_across_runs(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'MOC.md'; p.write_text('Legacy index and hand-edited facts')
            self.assertFalse(save_moc(p, '# Generated'))
            self.assertEqual(p.read_text(), 'Legacy index and hand-edited facts')
            q = Path(d) / 'new.md'
            save_moc(q, '---\ntype: index\n---\n# First')
            q.write_text(q.read_text() + '\n## Manual\nDo not lose this\n')
            save_moc(q, '---\ntype: index\n---\n# Second')
            save_moc(q, '---\ntype: index\n---\n# Third')
            self.assertIn('Do not lose this', q.read_text())
            self.assertIn('# Third', q.read_text())
            self.assertNotIn('# Second', q.read_text())
            self.assertEqual(q.read_text().count('type: index'), 1)

    def test_generated_review_commands_use_declared_dependency_runner(self):
        from orchestrate import cmd_dedup_prepare, cmd_link_prepare
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); graph = root / '.graph'; graph.mkdir()
            (graph / 'dedup-manifest.json').write_text(json.dumps({
                'clusters': [{'canonical': 'a.md', 'extras': ['b.md']}]
            }))
            cmd_dedup_prepare(root)
            scan = ({'a'}, {'a': 'a.md'}, {}, [{'path': 'a.md', 'domain': 'knowledge'}])
            with patch('orchestrate.scan_vault_for_links', return_value=scan):
                cmd_link_prepare(root)
            for filename, script, arguments in (
                ('dedup-review-input.json', 'dedup.py', '--apply-manifest'),
                ('link-review-input.json', 'enrich.py', 'swarm-links'),
            ):
                with self.subTest(filename=filename):
                    instructions = json.loads((graph / filename).read_text())['instructions']
                    self.assertRegex(instructions, rf'uv run (?:scripts/)?{script}')
                    self.assertIn(arguments, instructions)
                    self.assertNotIn('python3 ', instructions)

    def test_health_does_not_dispatch_implicit_mutations(self):
        from orchestrate import cmd_health
        with tempfile.TemporaryDirectory() as d, patch('orchestrate.run_script', return_value=(0, '{}')) as run:
            cmd_health(Path(d))
            self.assertEqual([c.args[0] for c in run.call_args_list], ['graph.py', 'enforce.py'])
            self.assertNotIn('--apply', str(run.call_args_list))

    def test_roundtrip_special_list_and_multiline(self):
        fields = {'type': 'note', 'tags': ['@handle', 'comma,value', 'on', '2026'],
                  'phone': '00123', 'count': 42,
                  'source_urls': ['https://example.test/?a=b&c=d'],
                  'description': 'first line\nsecond line',
                  'nested': {'value': 'keep [brackets]'}}
        raw = write_frontmatter(fields, [])
        recovered, _, _ = parse_frontmatter('---\n' + raw + '\n---\nBody')
        self.assertEqual(fields, recovered)

    def test_invalid_original_cannot_be_rewritten(self):
        with self.assertRaises(ValueError):
            write_frontmatter({'status': 'active'}, ['status: blocked', 'status: active'])

    def test_unknown_status_and_invalid_yaml_stay_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'notes').mkdir()
            p = root / 'notes/a.md'; p.write_text('---\ntype: note\nstatus: blocked\ndescription: A note\ntags: [a]\n---\nBody\n')
            q = root / 'notes/b.md'; q.write_text('---\ntype: note\nhandle: @broken\n---\nBody\n')
            before = [p.read_bytes(), q.read_bytes()]
            stats, _ = enforce(root, SCHEMA, apply=True)
            self.assertEqual(before, [p.read_bytes(), q.read_bytes()])
            self.assertGreaterEqual(stats['needs_review'], 2)

    def test_index_does_not_require_tags(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / '_index.md'; p.write_text('---\ntype: index\nstatus: active\ndescription: An index\n---\n')
            stats, _ = enforce(Path(d), SCHEMA)
            self.assertEqual(stats['needs_review'], 0)

    def test_code_examples_are_not_links(self):
        text = '[[real]] `[[inline]]`\n```md\n[[fenced]]\n```\n<!-- [[comment]] -->'
        self.assertEqual(extract_wikilinks(text), [('real', 'real')])

    def test_graph_metadata_relative_unicode_and_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / 'notes').mkdir()
            (root / 'notes/_index.md').write_text('---\ntype: index\nrelated: [notes/a]\n---\n')
            (root / 'notes/a.md').write_text('---\ntype: note\nrelated: ["./café", notes/absent]\n---\n`[[example]]`\n')
            (root / 'notes/cafe\u0301.md').write_text('# C\n')
            (root / 'notes/alone.md').write_text('# Alone\n')
            report = build_graph(root, SCHEMA)
            self.assertEqual(report['nodes']['notes/a']['incoming'], ['notes/_index'])
            self.assertEqual(report['nodes']['notes/cafe\u0301']['incoming'], ['notes/a'])
            self.assertEqual(report['broken_link_list'], [{'source': 'notes/a', 'target': 'notes/absent'}])
            self.assertEqual(report['isolated_list'], ['notes/alone'])


if __name__ == '__main__':
    unittest.main()
