# -*- coding: utf-8 -*-
"""Frame helpers: detect placeholders inside a pattern and convert between a
pattern and a concrete frame path."""

import re

from pathlib import Path
from typing import Callable, List, Match, Optional, Pattern, Tuple, TYPE_CHECKING, Union

if TYPE_CHECKING:                                            # pragma: no cover
    from .sequences import SequentialFiles

__all__ = ['frame_path', 'frame_tokens']

#: A placeholder regex plus the callable that renders a frame number with it.
_TokenRule = Tuple[Pattern[str], Callable[[Match[str], int], str]]

#: Supported placeholder spellings (``re.Pattern`` + replacement callable):
#:
#: * ``name.%04d.exr``
#: * ``name.%4d.exr``
#: * ``name.%d.exr``
#: * ``name.####.exr`` (at least two ``#``, so a single ``#`` in a file name such
#:   as ``abc#1.exr`` is not mistaken for a placeholder)
#: * ``name.$F4.exr``
#:
#: Order matters: ``%04d`` has to come before ``%4d`` / ``%d``.
_FRAME_TOKEN_PATTERNS: Tuple[_TokenRule, ...] = (
    (re.compile(r'%0(\d+)d'),
     lambda match, frame: str(frame).zfill(int(match.group(1)))),
    (re.compile(r'%(\d+)d'),
     lambda match, frame: str(frame).zfill(int(match.group(1)))),
    (re.compile(r'%d'),
     lambda match, frame: str(frame)),
    (re.compile(r'##+'),
     lambda match, frame: str(frame).zfill(len(match.group(0)))),
    (re.compile(r'\$F(\d+)'),
     lambda match, frame: str(frame).zfill(int(match.group(1)))),
)


def _find_tokens(name: str) -> List[Tuple[int, int, str]]:
    """Return ``[(start, end, token), ...]`` in order of appearance; overlapping
    matches keep only the first one found.

    The overlap check is required: ``abc.%04d.exr`` matches both ``%0(\\d+)d``
    and ``%(\\d+)d``, and without deduplication the result would contain
    ``%04d`` twice.
    """
    found: List[Tuple[int, int, str]] = []
    for pattern, _ in _FRAME_TOKEN_PATTERNS:
        for match in pattern.finditer(name):
            start, end = match.span()
            if any(start < other_end and end > other_start
                   for other_start, other_end, _ in found):
                continue
            found.append((start, end, match.group(0)))
    found.sort()
    return found


def frame_tokens(name: str) -> List[str]:
    """Return the placeholders found in a file name (in order, overlaps counted once).

    >>> frame_tokens('abc.%04d.exr')
    ['%04d']
    >>> frame_tokens('abc.####.exr')
    ['####']
    >>> frame_tokens('abc.0001.exr')
    []
    >>> frame_tokens('abc.100%0.exr')
    []
    """
    return [token for _, _, token in _find_tokens(name)]


def frame_path(sequence: Union['SequentialFiles', str], frame: int) -> Path:
    """Expand a sequence pattern path into the path of one concrete frame.

    :param sequence: a :class:`~sublevel_rules.sequences.SequentialFiles`, or a
        pattern path / name (``str``).
    :param frame: frame number.
    :returns: :class:`pathlib.Path`

    >>> frame_path('abc.%04d.exr', 7).name
    'abc.0007.exr'
    >>> frame_path('abc.%4d.exr', 7).name
    'abc.0007.exr'
    >>> frame_path('abc.####.exr', 12).name
    'abc.0012.exr'
    >>> frame_path('abc.$F4.exr', 12).name
    'abc.0012.exr'
    """
    if isinstance(sequence, str):
        parent: Optional[Path] = None
        name: str = sequence
    else:
        parent = sequence.path.parent
        name = sequence.name

    tokens = _find_tokens(name)
    resolved = name
    if tokens:
        start, end, token = tokens[0]
        for pattern, replace in _FRAME_TOKEN_PATTERNS:
            match = pattern.match(name, start)
            if match is not None and match.group(0) == token:
                resolved = name[:start] + replace(match, frame) + name[end:]
                break

    return parent / resolved if parent is not None else Path(resolved)
