# -*- coding: utf-8 -*-
"""YAML rule adapter -- **removable**.

This is the only file in the package that knows about YAML: **delete it and no
other file has to change**, the library keeps working, the command line simply
stops understanding ``.yaml`` / ``.yml`` rule files.

The CLI discovers it by convention: any ``*_rules.py`` in the package directory
that exposes ``SUFFIXES`` and ``load_rules()`` is wired up automatically. So to
drop YAML support completely, delete this file plus the matching extra line in
``setup.cfg``.

Requires PyYAML (optional dependency)::

    pip install "sublevel-rules[yaml]"
"""

from typing import Any, Optional, Tuple

from .errors import SubLevelRulesError
from .rule_dict import rule_from_dict, rule_to_dict

__all__ = ['SUFFIXES', 'dump_rules', 'load_rules']

#: File suffixes handled by this adapter (the CLI registers them).
SUFFIXES: Tuple[str, ...] = ('.yaml', '.yml')


def _import_yaml() -> Any:
    try:
        import yaml
    except ImportError:
        raise SubLevelRulesError(
            '读取 YAML 规则需要 PyYAML，请先安装：pip install "sublevel-rules[yaml]"')
    return yaml


def load_rules(path: str, name: Optional[str] = None) -> Any:
    """Read one rule from a YAML file.

    :param path: ``.yaml`` / ``.yml`` file path.
    :param name: when one file holds several rules, this key selects one of
        them::

            mod:                # --rules rules.yaml:mod
              type: group
              rules: [...]

    :returns: the rule object.
    """
    yaml = _import_yaml()
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = yaml.safe_load(handle)
    except (IOError, OSError) as exc:
        raise SubLevelRulesError('读取 YAML 规则失败: {}'.format(exc))
    except yaml.YAMLError as exc:
        # YAMLError is not part of this library's exception hierarchy, so it must
        # not leak out to callers that only catch SubLevelRulesError.
        raise SubLevelRulesError('{} 不是合法的 YAML: {}'.format(path, exc))

    if data is None:
        raise SubLevelRulesError('{} 是空文件'.format(path))

    if name:
        if not isinstance(data, dict) or name not in data:
            raise SubLevelRulesError('{} 里没有名为 {!r} 的规则'.format(path, name))
        data = data[name]

    return rule_from_dict(data)


def dump_rules(rule: Any, path: Optional[str] = None) -> str:
    """Dump a rule object as YAML text; when ``path`` is given, also write it out.

    Useful for turning existing Python rules into a YAML template.
    """
    yaml = _import_yaml()
    text = yaml.safe_dump(rule_to_dict(rule), allow_unicode=True, sort_keys=False)
    if path:
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
    return text
