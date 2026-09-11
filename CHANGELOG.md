# Changelog

Version numbers follow [Semantic Versioning](https://semver.org/).

## 0.1.0

First release of `sublevel-rules`: a zero-dependency rule engine that turns a
version folder into the list of importable resources (the *sub level*) a pipeline
UI can consume.

Naming: the release / repository name is ``sublevel-rules``, the import name is
``sublevel_rules``.

### Added

* Rule DSL: `Level` / `Multi` / `Action` / `Rule` / `Group`.
* Resolver `Resolver` and result object `Match` (which also unpacks like the
  `(sequence, method, action)` three-tuple).
* Data assembly `build_operations()` with `group_mode='flat' / 'nested' / None`.
* Pipeline entry point `get_sub_level_op(pipeline_module, version_data)`.
* Zero-dependency path layer `Entry` (accepts `str` / `pathlib.Path` / `bytes` /
  any object implementing `__fspath__`).
* Command line preview `sublevel-rules <version folder>` / `python -m sublevel_rules`.
* Preset rules `mod_rules()` / `rig_rules()` / `tex_rules()` / `ani_rules()`.
* Path-selection semantics:

  * `Group(mode='first')` -- **fallback chain**: the first branch producing a
    non-empty result wins, for "the same asset has two valid directory layouts
    depending on the project";
  * `Level(..., mode='latest')` -- take the newest by **natural numeric order**
    (`v10` > `v9`);
  * `Level(..., optional=True)` -- optional level: skip it when it does not exist and
    keep matching below;
  * `Level(..., require_content=True)` -- skip candidate directories where the next
    level would match nothing.
* `rule_dict.py`: lossless conversion between rules and nested dicts
  (`rule_to_dict()` / `rule_from_dict()`); a wrong structure points at its location
  instead of being ignored silently.
* `yaml_rules.py`: the YAML adapter, **removable** -- deleting that file drops YAML
  support without touching any other file (the CLI discovers adapters by looking for
  `*_rules.py` in the package); plus the optional extra
  `pip install "sublevel-rules[yaml]"`.
* `docs/limitations.md`: the capabilities that are **deliberately not implemented**
  (recursive `**`, UI logical grouping, Action level excludes, `min_frames`, logic
  inside rules) together with the workaround for each.
* `list_entries()` uses `os.scandir()`: `Entry` reuses what the system already knows
  from listing the directory instead of issuing one `stat` per entry (a very visible
  difference on network storage).
* 330 unit tests (written with `unittest`, compatible with `pytest`), including
  docstring examples (doctests); two groups are dedicated: `tests/test_combinations.py`
  (semantic combinations) and `tests/test_edge_branches.py` (error / defensive
  branches). Branch coverage **99%**.
* `Resolver(exclude_patterns=...)`: skip noisy names such as `.git` / `__pycache__`
  while listing directories.
* `Action(files_only=True)`: match files only, no longer treating a directory of the
  same name as an entry.
* `describe_rule()` and the CLI `--describe`: print the rule tree in a human readable
  form for debugging rules.
* `Match.to_dict()`: convert a match into a plain dict for logging / serialization.
* CLI `--exclude`: skip the given names on the command line.
* A `NullHandler` is injected into the package, so callers that do not configure
  logging see no noise.
* English docstrings and comments throughout the code; runtime messages (exception
  texts, logs, CLI output) stay Chinese; `README.md` is English with a Chinese
  translation in `README.zh-CN.md`, and the same for `docs/limitations.*`.
* Type annotations across the whole package plus a PEP 561 `py.typed` marker, so type
  checkers understand the public API (the mypy configuration lives in `setup.cfg`).
* `Resolver(keep_cache=True)` with `clear_cache()` / `cache_info()`: the directory and
  sequence caches can be kept across `resolve()` calls, which makes refreshing the
  same version folder in a UI far cheaper (numbers in `docs/benchmark.md`).
* `scripts/benchmark.py` and `docs/benchmark.md`: resolution timings on synthetic
  version folders of 1k / 5k / 20k files, for a cold, a warm and a cached resolver.
* CI (`.github/workflows/tests.yml`): the test matrix covers Linux, Windows and macOS;
  a `lint and types` job runs flake8 and mypy; a `build` job builds the sdist/wheel,
  checks the metadata and uploads to PyPI only when a release is published and a
  `PYPI_API_TOKEN` secret is configured.

### Design decisions (the defaults worth knowing about)

* File-name matching is **case insensitive** by default, so behaviour does not
  depend on the platform; `Resolver(case_sensitive=True)` turns on strict matching.
* When nothing in a mutex group is explicitly checked, the first match is **checked
  automatically**; `Resolver(auto_select_first=False)` disables that.
* Results are deduplicated by `(path, method)` by default, so a file matched by
  several rules keeps only its first match; `Resolver(dedupe=False)` disables that.
* A resolution result is a `Match` object rather than a bare three-tuple: it still
  unpacks as `(sequence, method, action)` and its `action` field points at the
  `Action` that produced it.
* Side collection (`Level(collect=...)`) defaults to `collect_scope='children'`
  (inside the directories matched by that level); `'parent'` collects in the
  directory the level itself lives in.
* `options` are merged along `Group -> Rule -> Level -> Action`, children
  overriding parents, so a parameter can be declared once near the top.
* Frame-number detection takes the **last run of digits** in the name; only an
  `Action(is_sequence=True)` collapses anything (see `docs/limitations.md` §6 for
  what this means for versioned file names).

### Not covered

* Python 3.8 / 3.10 are not verified locally (the development machine only has
  3.7.7 / 3.9.7 / 3.11.8); the code uses no version specific features, only syntax
  and standard library available since Python 3.7.
