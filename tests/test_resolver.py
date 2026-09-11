# -*- coding: utf-8 -*-
"""Tests for the resolution engine (focused on the compatibility behaviours)."""

import tempfile
import unittest

from pathlib import Path

from sublevel_rules.errors import (
    RuleDefinitionError,
    RuleFormatError,
    RuleStructureError,
)
from sublevel_rules.rules import Action, Group, Level, Multi, Rule
from sublevel_rules.resolver import Resolver, format_pattern, resolve

from .support import touch


class FormatPatternTest(unittest.TestCase):

    def test_fill_placeholder(self):
        self.assertEqual(
            format_pattern('*_v{version_part}.ma', {'version_part': '001'}),
            '*_v001.ma')

    def test_without_version_data_returns_pattern(self):
        self.assertEqual(format_pattern('*_v{version_part}.ma', None),
                         '*_v{version_part}.ma')

    def test_missing_placeholder_raises(self):
        with self.assertRaises(RuleFormatError):
            format_pattern('*_v{version_part}.ma', {'other': '1'})

    def test_lenient_mode_keeps_placeholder(self):
        self.assertEqual(
            format_pattern('*_v{version_part}.ma', {'other': '1'}, strict=False),
            '*_v{version_part}.ma')

    def test_broken_braces_raise(self):
        with self.assertRaises(RuleFormatError):
            format_pattern('*_{oops.ma', {'a': '1'})


class ResolverTestCase(unittest.TestCase):

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()


class ResolveBasicTest(ResolverTestCase):

    def test_action_first_mode_takes_first_pattern_hit(self):
        touch(self.root, 'abc_v001.ma', 'abc_v001.mb')
        rules = Group(Action(['*_v{version_part}.ma', '*_v{version_part}.mb'],
                             method='geo', mode='first', checked=2))
        matches = resolve(rules, self.root, {'version_part': '001'})
        self.assertEqual([match.name for match in matches], ['abc_v001.ma'])
        self.assertEqual(matches[0].state, 2)
        self.assertEqual(matches[0].method, 'geo')

    def test_action_multiple_mode_collects_all(self):
        touch(self.root, 'abc_v001.ma', 'abc_v001.mb', 'other_v001.txt')
        rules = Group(Action(['*_v{version_part}.ma', '*_v{version_part}.mb'],
                             method='geo', mode='multiple'))
        matches = resolve(rules, self.root, {'version_part': '001'})
        self.assertEqual(sorted(match.name for match in matches),
                         ['abc_v001.ma', 'abc_v001.mb'])

    def test_match_is_unpackable_like_old_tuple(self):
        touch(self.root, 'abc_v001.ma')
        rules = Group(Action('*_v{version_part}.ma', method='geo'))
        for sequence, method, action in resolve(rules, self.root, {'version_part': '001'}):
            self.assertEqual(method, 'geo')
            self.assertEqual(sequence.filename.name, 'abc_v001.ma')
            self.assertIsInstance(action, Action)

    def test_rule_walks_directories(self):
        touch(self.root, 'cache/v001/a.abc', 'cache/v001/b.abc', 'cache/v002/c.abc')
        rules = Group(Rule(
            Level('cache'),
            Level('v{version_part}'),
            Action('*.abc', method='animation', mode='multiple', checked=2),
        ))
        matches = resolve(rules, self.root, {'version_part': '001'})
        self.assertEqual(sorted(match.name for match in matches), ['a.abc', 'b.abc'])
        self.assertEqual(matches[0].path.parent.name, 'v001')

    def test_level_multiple_mode(self):
        touch(self.root, 'cache/v001/a.abc', 'cache/v002/b.abc')
        rules = Group(Rule(
            Level('cache'),
            Multi('v{version_part}', 'v*'),
            Action('*.abc', method='animation', mode='multiple'),
        ))
        matches = resolve(rules, self.root, {'version_part': '001'})
        self.assertEqual(sorted(match.name for match in matches), ['a.abc', 'b.abc'])

    def test_missing_root_returns_empty(self):
        rules = Group(Action('*.ma', method='geo'))
        self.assertEqual(resolve(rules, self.root / 'nope'), [])

    def test_sequence_matching(self):
        touch(self.root, 'cache/v001/abc.0001.abc', 'cache/v001/abc.0002.abc',
              'cache/v001/readme.txt')
        rules = Group(Rule(
            Level('cache'),
            Level('v{version_part}'),
            Action('*.abc', method='animation', mode='multiple', is_sequence=True),
        ))
        matches = resolve(rules, self.root, {'version_part': '001'})
        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0].is_sequence)
        self.assertEqual(matches[0].frames, [1, 2])
        self.assertEqual(matches[0].name, 'abc.%04d.abc')

    def test_collect_side_collection(self):
        touch(self.root, 'cache/readme.txt', 'cache/v001/a.abc')
        rules = Group(Rule(
            Level('cache', collect=Action('*.txt', method='info')),
            Level('v001'),
            Action('*.abc', method='geo'),
        ))
        matches = resolve(rules, self.root)
        pairs = sorted((match.name, match.method) for match in matches)
        self.assertEqual(pairs, [('a.abc', 'geo'), ('readme.txt', 'info')])

    def test_case_insensitive_by_default(self):
        touch(self.root, 'ABC_V001.MA')
        rules = Group(Action('*_v{version_part}.ma', method='geo'))
        self.assertEqual(len(resolve(rules, self.root, {'version_part': '001'})), 1)

    def test_case_sensitive_option(self):
        touch(self.root, 'ABC_V001.MA')
        rules = Group(Action('*_v{version_part}.ma', method='geo'))
        self.assertEqual(
            resolve(rules, self.root, {'version_part': '001'}, case_sensitive=True), [])

    def test_options_are_inherited(self):
        touch(self.root, 'abc_v001.exr')
        rules = Group(
            Action('*_v{version_part}.exr', method='texture'),
            tag='beauty',
        )
        matches = resolve(rules, self.root, {'version_part': '001'})
        self.assertEqual(matches[0].options['tag'], 'beauty')

    def test_action_options_override_group_options(self):
        touch(self.root, 'abc_v001.exr')
        rules = Group(
            Action('*_v{version_part}.exr', method='texture', tag='action'),
            tag='group',
        )
        matches = resolve(rules, self.root, {'version_part': '001'})
        self.assertEqual(matches[0].options['tag'], 'action')

    def test_level_options_are_inherited_downwards(self):
        """Options of a middle ``Level`` are inherited along the chain too
        (Group -> Rule -> Level -> Action)."""
        touch(self.root, 'cache/v001/a.abc')
        rules = Group(
            Rule(Level('cache', tag='level', ui_group='cache'),
                 Level('v001'),
                 Action('*.abc', method='geo')),
            tag='group',
        )
        options = resolve(rules, self.root)[0].options
        self.assertEqual(options['ui_group'], 'cache')   # only on the middle level
        self.assertEqual(options['tag'], 'level')        # lower nodes win

    def test_frame_pattern_option_per_action(self):
        touch(self.root, 'abc.0001.exr')
        rules = Group(Action('*.exr', method='texture', is_sequence=True,
                             frame_pattern='#'))
        matches = resolve(rules, self.root)
        self.assertEqual(matches[0].name, 'abc.####.exr')


class ResolveMutexTest(ResolverTestCase):

    def test_explicit_checked_keeps_first(self):
        touch(self.root, 'a.ma', 'b.ma')
        rules = Group(
            Action('a.ma', method='geo', checked=2, mutex='m'),
            Action('b.ma', method='geo', checked=2, mutex='m'),
        )
        matches = resolve(rules, self.root)
        states = {match.name: match.state for match in matches}
        self.assertEqual(states, {'a.ma': 2, 'b.ma': 0})

    def test_auto_select_first_when_nothing_checked(self):
        touch(self.root, 'a.ma', 'b.ma')
        rules = Group(
            Action('a.ma', method='geo', mutex='m'),
            Action('b.ma', method='geo', mutex='m'),
        )
        matches = resolve(rules, self.root)
        states = {match.name: match.state for match in matches}
        self.assertEqual(states, {'a.ma': 2, 'b.ma': 0})

    def test_auto_select_can_be_disabled(self):
        touch(self.root, 'a.ma', 'b.ma')
        rules = Group(
            Action('a.ma', method='geo', mutex='m'),
            Action('b.ma', method='geo', mutex='m'),
        )
        matches = resolve(rules, self.root, auto_select_first=False)
        self.assertEqual({match.state for match in matches}, {0})

    def test_mutex_can_come_from_options(self):
        touch(self.root, 'a.ma', 'b.ma')
        rules = Group(
            Action('a.ma', method='geo', checked=2),
            Action('b.ma', method='geo', checked=2),
            mutex='shared',
        )
        matches = resolve(rules, self.root)
        states = {match.name: match.state for match in matches}
        self.assertEqual(states, {'a.ma': 2, 'b.ma': 0})

    def test_mutex_declared_on_a_level_applies(self):
        """A mutex written on a middle ``Level`` has to take effect, not be
        silently ignored."""
        touch(self.root, 'sub/a.ma', 'sub/b.ma')
        rules = Group(
            Rule(Level('sub', mutex='m'), Action('a.ma', method='geo', checked=2)),
            Rule(Level('sub', mutex='m'), Action('b.ma', method='geo', checked=2)),
        )
        matches = resolve(rules, self.root)
        states = {match.name: match.state for match in matches}

        self.assertEqual({match.mutex for match in matches}, {'m'})
        self.assertEqual(states, {'a.ma': 2, 'b.ma': 0})

    def test_mutex_across_nested_groups(self):
        touch(self.root, 'a.ma', 'b.ma')
        rules = Group(
            Group(Action('a.ma', method='geo', checked=2, mutex='m')),
            Group(Action('b.ma', method='geo', checked=2, mutex='m')),
        )
        matches = resolve(rules, self.root)
        self.assertEqual(len([m for m in matches if m.state == 2]), 1)

    def test_independent_mutex_groups(self):
        touch(self.root, 'a.ma', 'b.ma')
        rules = Group(
            Action('a.ma', method='geo', checked=2, mutex='m1'),
            Action('b.ma', method='geo', checked=2, mutex='m2'),
        )
        matches = resolve(rules, self.root)
        self.assertEqual({match.state for match in matches}, {2})


class ResolveDedupeTest(ResolverTestCase):

    def test_same_file_same_method_deduped(self):
        touch(self.root, 'a.ma')
        rules = Group(
            Action('a.ma', method='geo', mode='multiple'),
            Action('a.ma', method='geo', mode='multiple'),
        )
        self.assertEqual(len(resolve(rules, self.root)), 1)

    def test_same_file_different_method_kept(self):
        touch(self.root, 'a.ma')
        rules = Group(
            Action('a.ma', method='geo', mode='multiple'),
            Action('a.ma', method='animation', mode='multiple'),
        )
        self.assertEqual(len(resolve(rules, self.root)), 2)

    def test_dedupe_can_be_disabled(self):
        touch(self.root, 'a.ma')
        rules = Group(
            Action('a.ma', method='geo', mode='multiple'),
            Action('a.ma', method='geo', mode='multiple'),
        )
        self.assertEqual(len(resolve(rules, self.root, dedupe=False)), 2)

    def test_same_file_matched_by_two_patterns_counted_once(self):
        touch(self.root, 'a.ma')
        rules = Group(Action(['a.ma', '*.ma'], method='geo', mode='multiple'))
        self.assertEqual(len(resolve(rules, self.root)), 1)


class ResolveStructureTest(ResolverTestCase):

    def test_bare_level_raises(self):
        with self.assertRaises(RuleStructureError):
            resolve(Level('cache'), self.root)

    def test_unknown_object_raises(self):
        with self.assertRaises(RuleDefinitionError):
            resolve('not a rule', self.root)


class ResolverStateTest(ResolverTestCase):

    def test_result_is_stable_across_repeated_resolves(self):
        touch(self.root, 'a.ma', 'b.ma')
        rules = Group(
            Action('a.ma', method='geo', checked=2, mutex='m'),
            Action('b.ma', method='geo', checked=2, mutex='m'),
        )
        resolver = Resolver()
        first = resolver.resolve(rules, self.root)
        second = resolver.resolve(rules, self.root)
        self.assertEqual([match.checked for match in first],
                         [match.checked for match in second])
        # User-defined Action objects must not be mutated by the resolution.
        self.assertEqual(rules.rules[0].checked, 2)
        self.assertEqual(rules.rules[1].checked, 2)

    def test_match_repr_and_as_tuple(self):
        touch(self.root, 'a.ma')
        matches = resolve(Group(Action('a.ma', method='geo')), self.root)
        self.assertIn('a.ma', repr(matches[0]))
        self.assertEqual(len(matches[0].as_tuple()), 3)


class ResolverCacheTest(ResolverTestCase):

    def test_caches_are_released_by_default(self):
        touch(self.root, 'a.ma')
        resolver = Resolver()
        resolver.resolve(Group(Action('*.ma', method='geo')), self.root)
        self.assertEqual(resolver.cache_info(), (0, 0))

    def test_keep_cache_reuses_listings_between_resolutions(self):
        touch(self.root, 'a.ma')
        rules = Group(Action('*.ma', method='geo'))
        resolver = Resolver(keep_cache=True)

        first = [match.name for match in resolver.resolve(rules, self.root)]
        self.assertEqual(first, ['a.ma'])
        self.assertGreater(resolver.cache_info()[0], 0)

        second = [match.name for match in resolver.resolve(rules, self.root)]
        self.assertEqual(second, first)

    def test_keep_cache_does_not_notice_new_files_until_cleared(self):
        """The documented trade-off: a kept cache must be cleared by the caller."""
        touch(self.root, 'a.ma')
        rules = Group(Action('*.ma', method='geo', mode='multiple'))
        resolver = Resolver(keep_cache=True)

        self.assertEqual([match.name for match in resolver.resolve(rules, self.root)],
                         ['a.ma'])

        touch(self.root, 'b.ma')
        self.assertEqual([match.name for match in resolver.resolve(rules, self.root)],
                         ['a.ma'])

        resolver.clear_cache()
        self.assertEqual(
            sorted(match.name for match in resolver.resolve(rules, self.root)),
            ['a.ma', 'b.ma'])


if __name__ == '__main__':
    unittest.main()
