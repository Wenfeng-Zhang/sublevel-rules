# -*- coding: utf-8 -*-
"""Tests for ``rule_dict`` (rules <-> nested dict)."""

import tempfile
import unittest

from pathlib import Path

from sublevel_rules.errors import RuleDefinitionError
from sublevel_rules.rule_dict import NODE_TYPES, rule_from_dict, rule_to_dict
from sublevel_rules.rules import Action, Group, Level, Multi, Rule
from sublevel_rules.resolver import resolve

from .support import touch


class RuleFromDictTest(unittest.TestCase):

    def test_minimal_action(self):
        action = rule_from_dict({'type': 'action', 'patterns': ['*.ma'],
                                 'method': 'geo'})
        self.assertIsInstance(action, Action)
        self.assertEqual(action.patterns, ('*.ma',))
        self.assertEqual(action.method, 'geo')

    def test_full_tree(self):
        data = {
            'type': 'group',
            'mode': 'first',
            'options': {'tag': 'beauty'},
            'rules': [
                {'type': 'action', 'patterns': ['*.abc'], 'method': 'geo',
                 'checked': 2, 'mutex': 'm'},
                {'type': 'rule',
                 'levels': [
                     {'type': 'level', 'patterns': ['cache']},
                     {'type': 'level', 'patterns': ['v*'], 'mode': 'latest',
                      'require_content': True, 'optional': False},
                     {'type': 'action', 'patterns': ['*.abc'], 'method': 'ani',
                      'mode': 'multiple', 'is_sequence': True},
                 ]},
            ],
        }
        rules = rule_from_dict(data)

        self.assertIsInstance(rules, Group)
        self.assertEqual(rules.mode, 'first')
        self.assertEqual(rules.options['tag'], 'beauty')
        self.assertIsInstance(rules.rules[1], Rule)
        self.assertEqual(rules.rules[1].levels[1].mode, 'latest')
        self.assertTrue(rules.rules[1].levels[1].require_content)

    def test_multi_is_flattened(self):
        node = rule_from_dict({'type': 'multi', 'patterns': ['a', 'b']})
        self.assertIsInstance(node, Multi)
        self.assertEqual(node.patterns, ('a', 'b'))
        self.assertEqual(node.mode, 'multiple')

    def test_collect_is_recursive(self):
        data = {
            'type': 'level',
            'patterns': ['tex'],
            'collect': [{'type': 'action', 'patterns': ['*.txt'], 'method': 'readme'}],
            'collect_scope': 'parent',
        }
        level = rule_from_dict(data)
        self.assertEqual([item.method for item in level.collect], ['readme'])
        self.assertEqual(level.collect_scope, 'parent')

    def test_multi_collect_is_recursive(self):
        """``type: multi`` supports collect too -- it used to be silently dropped
        (and lost again on the way back through ``rule_to_dict``)."""
        node = rule_from_dict({
            'type': 'multi',
            'patterns': ['tex'],
            'collect': [{'type': 'action', 'patterns': ['*.txt'], 'method': 'readme'}],
        })
        self.assertEqual([item.method for item in node.collect], ['readme'])
        self.assertEqual(rule_to_dict(node)['collect'][0]['method'], 'readme')
        self.assertEqual(
            [item.method for item in rule_from_dict(rule_to_dict(node)).collect],
            ['readme'])

    def test_missing_required_key_points_at_path(self):
        """A missing required key raises a RuleDefinitionError carrying the
        location, not a bare TypeError."""
        with self.assertRaises(RuleDefinitionError) as ctx:
            rule_from_dict({'type': 'level'})
        self.assertIn('root', str(ctx.exception))
        self.assertIn('patterns', str(ctx.exception))

        with self.assertRaises(RuleDefinitionError) as ctx:
            rule_from_dict({'type': 'action', 'patterns': ['*.ma']})
        self.assertIn('method', str(ctx.exception))

    def test_action_collect_is_recursive(self):
        data = {'type': 'action', 'patterns': ['*.ma'], 'method': 'geo',
                'collect': {'type': 'action', 'patterns': ['*.txt'], 'method': 'readme'}}
        action = rule_from_dict(data)
        self.assertEqual([item.method for item in action.collect], ['readme'])

    def test_options_are_expanded(self):
        action = rule_from_dict({'type': 'action', 'patterns': ['*.exr'],
                                 'method': 'tex', 'options': {'frame_pattern': '#'}})
        self.assertEqual(action.options['frame_pattern'], '#')

    def test_unknown_type_raises_with_hint(self):
        with self.assertRaises(RuleDefinitionError) as ctx:
            rule_from_dict({'type': 'branch'})
        self.assertIn('type', str(ctx.exception))
        self.assertIn('action', str(ctx.exception))

    def test_missing_type_raises(self):
        with self.assertRaises(RuleDefinitionError):
            rule_from_dict({'patterns': ['*.ma']})

    def test_unknown_key_points_at_path(self):
        with self.assertRaises(RuleDefinitionError) as ctx:
            rule_from_dict({'type': 'group',
                            'rules': [{'type': 'action', 'patterns': ['*.ma'],
                                       'method': 'geo', 'cheked': 2}]})
        message = str(ctx.exception)
        self.assertIn('root.rules[0]', message)
        self.assertIn('cheked', message)

    def test_not_a_dict_raises(self):
        with self.assertRaises(RuleDefinitionError):
            rule_from_dict(['not', 'a', 'dict'])

    def test_wrong_options_type_raises(self):
        with self.assertRaises(RuleDefinitionError):
            rule_from_dict({'type': 'action', 'patterns': ['*.ma'],
                            'method': 'geo', 'options': 'nope'})

    def test_node_types_are_exposed(self):
        self.assertEqual(NODE_TYPES, ('action', 'group', 'level', 'multi', 'rule'))


class RuleToDictTest(unittest.TestCase):

    def test_roundtrip_is_stable(self):
        rules = Group(
            Action(['*.ma'], method='geo', checked=2, mutex='m'),
            Rule(Level('cache'),
                 Level('v*', mode='latest', require_content=True),
                 Action('*.abc', method='ani', mode='multiple', is_sequence=True)),
            mode='first',
        )
        first = rule_to_dict(rules)
        self.assertEqual(rule_to_dict(rule_from_dict(first)), first)

    def test_defaults_are_omitted(self):
        data = rule_to_dict(Action('*.ma', method='geo'))
        self.assertEqual(data['type'], 'action')
        self.assertEqual(data['patterns'], ['*.ma'])
        self.assertNotIn('checked', data)
        self.assertNotIn('mutex', data)
        self.assertNotIn('files_only', data)

    def test_group_mode_omitted_when_default(self):
        self.assertNotIn('mode', rule_to_dict(Group(Action('*.ma', method='geo'))))
        self.assertEqual(rule_to_dict(Group(Action('*.ma', method='geo'),
                                            mode='first'))['mode'], 'first')

    def test_multi_exported_as_multi(self):
        data = rule_to_dict(Multi('a', 'b'))
        self.assertEqual(data['type'], 'multi')
        self.assertEqual(data['patterns'], ['a', 'b'])

    def test_unknown_object_raises(self):
        with self.assertRaises(RuleDefinitionError):
            rule_to_dict(object())


class RuleFromDictIntegrationTest(unittest.TestCase):

    def test_dicted_rules_resolve_like_python_rules(self):
        data = {
            'type': 'group',
            'rules': [
                {'type': 'action', 'patterns': ['*_v{version_part}.ma'],
                 'method': 'ani', 'checked': 2},
                {'type': 'rule',
                 'levels': [
                     {'type': 'level', 'patterns': ['cache']},
                     {'type': 'level', 'patterns': ['v{version_part}']},
                     {'type': 'action', 'patterns': ['*.abc'], 'method': 'ani',
                      'mode': 'multiple', 'is_sequence': True},
                 ]},
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'abc_v001.ma', 'cache/v001/c.0001.abc', 'cache/v001/c.0002.abc')
            matches = resolve(rule_from_dict(data), Path(temp),
                              {'version_part': '001'})

        self.assertEqual(sorted(match.name for match in matches),
                         ['abc_v001.ma', 'c.%04d.abc'])


if __name__ == '__main__':
    unittest.main()
