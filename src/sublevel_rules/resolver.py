# -*- coding: utf-8 -*-
"""Rule resolution engine.

Takes a rule tree plus a version folder and returns every resource that matched
(:class:`Match`).

Design notes -- the behaviours worth knowing before changing anything here:

* **mutex is applied once, on the final result set.** Applying it recursively
  would be idempotent, but it makes the outcome much harder to reason about.
* **mutex may come from ``options``**, so a group can be declared once on a
  ``Group`` / ``Rule`` / ``Level`` instead of on every ``Action``.
* **User-defined Action objects are never mutated**: the check state lives on
  :class:`Match`, so a rule tree can be resolved repeatedly and shared.
* **The opts / options inheritance chain is explicit**: Group -> Rule -> Level ->
  Action, each level overriding the previous one.
* **Directory listing and sequence scanning are cached**, so one directory is
  listed only once per resolution.
* **A formatting failure raises a clear exception** (``RuleFormatError``) instead
  of a bare ``KeyError``.
* **Results are deduplicated**: when several rules hit the same file only the
  first match is kept (turn it off with ``dedupe=False``).
* **Debug output goes through :mod:`logging`**, never ``print``.

On top of that, several "path selection" semantics were added (all new, none of
them changes the previous defaults):

* ``Group(..., mode='first')`` -- fallback chain: the first branch producing a
  non-empty result wins;
* ``Level(..., mode='latest')`` -- take the newest entry by natural numeric
  order (``v10`` > ``v9``);
* ``Level(..., optional=True)`` -- optional level: when it does not exist, skip
  it and keep matching below;
* ``Level(..., require_content=True)`` -- skip candidate directories in which the
  next level would match nothing.
"""

import fnmatch
import logging
import re

from functools import partial
from pathlib import Path
from typing import (Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional,
                    Sequence, Set, Tuple)

from .const import (
    CHECKED_CHECKED,
    CHECKED_UNCHECKED,
    DEFAULT_FRAME_PATTERN,
    GROUP_MODE_ALL,
    GROUP_MODE_FIRST,
    MODE_FIRST,
    MODE_LATEST,
)
from .errors import RuleDefinitionError, RuleFormatError, RuleStructureError
from .paths import Entry, PathValue, as_path, list_entries
from .rules import (
    Action,
    COLLECT_SCOPE_CHILDREN,
    COLLECT_SCOPE_PARENT,
    Group,
    Level,
    Rule,
    to_check_state,
)
from .sequences import SequentialFiles, scan_sequences

__all__ = ['Match', 'Resolver', 'format_pattern', 'resolve', 'resolve_smart_rule']

_LOGGER = logging.getLogger('sublevel_rules')


class _SafeDict(Dict[str, Any]):
    """In lenient mode a missing placeholder is kept verbatim."""

    def __missing__(self, key: str) -> str:
        return '{' + key + '}'


def format_pattern(pattern: str, version_data: Optional[Mapping[str, Any]] = None,
                   strict: bool = True) -> str:
    """Fill the ``{placeholders}`` of a pattern from ``version_data``.

    :param pattern: pattern string, e.g. ``'*_v{version_part}.ma'``.
    :param version_data: source of the placeholder values.
    :param strict: with ``True`` a missing placeholder raises
        :class:`RuleFormatError`; with ``False`` the ``{placeholder}`` text is
        kept as is.
    :raises RuleFormatError: missing placeholder (strict mode) or broken braces.

    >>> format_pattern('*_v{version_part}.ma', {'version_part': '001'})
    '*_v001.ma'
    """
    if not version_data:
        if '{' in pattern:
            _LOGGER.warning(
                '模式 %r 里含占位符，但 version_data 为空，将按原样匹配（通常匹配不到）',
                pattern)
        return pattern
    mapping: Mapping[str, Any] = (dict(version_data) if strict
                                  else _SafeDict(version_data))
    try:
        return pattern.format_map(mapping)
    except KeyError as exc:
        raise RuleFormatError(
            '模式 {!r} 里的占位符 {} 不存在于 version_data 中'.format(pattern, exc))
    except (IndexError, ValueError) as exc:
        raise RuleFormatError('模式 {!r} 格式化失败: {}'.format(pattern, exc))


def _merge_options(parent_options: Optional[Mapping[str, Any]],
                   extra_options: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Options of a child node override those of its parent."""
    if not extra_options:
        return dict(parent_options) if parent_options else {}
    merged: Dict[str, Any] = dict(parent_options) if parent_options else {}
    merged.update(extra_options)
    return merged


def _natural_key(name: Any) -> List[Tuple[int, Any]]:
    """Natural sort key: digit runs compare numerically, everything else as lower-case text.

    This makes ``v10`` sort after ``v9`` (in plain lexicographic order
    ``'v10' < 'v9'``), which is what ``mode='latest'`` needs to mean "newest
    version".

    >>> sorted(['v9', 'v10', 'v100'], key=_natural_key)
    ['v9', 'v10', 'v100']
    """
    parts = re.split(r'(\d+)', str(name).lower())
    return [(1, int(part)) if part.isdigit() else (0, part) for part in parts]


class Match(object):
    """One match.

    ``Match`` also unpacks like a ``(sequence, method, action)`` three-tuple::

        for sequence, method, action in matches:
            ...
    """

    __slots__ = ('sequence', 'method', 'action', 'checked', 'options', 'depth')

    def __init__(self, sequence: SequentialFiles, method: str,
                 action: Optional[Action], checked: Any = None,
                 options: Optional[Mapping[str, Any]] = None,
                 depth: int = 0) -> None:
        self.sequence: SequentialFiles = sequence
        self.method: str = method
        self.action: Optional[Action] = action
        self.checked: Any = checked
        self.options: Mapping[str, Any] = options or {}
        self.depth: int = depth

    # ------------------------------------------------------------- convenience
    @property
    def entry(self) -> Entry:
        """:class:`~sublevel_rules.paths.Entry` (the pattern entry for a sequence)."""
        return self.sequence.filename

    @property
    def path(self) -> Path:
        """:class:`pathlib.Path`."""
        return self.sequence.path

    @property
    def filename(self) -> Entry:
        return self.sequence.filename

    @property
    def name(self) -> str:
        return self.sequence.name

    @property
    def frames(self) -> List[int]:
        return self.sequence.frames

    @property
    def missing(self) -> List[int]:
        return self.sequence.missing

    @property
    def is_sequence(self) -> bool:
        return self.sequence.is_sequence

    @property
    def state(self) -> int:
        """Normalized check state (``0`` / ``1`` / ``2``)."""
        return to_check_state(self.checked)

    @property
    def mutex(self) -> Optional[str]:
        """Mutex group ID: ``Action.mutex`` first, then the inherited options."""
        if self.action is not None and self.action.mutex:
            return self.action.mutex
        return self.options.get('mutex')

    @property
    def frame_pattern(self) -> str:
        return self.options.get('frame_pattern', DEFAULT_FRAME_PATTERN)

    # ---------------------------------------------------------------- protocol
    def to_dict(self) -> Dict[str, Any]:
        """Convert into a plain dict for logging / serialization (no runtime
        objects such as ``Action``)."""
        return {
            'name': self.name,
            'path': str(self.path),
            'method': self.method,
            'checked': self.state,
            'is_sequence': self.is_sequence,
            'frames': list(self.frames),
            'missing': list(self.missing),
            'mutex': self.mutex,
            'options': dict(self.options),
        }

    def as_tuple(self) -> Tuple[SequentialFiles, str, Optional[Action]]:
        """Return the ``(sequence, method, action)`` three-tuple."""
        return self.sequence, self.method, self.action

    def __iter__(self) -> Iterator[Any]:
        return iter(self.as_tuple())

    def __repr__(self) -> str:
        return 'Match(name={!r}, method={!r}, checked={!r})'.format(
            self.name, self.method, self.checked)


class Resolver(object):
    """Rule resolver.

    :param frame_pattern: frame placeholder style (``'%'`` / ``'#'`` / ``'$'``),
        overridable per ``Action(options={'frame_pattern': ...})``.
    :param case_sensitive: whether file name matching is case sensitive.
        Defaults to ``False`` so behaviour does not depend on the platform.
    :param dedupe: whether to deduplicate the final results by ``(path, method)``.
    :param auto_select_first: whether to check the first entry of a mutex group
        automatically when nothing in it is checked.
    :param strict_format: strict pattern formatting, see :func:`format_pattern`.
    :param single_media_exts: single-frame media suffixes; ``None`` uses the default.
    :param exclude_patterns: entry names to skip (fnmatch style, following the
        same case rules), e.g. ``('.git', '__pycache__', '*.tmp')``. Nothing is
        skipped by default.
    :param logger: custom logger.
    :param keep_cache: whether the directory / sequence caches survive between
        ``resolve()`` calls. ``False`` (the default) releases them after every
        resolution; ``True`` keeps them, which makes repeated resolutions of a
        tree that barely changes (a UI refreshing the same version folder) much
        cheaper. Call :meth:`clear_cache` when the directories may have changed.

    Note: a ``Resolver`` instance carries a resolution cache (one directory is
    listed once per resolution), so **do not share one instance between
    threads**; create one per thread instead. That applies to ``keep_cache=True``
    as well.
    """

    def __init__(self, frame_pattern: str = DEFAULT_FRAME_PATTERN,
                 case_sensitive: bool = False, dedupe: bool = True,
                 auto_select_first: bool = True, strict_format: bool = True,
                 single_media_exts: Optional[Iterable[str]] = None,
                 exclude_patterns: Optional[Iterable[str]] = None,
                 logger: Optional[logging.Logger] = None,
                 keep_cache: bool = False) -> None:
        self.frame_pattern: str = frame_pattern
        self.case_sensitive: bool = case_sensitive
        self.dedupe: bool = dedupe
        self.auto_select_first: bool = auto_select_first
        self.strict_format: bool = strict_format
        self.single_media_exts: Optional[Iterable[str]] = single_media_exts
        self.exclude_patterns: Tuple[str, ...] = tuple(exclude_patterns or ())
        self.logger: logging.Logger = logger or _LOGGER
        self.keep_cache: bool = keep_cache
        self._listing_cache: Dict[str, List[Entry]] = {}
        self._sequence_cache: Dict[Tuple[str, str], List[SequentialFiles]] = {}

    # ------------------------------------------------------------------- entry
    def resolve(self, rule: Any, root_path: PathValue,
                version_data: Optional[Mapping[str, Any]] = None,
                inherited_options: Optional[Mapping[str, Any]] = None) -> List['Match']:
        """Resolve ``rule``.

        :param rule: :class:`~sublevel_rules.rules.Group` / ``Rule`` / ``Action``.
        :param root_path: version folder (the starting point of the rule).
        :param version_data: placeholder data, e.g.
            ``{'version_part': '001', 'path': ...}``.
        :param inherited_options: parameters inherited from above.
        :returns: ``list`` of :class:`Match`; an empty list when the directory
            does not exist.
        """
        root = as_path(root_path)
        data: Dict[str, Any] = dict(version_data or {})

        # Caches are per resolution unless the caller asked to keep them (see
        # ``keep_cache``); either way they are dropped when resolution ends.
        if not self.keep_cache:
            self.clear_cache()

        try:
            if not root.is_dir():
                self.logger.debug('root 路径不存在或不是目录: %s', root)
                return []

            matches: List[Match] = []
            self._visit(rule, root, inherited_options or {}, data, matches, 0)
            if self.dedupe:
                matches = self._dedupe(matches)
            self._apply_mutex(matches)
            return matches
        finally:
            if not self.keep_cache:
                self.clear_cache()

    def clear_cache(self) -> None:
        """Drop the cached directory listings and sequence scans.

        Only needed with ``keep_cache=True``: call it when the directories may have
        changed (files added, removed or renamed) so the next resolution lists them
        again.
        """
        self._listing_cache.clear()
        self._sequence_cache.clear()

    def cache_info(self) -> Tuple[int, int]:
        """Return how many directory listings and sequence scans are cached.

        :returns: ``(listing entries, sequence entries)``.
        """
        return len(self._listing_cache), len(self._sequence_cache)

    # -------------------------------------------------------------------- walk
    def _visit(self, node: Any, root: Any,
               inherited_options: Mapping[str, Any], version_data: Mapping[str, Any],
               out: List[Match], depth: int) -> None:
        options = _merge_options(inherited_options, getattr(node, 'options', None))
        kind = getattr(node, 'kind', None)

        if kind == 'group':
            self._visit_group(node, root, options, version_data, out, depth)
        elif kind == 'rule':
            self._walk(node.levels, root, options, version_data, out)
        elif kind == 'action':
            # A bare Action can carry a collect too: behave exactly like the
            # Action at the end of a Rule chain.
            if node.collect:
                out.extend(self._collect_files(root, node.collect, options,
                                               version_data, 0))
            out.extend(self._collect_files(root, (node,), options, version_data, 0))
        elif kind == 'level':
            raise RuleStructureError(
                '单独的 Level 无法确定导入方法，请放进 Rule 并以 Action 结尾: {!r}'.format(node))
        elif isinstance(node, (Group, Rule, Action, Level)):
            raise RuleDefinitionError('规则对象的 kind 无法识别: {!r}'.format(node))
        else:
            raise RuleDefinitionError('无法识别的规则对象: {!r}'.format(node))

    def _visit_group(self, node: Any, root: Any, options: Mapping[str, Any],
                     version_data: Mapping[str, Any], out: List[Match],
                     depth: int) -> None:
        """Execute one :class:`~sublevel_rules.rules.Group`.

        With ``mode='all'`` (the default) every child rule runs and the results
        are merged. With ``mode='first'`` they run in order and **the first child
        producing a non-empty result wins**, the rest are skipped -- that is the
        "fallback chain", used to express "the same asset has two valid directory
        layouts depending on the project, take whichever exists".
        """
        if getattr(node, 'mode', GROUP_MODE_ALL) != GROUP_MODE_FIRST:
            for sub_rule in node.rules:
                self._visit(sub_rule, root, options, version_data, out, depth + 1)
            return

        for sub_rule in node.rules:
            branch: List[Match] = []
            self._visit(sub_rule, root, options, version_data, branch, depth + 1)
            if branch:
                self.logger.debug('备选链命中 %r，跳过其余分支', sub_rule)
                out.extend(branch)
                return

        self.logger.debug('备选链里没有任何分支命中')

    def _walk(self, levels: Sequence[Level], root: Any, options: Mapping[str, Any],
              version_data: Mapping[str, Any], out: List[Match]) -> None:
        current_paths: List[Any] = [root]
        # options are merged along Group -> Rule -> Level -> Action (children
        # override parents), so each level has to accumulate them and pass them
        # on instead of re-merging from the top every time.
        current_options: Dict[str, Any] = dict(options)
        for index, level in enumerate(levels):
            if not current_paths:
                return
            is_last = index == len(levels) - 1
            current_options = _merge_options(
                current_options, getattr(level, 'options', None))
            level_options = current_options
            next_paths: List[Any] = []

            collect_scope = getattr(level, 'collect_scope', COLLECT_SCOPE_CHILDREN)
            for path in current_paths:
                if not path.is_dir():
                    continue

                if is_last:
                    # 1) Last level: the Action collects itself; collect lands in
                    #    the current directory.
                    if level.collect:
                        out.extend(self._collect_files(
                            path, level.collect, level_options, version_data, index))
                    if isinstance(level, Action):
                        out.extend(self._collect_files(
                            path, (level,), level_options, version_data, index))
                    else:
                        raise RuleStructureError(
                            '规则的第 {} 层是最后一层但不是 Action: {!r}'.format(index, level))
                    continue

                # 2) Middle level: match the next level's directories.
                #    require_content has to take effect *before* the mode picks a
                #    candidate, otherwise mode='first' locks onto an empty
                #    directory and nothing takes its place once it is filtered out.
                content_probe: Optional[Callable[[Entry], bool]] = None
                if getattr(level, 'require_content', False):
                    # The probe must use exactly the same options as the real
                    # collection: an inherited frame_pattern would otherwise make
                    # the probe collapse a different pattern name and mistake a
                    # directory that does have content for an empty one (leaving
                    # the whole chain silently empty).
                    content_probe = partial(self._has_content, levels=levels,
                                            start_index=index + 1,
                                            version_data=version_data,
                                            parent_options=level_options)

                candidates = self._match_directories(path, level, version_data,
                                                     content_probe=content_probe)

                # 2.1) Optional level: when nothing matches, pass the current
                #      directory on to the next level.
                if not candidates and getattr(level, 'optional', False):
                    self.logger.debug('可选层 %r 未命中，跳过该层继续匹配', level.patterns)
                    candidates = [path]

                # 3) Side collection.
                if level.collect:
                    if collect_scope == COLLECT_SCOPE_PARENT:
                        out.extend(self._collect_files(
                            path, level.collect, level_options, version_data, index))
                    else:
                        for candidate in candidates:
                            if candidate.is_dir():
                                out.extend(self._collect_files(
                                    candidate, level.collect, level_options,
                                    version_data, index))

                next_paths.extend(candidates)

            current_paths = next_paths

    def _has_content(self, path: Any, levels: Sequence[Level], start_index: int,
                     version_data: Mapping[str, Any],
                     parent_options: Optional[Mapping[str, Any]] = None) -> bool:
        """Probe whether anything can still be matched below ``path`` (used by
        ``require_content``).

        Only one level down is inspected: that is enough to filter out candidates
        that are completely empty, without walking the whole subtree just to probe
        (directory listings are cached anyway, so repeated probes cost no extra IO).

        ``parent_options`` must be the same options the real collection uses:
        otherwise an inherited ``frame_pattern`` makes the probe collapse a
        different pattern name, mistakes a directory that does have content for an
        empty one and the whole chain silently turns into an empty result.
        """
        if start_index >= len(levels) or not path.is_dir():
            return False
        level = levels[start_index]
        if isinstance(level, Action):
            return bool(self._collect_files(
                path, (level,), parent_options or {}, version_data, start_index))
        if self._match_directories(path, level, version_data):
            return True
        return bool(getattr(level, 'optional', False))

    def _match_directories(self, directory: Any, level: Level,
                           version_data: Mapping[str, Any],
                           content_probe: Optional[Callable[[Entry], bool]] = None
                           ) -> List[Any]:
        children = self._listdir(directory)
        patterns = self._format_patterns(level.patterns, version_data)
        matched: List[Entry] = []
        seen: Set[str] = set()

        for pattern in patterns:
            found = [child for child in children
                     if self._name_matches(child.name, pattern)]
            if found and content_probe is not None:
                # Drop candidates that hold nothing for the next level before
                # the mode gets to pick one.
                found = [child for child in found if content_probe(child)]
            if not found:
                continue
            for child in found:
                key = str(child.path)
                if key not in seen:
                    seen.add(key)
                    matched.append(child)
            if level.mode == MODE_FIRST:
                break

        if not matched:
            self.logger.debug(
                '层级 %r 的模式 %r 在 %s 下没有任何命中', level.patterns, patterns, directory)

        if level.mode == MODE_FIRST:
            matched = matched[:1]
        elif level.mode == MODE_LATEST and matched:
            matched = [max(matched, key=lambda entry: _natural_key(entry.name))]
        return matched

    def _collect_files(self, parent: Any, actions: Iterable[Action],
                       parent_options: Mapping[str, Any],
                       version_data: Mapping[str, Any],
                       level_index: int) -> List[Match]:
        if not parent.is_dir():
            return []

        children = self._listdir(parent)
        matches: List[Match] = []

        for action in actions:
            action_options = _merge_options(parent_options, getattr(action, 'options', None))
            patterns = self._format_patterns(action.patterns, version_data)

            # ``pool_items`` is explicitly List[Any]: the pool is either the
            # directory entries or the collapsed sequences, and the annotation
            # stops mypy from narrowing it to a union of the two.
            pool_items: List[Any]
            if action.is_sequence:
                frame_pattern = action_options.get('frame_pattern') or self.frame_pattern
                pool_items = self._sequences(parent, frame_pattern)
            else:
                pool_items = children

            candidates: List[SequentialFiles] = []
            seen: Set[str] = set()
            files_only = bool(getattr(action, 'files_only', False))
            for pattern in patterns:
                raw: List[Any] = [item for item in pool_items
                                  if self._name_matches(item.name, pattern)]
                if files_only and not action.is_sequence:
                    raw = [item for item in raw if item.is_file()]
                found: List[Any] = (raw if action.is_sequence
                                    else [_as_single_file(item) for item in raw])
                if not found:
                    continue
                for item in found:
                    key = str(item.filename.path)
                    if key not in seen:
                        seen.add(key)
                        candidates.append(item)
                if action.mode == MODE_FIRST:
                    break

            if action.mode == MODE_FIRST:
                candidates = candidates[:1]
            elif action.mode == MODE_LATEST and candidates:
                candidates = [max(candidates, key=lambda item: _natural_key(item.name))]

            for sequence in candidates:
                matches.append(Match(
                    sequence=sequence,
                    method=action.method,
                    action=action,
                    checked=action.checked,
                    options=action_options,
                    depth=level_index,
                ))

        return matches

    # ------------------------------------------------------------------ helpers
    def _format_patterns(self, patterns: Iterable[str],
                         version_data: Mapping[str, Any]) -> Tuple[str, ...]:
        return tuple(
            format_pattern(pattern, version_data, strict=self.strict_format)
            for pattern in patterns)

    def _name_matches(self, name: str, pattern: str) -> bool:
        if name == pattern:
            return True
        if self.case_sensitive:
            return fnmatch.fnmatchcase(name, pattern)
        return fnmatch.fnmatchcase(name.lower(), pattern.lower())

    def _is_excluded(self, name: str) -> bool:
        for pattern in self.exclude_patterns:
            if self._name_matches(name, pattern):
                return True
        return False

    def _listdir(self, directory: Any) -> List[Entry]:
        key = str(directory)
        if key not in self._listing_cache:
            entries = list_entries(directory)
            if self.exclude_patterns:
                entries = [entry for entry in entries
                           if not self._is_excluded(entry.name)]
            self._listing_cache[key] = entries
        return self._listing_cache[key]

    def _sequences(self, directory: Any, frame_pattern: str) -> List[SequentialFiles]:
        key = (str(directory), frame_pattern)
        if key not in self._sequence_cache:
            sequences = scan_sequences(
                directory,
                frame_pattern=frame_pattern,
                single_media_exts=self.single_media_exts,
            )
            if self.exclude_patterns:
                sequences = [item for item in sequences
                             if not self._is_excluded(item.name)]
            self._sequence_cache[key] = sequences
        return self._sequence_cache[key]

    def _dedupe(self, matches: Iterable[Match]) -> List[Match]:
        unique: List[Match] = []
        seen: Set[Tuple[str, str]] = set()
        for match in matches:
            path_key = str(match.path)
            if not self.case_sensitive:
                path_key = path_key.lower()
            key = (path_key, match.method)
            if key in seen:
                continue
            seen.add(key)
            unique.append(match)
        return unique

    def _apply_mutex(self, matches: Sequence[Match]) -> None:
        """Keep at most one checked entry per mutex group.

        Rule: the first already-checked entry of the group is kept; when nothing
        in the group is checked and ``auto_select_first`` is true (the default),
        the first match of the group gets checked.
        """
        groups: Dict[str, List[int]] = {}
        for index, match in enumerate(matches):
            mutex_id = match.mutex
            if mutex_id:
                groups.setdefault(mutex_id, []).append(index)

        for mutex_id, indexes in groups.items():
            active: Optional[int] = None
            for index in indexes:
                if to_check_state(matches[index].checked):
                    active = index
                    break
            if active is None and self.auto_select_first:
                active = indexes[0]
                self.logger.debug('互斥组 %r 内没有已勾选项，自动勾选第一个', mutex_id)

            for index in indexes:
                matches[index].checked = (
                    CHECKED_CHECKED if index == active else CHECKED_UNCHECKED)


def _as_single_file(entry: Entry) -> SequentialFiles:
    """Wrap a plain entry into a :class:`SequentialFiles` (no frame information)."""
    return SequentialFiles(entry, [], [])


def resolve(rule: Any, root_path: PathValue,
            version_data: Optional[Mapping[str, Any]] = None,
            inherited_options: Optional[Mapping[str, Any]] = None,
            **resolver_options: Any) -> List[Match]:
    """Convenience function: resolve once with a throwaway :class:`Resolver`.

    Extra keyword arguments are forwarded to :class:`Resolver`.
    """
    resolver = Resolver(**resolver_options)
    return resolver.resolve(rule, root_path, version_data,
                            inherited_options=inherited_options)


def resolve_smart_rule(rule: Any, root_path: PathValue,
                       version_data: Optional[Mapping[str, Any]] = None,
                       inherited_options: Optional[Mapping[str, Any]] = None,
                       **resolver_options: Any) -> List[Match]:
    """Alias of :func:`resolve`, kept for convenience.

    Identical in behaviour; the extra name exists so integrations that already
    call ``resolve_smart_rule`` do not have to change.
    """
    return resolve(rule, root_path, version_data, inherited_options=inherited_options,
                   **resolver_options)
