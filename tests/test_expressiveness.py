# -*- coding: utf-8 -*-
"""Tests for the expressiveness additions: fallback chain / take latest /
optional level / skip empty candidates.

All four answer the same question -- "which path or directory should be taken" --
so they are tested together.
"""

import tempfile
import unittest

from pathlib import Path

from sublevel_rules.errors import RuleDefinitionError
from sublevel_rules.paths import Entry, list_entries
from sublevel_rules.rules import Action, Group, Level, Rule
from sublevel_rules.resolver import resolve

from .support import make_dir, touch


class ResolverTestCase(unittest.TestCase):

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def names(self, matches):
        return [match.name for match in matches]


class FallbackGroupTest(ResolverTestCase):
    """``Group(mode='first')``: fallback chain; the first branch producing a
    non-empty result wins."""

    def _rules(self, mode='first'):
        return Group(
            Action('*.abc', method='root'),                            # layout A
            Rule(Level('cache'), Level('v001'),                        # layout B
                 Action('*.abc', method='cache')),
            mode=mode,
        )

    def test_takes_first_non_empty_branch(self):
        touch(self.root, 'a.abc', 'cache/v001/b.abc')
        matches = resolve(self._rules(), self.root)
        self.assertEqual(self.names(matches), ['a.abc'])
        self.assertEqual(matches[0].method, 'root')

    def test_falls_back_when_first_branch_is_empty(self):
        touch(self.root, 'cache/v001/b.abc')
        matches = resolve(self._rules(), self.root)
        self.assertEqual(self.names(matches), ['b.abc'])
        self.assertEqual(matches[0].method, 'cache')

    def test_all_mode_is_still_the_default(self):
        touch(self.root, 'a.abc', 'cache/v001/b.abc')
        rules = Group(
            Action('*.abc', method='root'),
            Rule(Level('cache'), Level('v001'), Action('*.abc', method='cache')),
        )
        self.assertEqual(sorted(self.names(resolve(rules, self.root))), ['a.abc', 'b.abc'])

    def test_nothing_matched_returns_empty(self):
        self.assertEqual(resolve(self._rules(), self.root), [])

    def test_invalid_group_mode_raises(self):
        with self.assertRaises(RuleDefinitionError):
            Group(Action('*.ma', method='geo'), mode='everything')

    def test_default_mode_attribute(self):
        self.assertEqual(Group(Action('*.ma', method='geo')).mode, 'all')


class LatestModeTest(ResolverTestCase):
    """``mode='latest'``: take the newest entry by natural numeric order."""

    def test_latest_beats_lexicographic_order(self):
        touch(self.root, 'cache/v009/a.abc', 'cache/v010/b.abc')
        rules = Group(Rule(Level('cache'), Level('v*', mode='latest'),
                           Action('*.abc', method='geo')))
        matches = resolve(rules, self.root)
        self.assertEqual(self.names(matches), ['b.abc'])

    def test_first_mode_would_pick_the_other_one(self):
        touch(self.root, 'cache/v009/a.abc', 'cache/v010/b.abc')
        rules = Group(Rule(Level('cache'), Level('v*', mode='first'),
                           Action('*.abc', method='geo')))
        self.assertEqual(self.names(resolve(rules, self.root)), ['a.abc'])

    def test_latest_on_action(self):
        touch(self.root, 'plate.0001.exr', 'plate.0010.exr')
        rules = Group(Action('plate.*.exr', method='tex', mode='latest'))
        self.assertEqual(self.names(resolve(rules, self.root)), ['plate.0010.exr'])

    def test_latest_with_single_candidate(self):
        touch(self.root, 'cache/v001/a.abc')
        rules = Group(Rule(Level('cache'), Level('v*', mode='latest'),
                           Action('*.abc', method='geo')))
        self.assertEqual(self.names(resolve(rules, self.root)), ['a.abc'])

    def test_latest_with_no_candidate(self):
        rules = Group(Rule(Level('cache'), Level('v*', mode='latest'),
                           Action('*.abc', method='geo')))
        self.assertEqual(resolve(rules, self.root), [])


class OptionalLevelTest(ResolverTestCase):
    """``Level(optional=True)``: when the level does not exist, skip it and keep
    matching below."""

    def _rules(self, optional):
        return Group(Rule(
            Level('cache'),
            Level('v*', optional=optional),
            Action('*.abc', method='geo'),
        ))

    def test_optional_level_skipped_when_missing(self):
        touch(self.root, 'cache/a.abc')
        self.assertEqual(self.names(resolve(self._rules(True), self.root)), ['a.abc'])

    def test_without_optional_it_matches_nothing(self):
        touch(self.root, 'cache/a.abc')
        self.assertEqual(resolve(self._rules(False), self.root), [])

    def test_optional_level_still_used_when_present(self):
        touch(self.root, 'cache/v001/a.abc')
        matches = resolve(self._rules(True), self.root)
        self.assertEqual(self.names(matches), ['a.abc'])
        self.assertEqual(matches[0].path.parent.name, 'v001')

    def test_two_optional_levels_in_a_row(self):
        touch(self.root, 'cache/a.abc')
        rules = Group(Rule(
            Level('cache'),
            Level('v*', optional=True),
            Level('sub', optional=True),
            Action('*.abc', method='geo'),
        ))
        self.assertEqual(self.names(resolve(rules, self.root)), ['a.abc'])

    def test_default_is_not_optional(self):
        self.assertFalse(Level('cache').optional)


class RequireContentTest(ResolverTestCase):
    """``Level(require_content=True)``: skip candidates where the next level would
    match nothing."""

    def _rules(self, **kwargs):
        return Group(Rule(
            Level('cache'),
            Level('v*', **kwargs),
            Action('*.abc', method='geo'),
        ))

    def test_first_skips_empty_candidate(self):
        make_dir(self.root, 'cache/v001')            # empty directory
        touch(self.root, 'cache/v002/b.abc')
        matches = resolve(self._rules(mode='first', require_content=True), self.root)
        self.assertEqual(self.names(matches), ['b.abc'])

    def test_without_it_first_wins_but_yields_nothing(self):
        make_dir(self.root, 'cache/v001')
        touch(self.root, 'cache/v002/b.abc')
        self.assertEqual(resolve(self._rules(mode='first'), self.root), [])

    def test_latest_with_require_content(self):
        make_dir(self.root, 'cache/v010')            # newest, but empty
        touch(self.root, 'cache/v009/b.abc')
        matches = resolve(self._rules(mode='latest', require_content=True), self.root)
        self.assertEqual(self.names(matches), ['b.abc'])

    def test_invalid_group_mode_still_raises(self):
        with self.assertRaises(RuleDefinitionError):
            Level('v*', mode='newest')

    def test_default_is_false(self):
        self.assertFalse(Level('cache').require_content)


class ScanDirEntryTest(ResolverTestCase):
    """Entry behaviour must not change after the scandir optimization."""

    def test_entries_from_list_entries_answer_questions(self):
        touch(self.root, 'a.ma')
        make_dir(self.root, 'sub')

        entries = {entry.name: entry for entry in list_entries(self.root)}
        self.assertTrue(entries['a.ma'].is_file())
        self.assertFalse(entries['a.ma'].is_dir())
        self.assertEqual(entries['a.ma'].size(), 0)
        self.assertEqual(entries['a.ma'].isfile(), True)
        self.assertTrue(entries['sub'].is_dir())
        self.assertFalse(entries['sub'].is_file())

    def test_files_only_still_filters_directories(self):
        touch(self.root, 'a.ma')
        make_dir(self.root, 'sub')
        self.assertEqual([entry.name for entry in list_entries(self.root, files_only=True)],
                         ['a.ma'])

    def test_manually_built_entry_still_works(self):
        touch(self.root, 'a.ma')
        entry = Entry(self.root / 'a.ma')
        self.assertTrue(entry.is_file())
        self.assertEqual(entry.size(), 0)

    def test_entry_without_dir_entry_reports_missing_file(self):
        entry = Entry(self.root / 'nope.ma')
        self.assertFalse(entry.is_file())
        self.assertEqual(entry.size(), 0)


class DescribeRuleNewSemanticsTest(ResolverTestCase):

    def test_describe_shows_group_mode(self):
        from sublevel_rules.rules import describe_rule
        text = describe_rule(Group(Action('*.ma', method='geo'), mode='first'))
        self.assertIn("Group(mode='first'", text)

    def test_describe_shows_level_flags(self):
        from sublevel_rules.rules import describe_rule
        text = describe_rule(Level('v*', optional=True, require_content=True))
        self.assertIn('optional=True', text)
        self.assertIn('require_content=True', text)


if __name__ == '__main__':
    unittest.main()
