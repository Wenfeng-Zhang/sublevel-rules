# -*- coding: utf-8 -*-
"""Combination coverage: the semantic dimensions of a rule show up in
**combinations**, so this file focuses on exactly that.

Each module's own tests answer "is this single feature correct"; this file answers
a different question: "are these switches still correct when combined two or three
at a time".

Dimensions covered:

* ``Level.mode`` x ``optional`` x ``require_content`` x directory shape;
* ``collect`` x ``collect_scope`` x ``mode``;
* the ``Group(mode='first')`` fallback chain x mutex / nesting / sequence branch;
* ``Action.mode`` x ``is_sequence`` x ``files_only``;
* ``build_operations`` ``size_mode`` x grouping x ``extra_fields``;
* plus a batch of error / edge branches that are easy to miss.
"""

import os
import subprocess
import sys
import tempfile
import unittest

from pathlib import Path
from unittest import mock as mock_module

from sublevel_rules.errors import (
    ParameterError,
    RuleDefinitionError,
    SubLevelRulesError,
)
from sublevel_rules.operations import build_operations
from sublevel_rules.paths import Entry, as_path, list_entries
from sublevel_rules.resolver import Resolver, resolve
from sublevel_rules.rule_dict import rule_from_dict, rule_to_dict
from sublevel_rules.rules import Action, Group, Level, Multi, Rule, describe_rule

from .support import make_dir, touch


class ComboTestCase(unittest.TestCase):

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def names(self, matches):
        return [match.name for match in matches]


# --------------------------------------------------------------------------
# selection semantics combined: mode x optional x require_content x directory shape
# --------------------------------------------------------------------------
class SelectionComboTest(ComboTestCase):

    def _rules(self, mode='first', optional=False, require_content=False):
        return Group(Rule(
            Level('cache'),
            Level('v*', mode=mode, optional=optional,
                  require_content=require_content),
            Action('*.abc', method='geo'),
        ))

    def test_latest_plus_require_content_skips_empty_latest(self):
        make_dir(self.root, 'cache/v010')                    # the newest one is empty
        touch(self.root, 'cache/v009/a.abc')
        matches = resolve(self._rules('latest', require_content=True), self.root)
        self.assertEqual(self.names(matches), ['a.abc'])

    def test_latest_plus_optional_when_no_version_dir(self):
        touch(self.root, 'cache/a.abc')                      # no version level at all
        matches = resolve(self._rules('latest', optional=True), self.root)
        self.assertEqual(self.names(matches), ['a.abc'])

    def test_latest_plus_optional_plus_require_content(self):
        make_dir(self.root, 'cache/v010')
        touch(self.root, 'cache/v009/a.abc')
        matches = resolve(self._rules('latest', optional=True, require_content=True),
                          self.root)
        self.assertEqual(self.names(matches), ['a.abc'])

    def test_multiple_plus_require_content_keeps_only_non_empty(self):
        make_dir(self.root, 'cache/v001')
        touch(self.root, 'cache/v002/b.abc', 'cache/v003/c.abc')
        matches = resolve(self._rules('multiple', require_content=True), self.root)
        self.assertEqual(sorted(self.names(matches)), ['b.abc', 'c.abc'])

    def test_first_require_content_falls_through_to_next_pattern(self):
        """When every directory matched by the first pattern is empty, the later
        patterns should still be tried."""
        make_dir(self.root, 'cache/empty')
        touch(self.root, 'cache/v001/a.abc')
        rules = Group(Rule(
            Level('cache'),
            Level(['empty', 'v*'], mode='first', require_content=True),
            Action('*.abc', method='geo'),
        ))
        self.assertEqual(self.names(resolve(rules, self.root)), ['a.abc'])

    def test_require_content_uses_inherited_options(self):
        """The probe must use the same options as the real collection, otherwise a
        directory that does have content is mistaken for an empty one."""
        touch(self.root, 'cache/abc.0001.abc', 'cache/abc.0002.abc')
        rules = Group(
            Rule(Level('cache', require_content=True),
                 Action('abc.####.abc', method='ani', is_sequence=True)),
            frame_pattern='#',                      # inherited from the Group
        )
        self.assertEqual(self.names(resolve(rules, self.root)), ['abc.####.abc'])

    def test_optional_then_require_content_on_next_level(self):
        """After an optional level passes the directory on, the next level keeps
        matching inside it as usual."""
        touch(self.root, 'cache/sub/a.abc')
        rules = Group(Rule(
            Level('cache'),
            Level('v*', optional=True),
            Level('sub'),
            Action('*.abc', method='geo'),
        ))
        self.assertEqual(self.names(resolve(rules, self.root)), ['a.abc'])

    def test_two_optional_levels_then_missing_level(self):
        touch(self.root, 'cache/a.abc')
        rules = Group(Rule(
            Level('cache'),
            Level('v*', optional=True),
            Level('sub', optional=True),
            Level('deep'),                                  # this one truly does not exist
            Action('*.abc', method='geo'),
        ))
        self.assertEqual(resolve(rules, self.root), [])


# --------------------------------------------------------------------------
# collect x collect_scope x mode
# --------------------------------------------------------------------------
class CollectComboTest(ComboTestCase):

    def test_collect_children_collects_from_the_matched_directory(self):
        """``children``: collect inside the **directory matched by this level**
        (without stepping one level further down)."""
        touch(self.root, 'tex/readme.txt', 'tex/v010/a.exr')
        rules = Group(Rule(
            Level('tex', collect=Action('*.txt', method='readme')),
            Level('v*', mode='latest'),
            Action('*.exr', method='texture'),
        ))
        self.assertEqual(sorted(match.name for match in resolve(rules, self.root)),
                         ['a.exr', 'readme.txt'])

    def test_collect_parent_collects_from_the_current_directory(self):
        """``parent``: collect inside the **directory this level lives in** (the
        version root here)."""
        touch(self.root, 'readme.txt', 'tex/v010/a.exr')
        rules = Group(Rule(
            Level('tex', collect=Action('*.txt', method='readme'),
                  collect_scope='parent'),
            Level('v*', mode='latest'),
            Action('*.exr', method='texture'),
        ))
        self.assertEqual(sorted(match.name for match in resolve(rules, self.root)),
                         ['a.exr', 'readme.txt'])

    def test_collect_children_with_multiple_directories(self):
        """With several candidate directories, each one is collected once."""
        touch(self.root, 'tex/v001/readme.txt', 'tex/v002/readme.txt',
              'tex/v001/a.exr')
        rules = Group(Rule(
            Level('tex'),
            Multi('v001', 'v002', collect=Action('*.txt', method='readme')),
            Action('*.exr', method='texture'),
        ))
        self.assertEqual(sorted(match.name for match in resolve(rules, self.root)),
                         ['a.exr', 'readme.txt', 'readme.txt'])

    def test_collect_children_skips_file_candidates(self):
        """When a file ends up among the candidates, collect only applies to
        directories (it never tries to list a file)."""
        touch(self.root, 'tex/a.exr', 'tex.txt')
        rules = Group(Rule(
            Multi('*', collect=Action('*.exr', method='tex')),
            Level('*'),
            Action('*.exr', method='geo'),
        ))
        self.assertEqual([match.name for match in resolve(rules, self.root)],
                         ['a.exr'])


# --------------------------------------------------------------------------
# Group(mode='first') combined with other semantics
# --------------------------------------------------------------------------
class GroupModeComboTest(ComboTestCase):

    def test_fallback_winner_only_even_with_mutex(self):
        touch(self.root, 'a.abc', 'cache/v001/b.abc')
        rules = Group(
            Action('*.abc', method='root', checked=2, mutex='m'),
            Rule(Level('cache'), Level('v001'),
                 Action('*.abc', method='cache', checked=2, mutex='m')),
            mode='first',
        )
        matches = resolve(rules, self.root)
        self.assertEqual([match.name for match in matches], ['a.abc'])
        self.assertEqual({match.method for match in matches}, {'root'})

    def test_nested_fallback_group(self):
        touch(self.root, 'cache/v001/b.abc')
        rules = Group(
            Group(Action('*.abc', method='root')),
            Group(Rule(Level('cache'), Level('v001'), Action('*.abc', method='cache'))),
            mode='first',
        )
        self.assertEqual([match.name for match in resolve(rules, self.root)], ['b.abc'])

    def test_fallback_inside_all_group(self):
        touch(self.root, 'x.abc', 'cache/v001/y.abc')
        rules = Group(
            Group(Action('*.abc', method='root'), mode='first'),
            Rule(Level('cache'), Level('v001'), Action('*.abc', method='cache')),
        )
        self.assertEqual(sorted(match.name for match in resolve(rules, self.root)),
                         ['x.abc', 'y.abc'])

    def test_fallback_with_sequence_branch(self):
        touch(self.root, 'cache/v001/c.0001.abc', 'cache/v001/c.0002.abc')
        rules = Group(
            Rule(Level('cache'), Level('v001'), Action('*.abc', method='plain')),
            Rule(Level('cache'), Level('v001'),
                 Action('*.abc', method='seq', is_sequence=True)),
            mode='first',
        )
        matches = resolve(rules, self.root)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].method, 'plain')

    def test_fallback_with_dedupe(self):
        touch(self.root, 'a.abc')
        rules = Group(
            Action('a.abc', method='geo'),
            Action('a.abc', method='geo'),
            mode='first',
        )
        self.assertEqual(len(resolve(rules, self.root)), 1)


# --------------------------------------------------------------------------
# Action.mode x is_sequence x files_only x several patterns
# --------------------------------------------------------------------------
class ActionModeComboTest(ComboTestCase):

    def test_latest_with_sequence_uses_pattern_name(self):
        touch(self.root, 'cache/v001/a.0001.abc', 'cache/v001/b.0001.abc')
        rules = Group(Rule(Level('cache'), Level('v001'),
                           Action('*.abc', method='ani', mode='latest',
                                  is_sequence=True)))
        self.assertEqual([match.name for match in resolve(rules, self.root)],
                         ['b.%04d.abc'])

    def test_latest_merges_all_patterns_before_picking(self):
        touch(self.root, 'alpha.0001.exr', 'beta.0010.exr')
        rules = Group(Action(['alpha.*.exr', 'beta.*.exr'], method='tex',
                             mode='latest'))
        self.assertEqual([match.name for match in resolve(rules, self.root)],
                         ['beta.0010.exr'])

    def test_files_only_with_sequence(self):
        touch(self.root, 'cache/v001/c.0001.abc')
        make_dir(self.root, 'cache/v001/dir.abc')
        rules = Group(Rule(Level('cache'), Level('v001'),
                           Action('*.abc', method='ani', is_sequence=True,
                                  files_only=True)))
        self.assertEqual([match.name for match in resolve(rules, self.root)],
                         ['c.%04d.abc'])

    def test_latest_with_files_only_skips_directory(self):
        touch(self.root, 'a.0010.ma')
        make_dir(self.root, 'a.9999.ma')                     # sorts higher, but is a dir
        rules = Group(Action('a.*.ma', method='geo', mode='latest', files_only=True))
        self.assertEqual([match.name for match in resolve(rules, self.root)],
                         ['a.0010.ma'])

    def test_frame_pattern_plus_latest(self):
        touch(self.root, 'a.0001.exr', 'a.0002.exr')
        rules = Group(Action('*.exr', method='tex', is_sequence=True,
                             frame_pattern='#', mode='latest'))
        matches = resolve(rules, self.root)
        self.assertEqual(matches[0].name, 'a.####.exr')
        self.assertEqual(matches[0].options['frame_pattern'], '#')


# --------------------------------------------------------------------------
# build_operations combinations: size_mode x grouping x extra_fields
# --------------------------------------------------------------------------
class OperationsComboTest(ComboTestCase):

    def _matches(self):
        touch(self.root, 'plain.ma', 'cache/v001/c.0001.abc', 'cache/v001/c.0002.abc')
        rules = Group(
            Action('*.ma', method='geo'),
            Rule(Level('cache'), Level('v001'),
                 Action('*.abc', method='ani', is_sequence=True)),
        )
        return resolve(rules, self.root)

    def test_size_modes_on_sequence_and_plain_file(self):
        matches = self._matches()
        for mode in ('first', 'total', 'none'):
            operations = build_operations(matches, str(self.root), {},
                                          size_mode=mode, group_mode=None)
            self.assertEqual(len(operations), 2, mode)
            self.assertIsInstance(operations[0]['size'], str, mode)

    def test_size_first_on_plain_file(self):
        touch(self.root, 'a.ma')
        matches = resolve(Group(Action('*.ma', method='geo')), self.root)
        operations = build_operations(matches, str(self.root), {}, size_mode='first')
        self.assertIsInstance(operations[0]['size'], str)

    def test_unknown_size_mode_raises(self):
        matches = self._matches()
        with self.assertRaises(ParameterError):
            build_operations(matches, str(self.root), {}, size_mode='huge')

    def test_extra_fields_as_dict_and_callable(self):
        matches = self._matches()

        operations = build_operations(matches, str(self.root), {}, size_mode='none',
                                      extra_fields={'tag': 'x'})
        self.assertEqual(operations[0]['tag'], 'x')

        operations = build_operations(
            matches, str(self.root), {}, size_mode='none',
            extra_fields=lambda match, asset: {'upper': match.method.upper()})
        self.assertEqual(operations[0]['upper'], 'GEO')

    def test_nested_group_mode_with_mixed_depth(self):
        touch(self.root, 'a.ma', 'cache/v001/deep/b.abc')
        rules = Group(
            Action('*.ma', method='geo'),
            Rule(Level('cache'), Level('v001'), Level('deep'),
                 Action('*.abc', method='ani')),
        )
        operations = build_operations(resolve(rules, self.root), str(self.root), {},
                                      size_mode='none', group_mode='nested')

        self.assertEqual([item['filename'] for item in operations], ['a.ma', 'cache'])
        cache_node = operations[1]
        self.assertEqual(cache_node['children'][0]['filename'], 'cache/v001')
        self.assertEqual(cache_node['children'][0]['children'][0]['filename'],
                         'cache/v001/deep')

    def test_path_outside_version_root_falls_back_to_name(self):
        """An entry outside ``version_root`` falls back to the file name instead of
        raising."""
        touch(self.root, 'other/a.ma')
        matches = resolve(Group(Action('a.ma', method='geo')), self.root / 'other')
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()

        operations = build_operations(matches, str(elsewhere), {}, size_mode='none')
        self.assertEqual(operations[0]['filename'], 'a.ma')
        self.assertEqual(operations[0]['relative_path'], 'a.ma')


# --------------------------------------------------------------------------
# rule_dict: turn every optional field on and verify export/import is lossless
# --------------------------------------------------------------------------
class RuleDictComboTest(unittest.TestCase):

    def test_action_all_fields_roundtrip(self):
        action = Action('*.exr', method='tex', mode='latest', is_sequence=True,
                        checked=2, mutex='m', files_only=True,
                        collect=Action('*.txt', method='readme'),
                        frame_pattern='#', tag='x')
        data = rule_to_dict(action)

        self.assertEqual(data['mode'], 'latest')
        self.assertTrue(data['is_sequence'])
        self.assertTrue(data['files_only'])
        self.assertEqual(data['mutex'], 'm')
        self.assertEqual(data['checked'], 2)
        self.assertEqual(data['collect'][0]['method'], 'readme')
        self.assertEqual(data['options'], {'frame_pattern': '#', 'tag': 'x'})
        self.assertEqual(rule_to_dict(rule_from_dict(data)), data)

    def test_level_all_fields_roundtrip(self):
        level = Level('v*', mode='latest', optional=True, require_content=True,
                      mutex='m', collect=Action('*.txt', method='readme'),
                      collect_scope='parent')
        data = rule_to_dict(level)

        self.assertTrue(data['optional'])
        self.assertTrue(data['require_content'])
        self.assertEqual(data['collect_scope'], 'parent')
        self.assertEqual(rule_to_dict(rule_from_dict(data)), data)

    def test_group_and_rule_options_roundtrip(self):
        rules = Group(Rule(Level('cache'), Action('*.abc', method='x'), tag='r'),
                      mode='first', tag='g')
        data = rule_to_dict(rules)

        self.assertEqual(data['options'], {'tag': 'g'})
        self.assertEqual(data['rules'][0]['options'], {'tag': 'r'})
        self.assertEqual(rule_to_dict(rule_from_dict(data)), data)

    def test_children_must_be_dict_or_list(self):
        with self.assertRaises(RuleDefinitionError):
            rule_from_dict({'type': 'group', 'rules': 'oops'})

    def test_unknown_type_and_bad_options(self):
        with self.assertRaises(RuleDefinitionError):
            rule_from_dict({'type': 'branch'})
        with self.assertRaises(RuleDefinitionError):
            rule_from_dict({'type': 'action', 'patterns': ['*.ma'], 'method': 'geo',
                            'options': 'nope'})

    def test_rule_to_dict_rejects_unknown_object(self):
        with self.assertRaises(RuleDefinitionError):
            rule_to_dict(object())


# --------------------------------------------------------------------------
# error / edge branches that are easy to miss
# --------------------------------------------------------------------------
class BranchEdgeTest(ComboTestCase):

    def test_patterns_reject_none_and_empty(self):
        with self.assertRaises(RuleDefinitionError):
            Level([None])
        with self.assertRaises(RuleDefinitionError):
            Level([''])
        with self.assertRaises(RuleDefinitionError):
            Level([])

    def test_patterns_accept_bytes(self):
        self.assertEqual(Level([b'a.ma']).patterns, ('a.ma',))

    def test_repr_is_readable(self):
        self.assertIn('Level', repr(Level('cache')))
        self.assertIn('Action', repr(Action('*.ma', method='geo')))
        self.assertIn('Group', repr(Group(Action('*.ma', method='geo'))))
        self.assertIn('Rule', repr(Rule(Level('cache'), Action('*.ma', method='geo'))))

    def test_describe_unknown_object(self):
        self.assertIn('object', describe_rule(object()))

    def test_as_path_accepts_bytes(self):
        self.assertEqual(as_path(b'a/b'), Path('a/b'))

    def test_entry_comparison_with_other_types(self):
        entry = Entry('a.ma')
        self.assertNotEqual(entry, 42)
        self.assertTrue(entry != 42)
        self.assertFalse(entry == 42)

    def test_list_entries_on_a_file_returns_empty(self):
        touch(self.root, 'a.ma')
        self.assertEqual(list_entries(self.root / 'a.ma'), [])

    def test_match_mutex_prefers_action_attribute(self):
        touch(self.root, 'a.ma')
        matches = resolve(Group(Action('a.ma', method='geo', mutex='from_action'),
                                mutex='from_options'), self.root)
        self.assertEqual(matches[0].mutex, 'from_action')

    def test_match_repr(self):
        touch(self.root, 'a.ma')
        matches = resolve(Group(Action('a.ma', method='geo')), self.root)
        self.assertIn('geo', repr(matches[0]))

    def test_apply_mutex_when_nothing_checked_and_autoselect_off(self):
        touch(self.root, 'a.ma', 'b.ma')
        rules = Group(
            Action('a.ma', method='geo', mutex='m'),
            Action('b.ma', method='geo', mutex='m'),
        )
        matches = resolve(rules, self.root, auto_select_first=False)
        self.assertEqual({match.state for match in matches}, {0})

    def test_resolver_is_reusable_across_roots(self):
        touch(self.root, 'a.ma')
        touch(self.root, 'sub/b.ma')
        resolver = Resolver()
        rules = Group(Action('*.ma', method='geo'))

        self.assertEqual([m.name for m in resolver.resolve(rules, self.root)], ['a.ma'])
        self.assertEqual([m.name for m in resolver.resolve(rules, self.root / 'sub')],
                         ['b.ma'])


class CliBranchTest(unittest.TestCase):

    def test_split_spec_variants(self):
        from sublevel_rules.cli import _split_spec

        self.assertEqual(_split_spec('mypkg.rules'), ('mypkg.rules', ''))
        self.assertEqual(_split_spec('mypkg.rules:attr'), ('mypkg.rules', 'attr'))
        self.assertEqual(_split_spec('C:\\proj\\rules.py'), ('C:\\proj\\rules.py', ''))
        self.assertEqual(_split_spec('C:\\proj\\rules.py:attr'),
                         ('C:\\proj\\rules.py', 'attr'))

    def test_unknown_rule_format_gives_hint(self):
        from sublevel_rules.cli import load_rules

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'rules.toml'
            path.write_text('x = 1', encoding='utf-8')
            with self.assertRaises(SubLevelRulesError) as ctx:
                load_rules(str(path))
            self.assertIn('.toml', str(ctx.exception))

    def test_missing_rule_file_raises(self):
        from sublevel_rules.cli import load_rules

        with self.assertRaises(SubLevelRulesError):
            load_rules('definitely/not/here.py:get_import_rules')


class YamlMissingDependencyTest(unittest.TestCase):
    """The error branch for a missing PyYAML (without actually uninstalling it)."""

    def test_missing_pyyaml_message(self):
        from sublevel_rules import yaml_rules

        with mock_module.patch.dict(sys.modules, {'yaml': None}):
            with self.assertRaises(SubLevelRulesError) as ctx:
                yaml_rules.load_rules('whatever.yaml')
        self.assertIn('PyYAML', str(ctx.exception))


class ModuleEntryTest(unittest.TestCase):
    """The ``python -m sublevel_rules`` entry point (covers __main__.py)."""

    def test_python_m_describe(self):
        src = str(Path(__file__).resolve().parent.parent / 'src')
        env = dict(os.environ)
        env['PYTHONPATH'] = src + os.pathsep + env.get('PYTHONPATH', '')

        process = subprocess.Popen(
            [sys.executable, '-m', 'sublevel_rules', '--preset', 'mod', '--describe'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        out, err = process.communicate()

        self.assertEqual(process.returncode, 0, err.decode('utf-8', 'replace'))
        self.assertIn(b'Group(', out)


if __name__ == '__main__':
    unittest.main()
