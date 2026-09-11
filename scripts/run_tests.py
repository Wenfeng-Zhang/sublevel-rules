# -*- coding: utf-8 -*-
"""Cross-platform test entry point: puts ``src`` and the project root on
``sys.path`` and runs every test.

Usage::

    python scripts/run_tests.py

Combine it with the different virtual environments to verify several Python
versions::

    .venv-3.7/Scripts/python.exe  scripts/run_tests.py
    .venv-3.9/Scripts/python.exe  scripts/run_tests.py
    .venv-3.11/Scripts/python.exe scripts/run_tests.py

With pytest installed, ``python -m pytest tests`` works as well (the tests are
written with unittest and stay compatible).
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _doctest_suite():
    """Run the examples in the package docstrings as tests too -- so a wrong
    example cannot slip through unnoticed."""
    import doctest
    import importlib
    import pkgutil

    import sublevel_rules

    suite = unittest.TestSuite()
    for info in pkgutil.iter_modules(sublevel_rules.__path__):
        if info.name.startswith('_'):
            continue
        module = importlib.import_module('sublevel_rules.' + info.name)
        try:
            suite.addTest(doctest.DocTestSuite(module))
        except ValueError:
            continue          # this module has no doctest
    return suite


def main():
    for path in (os.path.join(ROOT, 'src'), ROOT):
        if path not in sys.path:
            sys.path.insert(0, path)

    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(ROOT, 'tests'), top_level_dir=ROOT)
    suite.addTest(_doctest_suite())
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
