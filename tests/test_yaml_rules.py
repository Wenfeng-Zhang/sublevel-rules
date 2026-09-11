# -*- coding: utf-8 -*-
"""Tests for the (removable) YAML adapter.

When PyYAML is not installed this whole group is skipped -- which also proves
that "YAML support is removable": without it everything else keeps working.
"""

import io
import tempfile
import unittest

from contextlib import redirect_stdout
from pathlib import Path

from sublevel_rules.cli import _extra_rule_loaders, main
from sublevel_rules.errors import SubLevelRulesError
from sublevel_rules.rules import Action, Group, Level, Rule
from sublevel_rules.resolver import resolve

from .support import touch

try:
    import yaml                                            # noqa: F401
    _HAS_YAML = True
except ImportError:                                        # pragma: no cover
    _HAS_YAML = False

try:
    # The adapter itself is removable too: delete yaml_rules.py and this whole
    # group is skipped.
    from sublevel_rules.yaml_rules import dump_rules, load_rules
    _HAS_ADAPTER = True
except ImportError:                                        # pragma: no cover
    dump_rules = load_rules = None
    _HAS_ADAPTER = False

_SKIP_REASON = '需要 PyYAML 与 yaml_rules 适配器'

_YAML_RULES = """\
type: group
rules:
  - type: action
    patterns: ["*_v{version_part}.ma"]
    method: animation
    checked: 2
  - type: rule
    levels:
      - type: level
        patterns: ["cache"]
      - type: level
        patterns: ["v{version_part}"]
      - type: action
        patterns: ["*.abc"]
        method: animation
        mode: multiple
        is_sequence: true
"""


@unittest.skipUnless(_HAS_ADAPTER, 'yaml_rules.py 已被移除（可选适配器）')
class AdapterDiscoveryTest(unittest.TestCase):
    """Adapter discovery does not depend on PyYAML (yaml is imported lazily)."""

    def test_cli_discovers_yaml_suffixes(self):
        loaders = _extra_rule_loaders()
        self.assertIn('.yaml', loaders)
        self.assertIn('.yml', loaders)
        self.assertIs(loaders['.yaml'], load_rules)

    def test_discovery_is_cached(self):
        self.assertIs(_extra_rule_loaders(), _extra_rule_loaders())


@unittest.skipUnless(_HAS_YAML and _HAS_ADAPTER, _SKIP_REASON)
class YamlLoadTest(unittest.TestCase):

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def _write(self, text, name='rules.yaml'):
        path = self.root / name
        path.write_text(text, encoding='utf-8')
        return str(path)

    def test_load_rules_from_file(self):
        rules = load_rules(self._write(_YAML_RULES))
        self.assertIsInstance(rules, Group)
        self.assertIsInstance(rules.rules[1], Rule)
        self.assertTrue(rules.rules[1].levels[0].patterns == ('cache',))

    def test_loaded_rules_resolve(self):
        touch(self.root, 'abc_v001.ma', 'cache/v001/c.0001.abc')
        matches = resolve(load_rules(self._write(_YAML_RULES)), self.root,
                          {'version_part': '001'})
        self.assertEqual(sorted(match.name for match in matches),
                         ['abc_v001.ma', 'c.%04d.abc'])

    def test_named_rules_in_one_file(self):
        path = self._write('mod:\n'
                           '  type: action\n'
                           '  patterns: ["*.ma"]\n'
                           '  method: geo\n'
                           'ani:\n'
                           '  type: action\n'
                           '  patterns: ["*.abc"]\n'
                           '  method: ani\n')
        self.assertEqual(load_rules(path, 'mod').method, 'geo')
        self.assertEqual(load_rules(path, 'ani').method, 'ani')

    def test_missing_name_raises(self):
        path = self._write('mod:\n  type: action\n  patterns: ["*.ma"]\n  method: geo\n')
        with self.assertRaises(SubLevelRulesError):
            load_rules(path, 'nope')

    def test_empty_file_raises(self):
        with self.assertRaises(SubLevelRulesError):
            load_rules(self._write(''))

    def test_broken_yaml_raises_library_error(self):
        path = self._write('type: group\nrules: [')
        with self.assertRaises(SubLevelRulesError) as ctx:
            load_rules(path)
        self.assertIn('YAML', str(ctx.exception))

    def test_missing_file_raises(self):
        with self.assertRaises(SubLevelRulesError):
            load_rules(str(self.root / 'nope.yaml'))

    def test_dump_then_load_roundtrip(self):
        rules = Group(Action('*.ma', method='geo', checked=2),
                      Rule(Level('cache'), Level('v*', mode='latest'),
                           Action('*.abc', method='ani', mode='multiple')),
                      mode='first')
        path = str(self.root / 'out.yaml')
        dump_rules(rules, path)

        loaded = load_rules(path)
        self.assertEqual(loaded.mode, 'first')
        self.assertEqual(loaded.rules[1].levels[1].mode, 'latest')

    def test_dump_returns_text(self):
        text = dump_rules(Action('*.ma', method='geo'))
        self.assertIn('type: action', text)
        self.assertIn('method: geo', text)

    def test_cli_loads_yaml_rules(self):
        path = self._write(_YAML_RULES)
        touch(self.root, 'abc_v001.ma')

        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main(['--rules', path, '--describe'])
        self.assertEqual(code, 0)
        self.assertIn("method='animation'", stream.getvalue())


if __name__ == '__main__':
    unittest.main()
