# -*- coding: utf-8 -*-
"""Conversion between rule objects and plain data (nested ``dict``).

This layer is **format agnostic**: whether a rule comes from YAML, JSON, a
database or Python code, it is first normalized into the nested dict described
below and then handed to :func:`rule_from_dict`. Supporting another
configuration format therefore stays a thin few-dozen-line shell (see
:mod:`sublevel_rules.yaml_rules`) while the core knows no concrete format.

The data structure maps one-to-one onto the DSL::

    {'type': 'group',  'mode': 'all', 'options': {...}, 'rules':  [node, ...]}
    {'type': 'rule',   'options': {...}, 'levels': [node, ...]}
    {'type': 'level',  'patterns': [...], 'mode': 'first', ...}
    {'type': 'multi',  'patterns': [...], ...}
    {'type': 'action', 'patterns': [...], 'method': 'geo', ...}

Apart from ``type``, the keys of a ``level`` / ``multi`` / ``action`` node are
exactly the constructor arguments of :class:`~sublevel_rules.rules.Level` /
``Action``; a misspelled key **fails immediately and points at its location**
instead of being silently ignored.
"""

from typing import Any, Dict, List, NoReturn, Set, Tuple

from .const import MODE_FIRST
from .errors import RuleDefinitionError
from .rules import (
    COLLECT_SCOPE_CHILDREN,
    Action,
    Group,
    Level,
    Multi,
    Rule,
)

__all__ = ['NODE_TYPES', 'rule_from_dict', 'rule_to_dict']

#: Keys allowed on each node type (besides ``options``).
_ALLOWED_KEYS: Dict[str, Set[str]] = {
    'group': {'rules', 'mode'},
    'rule': {'levels'},
    'level': {'patterns', 'mode', 'collect', 'collect_scope', 'mutex',
              'optional', 'require_content'},
    'multi': {'patterns', 'collect', 'collect_scope', 'mutex',
              'optional', 'require_content'},
    'action': {'patterns', 'method', 'mode', 'is_sequence', 'checked', 'mutex',
               'collect', 'files_only'},
}

#: Supported node types.
NODE_TYPES: Tuple[str, ...] = tuple(sorted(_ALLOWED_KEYS))

#: Keys every node type has to provide (missing ones fail right away instead of
#: surfacing as a bare ``TypeError``).
#:
#: When ``rules`` / ``levels`` are missing from ``group`` / ``rule``, ``Group``
#: and ``Rule`` themselves produce a more specific message, so they are not
#: checked again here.
_REQUIRED_KEYS: Dict[str, Tuple[str, ...]] = {
    'level': ('patterns',),
    'multi': ('patterns',),
    'action': ('patterns', 'method'),
}

#: Sub-keys that need recursive conversion.
_CHILD_KEYS: Tuple[str, ...] = ('rules', 'levels', 'collect')


def _fail(path: str, message: str) -> NoReturn:
    raise RuleDefinitionError('{}: {}'.format(path, message))


def _children(value: Any, path: str) -> List[Any]:
    if isinstance(value, dict):
        return [rule_from_dict(value, path)]
    if isinstance(value, (list, tuple)):
        return [rule_from_dict(item, '{}[{}]'.format(path, index))
                for index, item in enumerate(value)]
    _fail(path, '期望 dict 或 list，收到 {}'.format(type(value).__name__))


def rule_from_dict(data: Any, _path: str = 'root') -> Any:
    """Turn a nested dict into rule objects.

    :param data: see the structure description in the module docstring. The
        smallest rule looks like::

        {'type': 'action', 'patterns': ['*.ma'], 'method': 'geo'}

    :raises RuleDefinitionError: bad structure, unknown type or misspelled key --
        every one of them points at the exact location.
    :returns: :class:`~sublevel_rules.rules.Group` / ``Rule`` / ``Level`` /
        ``Multi`` / ``Action``
    """
    if not isinstance(data, dict):
        _fail(_path, '期望 dict，收到 {}'.format(type(data).__name__))

    payload: Dict[str, Any] = dict(data)
    raw_type = payload.pop('type', None)
    node_type = str(raw_type).lower() if raw_type is not None else None
    if node_type is None or node_type not in _ALLOWED_KEYS:
        _fail(_path, '"type" 必须是 {} 之一，收到 {!r}'.format(
            '、'.join(NODE_TYPES), data.get('type')))

    options: Dict[str, Any] = payload.pop('options', None) or {}
    if not isinstance(options, dict):
        _fail('{}.options'.format(_path),
              '期望 dict，收到 {}'.format(type(options).__name__))

    unknown = sorted(set(payload) - _ALLOWED_KEYS[node_type])
    if unknown:
        _fail(_path, 'type={!r} 里不认识的键：{}（可用：{}）'.format(
            node_type, '、'.join(unknown), '、'.join(sorted(_ALLOWED_KEYS[node_type]))))

    missing = [key for key in _REQUIRED_KEYS.get(node_type, ())
               if key not in payload]
    if missing:
        _fail(_path, 'type={!r} 缺少必需的键：{}'.format(
            node_type, '、'.join(missing)))

    children: Dict[str, List[Any]] = {}
    for key in _CHILD_KEYS:
        if key in payload:
            children[key] = _children(payload.pop(key),
                                      '{}.{}'.format(_path, key))

    kwargs: Dict[str, Any] = dict(options)
    kwargs.update(payload)

    if node_type == 'group':
        return Group(*children.get('rules', []), **kwargs)
    if node_type == 'rule':
        return Rule(*children.get('levels', []), **kwargs)
    if node_type == 'multi':
        return Multi(kwargs.pop('patterns'),
                     collect=children.get('collect') or None, **kwargs)
    if node_type == 'level':
        return Level(collect=children.get('collect') or None, **kwargs)
    return Action(collect=children.get('collect') or None, **kwargs)


def rule_to_dict(node: Any) -> Dict[str, Any]:
    """Turn rule objects back into a nested dict (ready for :func:`rule_from_dict`).

    One use is exporting existing Python rules as a configuration template so
    people who do not write code can edit them.
    """
    kind = getattr(node, 'kind', None)

    if kind == 'group':
        data: Dict[str, Any] = {'type': 'group'}
        if getattr(node, 'mode', None) and node.mode != 'all':
            data['mode'] = node.mode
        if node.options:
            data['options'] = dict(node.options)
        data['rules'] = [rule_to_dict(item) for item in node.rules]
        return data

    if kind == 'rule':
        data = {'type': 'rule'}
        if node.options:
            data['options'] = dict(node.options)
        data['levels'] = [rule_to_dict(item) for item in node.levels]
        return data

    if kind == 'action':
        data = {'type': 'action',
                'patterns': list(node.patterns),
                'method': node.method}
        if node.mode != MODE_FIRST:
            data['mode'] = node.mode
        if node.is_sequence:
            data['is_sequence'] = True
        if node.checked is not None:
            data['checked'] = node.checked
        if node.mutex:
            data['mutex'] = node.mutex
        if node.files_only:
            data['files_only'] = True
        if node.collect:
            data['collect'] = [rule_to_dict(item) for item in node.collect]
        if node.options:
            data['options'] = dict(node.options)
        return data

    if kind == 'level':
        data = {'type': 'multi' if isinstance(node, Multi) else 'level',
                'patterns': list(node.patterns)}
        if node.mode != MODE_FIRST and not isinstance(node, Multi):
            data['mode'] = node.mode
        if node.collect:
            data['collect'] = [rule_to_dict(item) for item in node.collect]
        if node.collect_scope != COLLECT_SCOPE_CHILDREN:
            data['collect_scope'] = node.collect_scope
        # ``mutex`` was already written into ``options`` by ``Level.__init__``,
        # so it is not exported a second time here.
        if getattr(node, 'optional', False):
            data['optional'] = True
        if getattr(node, 'require_content', False):
            data['require_content'] = True
        if node.options:
            data['options'] = dict(node.options)
        return data

    raise RuleDefinitionError('无法导出的规则对象: {!r}'.format(node))
