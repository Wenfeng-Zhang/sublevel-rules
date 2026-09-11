# -*- coding: utf-8 -*-
"""Tests for the command line interface."""

import io
import json
import tempfile
import unittest

from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from sublevel_rules.cli import (
    build_parser,
    extract_version_part,
    load_rules,
    main,
    render_operations,
    to_jsonable,
)
from sublevel_rules.errors import SubLevelRulesError

from .support import touch


class ExtractVersionPartTest(unittest.TestCase):

    def test_takes_digits(self):
        self.assertEqual(extract_version_part('/show/asset/mod/v001'), '001')

    def test_windows_separator(self):
        self.assertEqual(extract_version_part('C:\\show\\asset\\v012'), '012')

    def test_no_digits(self):
        self.assertEqual(extract_version_part('/show/asset/mod'), '*')


class LoadRulesTest(unittest.TestCase):

    def test_from_python_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'my_rules.py'
            path.write_text(
                'from sublevel_rules import Action, Group\n\n\n'
                'def get_import_rules():\n'
                "    return Group(Action('*.ma', method='geo'))\n")
            rules = load_rules('{}:get_import_rules'.format(path))
            self.assertEqual(rules.kind, 'group')

    def test_from_module(self):
        rules = load_rules('sublevel_rules.presets:mod_rules')
        self.assertEqual(rules.kind, 'group')

    def test_missing_attribute_raises(self):
        with self.assertRaises(SubLevelRulesError):
            load_rules('sublevel_rules.presets:not_a_thing')

    def test_missing_file_raises(self):
        with self.assertRaises(SubLevelRulesError):
            load_rules('definitely/not/here.py:get_import_rules')


class ToJsonableTest(unittest.TestCase):

    def test_drops_unserializable_fields(self):
        operations = [{
            'filename': 'a.ma',
            'op_func': lambda: None,
            'args': (object(), {}),
            'orm': {},
            'sequence': object(),
        }]
        converted = to_jsonable(operations)
        self.assertEqual(converted, [{'filename': 'a.ma'}])


class ParserTest(unittest.TestCase):

    def test_defaults(self):
        args = build_parser().parse_args(['/tmp/v001'])
        self.assertEqual(args.version_path, '/tmp/v001')
        self.assertEqual(args.group_mode, 'flat')
        self.assertEqual(args.frame_pattern, '%')
        self.assertIsNone(args.rules)
        self.assertFalse(args.as_json)

    def test_version_path_is_optional_for_describe(self):
        args = build_parser().parse_args(['--describe'])
        self.assertIsNone(args.version_path)
        self.assertTrue(args.describe)

    def test_exclude_can_repeat(self):
        args = build_parser().parse_args(
            ['/tmp/v001', '--exclude', '.git', '--exclude', '*.bak'])
        self.assertEqual(args.exclude, ['.git', '*.bak'])


class RenderOperationsTest(unittest.TestCase):

    def test_renders_marks_groups_and_frames(self):
        operations = [
            {'filename': 'a.ma', 'filename_checked': 2, 'method': 'geo',
             'size': '1.00MB', 'is_sequence': False},
            {'filename': 'cache/v001', 'filename_checked': 1, 'children': [
                {'filename': 'c.%04d.abc', 'filename_checked': 0, 'method': 'ani',
                 'size': '2.00MB', 'is_sequence': True, 'frames': [1, 2]},
            ]},
        ]
        stream = io.StringIO()
        render_operations(operations, stream)
        text = stream.getvalue()

        self.assertIn('[x] a.ma', text)
        self.assertIn('[-] cache/v001', text)
        self.assertIn('[ ] c.%04d.abc', text)
        self.assertIn('2 frames', text)
        self.assertIn('|-- ', text)          # last line uses `--, earlier ones |--


class MainTest(unittest.TestCase):

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

    def test_json_output(self):
        touch(self.root, 'asset_mod_v001.abc', 'asset_v001.ma')
        code, output = self._run([str(self.root), '--preset', 'mod',
                                  '--version-part', '001', '--json'])
        self.assertEqual(code, 0)
        data = json.loads(output)
        states = {item['filename']: item['filename_checked'] for item in data}
        # In the mod rule abc and ma/mb share the 'mod_rule' mutex group, so only
        # the first match stays checked.
        self.assertEqual(states['asset_mod_v001.abc'], 2)
        self.assertEqual(states['asset_v001.ma'], 0)

    def test_text_output_with_groups(self):
        touch(self.root, 'abc_v001.ma', 'cache/v001/a.abc')
        code, output = self._run([str(self.root), '--preset', 'ani',
                                  '--version-part', '001'])
        self.assertEqual(code, 0)
        self.assertIn('abc_v001.ma', output)
        self.assertIn('cache/v001', output)
        self.assertIn('a.abc', output)

    def test_nested_group_mode(self):
        touch(self.root, 'cache/v001/a.abc')
        code, output = self._run([str(self.root), '--preset', 'ani',
                                  '--version-part', '001',
                                  '--group-mode', 'nested'])
        self.assertEqual(code, 0)
        self.assertIn('cache', output)

    def test_missing_root_reports_zero_matches(self):
        code, output = self._run([str(self.root / 'nope'), '--preset', 'mod'])
        self.assertEqual(code, 0)
        self.assertIn('matched      : 0', output)

    def test_custom_rules_file(self):
        touch(self.root, 'a.ma')
        rules_file = self.root / 'rules_here.py'
        rules_file.write_text(
            'from sublevel_rules import Action, Group\n\n\n'
            'def get_import_rules():\n'
            "    return Group(Action('*.ma', method='geo', checked=2))\n")
        code, output = self._run([str(self.root), '--rules', str(rules_file),
                                  '--json'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)[0]['filename'], 'a.ma')

    def test_rule_load_error_is_reported_without_traceback(self):
        """A broken rule file yields one error line plus exit code 2 instead of a
        raised exception."""
        stream, error = io.StringIO(), io.StringIO()
        with redirect_stdout(stream), redirect_stderr(error):
            code = main(['--rules', str(self.root / 'nope.py'), '--describe'])
        self.assertEqual(code, 2)
        self.assertIn('错误', error.getvalue())


if __name__ == '__main__':
    unittest.main()
