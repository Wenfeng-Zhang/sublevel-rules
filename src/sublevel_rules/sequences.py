# -*- coding: utf-8 -*-
"""Frame-sequence scanning and collapsing.

Three decisions that are easy to trip over:

* Entries are keyed by :class:`~sublevel_rules.paths.Entry`, so two files belong
  to the same sequence exactly when they collapse onto the same path -- no hidden
  dependence on how a path object compares.
* Frame numbers are deduplicated with a ``set`` while the surviving frames keep
  their sorted order.
* A file whose frame number cannot be parsed stays a standalone entry instead of
  being forced into a sequence with a bogus frame number.
"""

import bisect

from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, NamedTuple, Optional

from .const import DEFAULT_FRAME_PATTERN, SINGLE_MEDIA_EXTS
from .frames import frame_tokens
from .paths import Entry, frame_pattern_for, list_entries

__all__ = ['SequentialFiles', 'is_sequence_name', 'scan_sequences']


class SequentialFiles(NamedTuple):
    """One (possibly collapsed) frame-sequence entry.

    The fields are part of the compatibility contract:

    :param filename: :class:`~sublevel_rules.paths.Entry`. For a frame sequence
        this is the pattern entry (e.g. ``abc.%04d.exr``); for single-frame
        media or plain files it is the entry itself.
    :param frames: frame numbers that exist (sorted, deduplicated).
    :param missing: frame numbers missing between the first and the last frame
        (sorted).
    """

    filename: Entry
    frames: List[int]
    missing: List[int]

    @property
    def name(self) -> str:
        """File name (with extension)."""
        return self.filename.name

    @property
    def path(self) -> Path:
        """:class:`pathlib.Path`."""
        return self.filename.path

    @property
    def ext(self) -> str:
        """Extension, including the leading dot."""
        return self.filename.ext

    @property
    def is_sequence(self) -> bool:
        """Whether this entry is a collapsed frame sequence."""
        return is_sequence_name(self.filename.name)

    def __str__(self) -> str:
        return str(self.filename)


def is_sequence_name(name: str) -> bool:
    """Tell whether a file name is a (collapsed) frame-sequence name.

    Only real placeholders count (``%04d`` / ``%4d`` / ``%d`` / ``####`` /
    ``$F4``), so a name that merely contains ``%0`` by accident such as
    ``abc.100%0.exr`` is not mistaken for a sequence.

    >>> is_sequence_name('abc.%04d.exr')
    True
    >>> is_sequence_name('abc.100%0.exr')
    False
    """
    return bool(frame_tokens(name))


def scan_sequences(directory: Any, frame_pattern: str = DEFAULT_FRAME_PATTERN,
                   single_media_exts: Optional[Iterable[str]] = None
                   ) -> List[SequentialFiles]:
    """Scan ``directory`` (non-recursive) and collapse frame sequences.

    :param directory: directory path (anything :func:`~sublevel_rules.paths.as_path`
        accepts).
    :param frame_pattern: frame placeholder style, ``'%'`` / ``'#'`` / ``'$'``.
    :param single_media_exts: media suffixes that must be treated as single
        files; ``None`` uses :data:`~sublevel_rules.const.SINGLE_MEDIA_EXTS`.
        Pass an empty collection to drop that restriction entirely.
    :returns: ``list`` of :class:`SequentialFiles`, sorted by name.
    """
    media_exts: FrozenSet[str] = (
        SINGLE_MEDIA_EXTS if single_media_exts is None
        else frozenset(ext.lower() for ext in single_media_exts))

    # Validate the style early so a bad value fails here instead of mid-collapse.
    frame_pattern_for(frame_pattern, 1)

    collapse: Dict[Entry, List[int]] = {}
    for entry in list_entries(directory, files_only=True):
        if entry.ext.lower() in media_exts:
            # Single-frame media: the entry is the result, no frame collapsing.
            collapse.setdefault(entry, [])
            continue

        pattern_entry = entry.to_pattern(frame_pattern, media_exts)
        frames = collapse.setdefault(pattern_entry, [])
        if pattern_entry != entry:
            frame = entry.frame
            if frame >= 0:
                bisect.insort(frames, frame)

    sequences: List[SequentialFiles] = []
    for entry, frames in collapse.items():
        unique = sorted(set(frames))
        missing: List[int] = []
        if unique:
            missing = sorted(set(range(unique[0], unique[-1] + 1)) - set(unique))
        sequences.append(SequentialFiles(entry, unique, missing))

    sequences.sort(key=lambda item: item.name)
    return sequences
