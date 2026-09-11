# -*- coding: utf-8 -*-
"""Example that previews rule results through the library API (the equivalent of
the CLI output).

Usage::

    python examples/preview.py <version folder>
    python examples/preview.py <version folder> --group-mode nested
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

from sublevel_rules import Resolver, build_operations, mod_rules  # noqa: E402
from sublevel_rules.cli import extract_version_part, render_operations  # noqa: E402


def preview(root, version_part=None, group_mode='flat'):
    version_data = {
        'path': str(root),
        'version_part': version_part or extract_version_part(root),
    }
    resolver = Resolver()
    matches = resolver.resolve(mod_rules(), root, version_data)
    operations = build_operations(matches, str(root), version_data,
                                  group_mode=group_mode)

    print('root         : {}'.format(root))
    print('version_part : {}'.format(version_data['version_part']))
    print('matched      : {}'.format(len(matches)))
    print('')
    render_operations(operations)


def main(argv=None):
    parser = argparse.ArgumentParser(description='sublevel_rules 预览示例')
    parser.add_argument('version_path')
    parser.add_argument('--version-part', default=None)
    parser.add_argument('--group-mode', default='flat',
                        choices=['flat', 'nested', 'none'])
    args = parser.parse_args(argv)
    preview(args.version_path, args.version_part, args.group_mode)
    return 0


if __name__ == '__main__':
    sys.exit(main())
