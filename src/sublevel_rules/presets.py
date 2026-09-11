# -*- coding: utf-8 -*-
"""Preset rules.

Four ready-to-use rule sets for the common stages -- model (``mod``), rig,
texture (``tex``) and animation (``ani``). Use them as-is when your directory
conventions match, or copy one as a starting point and adapt it.
"""

from .rules import Action, Group, Level, Multi, Rule

__all__ = ['ani_rules', 'mod_rules', 'rig_rules', 'tex_rules']


def mod_rules() -> Group:
    """Model (mod): take abc first, then ma/mb; collect other formats on top.

    The ``'mod_rule'`` mutex group keeps abc and ma/mb from being checked at the
    same time.
    """
    return Group(
        Action('*mod_v{version_part}.abc', method='geo', checked=2,
               mutex='mod_rule', mode='first'),
        Action(['*_v{version_part}.ma', '*_v{version_part}.mb'], method='geo',
               checked=2, mutex='mod_rule', mode='first'),
        Action(['*_v{version_part}.usd', '*_v{version_part}.obj',
                '*_v{version_part}.ass', '*_gpu_v{version_part}.abc'],
               method='geo', mode='multiple'),
    )


def rig_rules() -> Group:
    """Rig: take ma/mb from the version folder, then collect other formats."""
    return Group(
        Action(['*_v{version_part}.ma', '*_v{version_part}.mb'], method='rig',
               checked=2, mode='first'),
        Action(['*_v{version_part}.abc', '*_v{version_part}.usd',
                '*_v{version_part}.obj', '*_v{version_part}.ass'],
               method='rig', mode='multiple'),
    )


def tex_rules() -> Group:
    """Texture (tex): take ma/mb from the version folder, then collect other formats."""
    return Group(
        Action(['*_v{version_part}.ma', '*_v{version_part}.mb'], method='material',
               checked=2, mode='first'),
        Action(['*_v{version_part}.usd', '*_v{version_part}.ass'], method='material',
               mode='multiple'),
    )


def ani_rules() -> Group:
    """Animation (ani): ma plus camera abc at the root, plus the abc sequence
    under ``cache/v{version}``.

    This demonstrates the typical sub level situation: everything below the
    ``cache`` level is project specific, so the levels have to be spelled out with
    :class:`Rule`.

    Two choices are worth knowing about: ``cache`` is entered with
    ``Multi('v{version_part}', '*')``, which picks up the version folder first and
    then catches other naming; and the ``Action`` sets ``is_sequence=True``, so the
    abc files under ``cache/v001`` collapse into one sequence. Narrow both down if
    your layout differs.
    """
    return Group(
        Action('*_v{version_part}.ma', method='animation', mode='first'),
        Action('*cam_v{version_part}.abc', method='animation', mode='first', checked=2),
        Rule(
            Level('cache'),
            Multi('v{version_part}', '*'),
            Action('*.abc', method='animation', mode='multiple', checked=2,
                   is_sequence=True),
        ),
    )
