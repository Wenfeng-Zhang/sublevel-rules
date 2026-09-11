# -*- coding: utf-8 -*-
"""Command line preview tool.

Needs no GUI at all; it answers "what would the rules match inside this version
folder" in one shot::

    sublevel-rules "D:/show/asset/mod/v001" --preset mod
    sublevel-rules "D:/show/asset/ani/v001" --preset ani --group-mode nested
    sublevel-rules "D:/show/asset/mod/v001" --rules mypipeline.rules:get_import_rules --json

``python -m sublevel_rules <version folder>`` works too.

Note: user-facing strings (CLI help, error messages, log text) are Chinese on
purpose -- this is an internal pipeline tool.
"""

import argparse
import importlib
import importlib.util
import json
import logging
import os
import re
import sys

from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, TextIO, Tuple

from .const import DEFAULT_FRAME_PATTERN, FRAME_PATTERN_STYLES
from .errors import SubLevelRulesError
from .operations import build_operations
from .paths import PathValue, as_path
from .presets import ani_rules, mod_rules, rig_rules, tex_rules
from .resolver import Resolver
from .rules import Group, describe_rule

__all__ = ['build_parser', 'load_rules', 'main', 'render_operations']

#: Loader signature every ``*_rules.py`` adapter has to expose.
_Loader = Callable[..., Any]

_PRESETS: Dict[str, Callable[[], Group]] = {
    'ani': ani_rules,
    'mod': mod_rules,
    'rig': rig_rules,
    'tex': tex_rules,
}

_MARKS: Dict[Optional[int], str] = {0: '[ ]', 1: '[-]', 2: '[x]'}

#: Fields dropped from JSON output (not serializable / internal details).
_JSON_SKIP_FIELDS: Tuple[str, ...] = ('op_func', 'args', 'orm', 'sequence')

#: Cache of discovered in-package ``*_rules.py`` adapters (suffix -> load_rules).
_EXTRA_LOADER_CACHE: Optional[Dict[str, _Loader]] = None


def _extra_rule_loaders() -> Dict[str, _Loader]:
    """Discover the removable rule-format adapters (``*_rules.py``) in the package.

    Convention: a module exposing ``SUFFIXES`` (a tuple of suffixes) and
    ``load_rules(path, name=None)`` is wired up automatically. So this CLI
    **knows no concrete format** -- deleting an adapter module removes support
    for that format without touching this file.
    """
    global _EXTRA_LOADER_CACHE
    if _EXTRA_LOADER_CACHE is not None:
        return _EXTRA_LOADER_CACHE

    loaders: Dict[str, _Loader] = {}
    package_dir = os.path.dirname(os.path.abspath(__file__))
    for filename in sorted(os.listdir(package_dir)):
        if not filename.endswith('_rules.py'):
            continue
        try:
            module = importlib.import_module('.' + filename[:-3], __package__)
        except ImportError:
            # The adapter's own optional dependency is missing (PyYAML),
            # just skip it.
            continue
        for suffix in getattr(module, 'SUFFIXES', ()):
            loaders[suffix] = module.load_rules
    _EXTRA_LOADER_CACHE = loaders
    return loaders


def extract_version_part(path: PathValue) -> str:
    """Extract the version number from a folder name, e.g. ``v001`` -> ``001``;
    returns ``'*'`` when nothing can be extracted.

    A digit group after ``v`` / ``V`` wins (``shot010_v002`` -> ``002``); without
    a ``v`` prefix the last digit group is used.
    """
    name = os.path.basename(str(path).rstrip('/\\'))
    match = re.search(r'[vV](\d+)', name)
    if match:
        return match.group(1)
    digits = re.findall(r'\d+', name)
    return digits[-1] if digits else '*'


def _split_spec(spec: str) -> Tuple[str, str]:
    """Split ``'module:attr'`` / ``'path/to/rules.py:attr'``.

    Windows drive letters are handled (the colon in ``'C:\\proj\\rules.py'`` is
    not a separator).
    """
    head, sep, tail = spec.rpartition(':')
    if not sep:
        return spec, ''
    if len(head) == 1 and tail[:1] in ('\\', '/'):
        return spec, ''
    return head, tail


def load_rules(spec: str) -> Any:
    """Load rules.

    :param spec: one of three spellings:

        * ``'module:attr'`` / ``'module'`` (attr defaults to ``get_import_rules``);
        * ``'path/to/rules.py:attr'``;
        * a data file (suffixes registered by the in-package ``*_rules.py``
          adapters, see :func:`_extra_rule_loaders`): ``'rules.yaml'``,
          ``'rules.yaml:rule name'``.

    :returns: the rule object (``Group`` / ``Rule`` / ``Action``).
    """
    target, name = _split_spec(spec)
    suffix = os.path.splitext(target)[1].lower()

    extra_loaders = _extra_rule_loaders()
    if suffix in extra_loaders:
        return extra_loaders[suffix](target, name or None)
    if suffix and suffix != '.py' and os.path.isfile(target):
        raise SubLevelRulesError(
            '不认识 {!r} 这种规则格式（已注册：{}）；需要的话装上对应适配器，'
            '例如 pip install "sublevel-rules[yaml]"'.format(
                suffix, '、'.join(sorted(extra_loaders)) or '无'))

    module_name = target
    attr = name or 'get_import_rules'

    is_file = module_name.endswith('.py') or os.sep in module_name or '/' in module_name
    if is_file:
        path = os.path.abspath(module_name)
        if not os.path.isfile(path):
            raise SubLevelRulesError('规则文件不存在: {}'.format(path))
        module_spec = importlib.util.spec_from_file_location(
            'sublevel_rules_cli_rules', path)
        if module_spec is None or module_spec.loader is None:
            raise SubLevelRulesError('无法加载规则文件: {}'.format(path))
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    else:
        module = importlib.import_module(module_name)

    rules = getattr(module, attr, None)
    if rules is None:
        raise SubLevelRulesError('{} 里没有 {}'.format(spec, attr))
    return rules() if callable(rules) else rules


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='sublevel-rules',
        description='在某个版本目录上跑一遍 sub level 规则并打印结果')
    parser.add_argument('version_path', nargs='?',
                        help='版本目录（规则的起点）；配合 --describe 时可省略')
    parser.add_argument('--rules', default=None,
                        help="规则来源：'module:attr' 或 'path/to/rules.py:attr'")
    parser.add_argument('--preset', default=None, choices=sorted(_PRESETS),
                        help='使用内置预设规则（未指定 --rules 时默认 mod）')
    parser.add_argument('--version-part', default=None,
                        help='覆盖 {version_part} 的取值（默认从目录名里取数字）')
    parser.add_argument('--frame-pattern', default=DEFAULT_FRAME_PATTERN,
                        choices=list(FRAME_PATTERN_STYLES),
                        help='序列帧占位符风格')
    parser.add_argument('--group-mode', default='flat',
                        choices=['flat', 'nested', 'none'], help='分组方式')
    parser.add_argument('--case-sensitive', action='store_true',
                        help='文件名匹配区分大小写（默认不区分）')
    parser.add_argument('--no-auto-select', action='store_true',
                        help='互斥组内没有已勾选项时不自动勾选第一个')
    parser.add_argument('--exclude', action='append', default=None, metavar='PATTERN',
                        help='跳过名字匹配该模式的条目，可重复'
                             '（例如 --exclude .git --exclude __pycache__）')
    parser.add_argument('--describe', action='store_true',
                        help='只打印规则树结构，不扫描目录')
    parser.add_argument('--json', action='store_true', dest='as_json',
                        help='以 JSON 输出')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                        help='打印调试日志（可重复）')
    return parser


def render_operations(operations: Iterable[Mapping[str, Any]],
                      stream: Optional[TextIO] = None) -> None:
    """Render hierarchical data as a tree of text."""
    out = stream if stream is not None else sys.stdout

    def walk(items: Sequence[Mapping[str, Any]], prefix: str = '') -> None:
        for index, item in enumerate(items):
            is_last = index == len(items) - 1
            branch = '`-- ' if is_last else '|-- '
            mark = _MARKS.get(item.get('filename_checked'), '[ ]')
            if 'children' in item:
                out.write('{}{}{} {}/\n'.format(prefix, branch, mark, item['filename']))
                walk(item['children'], prefix + ('    ' if is_last else '|   '))
                continue
            frames = item.get('frames') or []
            extra = '{} frames'.format(len(frames)) if item.get('is_sequence') else ''
            out.write('{}{}{} {:<38} {:<12} {:<10} {}\n'.format(
                prefix, branch, mark, item.get('filename', ''),
                item.get('method') or '', item.get('size') or '', extra))

    walk(list(operations))


def to_jsonable(operations: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Drop the fields of hierarchical data that are not JSON serializable."""
    converted: List[Dict[str, Any]] = []
    for item in operations:
        entry: Dict[str, Any] = {}
        for key, value in item.items():
            if key in _JSON_SKIP_FIELDS:
                continue
            if key == 'children':
                entry[key] = to_jsonable(value)
            else:
                entry[key] = value
        converted.append(entry)
    return converted


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format='%(levelname)s %(name)s: %(message)s')

    try:
        if args.rules:
            rules = load_rules(args.rules)
        elif args.preset:
            rules = _PRESETS[args.preset]()
        else:
            rules = mod_rules()

        if args.describe:
            sys.stdout.write(describe_rule(rules) + '\n')
            return 0

        if not args.version_path:
            parser.error('需要给出 version_path（除非使用 --describe）')

        root = as_path(args.version_path)
        version_data: Dict[str, Any] = {
            'path': str(root),
            'version_part': args.version_part or extract_version_part(root),
        }

        resolver = Resolver(
            frame_pattern=args.frame_pattern,
            case_sensitive=args.case_sensitive,
            auto_select_first=not args.no_auto_select,
            exclude_patterns=args.exclude,
        )
        matches = resolver.resolve(rules, root, version_data)
        operations = build_operations(
            matches, str(root), version_data,
            group_mode=None if args.group_mode == 'none' else args.group_mode)
    except SubLevelRulesError as exc:
        # User-side problems (bad rule file, missing placeholder...) get one
        # readable line instead of a traceback.
        sys.stderr.write('错误: {}\n'.format(exc))
        return 2

    if args.as_json:
        json.dump(to_jsonable(operations), sys.stdout, indent=2,
                  ensure_ascii=False, default=str)
        sys.stdout.write('\n')
        return 0

    sys.stdout.write('root         : {}\n'.format(root))
    sys.stdout.write('version_part : {}\n'.format(version_data['version_part']))
    sys.stdout.write('matched      : {}\n\n'.format(len(matches)))
    render_operations(operations, sys.stdout)
    return 0
