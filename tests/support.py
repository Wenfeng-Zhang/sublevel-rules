# -*- coding: utf-8 -*-
"""Shared test helpers."""

from pathlib import Path

__all__ = ['make_dir', 'touch']


def touch(base, *names, **kwargs):
    """Create files under ``base`` (parent directories are created as needed) and
    return the list of created paths.

    :param names: relative paths, e.g. ``'cache/v001/a.abc'``.
    :param content: optional initial content.
    """
    content = kwargs.pop('content', '')
    if kwargs:
        raise TypeError('未知参数: {}'.format(sorted(kwargs)))
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    created = []
    for name in names:
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(path), 'w') as handle:
            handle.write(content)
        created.append(path)
    return created


def make_dir(base, *names):
    """Create directories under ``base`` and return ``base``."""
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    for name in names:
        (base / name).mkdir(parents=True, exist_ok=True)
    return base
