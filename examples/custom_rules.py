# -*- coding: utf-8 -*-
"""Custom rule example: walks through the whole sublevel_rules syntax.

Run it directly (the script puts ``src`` on ``sys.path`` itself)::

    python examples/custom_rules.py
"""

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from sublevel_rules import Action, Group, Level, Multi, Rule  # noqa: E402


def get_import_rules():
    """Return one rule set.

    The structure is the resource list of "version folder v001".
    """
    return Group(
        # ---- 1) at the version folder root: model files, abc first, mutex with ma/mb ----
        Action('*mod_v{version_part}.abc', method='geo', checked=2,
               mutex='mod_file', mode='first'),
        Action(['*_v{version_part}.ma', '*_v{version_part}.mb'], method='geo',
               checked=2, mutex='mod_file', mode='first'),

        # ---- 2) other formats collected at the same level, unchecked by default ----
        Action(['*_v{version_part}.usd', '*_v{version_part}.obj',
                '*_v{version_part}.ass'], method='geo', mode='multiple'),

        # ---- 3) branch: the abc sequence under cache/<version>/, checked by default ----
        Rule(
            Level('cache'),                       # level 1 directory
            Level('v{version_part}'),             # level 2 directory
            Action('*.abc', method='animation', mode='multiple', checked=2,
                   is_sequence=True,                  # collapse the frame sequence
                   frame_pattern='%'),                # placeholder style, '#' also works
                   # it can be written as options={'frame_pattern': '#'} too
        ),

        # ---- 4) branch: textures two levels down, collecting the root readme ----
        Rule(
            Level('tex', collect=Action('*.txt', method='readme')),  # collect on the way in
            Multi('v{version_part}', '*'),        # this level collects every subdirectory
            Action(['*.exr', '*.tx'], method='texture', mode='multiple',
                   is_sequence=True, checked=2),
        ),
    )


if __name__ == '__main__':
    rules = get_import_rules()
    print(rules)
