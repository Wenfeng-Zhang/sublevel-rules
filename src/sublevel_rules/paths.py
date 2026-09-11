# -*- coding: utf-8 -*-
"""Zero-dependency path adapter layer.

Everything works on the standard :mod:`pathlib` and on anything :func:`os.fspath`
can digest (``str`` / ``pathlib.Path`` / ``bytes`` / any object implementing
``__fspath__``), so callers can pass whichever path type they already use.

:class:`Entry` adds the small view the rule engine needs on top of a path:
``name`` / ``stem`` / ``ext`` / ``parent`` / ``frame`` / ``size()`` /
``to_pattern()``.
"""

import os
import re

from pathlib import Path
from typing import Any, FrozenSet, Iterable, List, Optional, Tuple

from .const import DEFAULT_FRAME_PATTERN, FRAME_PATTERN_STYLES, SINGLE_MEDIA_EXTS
from .errors import PathError, SubLevelRulesError
from .frames import frame_tokens

__all__ = [
    'PathValue',
    'Entry',
    'as_path',
    'frame_pattern_for',
    'list_entries',
    'split_frame',
]

#: Anything a path argument may be: a ``str``, ``bytes``, a :class:`pathlib.Path`
#: or any other object implementing ``__fspath__`` / rendering correctly through
#: ``str()``. Kept as :data:`~typing.Any` on purpose -- being permissive at runtime
#: is the whole point of this layer.
PathValue = Any


def as_path(value: PathValue) -> Path:
    """Convert any path-like object into a :class:`pathlib.Path`.

    :param value: a :class:`pathlib.Path`, a ``str`` (or ``bytes``), or any other
        object implementing ``__fspath__`` / rendering correctly through ``str()``.
    :returns: :class:`pathlib.Path`
    :raises PathError: ``value`` is ``None`` or an empty string.
    """
    if isinstance(value, Path):
        return value
    if value is None:
        raise PathError('path 不能为 None')
    # ``text`` stays Any on purpose: os.fspath may return str *or* bytes.
    text: Any
    try:
        text = os.fspath(value)
    except TypeError:
        text = str(value)
    if isinstance(text, bytes):
        text = text.decode('utf-8')
    if not text.strip():
        raise PathError('path 不能为空字符串')
    return Path(text)


def split_frame(stem: str) -> Optional[Tuple[str, str, str]]:
    """Split the **last run of consecutive digits** out of ``stem``.

    :param stem: file name without extension, e.g. ``'abc_v001_0001'``.
    :returns: ``(prefix, digits, suffix)``; ``None`` when there is no digit.

    >>> split_frame('abc_v001_0001')
    ('abc_v001_', '0001', '')
    >>> split_frame('readme') is None
    True
    """
    matches = list(re.finditer(r'\d+', stem))
    if not matches:
        return None
    match = matches[-1]
    return stem[:match.start()], match.group(0), stem[match.end():]


def frame_pattern_for(frame_pattern: str, width: int) -> str:
    """Build a placeholder from a style and a frame-number width.

    :param frame_pattern: ``'%'`` / ``'#'`` / ``'$'``.
    :param width: width of the original frame number, e.g. ``'0001'`` is 4.
    :raises SubLevelRulesError: unsupported style.
    """
    if frame_pattern not in FRAME_PATTERN_STYLES:
        raise SubLevelRulesError(
            '不支持的 frame_pattern: {!r}，可选: {}'.format(
                frame_pattern, ', '.join(FRAME_PATTERN_STYLES))
        )
    if frame_pattern == '%':
        return '%0{}d'.format(width)
    if frame_pattern == '#':
        return '#' * width
    return '$F{}'.format(width)


class Entry(object):
    """A lightweight view of one entry (file or subdirectory) in a directory.

    The interface is deliberately small and stays out of the way of the path
    object underneath: ``name`` / ``stem`` / ``ext`` / ``parent`` / ``isdir()`` /
    ``isfile()`` / ``exists()`` / ``size()`` / ``frame`` / ``to_pattern()``.
    """

    __slots__ = ('path', '_dir_entry')

    def __init__(self, path: PathValue, dir_entry: Optional[os.DirEntry] = None) -> None:
        self.path = as_path(path)
        #: Optional :class:`os.DirEntry` (coming from :func:`os.scandir`).
        #: Carrying it lets ``is_file()`` / ``is_dir()`` reuse what the system
        #: already knows from listing the directory, instead of issuing one
        #: ``stat`` per entry.
        self._dir_entry = dir_entry

    # ------------------------------------------------------------------ attrs
    @property
    def name(self) -> str:
        """Entry name including the extension, e.g. ``'abc_0001.abc'``."""
        return self.path.name

    @property
    def stem(self) -> str:
        """File name without extension, e.g. ``'abc_0001'``."""
        return self.path.stem

    @property
    def ext(self) -> str:
        """Extension including the leading dot, original case preserved (``'.ABC'``).

        Always a ``str``, never a path object, so ``.lower()`` works on it
        directly.
        """
        return self.path.suffix

    @property
    def parent(self) -> Path:
        """Parent directory, as a :class:`pathlib.Path`."""
        return self.path.parent

    @property
    def frame(self) -> int:
        """Parsed frame number; ``-1`` when it cannot be parsed or for single-frame media."""
        if self.ext.lower() in SINGLE_MEDIA_EXTS:
            return -1
        split = split_frame(self.stem)
        return int(split[1]) if split else -1

    # ----------------------------------------------------------------- methods
    def is_file(self) -> bool:
        """Whether this is a file (same name and meaning as :class:`pathlib.Path`)."""
        if self._dir_entry is not None:
            return self._dir_entry.is_file()
        return self.path.is_file()

    def is_dir(self) -> bool:
        """Whether this is a directory (same name and meaning as :class:`pathlib.Path`)."""
        if self._dir_entry is not None:
            return self._dir_entry.is_dir()
        return self.path.is_dir()

    def isfile(self) -> bool:
        """Alias for :meth:`is_file`, for callers used to that spelling."""
        return self.is_file()

    def isdir(self) -> bool:
        """Alias for :meth:`is_dir`, for callers used to that spelling."""
        return self.is_dir()

    def exists(self) -> bool:
        return self.path.exists()

    def size(self, default: int = 0) -> int:
        """File size in bytes.

        A path that does not exist (for instance the pattern path of a collapsed
        sequence such as ``name.%04d.exr``) returns ``default`` instead of raising.

        Note: the size is **always read fresh**; the cached value of
        ``os.DirEntry`` is deliberately not reused, because ``DirEntry.stat()``
        on Windows returns the snapshot taken while listing the directory, so a
        long-running process reading the size of an already obtained
        :class:`Entry` again would see a stale number.
        """
        try:
            return self.path.stat().st_size
        except OSError:
            return default

    def to_pattern(self, frame_pattern: str = DEFAULT_FRAME_PATTERN,
                   single_media_exts: Optional[Iterable[str]] = None) -> 'Entry':
        """Collapse this entry into a frame-sequence pattern entry.

        :param single_media_exts: media suffixes that must be treated as single
            files (lower case, leading dot). ``None`` uses
            :data:`~sublevel_rules.const.SINGLE_MEDIA_EXTS`; pass an empty
            collection to **drop** that restriction (so that e.g. ``.mov``
            takes part in collapsing).
        :returns: a new :class:`Entry`; ``self`` when it cannot be collapsed or
            already is a pattern.

        >>> Entry('/show/abc_0001.abc').to_pattern('%').name
        'abc_%04d.abc'
        >>> Entry('/show/readme.txt').to_pattern('%').name
        'readme.txt'
        >>> Entry('/show/abc.%04d.abc').to_pattern('%').name
        'abc.%04d.abc'
        """
        media_exts: FrozenSet[str] = (
            SINGLE_MEDIA_EXTS if single_media_exts is None
            else frozenset(ext.lower() for ext in single_media_exts))
        if self.ext.lower() in media_exts:
            return self
        # A name that already is a pattern must not be collapsed again, or the
        # ``04`` inside ``%04d`` would be taken for a frame number.
        if frame_tokens(self.stem):
            return self
        split = split_frame(self.stem)
        if split is None:
            return self
        prefix, digits, suffix = split
        placeholder = frame_pattern_for(frame_pattern, len(digits))
        return Entry(self.path.parent / (prefix + placeholder + suffix + self.ext))

    # -------------------------------------------------------- container protocol
    def __fspath__(self) -> str:
        return os.fspath(self.path)

    def __str__(self) -> str:
        return str(self.path)

    def __repr__(self) -> str:
        return 'Entry({!r})'.format(str(self.path))

    def __eq__(self, other: object) -> Any:
        if isinstance(other, Entry):
            return self.path == other.path
        if isinstance(other, (str, os.PathLike)):
            try:
                return self.path == as_path(other)
            except SubLevelRulesError:
                return NotImplemented
        return NotImplemented

    def __ne__(self, other: object) -> Any:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self) -> int:
        return hash(self.path)

    def __lt__(self, other: object) -> bool:
        return str(self) < str(other)


def list_entries(directory: PathValue, files_only: bool = False) -> List[Entry]:
    """List the entries of a directory (non-recursive), sorted by name.

    Uses :func:`os.scandir` instead of ``Path.iterdir()``: the returned
    :class:`Entry` objects carry their :class:`os.DirEntry`, so ``is_file()`` /
    ``is_dir()`` can reuse what the system already knows from listing the
    directory. On POSIX, ``d_type`` answers "is this a file" without one extra
    ``stat`` per entry -- a difference that is very visible on network storage
    (NFS / SMB).
    """
    path = as_path(directory)
    if not path.is_dir():
        return []
    entries: List[Entry] = []
    with os.scandir(str(path)) as iterator:
        for dir_entry in iterator:
            entries.append(Entry(dir_entry.path, dir_entry=dir_entry))
    if files_only:
        entries = [entry for entry in entries if entry.is_file()]
    entries.sort(key=lambda entry: entry.name)
    return entries
