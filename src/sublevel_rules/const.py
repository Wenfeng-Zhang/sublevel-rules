# -*- coding: utf-8 -*-
"""Constant definitions.

Only what the sub level rule engine itself needs lives here: the single-frame
media suffixes, the Qt check states, the frame placeholder styles and the
accepted ``mode`` values.
"""

#: Single-frame media suffixes (lower case, leading dot). Files with these
#: suffixes are never collapsed into a frame sequence -- each one stays a
#: standalone entry.
SINGLE_MEDIA_EXTS = frozenset((
    '.mov',
    '.mp4',
    '.avi',
    '.r3d',
    '.nk',
    '.ren',
))

#: Qt check-state semantics: 0 = unchecked, 1 = partially checked, 2 = checked.
CHECKED_UNCHECKED = 0
CHECKED_PARTIAL = 1
CHECKED_CHECKED = 2

#: Supported frame placeholder styles:
#:
#: * ``'%'`` -> ``name.%04d.exr``
#: * ``'#'`` -> ``name.####.exr``
#: * ``'$'`` -> ``name.$F4.exr``
FRAME_PATTERN_STYLES = ('%', '#', '$')

#: Default frame placeholder style.
DEFAULT_FRAME_PATTERN = '%'

#: Accepted values for ``Level.mode`` / ``Action.mode``:
#:
#: * ``'first'`` -- take the first hit in pattern order;
#: * ``'multiple'`` -- collect every hit;
#: * ``'latest'`` -- take the largest hit by *natural numeric order*
#:   (``v10`` sorts after ``v9``, whereas in plain lexicographic order
#:   ``v10`` sorts before ``v9``).
MODE_FIRST = 'first'
MODE_MULTIPLE = 'multiple'
MODE_LATEST = 'latest'
MODES = (MODE_FIRST, MODE_MULTIPLE, MODE_LATEST)

#: Accepted values for ``Group.mode``:
#:
#: * ``'all'`` (default) -- run every child rule and merge the results;
#: * ``'first'`` -- fallback chain: run the children in order and stop at the
#:   first one that produces a non-empty result (used to express "the same
#:   asset has two valid directory layouts depending on the project").
GROUP_MODE_ALL = 'all'
GROUP_MODE_FIRST = 'first'
GROUP_MODES = (GROUP_MODE_ALL, GROUP_MODE_FIRST)
