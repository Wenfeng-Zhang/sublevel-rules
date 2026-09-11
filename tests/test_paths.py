# -*- coding: utf-8 -*-
"""Tests for the path adapter layer."""

import tempfile
import unittest

from pathlib import Path

from sublevel_rules.errors import PathError, SubLevelRulesError
from sublevel_rules.paths import (
    Entry,
    as_path,
    frame_pattern_for,
    list_entries,
    split_frame,
)

from .support import make_dir, touch


class SplitFrameTest(unittest.TestCase):

    def test_takes_last_digit_group(self):
        self.assertEqual(split_frame('abc_v001_0001'), ('abc_v001_', '0001', ''))

    def test_keeps_suffix_text(self):
        self.assertEqual(split_frame('abc100_beauty'), ('abc', '100', '_beauty'))

    def test_returns_none_without_digits(self):
        self.assertIsNone(split_frame('readme'))
        self.assertIsNone(split_frame(''))


class FramePatternForTest(unittest.TestCase):

    def test_percent_style(self):
        self.assertEqual(frame_pattern_for('%', 4), '%04d')

    def test_sharp_style(self):
        self.assertEqual(frame_pattern_for('#', 4), '####')

    def test_dollar_style(self):
        self.assertEqual(frame_pattern_for('$', 4), '$F4')

    def test_unknown_style_raises(self):
        with self.assertRaises(SubLevelRulesError):
            frame_pattern_for('?', 4)


class AsPathTest(unittest.TestCase):

    def test_none_raises(self):
        with self.assertRaises(PathError):
            as_path(None)

    def test_empty_string_raises(self):
        with self.assertRaises(PathError):
            as_path('   ')

    def test_path_passthrough(self):
        path = Path('a/b')
        self.assertIs(as_path(path), path)

    def test_string_converted(self):
        self.assertEqual(as_path('a/b'), Path('a/b'))

    def test_path_like_object_supported(self):
        class FakePathLike(object):
            def __fspath__(self):
                return 'a/b/c.ma'

        self.assertEqual(as_path(FakePathLike()), Path('a/b/c.ma'))

    def test_object_without_fspath(self):
        class OldStyle(object):
            def __str__(self):
                return 'a/b/c.ma'

        self.assertEqual(as_path(OldStyle()), Path('a/b/c.ma'))


class EntryTest(unittest.TestCase):

    def test_to_pattern(self):
        entry = Entry('abc_0001.abc')
        self.assertEqual(entry.to_pattern('%').name, 'abc_%04d.abc')
        self.assertEqual(entry.to_pattern('#').name, 'abc_####.abc')
        self.assertEqual(entry.to_pattern('$').name, 'abc_$F4.abc')

    def test_to_pattern_keeps_plain_name(self):
        entry = Entry('readme.txt')
        self.assertTrue(entry.to_pattern('%') is entry)

    def test_to_pattern_skips_single_media(self):
        entry = Entry('shot_0001.mov')
        self.assertTrue(entry.to_pattern('%') is entry)

    def test_frame(self):
        self.assertEqual(Entry('abc_0012.exr').frame, 12)
        self.assertEqual(Entry('readme.txt').frame, -1)
        self.assertEqual(Entry('plate.mov').frame, -1)

    def test_size_missing_file_returns_default(self):
        self.assertEqual(Entry('definitely/not/here.exr').size(), 0)
        self.assertEqual(Entry('definitely/not/here.exr').size(default=-1), -1)

    def test_size_reflects_current_file_size(self):
        """``size()`` reads the current value, not the cached listing snapshot.

        On Windows ``os.DirEntry.stat()`` caches its result, so it must not be
        reused -- otherwise a long-running process asking the same Entry for its
        size again would keep getting the old number.
        """
        with tempfile.TemporaryDirectory() as temp:
            path = touch(temp, 'a.ma')[0]
            entry = [item for item in list_entries(temp) if item.name == 'a.ma'][0]
            self.assertEqual(entry.size(), 0)

            with open(str(path), 'w') as handle:
                handle.write('x' * 100)
            self.assertEqual(entry.size(), 100)

    def test_comparison_and_hash(self):
        self.assertEqual(Entry('a/b'), Entry('a/b'))
        self.assertEqual(hash(Entry('a/b')), hash(Entry('a/b')))
        self.assertEqual(Entry('a/b'), 'a/b')
        self.assertNotEqual(Entry('a/b'), Entry('a/c'))

    def test_sorting(self):
        entries = sorted([Entry('b.ma'), Entry('a.ma')])
        self.assertEqual([entry.name for entry in entries], ['a.ma', 'b.ma'])

    def test_attributes(self):
        entry = Entry('a/b/c.ma')
        self.assertEqual(entry.name, 'c.ma')
        self.assertEqual(entry.stem, 'c')
        self.assertEqual(entry.ext, '.ma')
        self.assertEqual(entry.parent, Path('a/b'))
        self.assertEqual(str(entry), str(Path('a/b/c.ma')))

    def test_isfile_and_isdir_aliases(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'a.ma')
            make_dir(temp, 'sub')
            entries = {entry.name: entry for entry in list_entries(temp)}

            self.assertTrue(entries['a.ma'].isfile())
            self.assertFalse(entries['a.ma'].isdir())
            self.assertTrue(entries['sub'].isdir())
            self.assertFalse(entries['sub'].isfile())

    def test_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'a.ma')
            self.assertTrue(Entry(Path(temp) / 'a.ma').exists())
            self.assertFalse(Entry(Path(temp) / 'nope.ma').exists())


class ListEntriesTest(unittest.TestCase):

    def test_sorted_and_files_only(self):
        with tempfile.TemporaryDirectory() as temp:
            touch(temp, 'b.ma', 'a.ma')
            make_dir(temp, 'sub')

            names = [entry.name for entry in list_entries(temp)]
            self.assertEqual(names, ['a.ma', 'b.ma', 'sub'])

            files = [entry.name for entry in list_entries(temp, files_only=True)]
            self.assertEqual(files, ['a.ma', 'b.ma'])

    def test_missing_directory(self):
        self.assertEqual(list_entries('definitely/not/here'), [])


if __name__ == '__main__':
    unittest.main()
