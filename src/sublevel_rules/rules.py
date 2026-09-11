# -*- coding: utf-8 -*-
"""The rule DSL: describe declaratively "which resources live at which level
below a version folder".

Concept (sub level):

Inside a version folder (e.g. ``.../asset/element/mod/.../v001``) there are the
few files at the root, and usually more internal resources scattered further
down such as ``cache/v001/xxx.abc`` or ``abc/v001/tex/...``. How deep that
structure goes is not standardized -- every project and every stage may differ --
and everything below that point is the **sub level**, which is what a rule
describes.

This module provides three kinds of nodes:

* :class:`Level` / :class:`Multi` -- directory levels;
* :class:`Action` -- the files of the final level, carrying the import
  ``method``;
* :class:`Rule` / :class:`Group` -- chain levels into one complete rule, or
  combine several chains.

Example::

    from sublevel_rules import Action, Group, Level, Rule

    rules = Group(
        # project files at the root of the version folder
        Action('*_v{version_part}.ma', method='animation', mode='first', checked=2),
        # side branch: cache/v001/*.abc
        Rule(
            Level('cache'),
            Level('v{version_part}'),
            Action('*.abc', method='animation', mode='multiple', checked=2),
        ),
    )
"""

from typing import Any, Dict, List, Optional, Tuple

from .const import (
    CHECKED_CHECKED,
    CHECKED_PARTIAL,
    CHECKED_UNCHECKED,
    GROUP_MODE_ALL,
    GROUP_MODES,
    MODE_FIRST,
    MODE_MULTIPLE,
    MODES,
)
from .errors import RuleDefinitionError, RuleStructureError

__all__ = [
    'Action',
    'COLLECT_SCOPE_CHILDREN',
    'COLLECT_SCOPE_PARENT',
    'COLLECT_SCOPES',
    'Group',
    'Level',
    'Multi',
    'Rule',
    'describe_rule',
    'to_check_state',
]


def to_check_state(value: Any) -> int:
    """Normalize every legal ``checked`` value into a Qt check state ``0`` / ``1`` / ``2``.

    Comparing raw values with ``== 2`` would be wrong here: ``True == 2`` is
    ``False`` in Python, so an entry whose ``checked`` was ``True`` would be
    counted as partially checked. Routing everything through this function
    avoids that.

    ======================  =========
    Input                   Result
    ======================  =========
    ``None``                ``0``
    ``False``               ``0``
    ``True``                ``2``
    ``0`` / ``1`` / ``2``   unchanged
    any other truthy value  ``2``
    ======================  =========
    """
    if value is None:
        return CHECKED_UNCHECKED
    if value is True:
        return CHECKED_CHECKED
    if value is False:
        return CHECKED_UNCHECKED
    if isinstance(value, int):
        if value <= 0:
            return CHECKED_UNCHECKED
        if value >= CHECKED_CHECKED:
            return CHECKED_CHECKED
        return CHECKED_PARTIAL
    return CHECKED_CHECKED if value else CHECKED_UNCHECKED


def _normalize_patterns(patterns: Any) -> Tuple[str, ...]:
    """Normalize ``patterns`` into a non-empty ``tuple[str, ...]``."""
    if patterns is None:
        raise RuleDefinitionError('patterns 不能为 None')
    items: List[Any]
    if isinstance(patterns, (str, bytes)):
        items = [patterns]
    elif isinstance(patterns, (set, frozenset)):
        # A set is unordered; sorting makes ``mode='first'`` reproducible.
        items = sorted(patterns)
    elif isinstance(patterns, (list, tuple)):
        items = list(patterns)
    else:
        items = [patterns]
    if not items:
        raise RuleDefinitionError('patterns 不能为空')
    normalized: List[str] = []
    for item in items:
        if item is None:
            raise RuleDefinitionError('patterns 里不能包含 None')
        text = item.decode('utf-8') if isinstance(item, bytes) else str(item)
        if not text:
            raise RuleDefinitionError('patterns 里不能包含空字符串')
        normalized.append(text)
    return tuple(normalized)


def _normalize_mode(mode: str) -> str:
    if mode not in MODES:
        raise RuleDefinitionError('mode 只能是 {}，收到 {!r}'.format(
            '、'.join(repr(item) for item in MODES), mode))
    return mode


#: Where side collection (``Level.collect``) happens:
#:
#: * ``'children'`` (default) -- inside every subdirectory matched by this level;
#: * ``'parent'`` -- inside the directory this level lives in.
COLLECT_SCOPE_CHILDREN: str = 'children'
COLLECT_SCOPE_PARENT: str = 'parent'
COLLECT_SCOPES: Tuple[str, ...] = (COLLECT_SCOPE_CHILDREN, COLLECT_SCOPE_PARENT)


def _normalize_collect(collect: Any) -> Tuple['Action', ...]:
    """``collect`` accepts only Action objects (or a sequence of them)."""
    if collect is None:
        return ()
    items: Tuple[Any, ...]
    if isinstance(collect, (list, tuple)):
        items = tuple(collect)
    else:
        items = (collect,)
    for item in items:
        if not isinstance(item, Action):
            raise RuleDefinitionError(
                'Level.collect 只支持 Action，收到 {!r}'.format(type(item).__name__))
    return items


class Level(object):
    """A directory level.

    :param patterns: directory-name patterns to match at this level, as a ``str``
        or a sequence. Placeholders such as ``{version_part}`` are allowed and
        are filled from ``version_data``.
    :param mode: ``'first'`` takes only the first hit in pattern order;
        ``'multiple'`` collects every hit.
    :param collect: side collector, one or more :class:`Action` objects. It
        gathers extra resources on the way down without taking part in the
        matching itself.
    :param collect_scope: where side collection happens:

        * ``'children'`` (default) -- inside every subdirectory matched at this
          level;
        * ``'parent'`` -- inside the directory this level lives in (its parent).

        The last level (``Action``) always behaves like ``'parent'``.
    :param optional: optional level. With ``True`` this level not matching
        anything **does not break the chain**; the current directory is passed on
        to the next level instead -- useful for "some projects have one more
        directory here, others do not".
    :param require_content: require that a candidate directory actually contains
        what the next level matches, otherwise skip that candidate. Combine it
        with ``mode='first'`` / ``'latest'`` so that picking an empty directory
        cannot leave the whole chain without results.
    :param mutex: mutex group ID, see :class:`Action`. Written on a ``Level`` it
        is inherited downwards through ``options``, so one group can be declared
        once in the middle of a chain.
    :param options: every other key is inherited downwards as a parameter
        (child nodes override their parents).
    """

    kind: str = 'level'

    #: Whether ``mutex`` also goes into ``options`` -- it is inherited downwards
    #: through ``options`` and ends up in the resolution results. ``Action`` has
    #: its own dedicated ``mutex`` field and turns this switch off, so the same
    #: value never has two sources.
    _mutex_via_options: bool = True

    def __init__(self, patterns: Any, mode: str = MODE_FIRST, collect: Any = None,
                 mutex: Optional[str] = None,
                 collect_scope: str = COLLECT_SCOPE_CHILDREN, optional: bool = False,
                 require_content: bool = False, **options: Any) -> None:
        if collect_scope not in COLLECT_SCOPES:
            raise RuleDefinitionError('collect_scope 只能是 {}，收到 {!r}'.format(
                ' 或 '.join(repr(item) for item in COLLECT_SCOPES), collect_scope))
        self.patterns: Tuple[str, ...] = _normalize_patterns(patterns)
        self.mode: str = _normalize_mode(mode)
        self.collect: Tuple['Action', ...] = _normalize_collect(collect)
        self.collect_scope: str = collect_scope
        self.optional: bool = bool(optional)
        self.require_content: bool = bool(require_content)
        self.mutex: Optional[str] = mutex
        self.options: Dict[str, Any] = dict(options)
        if mutex and self._mutex_via_options:
            # ``Match.mutex`` reads ``Action.mutex`` and the inherited
            # ``options``; it never looks at the ``Level.mutex`` attribute. So
            # the value has to be copied into options as well, otherwise a mutex
            # declared in the middle of a chain would be silently ignored.
            self.options['mutex'] = mutex

    def __repr__(self) -> str:
        return '{}(patterns={!r}, mode={!r})'.format(
            type(self).__name__, self.patterns, self.mode)


class Multi(Level):
    """Syntactic sugar for ``mode='multiple'``::

        Multi('abc', 'xyz')            # collect both patterns
        Multi(['abc', 'xyz'], checked=2)
    """

    kind: str = 'level'

    def __init__(self, *patterns: Any, **kwargs: Any) -> None:
        if len(patterns) == 1 and isinstance(patterns[0], (list, tuple, set, frozenset)):
            patterns = tuple(patterns[0])
        collect = kwargs.pop('collect', None)
        kwargs.pop('mode', None)  # Multi is always multiple
        super(Multi, self).__init__(patterns, mode=MODE_MULTIPLE, collect=collect, **kwargs)


class Action(Level):
    """The final level of a chain: a set of files plus the import method.

    :param patterns: file-name patterns (``{version_part}`` placeholders allowed).
    :param method: import method name; the caller uses it to find the real import
        function; the caller typically resolves it through
        ``pipeline_module.create_api_version``.
    :param mode: ``'first'`` / ``'multiple'``.
    :param is_sequence: whether this level matches frame sequences (collapsing
        them first).
    :param checked: default UI check state, ``None`` / ``True`` / ``False`` /
        ``0`` / ``1`` / ``2``.
    :param mutex: mutex group ID. At most one entry per group stays checked.
    :param collect: rarely needed; kept so the signature matches ``Level``.
    :param files_only: match files only and ignore directories of the same name.
        When it is off (the default) directories are matched as entries too.
    :param options: every other key is inherited by the resolution results (for
        example ``frame_pattern``).
    """

    kind: str = 'action'

    #: ``Action`` has its own dedicated ``mutex`` field (``Match.mutex`` reads it
    #: first), so it does not put a second copy into ``options``.
    _mutex_via_options: bool = False

    def __init__(self, patterns: Any, method: str, mode: str = MODE_FIRST,
                 is_sequence: bool = False, checked: Any = None,
                 mutex: Optional[str] = None, collect: Any = None,
                 files_only: bool = False, **options: Any) -> None:
        super(Action, self).__init__(patterns, mode=mode, collect=collect,
                                     mutex=mutex, **options)
        if not method or not isinstance(method, str):
            raise RuleDefinitionError('Action.method 必须是非空字符串')
        self.method: str = method
        self.is_sequence: bool = bool(is_sequence)
        self.checked: Any = checked
        self.files_only: bool = bool(files_only)

    def __repr__(self) -> str:
        return ('Action(patterns={!r}, method={!r}, mode={!r}, checked={!r}, '
                'files_only={!r})').format(
            self.patterns, self.method, self.mode, self.checked, self.files_only)


class Rule(object):
    """One complete rule chain: ``Rule(Level(...), Level(...), Action(...))``.

    Constraints (checked at definition time, so a broken rule fails immediately):

    * at least one level;
    * the last level must be an :class:`Action`;
    * an ``Action`` may only appear as the last level.
    """

    kind: str = 'rule'

    def __init__(self, *levels: Level, **options: Any) -> None:
        if not levels:
            raise RuleDefinitionError('Rule 至少需要一个 Level/Action')
        for index, level in enumerate(levels):
            if not isinstance(level, Level):
                raise RuleDefinitionError(
                    'Rule 的第 {} 层不是 Level/Action，收到 {!r}'.format(
                        index, type(level).__name__))
            is_last = index == len(levels) - 1
            if isinstance(level, Action) and not is_last:
                raise RuleStructureError(
                    'Action 只能出现在 Rule 的最后一层（第 {} 层是 Action）'.format(index))
        if not isinstance(levels[-1], Action):
            raise RuleStructureError(
                'Rule 的最后一层必须是 Action，收到 {!r}；'
                '如果只想收集目录，请在该层用 Action 明确导出什么文件'.format(
                    type(levels[-1]).__name__))
        self.levels: Tuple[Level, ...] = tuple(levels)
        self.options: Dict[str, Any] = dict(options)

    def __repr__(self) -> str:
        return 'Rule({})'.format(', '.join(repr(level) for level in self.levels))


class Group(object):
    """A collection of rules, used to express branch logic::

        Group(
            Action('*_v{version_part}.ma', method='geo', checked=2),
            Rule(Level('cache'), Level('v{version_part}'), Action('*.abc', method='geo')),
        )

    :param mode: ``'all'`` (default) runs every child rule and merges the
        results; ``'first'`` is a **fallback chain**: rules run in order and the
        first one producing a non-empty result wins, the rest are skipped. It
        expresses "the same asset has two valid directory layouts depending on
        the project"::

            Group(
                Action('*.abc', method='geo', checked=2),                    # layout A
                Rule(Level('cache'), Level('v{version_part}'),               # layout B
                     Action('*.abc', method='geo', checked=2)),
                mode='first',
            )
    """

    kind: str = 'group'

    def __init__(self, *rules: Any, mode: str = GROUP_MODE_ALL, **options: Any) -> None:
        if len(rules) == 1 and isinstance(rules[0], (list, tuple)):
            rules = tuple(rules[0])
        if not rules:
            raise RuleDefinitionError('Group 至少要包含一条规则')
        if mode not in GROUP_MODES:
            raise RuleDefinitionError('Group.mode 只能是 {}，收到 {!r}'.format(
                ' 或 '.join(repr(item) for item in GROUP_MODES), mode))
        for rule in rules:
            if isinstance(rule, Action):
                continue
            if isinstance(rule, (Rule, Group)):
                continue
            raise RuleStructureError(
                'Group 只接受 Action / Rule / Group，收到 {!r}'.format(type(rule).__name__))
        self.mode: str = mode
        self.rules: Tuple[Any, ...] = tuple(rules)
        self.options: Dict[str, Any] = dict(options)

    def __repr__(self) -> str:
        return 'Group({})'.format(', '.join(repr(rule) for rule in self.rules))


def describe_rule(node: Any, _indent: int = 0) -> str:
    """Render a rule tree as human readable multi-line text (for debugging and
    the CLI ``--describe`` flag).

    >>> print(describe_rule(Level('cache')))
    Level(patterns=['cache'], mode='first')
    """
    pad = '  ' * _indent
    kind = getattr(node, 'kind', None)

    if kind == 'group':
        lines = ['{}Group(mode={!r}, options={})'.format(
            pad, getattr(node, 'mode', GROUP_MODE_ALL), dict(node.options))]
        for sub_rule in node.rules:
            lines.append(describe_rule(sub_rule, _indent + 1))
        return '\n'.join(lines)

    if kind == 'rule':
        lines = ['{}Rule(options={})'.format(pad, dict(node.options))]
        for level in node.levels:
            lines.append(describe_rule(level, _indent + 1))
        return '\n'.join(lines)

    if kind == 'action':
        return ('{}Action(patterns={}, method={!r}, mode={!r}, checked={!r}, '
                'is_sequence={!r}, files_only={!r}, mutex={!r})').format(
            pad, list(node.patterns), node.method, node.mode, node.checked,
            node.is_sequence, getattr(node, 'files_only', False), node.mutex)

    if kind == 'level':
        extra = ''
        if node.collect:
            extra = ', collect=[{}]'.format(
                ', '.join('{!r}'.format(item.method) for item in node.collect))
        if node.collect_scope != COLLECT_SCOPE_CHILDREN:
            extra += ', collect_scope={!r}'.format(node.collect_scope)
        if getattr(node, 'mutex', None):
            extra += ', mutex={!r}'.format(node.mutex)
        if getattr(node, 'optional', False):
            extra += ', optional=True'
        if getattr(node, 'require_content', False):
            extra += ', require_content=True'
        return '{}Level(patterns={}, mode={!r}{})'.format(
            pad, list(node.patterns), node.mode, extra)

    return '{}{!r}'.format(pad, node)
