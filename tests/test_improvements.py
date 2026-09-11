# -*- coding: utf-8 -*-
"""Regression tests for the fixes and new features added after the code review.

Covers:

* ``Entry.to_pattern()`` no longer collapses an existing pattern name twice;
* the overlap deduplication of ``frame_tokens``, ``%4d`` support and the fact
  that a single ``#`` is not a placeholder;
* ``is_sequence_name`` no longer misjudges names by substring;
* deterministic ordering for ``set`` patterns;
* ``Action(files_only=True)`` skipping directory entries;
* ``Resolver(exclude_patterns=...)`` skipping the given entries;
* ``Match.to_dict()`` / ``describe_rule()``;
* the CLI's ``extract_version_part``, ``--describe`` and ``--exclude``.
"""

import io
import json
import tempfile
import unittest

from contextlib import redirect_stdout
from pathlib import Path

from sublevel_rules.cli import extract_version_part, main
from sublevel_rules.frames import frame_path, frame_tokens
from sublevel_rules.operations import get_sub_level_op
from sublevel_rules.paths import Entry
from sublevel_rules.rules import Action, Group, Level, Multi, Rule, describe_rule
from sublevel_rules.resolver import Match, resolve, resolve_smart_rule
from sublevel_rules.sequences import is_sequence_name, scan_sequences

from .support import make_dir, touch


class ToPatternIdempotentTest(unittest.TestCase):

    def test_percent_pattern_not_folded_twice(self):
        entry = Entry('abc.%04d.exr')
        self.assertTrue(entry.to_pattern('%') is entry)
        self.assertEqual(entry.to_pattern('%').name, 'abc.%04d.exr')

    def test_dollar_pattern_not_folded_twice(self):
        entry = Entry('abc.$F4.exr')
        self.assertEqual(entry.to_pattern('%').name, 'abc.$F4.exr')

    def test_sharp_pattern_not_folded_twice(self):
        entry = Entry('abc.####.exr')
        self.assertEqual(entry.to_pattern('%').name, 'abc.####.exr')

    def test_scan_sequences_keeps_existing_pattern_name(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'abc.%04d.exr')
            sequences = scan_sequences(temp)
            self.assertEqual([item.name for item in sequences], ['abc.%04d.exr'])
            self.assertEqual(sequences[0].frames, [])


class FrameTokensTest(unittest.TestCase):

    def test_no_duplicate_for_percent_padding(self):
        self.assertEqual(frame_tokens('abc.%04d.exr'), ['%04d'])

    def test_single_sharp_is_not_a_placeholder(self):
        self.assertEqual(frame_tokens('abc#1.exr'), [])

    def test_double_sharp_is_a_placeholder(self):
        self.assertEqual(frame_tokens('abc.##.exr'), ['##'])

    def test_multiple_tokens_in_order(self):
        self.assertEqual(frame_tokens('a.####_%02d.exr'), ['####', '%02d'])

    def test_percent_without_padding_supported(self):
        self.assertEqual(frame_path('abc.%4d.exr', 7).name, 'abc.0007.exr')

    def test_frame_path_without_token_returns_same_name(self):
        self.assertEqual(frame_path('abc.0001.exr', 7).name, 'abc.0001.exr')

    def test_frame_path_replaces_only_first_token(self):
        self.assertEqual(frame_path('a.%04d.%04d.exr', 7).name, 'a.0007.%04d.exr')


class IsSequenceNameTest(unittest.TestCase):

    def test_percent_like_name_is_not_sequence(self):
        self.assertFalse(is_sequence_name('abc.100%0.exr'))

    def test_real_patterns_are_sequences(self):
        for name in ('abc.%04d.exr', 'abc.%d.exr', 'abc.####.exr', 'abc.$F4.exr'):
            self.assertTrue(is_sequence_name(name), name)

    def test_plain_name(self):
        self.assertFalse(is_sequence_name('abc.0001.exr'))


class PatternOrderTest(unittest.TestCase):

    def test_set_patterns_are_sorted(self):
        self.assertEqual(Action({'b.ma', 'a.ma'}, method='geo').patterns,
                         ('a.ma', 'b.ma'))
        self.assertEqual(Level({'b', 'a'}).patterns, ('a', 'b'))

    def test_set_first_mode_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'a.ma', 'b.ma')
            rules = Group(Action({'b.ma', 'a.ma'}, method='geo', mode='first'))
            for _ in range(5):
                matches = resolve(rules, temp)
                self.assertEqual([match.name for match in matches], ['a.ma'])


class FilesOnlyTest(unittest.TestCase):

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def test_default_still_matches_directories(self):
        touch(self.root, 'b.ma')
        make_dir(self.root, 'a.ma')
        rules = Group(Action(['a.ma', 'b.ma'], method='geo', mode='multiple'))
        self.assertEqual(sorted(match.name for match in resolve(rules, self.root)),
                         ['a.ma', 'b.ma'])

    def test_files_only_skips_directories(self):
        touch(self.root, 'b.ma')
        make_dir(self.root, 'a.ma')
        rules = Group(Action(['a.ma', 'b.ma'], method='geo', mode='multiple',
                             files_only=True))
        self.assertEqual([match.name for match in resolve(rules, self.root)],
                         ['b.ma'])

    def test_files_only_default_is_false(self):
        self.assertFalse(Action('*.ma', method='geo').files_only)


class ExcludePatternsTest(unittest.TestCase):

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def test_exclude_skips_directories(self):
        touch(self.root, 'cache/a.ma', '.git/b.ma')
        # Level('*') defaults to mode='first' and would only enter the first
        # directory; Multi is needed to enter both.
        rules = Group(Rule(Multi('*'),
                           Action('*.ma', method='geo', mode='multiple')))

        self.assertEqual(sorted(match.name for match in resolve(rules, self.root)),
                         ['a.ma', 'b.ma'])

        matches = resolve(rules, self.root, exclude_patterns=['.*'])
        self.assertEqual([match.name for match in matches], ['a.ma'])

    def test_exclude_applies_to_sequences(self):
        touch(self.root, 'cache/ok.0001.exr', '__pycache__/bad.0001.exr')
        rules = Group(Rule(Level('*'),
                           Action('*.exr', method='tex', mode='multiple',
                                  is_sequence=True)))
        matches = resolve(rules, self.root, exclude_patterns=['__pycache__'])
        self.assertEqual([match.name for match in matches], ['ok.%04d.exr'])


class MatchToDictTest(unittest.TestCase):

    def test_to_dict(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'a.0001.exr', 'a.0002.exr')
            rules = Group(Action('*.exr', method='tex', is_sequence=True, checked=2))
            match = resolve(rules, temp)[0]
            self.assertIsInstance(match, Match)              # the result type itself
            self.assertEqual(match.as_tuple()[1], 'tex')     # the old tuple protocol
            data = match.to_dict()

            self.assertEqual(data['name'], 'a.%04d.exr')
            self.assertEqual(data['method'], 'tex')
            self.assertEqual(data['checked'], 2)
            self.assertTrue(data['is_sequence'])
            self.assertEqual(data['frames'], [1, 2])
            self.assertEqual(data['missing'], [])
            self.assertIn('path', data)


class DescribeRuleTest(unittest.TestCase):

    def test_describe_group_rule_action(self):
        rules = Group(
            Action('*.ma', method='geo', checked=2),
            Rule(Level('cache'), Level('v001'), Action('*.abc', method='ani')),
        )
        text = describe_rule(rules)
        self.assertIn('Group(', text)
        self.assertIn('Rule(', text)
        self.assertIn("method='geo'", text)
        self.assertIn("Level(patterns=['cache']", text)

    def test_describe_action_marks_files_only(self):
        text = describe_rule(Action('*.ma', method='geo', files_only=True))
        self.assertIn('files_only=True', text)

    def test_describe_level_marks_collect(self):
        text = describe_rule(Level('tex', collect=Action('*.txt', method='readme'),
                                   collect_scope='parent'))
        self.assertIn("collect=['readme']", text)
        self.assertIn("collect_scope='parent'", text)

    def test_describe_level_marks_mutex(self):
        """A mutex on a Level takes effect through options, so describe shows it."""
        self.assertIn("mutex='m'", describe_rule(Level('cache', mutex='m')))


class CliImprovementsTest(unittest.TestCase):

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def _run(self, argv):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main(argv)
        return code, stream.getvalue()

    def test_extract_version_part_prefers_v_prefix(self):
        self.assertEqual(extract_version_part('/show/shot010/v002'), '002')
        self.assertEqual(extract_version_part('/show/shot010'), '010')
        self.assertEqual(extract_version_part('/show/asset'), '*')

    def test_describe_without_version_path(self):
        code, output = self._run(['--preset', 'mod', '--describe'])
        self.assertEqual(code, 0)
        self.assertIn('Group(', output)
        self.assertIn("method='geo'", output)

    def test_describe_with_rules_file(self):
        rules_file = self.root / 'rules_here.py'
        rules_file.write_text(
            'from sublevel_rules import Action, Group\n\n\n'
            'def get_import_rules():\n'
            "    return Group(Action('*.ma', method='geo', files_only=True))\n")
        code, output = self._run(['--rules', str(rules_file), '--describe'])
        self.assertEqual(code, 0)
        self.assertIn('files_only=True', output)

    def _flatten(self, operations):
        names = []
        for item in operations:
            if 'children' in item:
                names.extend(self._flatten(item['children']))
            else:
                names.append(item['filename'])
        return names

    def test_exclude_option(self):
        touch(self.root, 'abc_v001.ma', 'cache/v001/a.abc')

        code, output = self._run([str(self.root), '--preset', 'ani',
                                  '--version-part', '001', '--json'])
        self.assertEqual(code, 0)
        self.assertIn('a.abc', self._flatten(json.loads(output)))

        code, output = self._run([str(self.root), '--preset', 'ani',
                                  '--version-part', '001',
                                  '--exclude', 'cache', '--json'])
        self.assertEqual(code, 0)
        names = self._flatten(json.loads(output))
        self.assertIn('abc_v001.ma', names)
        self.assertNotIn('a.abc', names)


class AliasEntryPointsTest(unittest.TestCase):
    """The compatibility entry points get their own protection."""

    def test_resolve_smart_rule_behaves_like_resolve(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'a.ma', 'b.ma')
            rules = Group(Action(['a.ma', 'b.ma'], method='geo', mode='multiple'))

            aliased = resolve_smart_rule(rules, temp)
            current = resolve(rules, temp)
            self.assertEqual([match.name for match in aliased],
                             [match.name for match in current])

    def test_resolve_smart_rule_accepts_inherited_options(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'a.ma')
            rules = Group(Action('*.ma', method='geo'))
            matches = resolve_smart_rule(rules, temp, inherited_options={'tag': 'x'})
            self.assertEqual(matches[0].options['tag'], 'x')

    def test_get_sub_level_op_keeps_compat_field_names(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'a.ma')

            class FakeModule(object):
                @staticmethod
                def get_import_rules():
                    return Group(Action('*.ma', method='geo', checked=2))

                @staticmethod
                def create_api_version(method):
                    return lambda *args, **kwargs: method

            operations = get_sub_level_op(FakeModule, {'path': temp}, size_mode='none')
            self.assertEqual([item['filename'] for item in operations], ['a.ma'])
            self.assertEqual(operations[0]['filename_checked'], 2)


if __name__ == '__main__':
    unittest.main()
