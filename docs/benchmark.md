# Benchmark

Measured with ``python scripts/benchmark.py --write-doc`` on:

* platform: ``Windows-10-10.0.19044-SP0``
* python: ``3.11.8``
* scratch directory: ``build/benchmark``

**cold** is a fresh ``Resolver`` per run (the default behaviour), **warm** is a ``Resolver(keep_cache=True)`` whose caches are dropped before every run (a real cache miss) and **cached** is the same resolver with the caches already filled. ``build_operations`` uses ``size_mode="none"``, so it measures the assembly only, not the file stat calls.

| files | matches | resolve, cold (ms) | per file (us) | resolve, warm (ms) | resolve, cached (ms) | build_operations (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| 1000 | 3 | 19.3 | 19.3 | 19.1 | 1.2 | 0.1 |
| 5000 | 3 | 98.5 | 19.7 | 122.4 | 5.4 | 0.1 |
| 20000 | 3 | 383.7 | 19.2 | 416.5 | 20.3 | 0.1 |

Notes:

* the numbers are storage bound -- a network share (NFS / SMB) is usually an order of magnitude slower, so re-run this on the storage you actually use (`--workdir` points the trees at another disk);
* ``keep_cache=True`` pays off when the same tree is resolved again and again (a UI refreshing a version folder); call ``Resolver.clear_cache()`` whenever the directories may have changed.
