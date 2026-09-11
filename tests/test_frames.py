# -*- coding: utf-8 -*-
"""Tests for the frame expansion helpers."""

import unittest

from sublevel_rules.frames import frame_path, frame_tokens


class FramePathTest(unittest.TestCase):

    def test_percent_style(self):
        self.assertEqual(frame_path('abc.%04d.exr', 7).name, 'abc.0007.exr')

    def test_sharp_style(self):
        self.assertEqual(frame_path('abc.####.exr', 12).name, 'abc.0012.exr')

    def test_dollar_style(self):
        self.assertEqual(frame_path('abc.$F4.exr', 12).name, 'abc.0012.exr')

    def test_plain_name_unchanged(self):
        self.assertEqual(frame_path('abc.ma', 1).name, 'abc.ma')

    def test_sequence_object(self):
        from sublevel_rules.paths import Entry
        from sublevel_rules.sequences import SequentialFiles
        sequence = SequentialFiles(Entry('/tmp/abc.%04d.exr'), [1, 2], [])
        path = frame_path(sequence, 2)
        self.assertEqual(path.name, 'abc.0002.exr')
        self.assertEqual(str(path.parent).replace('\\', '/'), '/tmp')


class FrameTokensTest(unittest.TestCase):

    def test_tokens(self):
        self.assertEqual(frame_tokens('abc.%04d.exr'), ['%04d'])
        self.assertEqual(frame_tokens('abc.####.exr'), ['####'])
        self.assertEqual(frame_tokens('abc.$F4.exr'), ['$F4'])
        self.assertEqual(frame_tokens('abc.ma'), [])


if __name__ == '__main__':
    unittest.main()
