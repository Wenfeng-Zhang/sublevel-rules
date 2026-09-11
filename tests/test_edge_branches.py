# -*- coding: utf-8 -*-
"""Edge cases and error branches: pinning down the paths that normal business
flows never reach but that still have to be correct.

Most of these only appear on exception or defensive paths (frame file deleted,
adapter import failure, cache hit, case sensitive matching...). They are the
library's safety net and the first thing a refactor breaks silently.
"""

import io
import tempfile
import unittest

from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from sublevel_rules.cli import main
from sublevel_rules.errors import RuleDefinitionError
from sublevel_rules.operations import build_operations, get_sub_level_op
from sublevel_rules.paths import Entry
from sublevel_rules.resolver import resolve
from sublevel_rules.rule_dict import rule_to_dict
from sublevel_rules.rules import Action, Group, Level, Rule
from sublevel_rules.sequences import SequentialFiles

from .support import make_dir, touch


class EdgeTestCase(unittest.TestCase):

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def names(self, matches):
        return sorted(match.name for match in matches)


# --------------------------------------------------------------------------
# CLI corners
# --------------------------------------------------------------------------
class CliEdgeTest(EdgeTestCase):

    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue()

    def test_adapter_import_error_is_skipped(self):
        """When one *_rules.py fails to import (missing dependency) it is skipped
        without affecting the other adapters."""
        import sublevel_rules.cli as cli

        cached = cli._EXTRA_LOADER_CACHE
        cli._EXTRA_LOADER_CACHE = None
        try:
            with mock.patch.object(cli.importlib, 'import_module',
                                   side_effect=ImportError('boom')):
                self.assertEqual(cli._extra_rule_loaders(), {})
        finally:
            cli._EXTRA_LOADER_CACHE = cached

    def test_without_preset_or_rules_falls_back_to_mod(self):
        touch(self.root, 'asset_mod_v001.abc')
        code, output = self._run([str(self.root), '--version-part', '001', '--json'])
        self.assertEqual(code, 0)
        self.assertIn('asset_mod_v001.abc', output)

    def test_missing_version_path_and_no_describe_errors(self):
        with self.assertRaises(SystemExit):
            self._run(['--json'])

    def test_describe_without_rules_uses_default_preset(self):
        code, output = self._run(['--describe'])
        self.assertEqual(code, 0)
        self.assertIn('Group(', output)


# --------------------------------------------------------------------------
# data assembly: vanished files / several files in one directory / custom resolver
# --------------------------------------------------------------------------
class OperationsEdgeTest(EdgeTestCase):

    def test_size_when_frame_files_are_gone(self):
        """Measuring the size must not blow up when the frame files are deleted
        after resolution (a cleaned up publish folder)."""
        touch(self.root, 'cache/v001/c.0001.abc')
        rules = Group(Rule(Level('cache'), Level('v001'),
                           Action('*.abc', method='ani', is_sequence=True)))
        matches = resolve(rules, self.root)
        (self.root / 'cache/v001/c.0001.abc').unlink()

        for mode in ('first', 'total'):
            operations = build_operations(matches, str(self.root), {},
                                          size_mode=mode, group_mode=None)
            self.assertIsInstance(operations[0]['size'], str, mode)

    def test_nested_group_reuses_node_for_siblings(self):
        """The second file in the same directory reuses the node built earlier."""
        touch(self.root, 'cache/v001/a.abc', 'cache/v001/b.abc')
        rules = Group(Rule(Level('cache'), Level('v001'),
                           Action('*.abc', method='geo', mode='multiple')))
        operations = build_operations(resolve(rules, self.root), str(self.root), {},
                                      size_mode='none', group_mode='nested')

        v001 = operations[0]['children'][0]
        self.assertEqual(v001['filename'], 'cache/v001')
        self.assertEqual(sorted(item['filename'] for item in v001['children']),
                         ['a.abc', 'b.abc'])

    def test_get_sub_level_op_with_custom_op_resolver(self):
        touch(self.root, 'a.ma')

        class FakeModule(object):
            @staticmethod
            def get_import_rules():
                return Group(Action('*.ma', method='geo'))

            @staticmethod
            def create_api_version(method):
                return lambda *args, **kwargs: 'from-module'

        operations = get_sub_level_op(
            FakeModule, {'path': str(self.root)}, size_mode='none',
            op_resolver=lambda method: (lambda *args, **kwargs: 'from-resolver'))

        self.assertEqual(operations[0]['op_func'](), 'from-resolver')


# --------------------------------------------------------------------------
# path layer: hand-built Entry (no DirEntry cache)
# --------------------------------------------------------------------------
class PathsEdgeTest(EdgeTestCase):

    def test_is_dir_without_dir_entry(self):
        make_dir(self.root, 'sub')
        self.assertTrue(Entry(self.root / 'sub').is_dir())
        self.assertFalse(Entry(self.root / 'sub').is_file())

    def test_repr(self):
        self.assertIn('a.ma', repr(Entry('a.ma')))

    def test_equality_with_invalid_path_value(self):
        """An invalid path (empty string) on the other side returns NotImplemented
        instead of raising."""
        entry = Entry('a.ma')
        self.assertFalse(entry == '')
        self.assertTrue(entry != '')


# --------------------------------------------------------------------------
# resolver: properties, structure errors, final level collect, require_content
# probe, cache
# --------------------------------------------------------------------------
class ResolverEdgeTest(EdgeTestCase):

    def test_match_entry_and_frame_pattern_properties(self):
        touch(self.root, 'a.0001.exr')
        rules = Group(Action('*.exr', method='tex', is_sequence=True,
                             frame_pattern='#'))
        match = resolve(rules, self.root)[0]

        self.assertEqual(match.entry.name, 'a.####.exr')
        self.assertEqual(match.frame_pattern, '#')

    def test_unknown_kind_is_rejected(self):
        class Weird(object):
            kind = 'weird'
            options = {}

        with self.assertRaises(RuleDefinitionError):
            resolve(Weird(), self.root)

    def test_collect_on_bare_action_in_group(self):
        """A bare Action inside a Group can carry collect too (same behaviour as
        the Action at the end of a Rule)."""
        touch(self.root, 'a.ma', 'notes.txt')
        rules = Group(Action('*.ma', method='geo',
                             collect=Action('*.txt', method='readme')))
        self.assertEqual(self.names(resolve(rules, self.root)), ['a.ma', 'notes.txt'])

    def test_collect_on_rule_last_level_action(self):
        """An Action at the end of a Rule chain with collect lands in its own
        directory."""
        touch(self.root, 'cache/a.ma', 'cache/notes.txt')
        rules = Group(Rule(Level('cache'),
                           Action('*.ma', method='geo',
                                  collect=Action('*.txt', method='readme'))))
        self.assertEqual(self.names(resolve(rules, self.root)), ['a.ma', 'notes.txt'])

    def test_require_content_probes_the_next_level(self):
        touch(self.root, 'cache/v001/a.abc')
        rules = Group(Rule(
            Level('cache', require_content=True),
            Level('v001'),
            Action('*.abc', method='geo'),
        ))
        self.assertEqual(self.names(resolve(rules, self.root)), ['a.abc'])

    def test_require_content_treats_optional_next_level_as_content(self):
        """When the next level is optional, its absence still counts as "can go
        on"."""
        touch(self.root, 'cache/a.abc')
        rules = Group(Rule(
            Level('cache', require_content=True),
            Level('v001', optional=True),
            Action('*.abc', method='geo'),
        ))
        self.assertEqual(self.names(resolve(rules, self.root)), ['a.abc'])

    def test_collect_files_on_file_path_returns_empty(self):
        """When a level matched a file, collecting at the last level safely does
        nothing."""
        touch(self.root, 'a.ma')
        rules = Group(Rule(Level('*'), Action('*.ma', method='geo')))
        self.assertEqual(resolve(rules, self.root), [])

    def test_directory_listing_cache_is_reused(self):
        """Two branches pointing at the same directory list it only once (cache
        hit)."""
        touch(self.root, 'cache/v001/a.abc')
        rules = Group(
            Rule(Level('cache'), Level('v001'), Action('*.abc', method='geo')),
            Rule(Level('cache'), Level('v001'), Action('*.abc', method='ani')),
        )
        self.assertEqual(len(resolve(rules, self.root)), 2)

    def test_dedupe_with_case_sensitive(self):
        touch(self.root, 'a.ma')
        rules = Group(
            Action('a.ma', method='geo'),
            Action('a.ma', method='geo'),
        )
        self.assertEqual(len(resolve(rules, self.root, case_sensitive=True)), 1)


# --------------------------------------------------------------------------
# odds and ends of DSL / dict / sequences
# --------------------------------------------------------------------------
class DslEdgeTest(EdgeTestCase):

    def test_patterns_accept_a_single_non_string_object(self):
        # Platform independent: everything becomes str (a\b on Windows, a/b on POSIX).
        self.assertEqual(Level(Path('a/b')).patterns, (str(Path('a/b')),))

    def test_invalid_collect_scope_is_rejected(self):
        with self.assertRaises(RuleDefinitionError):
            Level('tex', collect_scope='somewhere')

    def test_rule_to_dict_keeps_level_options(self):
        data = rule_to_dict(Level('cache', tag='x'))
        self.assertEqual(data['options'], {'tag': 'x'})

    def test_sequential_files_ext(self):
        sequence = SequentialFiles(Entry('a.%04d.exr'), [1], [])
        self.assertEqual(sequence.ext, '.exr')
        self.assertEqual(sequence.path.name, 'a.%04d.exr')


if __name__ == '__main__':
    unittest.main()
