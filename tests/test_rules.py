# -*- coding: utf-8 -*-
"""Tests for the rule DSL."""

import unittest

from sublevel_rules.errors import RuleDefinitionError, RuleStructureError
from sublevel_rules.rules import Action, Group, Level, Multi, Rule, to_check_state


class ToCheckStateTest(unittest.TestCase):

    def test_table(self):
        self.assertEqual(to_check_state(None), 0)
        self.assertEqual(to_check_state(False), 0)
        self.assertEqual(to_check_state(True), 2)
        self.assertEqual(to_check_state(0), 0)
        self.assertEqual(to_check_state(1), 1)
        self.assertEqual(to_check_state(2), 2)
        self.assertEqual(to_check_state(3), 2)
        self.assertEqual(to_check_state(-1), 0)
        self.assertEqual(to_check_state('yes'), 2)


class LevelTest(unittest.TestCase):

    def test_patterns_normalized_to_tuple(self):
        self.assertEqual(Level('cache').patterns, ('cache',))
        self.assertEqual(Level(['a', 'b']).patterns, ('a', 'b'))

    def test_default_mode(self):
        self.assertEqual(Level('cache').mode, 'first')
        self.assertEqual(Multi('a', 'b').mode, 'multiple')

    def test_multi_flattens_list(self):
        self.assertEqual(Multi(['a', 'b']).patterns, ('a', 'b'))

    def test_empty_patterns_raises(self):
        with self.assertRaises(RuleDefinitionError):
            Level([])
        with self.assertRaises(RuleDefinitionError):
            Level(None)

    def test_invalid_mode_raises(self):
        with self.assertRaises(RuleDefinitionError):
            Level('cache', mode='everything')

    def test_collect_requires_action(self):
        Level('cache', collect=Action('*.abc', method='geo'))
        with self.assertRaises(RuleDefinitionError):
            Level('cache', collect='*.abc')


class ActionTest(unittest.TestCase):

    def test_defaults(self):
        action = Action('*.ma', method='geo')
        self.assertEqual(action.method, 'geo')
        self.assertFalse(action.is_sequence)
        self.assertIsNone(action.checked)
        self.assertIsNone(action.mutex)

    def test_method_required(self):
        with self.assertRaises(RuleDefinitionError):
            Action('*.ma', method='')

    def test_extra_options_are_kept(self):
        action = Action('*.exr', method='texture', is_sequence=True,
                        frame_pattern='#', tag='beauty')
        self.assertEqual(action.options['frame_pattern'], '#')
        self.assertEqual(action.options['tag'], 'beauty')


class RuleTest(unittest.TestCase):

    def test_valid_rule(self):
        rule = Rule(Level('cache'), Level('v{version_part}'),
                    Action('*.abc', method='geo'))
        self.assertEqual(len(rule.levels), 3)

    def test_empty_raises(self):
        with self.assertRaises(RuleDefinitionError):
            Rule()

    def test_last_level_must_be_action(self):
        with self.assertRaises(RuleStructureError):
            Rule(Level('cache'))

    def test_action_must_be_last(self):
        with self.assertRaises(RuleStructureError):
            Rule(Action('*.ma', method='geo'), Level('cache'))

    def test_non_level_member_raises(self):
        with self.assertRaises(RuleDefinitionError):
            Rule('cache')


class GroupTest(unittest.TestCase):

    def test_valid_members(self):
        group = Group(
            Action('*.ma', method='geo'),
            Rule(Level('cache'), Action('*.abc', method='geo')),
            Group(Action('*.usd', method='geo')),
        )
        self.assertEqual(len(group.rules), 3)

    def test_bare_level_raises(self):
        with self.assertRaises(RuleStructureError):
            Group(Level('cache'))

    def test_empty_raises(self):
        with self.assertRaises(RuleDefinitionError):
            Group()

    def test_list_form(self):
        group = Group([Action('*.ma', method='geo')])
        self.assertEqual(len(group.rules), 1)


class ReprTest(unittest.TestCase):

    def test_repr_is_informative(self):
        self.assertIn('Action', repr(Action('*.ma', method='geo')))
        self.assertIn('Rule', repr(Rule(Action('*.ma', method='geo'))))


if __name__ == '__main__':
    unittest.main()
