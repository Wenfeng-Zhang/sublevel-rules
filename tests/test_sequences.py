# -*- coding: utf-8 -*-
"""Tests for frame-sequence scanning."""

import tempfile
import unittest

from pathlib import Path

from sublevel_rules.errors import SubLevelRulesError
from sublevel_rules.sequences import (
    SequentialFiles,
    is_sequence_name,
    scan_sequences,
)

from .support import make_dir, touch


class ScanSequencesTest(unittest.TestCase):

    def test_collapse_frames(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'abc.0001.exr', 'abc.0002.exr', 'abc.0003.exr', 'readme.txt')
            sequences = scan_sequences(temp)
            by_name = {item.name: item for item in sequences}

            self.assertIn('abc.%04d.exr', by_name)
            self.assertIn('readme.txt', by_name)

            sequence = by_name['abc.%04d.exr']
            self.assertEqual(sequence.frames, [1, 2, 3])
            self.assertEqual(sequence.missing, [])
            self.assertTrue(sequence.is_sequence)
            self.assertEqual(sequence.path.name, 'abc.%04d.exr')
            self.assertEqual(sequence.path.parent, Path(temp))

    def test_missing_frames(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'abc.0001.exr', 'abc.0003.exr', 'abc.0003.exr.bak')
            sequence = [item for item in scan_sequences(temp)
                        if item.name == 'abc.%04d.exr'][0]
            self.assertEqual(sequence.frames, [1, 3])
            self.assertEqual(sequence.missing, [2])

    def test_single_media_not_collapsed(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'plate.0001.mov', 'plate.0002.mov')
            sequences = scan_sequences(temp)
            self.assertEqual(sorted(item.name for item in sequences),
                             ['plate.0001.mov', 'plate.0002.mov'])
            for item in sequences:
                self.assertEqual(item.frames, [])
                self.assertFalse(item.is_sequence)

    def test_single_media_exts_can_be_overridden(self):
        """An empty collection drops the "single-frame media" restriction, so
        ``.mov`` takes part in collapsing too."""
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'shot.0001.mov', 'shot.0002.mov')
            self.assertEqual(
                [item.name for item in scan_sequences(temp, single_media_exts=[])],
                ['shot.%04d.mov'])
            self.assertEqual(
                [item.name for item in scan_sequences(temp, single_media_exts=['.mov'])],
                ['shot.0001.mov', 'shot.0002.mov'])

    def test_sharp_frame_pattern(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'abc.0001.exr', 'abc.0002.exr')
            names = [item.name for item in scan_sequences(temp, frame_pattern='#')]
            self.assertEqual(names, ['abc.####.exr'])

    def test_dollar_frame_pattern(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'abc.0001.exr')
            names = [item.name for item in scan_sequences(temp, frame_pattern='$')]
            self.assertEqual(names, ['abc.$F4.exr'])

    def test_invalid_frame_pattern_raises(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'abc.0001.exr')
            with self.assertRaises(SubLevelRulesError):
                scan_sequences(temp, frame_pattern='?')

    def test_directories_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            make_dir(temp, 'subfolder')
            touch(temp, 'abc.0001.exr')
            names = [item.name for item in scan_sequences(temp)]
            self.assertEqual(names, ['abc.%04d.exr'])

    def test_missing_directory_returns_empty(self):
        self.assertEqual(scan_sequences('definitely/not/here'), [])

    def test_frames_are_sorted(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'abc.0003.exr', 'abc.0001.exr', 'abc.0002.exr')
            sequence = scan_sequences(temp)[0]
            self.assertEqual(sequence.frames, [1, 2, 3])
            self.assertEqual(str(sequence), str(Path(temp) / 'abc.%04d.exr'))


class IsSequenceNameTest(unittest.TestCase):

    def test_percent(self):
        self.assertTrue(is_sequence_name('abc.%04d.exr'))

    def test_sharp(self):
        self.assertTrue(is_sequence_name('abc.####.exr'))

    def test_dollar(self):
        self.assertTrue(is_sequence_name('abc.$F4.exr'))

    def test_plain(self):
        self.assertFalse(is_sequence_name('abc.ma'))
        self.assertFalse(is_sequence_name('single.0001.mov'))


class SequentialFilesTest(unittest.TestCase):

    def test_namedtuple_compatibility(self):
        from sublevel_rules.paths import Entry
        entry = Entry('abc.%04d.exr')
        sequence = SequentialFiles(entry, [1, 2], [])
        filename, frames, missing = sequence
        self.assertEqual(filename, entry)
        self.assertEqual(frames, [1, 2])
        self.assertEqual(missing, [])


if __name__ == '__main__':
    unittest.main()
