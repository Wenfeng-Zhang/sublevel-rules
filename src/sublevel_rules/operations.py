# -*- coding: utf-8 -*-
"""Assemble resolution results into the hierarchical data a UI can consume.

Two details are worth spelling out because they are easy to get wrong:

* **Parent check states** are derived through
  :func:`~sublevel_rules.rules.to_check_state`, so ``checked=True`` (a boolean)
  and ``checked=2`` (a Qt state) behave identically. Comparing raw values with
  ``== 2`` would silently treat ``True`` as "partially checked".
* **Relative paths** come from ``Path.relative_to``, which keeps every path
  segment intact and yields a POSIX style path on every platform.

Other knobs: grouping is selectable (``group_mode``: ``'flat'`` / ``'nested'`` /
``None``), sizes can be sampled from the first frame or summed over the whole
sequence (``size_mode``) and entries without an operation function can be skipped
(``skip_without_op``).
"""

import posixpath

from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .const import CHECKED_CHECKED, CHECKED_PARTIAL, CHECKED_UNCHECKED
from .errors import ParameterError, PathError
from .frames import frame_path
from .paths import PathValue, as_path
from .resolver import Match, Resolver
from .rules import to_check_state

__all__ = ['build_operations', 'get_sub_level_op', 'human_size', 'parent_check_state']

_UNITS: Tuple[str, ...] = ('B', 'KB', 'MB', 'GB', 'TB', 'PB')


def human_size(value: Any, target_unit: Optional[str] = 'MB') -> str:
    """Convert a byte count into a human readable string.

    The format is the one the pipeline UI displays (**the default unit is MB**)::

        >>> human_size(1024)
        '0.00MB'
        >>> human_size(2048, 'B')
        '2048.00B'
        >>> human_size(1024, 'KB')
        '1.00KB'
        >>> human_size(1536, None)
        '1.50KB'

    :param target_unit: target unit; ``None`` picks the most suitable unit
        automatically; an invalid unit returns an empty string.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ''
    if target_unit is not None:
        unit = target_unit.upper()
        if unit not in _UNITS:
            return ''
        for _ in range(_UNITS.index(unit)):
            number /= 1024.0
        return '{:.2f}{}'.format(number, unit)

    index = 0
    while number >= 1024.0 and index < len(_UNITS) - 1:
        number /= 1024.0
        index += 1
    return '{:.2f}{}'.format(number, _UNITS[index])


def parent_check_state(states: Iterable[int]) -> int:
    """Derive the state of a parent node from its children (all checked -> 2,
    none checked -> 0, anything else -> 1)."""
    values = list(states)
    if not values:
        return CHECKED_UNCHECKED
    if all(state == CHECKED_CHECKED for state in values):
        return CHECKED_CHECKED
    if all(state == CHECKED_UNCHECKED for state in values):
        return CHECKED_UNCHECKED
    return CHECKED_PARTIAL


def _relative_posix(path: Path, root: Path) -> Optional[str]:
    """Return the POSIX style path relative to ``root``; ``None`` if outside."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    return str(relative).replace('\\', '/')


def _entry_size(match: Match, size_mode: str) -> int:
    """Compute the byte size of an entry.

    :param size_mode: ``'first'`` (first frame / the file itself), ``'total'``
        (sum of every frame), ``'none'`` (do not measure).
    """
    if size_mode == 'none':
        return 0
    if size_mode == 'first':
        if match.sequence.frames:
            first = frame_path(match.sequence, match.sequence.frames[0])
            try:
                return first.stat().st_size
            except OSError:
                return 0
        return match.entry.size()
    if size_mode == 'total':
        total = 0
        if match.sequence.frames:
            for frame in match.sequence.frames:
                try:
                    total += frame_path(match.sequence, frame).stat().st_size
                except OSError:
                    continue
            return total
        return match.entry.size()
    raise ParameterError('未知的 size_mode: {!r}'.format(size_mode))


def build_operations(matches: Iterable[Match], version_root: PathValue,
                     version_data: Optional[Dict[str, Any]] = None,
                     op_resolver: Optional[Callable[[str], Any]] = None,
                     size_formatter: Callable[[int], str] = human_size,
                     size_mode: str = 'first', group_mode: Optional[str] = 'flat',
                     skip_without_op: bool = False,
                     extra_fields: Any = None) -> List[Dict[str, Any]]:
    """Assemble a list of :class:`~sublevel_rules.resolver.Match` into hierarchical data.

    :param matches: list of :class:`~sublevel_rules.resolver.Match`.
    :param version_root: version folder (used to compute relative paths).
    :param version_data: data passed through to the downstream operation
        function (stored in ``args`` / ``orm``).
    :param op_resolver: callable taking ``method`` and returning the matching
        operation function; a pipeline module typically supplies
        ``create_api_version``.
    :param size_formatter: byte-count formatter, :func:`human_size` by default.
    :param size_mode: ``'first'`` / ``'total'`` / ``'none'``, see :func:`_entry_size`.
    :param group_mode: ``'flat'`` (default; the full directory name becomes a
        single parent node), ``'nested'`` (a multi-level
        tree following the directory hierarchy), ``None`` (no grouping).
    :param skip_without_op: whether to skip entries for which ``op_resolver``
        finds no operation function.
    :param extra_fields: extra fields added to every file entry (a dict or a callable).
    :returns: ``list`` of ``dict``. File entry and parent node fields are
        described in the module docstring.

    File entry fields (the first 10 form the stable compatibility set):
    ``filename_checked`` / ``op_func`` / ``args`` / ``file_stem`` / ``path_name`` /
    ``filename`` / ``orm`` / ``size`` / ``type`` / ``options``, plus the added
    ``sequence`` / ``method`` / ``frames`` / ``missing`` / ``is_sequence`` /
    ``relative_path``.

    Parent node fields: ``filename`` / ``filename_checked`` / ``children``.
    """
    root = as_path(version_root)
    data: Dict[str, Any] = version_data if version_data is not None else {}
    file_entries: List[Dict[str, Any]] = []

    for match in matches:
        operation_func = None
        if op_resolver is not None:
            operation_func = op_resolver(match.method)
            if not operation_func and skip_without_op:
                continue

        relative = _relative_posix(match.path, root)
        if relative is None:
            relative = match.name
        directory, base_filename = posixpath.split(relative)
        parts = tuple(part for part in directory.split('/') if part)

        entry = match.entry
        asset: Dict[str, Any] = OrderedDict((
            ('filename_checked', to_check_state(match.checked)),
            ('op_func', operation_func),
            ('args', (match.sequence, data)),
            ('file_stem', entry.path.parent / entry.path.stem),
            ('path_name', str(entry)),
            ('filename', base_filename),
            ('orm', data),
            ('size', size_formatter(_entry_size(match, size_mode))),
            ('type', entry.ext),
            ('options', None),
            # ---- added fields (existing callers may ignore them) ----
            ('sequence', match.sequence),
            ('method', match.method),
            ('frames', list(match.frames)),
            ('missing', list(match.missing)),
            ('is_sequence', match.is_sequence),
            ('relative_path', relative),
        ))
        if extra_fields is not None:
            asset.update(extra_fields(match, asset) if callable(extra_fields)
                         else dict(extra_fields))

        asset['_dir_parts'] = parts
        file_entries.append(asset)

    if group_mode == 'flat':
        return _group_flat(file_entries)
    if group_mode == 'nested':
        return _group_nested(file_entries)
    if group_mode is None:
        return [_strip_internal(asset) for asset in file_entries]
    raise ParameterError(
        "group_mode 只能是 'flat' / 'nested' / None，收到 {!r}".format(group_mode))


def _strip_internal(asset: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = OrderedDict(asset)
    cleaned.pop('_dir_parts', None)
    return cleaned


def _group_flat(file_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group by full directory name, one single-level parent node each."""
    direct: List[Dict[str, Any]] = []
    groups: Dict[str, List[Dict[str, Any]]] = OrderedDict()
    for asset in file_entries:
        parts = asset['_dir_parts']
        if parts:
            groups.setdefault('/'.join(parts), []).append(asset)
        else:
            direct.append(asset)

    result = [_strip_internal(asset) for asset in direct]
    for directory, children in groups.items():
        cleaned = [_strip_internal(child) for child in children]
        result.append(OrderedDict((
            ('filename', directory),
            ('filename_checked', parent_check_state(
                child['filename_checked'] for child in cleaned)),
            ('children', cleaned),
        )))
    return result


def _group_nested(file_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build a multi-level tree from the directory hierarchy."""
    nodes: Dict[Tuple[str, ...], Dict[str, Any]] = OrderedDict()
    root_files: List[Dict[str, Any]] = []

    def ensure_node(parts: Tuple[str, ...]) -> Optional[Dict[str, Any]]:
        if not parts:
            return None
        node = nodes.get(parts)
        if node is not None:
            return node
        node = OrderedDict((('filename', '/'.join(parts)), ('children', [])))
        nodes[parts] = node
        parent = ensure_node(parts[:-1])
        (parent['children'] if parent is not None else root_files).append(node)
        return node

    for asset in file_entries:
        parts = asset['_dir_parts']
        if parts:
            node = ensure_node(parts)
            if node is not None:
                node['children'].append(_strip_internal(asset))
        else:
            root_files.append(_strip_internal(asset))

    def compute(node: Dict[str, Any]) -> int:
        states: List[int] = []
        for child in node['children']:
            if 'children' in child:
                states.append(compute(child))
            else:
                states.append(child['filename_checked'])
        state = parent_check_state(states)
        node['filename_checked'] = state
        return state

    for child in root_files:
        if 'children' in child:
            compute(child)

    return root_files


def get_sub_level_op(pipeline_module: Any, version_data: Optional[Dict[str, Any]],
                     resolver: Optional[Resolver] = None,
                     op_resolver: Optional[Callable[[str], Any]] = None,
                     **options: Any) -> List[Dict[str, Any]]:
    """Entry point for a pipeline module:
    ``get_sub_level_op(pipeline_module, version_data)``.

    ``pipeline_module`` has to provide:

    * ``get_import_rules()`` -> a rule tree;
    * ``create_api_version(method)`` -> the operation function for that method.

    When either one is missing, an empty list is returned.
    ``version_data`` must contain ``path`` (the version folder).
    """
    rules_getter = getattr(pipeline_module, 'get_import_rules', None)
    create_api_version = getattr(pipeline_module, 'create_api_version', None)
    if not callable(rules_getter) or not callable(create_api_version):
        return []

    root = (version_data or {}).get('path')
    if not root:
        raise PathError('version_data 缺少 path（版本目录）')

    active_resolver = resolver if resolver is not None else Resolver()
    matches = active_resolver.resolve(rules_getter(), root, version_data)
    return build_operations(
        matches, version_root=root, version_data=version_data,
        op_resolver=op_resolver if op_resolver is not None else create_api_version,
        skip_without_op=True, **options)
