# -*- coding: utf-8 -*-
"""Tests for the preset rules.

The presets are "ready to use" rule templates and, like the DSL and the resolver,
part of the public contract -- so every preset is exercised on a real directory
tree to confirm it matches the resources it promises.
"""

import tempfile
import unittest

from pathlib import Path

from sublevel_rules.presets import ani_rules, mod_rules, rig_rules, tex_rules
from sublevel_rules.resolver import resolve
from sublevel_rules.rules import describe_rule

from .support import touch

_ALL_PRESETS = (ani_rules, mod_rules, rig_rules, tex_rules)


class PresetStructureTest(unittest.TestCase):

    def test_all_presets_are_groups(self):
        for factory in _ALL_PRESETS:
            self.assertEqual(factory().kind, 'group', factory.__name__)

    def test_all_presets_are_describable(self):
        for factory in _ALL_PRESETS:
            text = describe_rule(factory())
            self.assertIn('Group(', text, factory.__name__)
            self.assertIn('Action(', text, factory.__name__)

    def test_each_call_returns_a_fresh_rule_tree(self):
        first = mod_rules()
        second = mod_rules()
        self.assertIsNot(first, second)
        self.assertIsNot(first.rules[0], second.rules[0])

    def test_ani_preset_walks_into_cache(self):
        rules = ani_rules()
        rule = [item for item in rules.rules if getattr(item, 'kind', None) == 'rule']
        self.assertEqual(len(rule), 1)
        self.assertEqual([level.patterns for level in rule[0].levels],
                         [('cache',), ('v{version_part}', '*'), ('*.abc',)])


class PresetResolutionTest(unittest.TestCase):

    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def _resolve(self, rules, version_data=None):
        return resolve(rules, self.root, version_data or {'version_part': '001'})

    def test_mod_preset_mutex_keeps_first_match(self):
        touch(self.root, 'asset_mod_v001.abc', 'asset_v001.ma')
        matches = self._resolve(mod_rules())
        states = {match.name: match.state for match in matches}

        self.assertEqual(states['asset_mod_v001.abc'], 2)
        self.assertEqual(states['asset_v001.ma'], 0)   # same 'mod_rule' mutex group
        self.assertEqual({match.method for match in matches}, {'geo'})

    def test_mod_preset_collects_extra_formats(self):
        touch(self.root, 'asset_mod_v001.abc', 'asset_v001.usd', 'asset_v001.obj')
        matches = self._resolve(mod_rules())
        self.assertEqual(sorted(match.name for match in matches),
                         ['asset_mod_v001.abc', 'asset_v001.obj', 'asset_v001.usd'])

    def test_rig_preset(self):
        touch(self.root, 'rig_v001.ma', 'rig_v001.usd')
        matches = self._resolve(rig_rules())
        self.assertEqual(sorted(match.name for match in matches),
                         ['rig_v001.ma', 'rig_v001.usd'])
        self.assertEqual({match.method for match in matches}, {'rig'})

    def test_tex_preset(self):
        touch(self.root, 'tex_v001.ma', 'tex_v001.ass')
        matches = self._resolve(tex_rules())
        self.assertEqual(sorted(match.name for match in matches),
                         ['tex_v001.ass', 'tex_v001.ma'])
        self.assertEqual({match.method for match in matches}, {'material'})

    def test_ani_preset_root_and_cache(self):
        touch(self.root, 'ani_v001.ma', 'ani_cam_v001.abc',
              'cache/v001/cache.0001.abc', 'cache/v001/cache.0002.abc')
        matches = self._resolve(ani_rules())
        by_name = {match.name: match for match in matches}

        self.assertIn('ani_v001.ma', by_name)
        self.assertIn('ani_cam_v001.abc', by_name)
        self.assertIn('cache.%04d.abc', by_name)
        self.assertEqual(by_name['cache.%04d.abc'].frames, [1, 2])
        self.assertTrue(by_name['cache.%04d.abc'].is_sequence)
        self.assertEqual({match.method for match in matches}, {'animation'})

    def test_ani_preset_without_cache_directory(self):
        touch(self.root, 'ani_v001.ma')
        matches = self._resolve(ani_rules())
        self.assertEqual([match.name for match in matches], ['ani_v001.ma'])

    def test_presets_on_empty_directory_return_empty(self):
        for factory in _ALL_PRESETS:
            self.assertEqual(self._resolve(factory()), [], factory.__name__)


if __name__ == '__main__':
    unittest.main()
