# -*- coding: utf-8 -*-
"""Measure how a resolution scales with the number of files in a version folder.

The script builds synthetic version folders -- project files at the root, a frame
sequence under ``cache/v001`` and another one under ``tex/v001`` -- and times
``Resolver.resolve()`` (cold, warm and cached) plus ``build_operations()``.

**Everything stays inside the project folder**: the trees are created under
``build/benchmark/`` (which ``.gitignore`` already covers) and removed again unless
``--keep`` is passed, so nothing lands in the system temp directory.

Usage::

    python scripts/benchmark.py
    python scripts/benchmark.py --sizes 2000 5000 --repeat 3
    python scripts/benchmark.py --keep --write-doc
    python scripts/benchmark.py --workdir D:/bench    # measure another disk

The numbers depend on the storage (local SSD vs. NFS), the OS, the file system and
anti-virus software, so compare runs on the same machine instead of across
machines. ``--write-doc`` records the table, together with the environment it was
measured in, in ``docs/benchmark.md``.
"""

import argparse
import os
import platform
import shutil
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'src'))

from sublevel_rules import (Action, Group, Level, Resolver, Rule,  # noqa: E402
                            build_operations)

DEFAULT_SIZES = (1000, 5000, 20000)

#: Scratch space for the generated trees (inside the project, git ignored).
DEFAULT_WORKDIR = os.path.join(PROJECT_ROOT, 'build', 'benchmark')

#: The rule used for the measurement: project files at the root, a frame sequence
#: under ``cache/v001`` and another one under ``tex/v001`` -- roughly the shape of a
#: real model / animation version folder.
RULES = Group(
    Action(['*_v{version_part}.ma', '*_v{version_part}.mb'], method='geo',
           mode='first', checked=2),
    Rule(Level('cache'), Level('v{version_part}'),
         Action('*.abc', method='animation', mode='multiple', checked=2,
                is_sequence=True)),
    Rule(Level('tex'), Level('v{version_part}'),
         Action('*.exr', method='texture', mode='multiple', checked=2,
                is_sequence=True)),
)


def build_tree(root, files):
    """Create a version folder holding roughly ``files`` files in three branches.

    :param root: directory to fill.
    :param files: target file count.
    :returns: the number of files actually created.
    """
    per_branch = max(files // 4, 1)
    cache_dir = os.path.join(root, 'cache', 'v001')
    tex_dir = os.path.join(root, 'tex', 'v001')
    for path in (cache_dir, tex_dir):
        os.makedirs(path, exist_ok=True)

    created = 0
    with open(os.path.join(root, 'asset_v001.ma'), 'w') as handle:
        handle.write('x')
    created += 1

    # Half of the files are frame sequences, spread over two branches.
    for index in range(per_branch):
        with open(os.path.join(cache_dir, 'cache.%04d.abc' % (index + 1)), 'w') as handle:
            handle.write('x')
        with open(os.path.join(tex_dir, 'tex.%04d.exr' % (index + 1)), 'w') as handle:
            handle.write('x')
        created += 2

    # The rest is noise (single-frame media, plain text), so the scan is not
    # purely frames -- and the tree really holds ``files`` files, not a fraction
    # of it (the table reports the exact number).
    for index in range(max(files - created, 0)):
        if index % 10 == 0:
            name = 'plate.%04d.mov' % (index // 10 + 1)
        else:
            name = 'notes_%05d.txt' % (index + 1)
        with open(os.path.join(root, name), 'w') as handle:
            handle.write('x')
        created += 1
    return created


def timeit(func, repeat):
    """Run ``func`` ``repeat`` times.

    :returns: ``(best_ms, median_ms)``.
    """
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        func()
        samples.append((time.perf_counter() - start) * 1000.0)
    samples.sort()
    return samples[0], samples[len(samples) // 2]


def measure(files, repeat, workdir):
    """Measure one directory size.

    :param files: target file count.
    :param repeat: runs per measurement.
    :param workdir: scratch directory (inside the project by default).
    :returns: a dict with the timings (all in milliseconds).
    """
    root = os.path.join(workdir, 'size-%d' % files)
    shutil.rmtree(root, ignore_errors=True)
    try:
        created = build_tree(root, files)
        version_data = {'version_part': '001', 'path': root}

        resolver = Resolver()
        cold = timeit(lambda: resolver.resolve(RULES, root, version_data), repeat)

        # "warm" is the same Resolver object, but with the caches dropped before
        # every run -- a real cache miss; "cached" has them filled already.
        warm_resolver = Resolver(keep_cache=True)

        def warm_run():
            warm_resolver.clear_cache()
            warm_resolver.resolve(RULES, root, version_data)

        warm = timeit(warm_run, repeat)

        warm_resolver.clear_cache()
        warm_resolver.resolve(RULES, root, version_data)      # fill the cache once
        cached = timeit(lambda: warm_resolver.resolve(RULES, root, version_data), repeat)

        matches = resolver.resolve(RULES, root, version_data)
        operations = timeit(
            lambda: build_operations(matches, root, version_data, size_mode='none'),
            repeat)

        return {
            'files': created,
            'matches': len(matches),
            'cold_ms': cold[1],
            'per_file_us': cold[1] * 1000.0 / created,
            'warm_ms': warm[1],
            'cached_ms': cached[1],
            'operations_ms': operations[1],
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def render(rows):
    """Render measurement rows as a markdown table."""
    lines = [
        '| files | matches | resolve, cold (ms) | per file (us) | resolve, warm (ms) | '
        'resolve, cached (ms) | build_operations (ms) |',
        '| --- | --- | --- | --- | --- | --- | --- |',
    ]
    for row in rows:
        lines.append(
            '| {files} | {matches} | {cold_ms:.1f} | {per_file_us:.1f} | '
            '{warm_ms:.1f} | {cached_ms:.1f} | {operations_ms:.1f} |'.format(**row))
    return '\n'.join(lines)


def display_path(path):
    """Render ``path`` relative to the project root, so the docs stay portable."""
    try:
        relative = os.path.relpath(path, PROJECT_ROOT)
    except ValueError:                                       # another drive
        return path
    return path if relative.startswith('..') else relative.replace('\\', '/')


def environment_lines(workdir):
    """Describe the machine and the scratch directory the numbers came from."""
    return [
        '* platform: ``%s``' % platform.platform(),
        '* python: ``%s``' % sys.version.split()[0],
        '* scratch directory: ``%s``' % display_path(workdir),
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='time rule resolution on synthetic version folders')
    parser.add_argument('--sizes', type=int, nargs='+', default=list(DEFAULT_SIZES),
                        help='file counts to measure (default: 1000 5000 20000)')
    parser.add_argument('--repeat', type=int, default=3,
                        help='runs per measurement (default: 3)')
    parser.add_argument('--workdir', default=DEFAULT_WORKDIR,
                        help='where to build the trees (default: <project>/build/benchmark)')
    parser.add_argument('--keep', action='store_true',
                        help='keep the largest tree on disk for inspection')
    parser.add_argument('--write-doc', action='store_true',
                        help='write the table into docs/benchmark.md')
    args = parser.parse_args(argv)

    workdir = os.path.abspath(args.workdir)
    os.makedirs(workdir, exist_ok=True)
    sys.stdout.write('workdir: %s\n' % workdir)

    rows = []
    for files in args.sizes:
        sys.stdout.write('measuring %d files ...\n' % files)
        sys.stdout.flush()
        rows.append(measure(files, args.repeat, workdir))

    table = render(rows)
    sys.stdout.write('\n' + table + '\n\n')

    if args.write_doc:
        doc = os.path.join(PROJECT_ROOT, 'docs', 'benchmark.md')
        text = [
            '# Benchmark',
            '',
            'Measured with ``python scripts/benchmark.py --write-doc`` on:',
            '',
        ] + environment_lines(workdir) + [
            '',
            '**cold** is a fresh ``Resolver`` per run (the default behaviour), **warm** '
            'is a ``Resolver(keep_cache=True)`` whose caches are dropped before every run '
            '(a real cache miss) and **cached** is the same resolver with the caches '
            'already filled. ``build_operations`` uses ``size_mode="none"``, so it measures '
            'the assembly only, not the file stat calls.',
            '',
            table,
            '',
            'Notes:',
            '',
            '* the numbers are storage bound -- a network share (NFS / SMB) is usually an '
            'order of magnitude slower, so re-run this on the storage you actually use '
            '(`--workdir` points the trees at another disk);',
            '* ``keep_cache=True`` pays off when the same tree is resolved again and '
            'again (a UI refreshing a version folder); call '
            '``Resolver.clear_cache()`` whenever the directories may have changed.',
            '',
        ]
        with open(doc, 'w', encoding='utf-8') as handle:
            handle.write('\n'.join(text))
        sys.stdout.write('written: %s\n' % doc)

    if args.keep:
        keep_dir = os.path.join(workdir, 'keep-%d' % max(args.sizes))
        shutil.rmtree(keep_dir, ignore_errors=True)
        created = build_tree(keep_dir, max(args.sizes))
        sys.stdout.write('kept %d files at: %s\n' % (created, keep_dir))
    elif os.path.isdir(workdir) and not os.listdir(workdir):
        # The trees are gone again, so drop the empty scratch directory too.
        os.rmdir(workdir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
