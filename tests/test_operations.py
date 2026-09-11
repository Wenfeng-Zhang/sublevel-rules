# -*- coding: utf-8 -*-
"""Tests for the data assembly layer (covers the two original bugs: parent state
and relative paths)."""

import tempfile
import unittest

from pathlib import Path

from sublevel_rules.errors import PathError
from sublevel_rules.operations import (
    build_operations,
    get_sub_level_op,
    human_size,
    parent_check_state,
)
from sublevel_rules.rules import Action, Group, Level, Rule, to_check_state
from sublevel_rules.resolver import resolve

from .support import touch


class HumanSizeTest(unittest.TestCase):

    def test_default_megabyte(self):
        self.assertEqual(human_size(1024), '0.00MB')

    def test_target_unit(self):
        self.assertEqual(human_size(2048, 'B'), '2048.00B')
        self.assertEqual(human_size(1024, 'KB'), '1.00KB')

    def test_auto_unit(self):
        self.assertEqual(human_size(1536, None), '1.50KB')

    def test_invalid_unit(self):
        self.assertEqual(human_size(1024, 'XB'), '')

    def test_invalid_value(self):
        self.assertEqual(human_size('abc'), '')


class ParentCheckStateTest(unittest.TestCase):

    def test_all_checked(self):
        self.assertEqual(parent_check_state([2, 2]), 2)

    def test_all_unchecked(self):
        self.assertEqual(parent_check_state([0, 0]), 0)

    def test_mixed(self):
        self.assertEqual(parent_check_state([2, 0]), 1)

    def test_true_counts_as_checked(self):
        # ``True == 2`` is False, so comparing raw values would count checked=True
        # entries as partially checked.
        states = [to_check_state(True), to_check_state(True)]
        self.assertEqual(parent_check_state(states), 2)

    def test_empty(self):
        self.assertEqual(parent_check_state([]), 0)


class BuildOperationsTestCase(unittest.TestCase):

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def _operations(self, rules, version_data=None, **kwargs):
        matches = resolve(rules, self.root, version_data)
        return build_operations(matches, str(self.root),
                                version_data if version_data is not None else {},
                                size_mode='none', **kwargs)


class BuildOperationsFlatTest(BuildOperationsTestCase):

    def test_relative_path_and_grouping(self):
        touch(self.root, 'abc_v001.ma', 'cache/v001/a.abc', 'cache/v001/b.abc')
        rules = Group(
            Action('*_v{version_part}.ma', method='geo', checked=2),
            Rule(Level('cache'), Level('v{version_part}'),
                 Action('*.abc', method='animation', mode='multiple', checked=2)),
        )
        operations = self._operations(rules, {'version_part': '001'})

        files = [item for item in operations if 'children' not in item]
        groups = [item for item in operations if 'children' in item]

        self.assertEqual([item['filename'] for item in files], ['abc_v001.ma'])
        self.assertEqual([item['relative_path'] for item in files], ['abc_v001.ma'])
        self.assertEqual([item['filename'] for item in groups], ['cache/v001'])
        self.assertEqual(groups[0]['filename_checked'], 2)
        self.assertEqual(sorted(child['filename'] for child in groups[0]['children']),
                         ['a.abc', 'b.abc'])
        self.assertEqual(groups[0]['children'][0]['relative_path'], 'cache/v001/a.abc')

    def test_old_field_names_are_kept(self):
        touch(self.root, 'a.ma')
        operations = self._operations(Group(Action('a.ma', method='geo', checked=2)))
        item = operations[0]
        for field in ('filename_checked', 'op_func', 'args', 'file_stem', 'path_name',
                      'filename', 'orm', 'size', 'type', 'options'):
            self.assertIn(field, item)
        self.assertEqual(item['filename_checked'], 2)
        self.assertEqual(item['type'], '.ma')
        self.assertEqual(item['file_stem'], self.root / 'a')

    def test_parent_state_with_boolean_checked(self):
        touch(self.root, 'cache/v001/a.abc', 'cache/v001/b.abc')
        rules = Group(
            Rule(Level('cache'), Level('v001'),
                 Action('a.abc', method='animation', checked=True)),
            Rule(Level('cache'), Level('v001'),
                 Action('b.abc', method='animation', checked=True)),
        )
        operations = self._operations(rules)
        groups = [item for item in operations if 'children' in item]
        self.assertEqual(groups[0]['filename_checked'], 2)

    def test_parent_state_partial(self):
        touch(self.root, 'cache/v001/a.abc', 'cache/v001/b.abc')
        rules = Group(
            Rule(Level('cache'), Level('v001'),
                 Action('a.abc', method='animation', checked=2)),
            Rule(Level('cache'), Level('v001'),
                 Action('b.abc', method='animation', checked=0)),
        )
        operations = self._operations(rules)
        groups = [item for item in operations if 'children' in item]
        self.assertEqual(groups[0]['filename_checked'], 1)

    def test_op_resolver_and_skip(self):
        touch(self.root, 'a.ma', 'b.abc')
        rules = Group(
            Action('a.ma', method='known', mode='multiple'),
            Action('b.abc', method='unknown', mode='multiple'),
        )
        matches = resolve(rules, self.root)
        operations = build_operations(
            matches, str(self.root), {}, op_resolver=lambda method: (
                (lambda: None) if method == 'known' else None),
            size_mode='none', skip_without_op=True)
        self.assertEqual([item['filename'] for item in operations], ['a.ma'])

    def test_size_of_sequence_does_not_raise(self):
        touch(self.root, 'cache/v001/abc.0001.abc', 'cache/v001/abc.0002.abc')
        rules = Group(Rule(Level('cache'), Level('v001'),
                           Action('*.abc', method='animation', mode='multiple',
                                  is_sequence=True)))
        matches = resolve(rules, self.root)
        operations = build_operations(matches, str(self.root), {}, size_mode='first')
        group = [entry for entry in operations if 'children' in entry][0]
        item = group['children'][0]
        self.assertIsInstance(item['size'], str)
        self.assertEqual(item['frames'], [1, 2])


class BuildOperationsGroupModeTest(BuildOperationsTestCase):

    def test_group_mode_none(self):
        touch(self.root, 'cache/v001/a.abc')
        rules = Group(Rule(Level('cache'), Level('v001'), Action('*.abc', method='geo')))
        operations = self._operations(rules, group_mode=None)
        self.assertEqual(len(operations), 1)
        self.assertNotIn('children', operations[0])
        self.assertNotIn('_dir_parts', operations[0])

    def test_group_mode_nested(self):
        touch(self.root, 'cache/v001/deep/a.abc')
        rules = Group(Rule(
            Level('cache'), Level('v001'), Level('deep'),
            Action('*.abc', method='geo', checked=2)))
        operations = self._operations(rules, group_mode='nested')
        self.assertEqual(len(operations), 1)
        node = operations[0]
        self.assertEqual(node['filename'], 'cache')
        self.assertEqual(node['filename_checked'], 2)
        child = node['children'][0]
        self.assertEqual(child['filename'], 'cache/v001')
        deep = child['children'][0]
        self.assertEqual(deep['filename'], 'cache/v001/deep')
        self.assertEqual(deep['children'][0]['filename'], 'a.abc')

    def test_invalid_group_mode(self):
        touch(self.root, 'a.ma')
        matches = resolve(Group(Action('a.ma', method='geo')), self.root)
        with self.assertRaises(ValueError):
            build_operations(matches, self.root, {}, group_mode='diagonal')


class GetSubLevelOpTest(BuildOperationsTestCase):

    def test_compatible_entry_point(self):
        touch(self.root, 'abc_v001.ma', 'cache/v001/a.abc')

        class FakeModule(object):
            @staticmethod
            def get_import_rules():
                return Group(
                    Action('*_v{version_part}.ma', method='geo', checked=2),
                    Rule(Level('cache'), Level('v{version_part}'),
                         Action('*.abc', method='animation', mode='multiple', checked=2)),
                )

            @staticmethod
            def create_api_version(method):
                return lambda *args, **kwargs: method

        version_data = {'version_part': '001', 'path': str(self.root)}
        operations = get_sub_level_op(FakeModule, version_data, size_mode='none')

        flat = {}
        for item in operations:
            if 'children' in item:
                for child in item['children']:
                    flat[child['filename']] = child
            else:
                flat[item['filename']] = item

        self.assertEqual(sorted(flat), ['a.abc', 'abc_v001.ma'])
        self.assertEqual(flat['abc_v001.ma']['filename_checked'], 2)
        self.assertEqual(flat['a.abc']['orm'], version_data)
        self.assertTrue(callable(flat['a.abc']['op_func']))

    def test_returns_empty_without_api(self):
        class FakeModule(object):
            @staticmethod
            def get_import_rules():
                return Group(Action('*.ma', method='geo'))

        self.assertEqual(get_sub_level_op(FakeModule, {'path': str(self.root)}), [])

    def test_missing_path_raises(self):
        class FakeModule(object):
            @staticmethod
            def get_import_rules():
                return Group(Action('*.ma', method='geo'))

            @staticmethod
            def create_api_version(method):
                return lambda *args, **kwargs: method

        with self.assertRaises(PathError):
            get_sub_level_op(FakeModule, {})

    def test_skips_entries_without_operation(self):
        touch(self.root, 'a.ma', 'b.abc')

        class FakeModule(object):
            @staticmethod
            def get_import_rules():
                return Group(
                    Action('a.ma', method='geo', mode='multiple'),
                    Action('b.abc', method='unknown', mode='multiple'),
                )

            @staticmethod
            def create_api_version(method):
                return (lambda *args, **kwargs: method) if method == 'geo' else None

        operations = get_sub_level_op(FakeModule, {'path': str(self.root)},
                                      size_mode='none')
        self.assertEqual([item['filename'] for item in operations], ['a.ma'])


if __name__ == '__main__':
    unittest.main()
