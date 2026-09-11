# sublevel-rules

**English** | [简体中文](README.zh-CN.md)

[![Python](https://img.shields.io/badge/python-3.7%20%7C%203.8%20%7C%203.9%20%7C%203.10%20%7C%203.11-blue.svg)](#compatibility-and-tests)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#features)
[![Tests](https://img.shields.io/badge/tests-330%20passed-brightgreen.svg)](#compatibility-and-tests)

> **Move "which resources live in a version folder, how they are imported and
> whether they are checked by default" out of code and into a declarative rule.**

`sublevel-rules` (import name `sublevel_rules`) is a **zero-dependency** Python
library: hand it a version folder and a rule and it scans the folder -- collapsing
frame sequences, applying mutual exclusion, deduplicating, deriving parent check
states -- then hands back hierarchical data a UI can consume directly.

```python
from sublevel_rules import Action, Group, Level, Resolver, Rule, build_operations

rules = Group(
    Action(['*_v{version_part}.ma', '*_v{version_part}.mb'],
           method='animation', mode='first', checked=2),
    Rule(Level('cache'), Level('v{version_part}'),
         Action('*.abc', method='animation', mode='multiple',
                is_sequence=True, checked=2)),
)

matches = Resolver().resolve(rules, '/show/asset/ani/v001', {'version_part': '001'})
operations = build_operations(matches, '/show/asset/ani/v001')
```

---

## What it buys you

| The old pain | With `sublevel-rules` |
| --- | --- |
| Every stage (mod / rig / ani / tex...) keeps its directory conventions inside importer code, so one more format means changing code | The conventions become **rule data**: change the rule, the import logic does not move |
| Frame sequences have to be collapsed by hand, missing frames counted, `%04d` assembled | Declare `is_sequence=True`; frame numbers, missing frames and the pattern all come back in the result |
| "Only one of abc and ma may be imported" turns into `if` statements | Declare a `mutex` group; the check states are derived automatically |
| Parent "partially checked" state has to be counted by hand | `build_operations()` returns `0` / `1` / `2` for you |
| Finding out what a version folder would import means opening the DCC | `sublevel-rules <version folder>` prints the tree in a second |
| Pulling third-party packages into a DCC environment fights the studio package manager | **Zero dependencies**, standard library only (`pathlib` / `fnmatch`) |
| Directory conventions end up scattered across importer code | Conventions live in **rule data**, so the import layer only needs a `method` name |

## Features

* **Zero third-party dependencies** -- pure standard library, safe to drop into a
  Maya / Nuke / Houdini Python environment;
* **Declarative rule DSL** -- `Level` / `Multi` / `Action` / `Rule` / `Group`
  express any hierarchy;
* **Frame-sequence collapsing** -- `%04d` / `####` / `$F4` placeholder styles with
  frame numbers and missing frames computed for you;
* **Mutex check state** -- at most one checked entry per `mutex` group, parent
  states derived from the children;
* **Side collection** -- gather branch resources while walking down (`collect`);
* **Grouping on demand** -- single-level parents / multi-level tree / no grouping;
* **Command line preview** -- `sublevel-rules` / `python -m sublevel_rules`, with
  `--describe` and `--json`;
* **Zero-dependency path layer** -- accepts `str` / `pathlib.Path` / `bytes` and
  any object implementing `__fspath__`;
* **Rules as configuration (optional)** -- rules convert losslessly between
  "Python objects <-> dict <-> YAML"; YAML support is a **removable** adapter file;
* **Stable public API** -- node classes, arguments and result fields are part of
  the contract;
* **Typed** -- the package ships a PEP 561 ``py.typed`` marker and full type
  annotations, checked by mypy in CI;

---

## Table of contents

- [What it buys you](#what-it-buys-you)
- [Quick start](#quick-start)
- [Installation](#installation)
- [Concept: what is a sub level](#concept-what-is-a-sub-level)
- [Rule syntax](#rule-syntax)
- [Resolution results: Match](#resolution-results-match)
- [Data assembly: build_operations](#data-assembly-build_operations)
- [Configuration files (optional YAML)](#configuration-files-optional-yaml)
- [Command line preview](#command-line-preview)
- [Using it from a pipeline module](#using-it-from-a-pipeline-module)
- [Defaults you may want to change](#defaults-you-may-want-to-change)
- [Compatibility and tests](#compatibility-and-tests)
- [FAQ](#faq)
- [Project layout and development](#project-layout-and-development)
- [License](#license)

---

## Quick start

### The 30 second version

```bash
# See what a version folder would import, using a built-in preset rule
sublevel-rules "/show/asset/mod/mdl/v001" --preset mod
```

```
root         : /show/asset/mod/mdl/v001
version_part : 001
matched      : 3

|-- [x] mdl_mod_v001.abc                       geo          12.40MB
|-- [ ] mdl_v001.ma                            geo          3.10MB
`-- [x] cache/v001/
    `-- [x] cache.%04d.abc                      geo          48.20MB     2 frames
```

### From code

```python
from sublevel_rules import Action, Group, Level, Resolver, Rule, build_operations

rules = Group(
    # 1) at the root of the version folder: ma / mb, take one, checked by default
    Action(['*_v{version_part}.ma', '*_v{version_part}.mb'],
           method='animation', mode='first', checked=2),
    # 2) camera files
    Action('*cam_v{version_part}.abc', method='animation', mode='first', checked=2),
    # 3) branch: cache/v001/*.abc, collapse the sequence, check everything
    Rule(
        Level('cache'),
        Level('v{version_part}'),
        Action('*.abc', method='animation', mode='multiple',
               is_sequence=True, checked=2),
    ),
)

version_data = {'version_part': '001', 'path': '/show/asset/ani/v001'}

matches = Resolver().resolve(rules, version_data['path'], version_data)
operations = build_operations(matches, version_data['path'], version_data)

for item in operations:
    print(item['filename'], item['filename_checked'])
    for child in item.get('children', []):
        print('  ', child['filename'], child['filename_checked'])
```

Every item in `operations` is either a file entry or a directory parent node with
`children`; the fields are described in
[Data assembly](#data-assembly-build_operations).

---

## Installation

```bash
pip install -e .                # development / local
pip install ".[test]"           # with the test dependencies (pytest)
pip install ".[yaml]"           # only needed to write rules in YAML (PyYAML)
```

> The core library has **zero dependencies**; `yaml` is an optional extra -- without
> it you only lose YAML rule support and everything else keeps working (the adapter
> file `yaml_rules.py` can simply be deleted).

You can also skip installing altogether and put `src` on `PYTHONPATH`:

```bash
PYTHONPATH=src python -c "import sublevel_rules; print(sublevel_rules.__version__)"
```

Behind a proxy or offline, use a mirror. If the environment has a system proxy that
pip picks up but cannot reach, clear it explicitly:

```bash
pip install -e ".[test]" \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn --proxy ""
```

---

## Concept: what is a sub level

One stage of an asset (a model, a rig, an animation) is published into a **version
folder**:

```
.../asset/mod/mdl/v001/
├── mdl_v001.abc                 # files at the version folder root
├── mdl_v001.ma
├── cache/
│   └── v001/
│       ├── abc.0001.abc         # more resources further down
│       └── abc.0002.abc
```

"Everything below the folder from which a uniform convention can still be derived
belongs to the **sub level**" -- below that point nothing is standardized and every
project and stage may differ. That structure does not belong in code, so it is
described by a **declarative rule**:

```python
Group(
    Action('*_v{version_part}.ma', method='animation', mode='first'),
    Rule(
        Level('cache'),
        Level('v{version_part}'),
        Action('*.abc', method='animation', mode='multiple', checked=2),
    ),
)
```

There are only four kinds of nodes:

| Node | Meaning |
| --- | --- |
| `Level` / `Multi` | an intermediate directory level (`Multi` = the `mode='multiple'` sugar) |
| `Action` | the files of the final level plus the import `method` |
| `Rule` | chains several levels into one complete rule; **must end with an `Action`** |
| `Group` | combines several `Rule` / `Action` nodes into a "branch set" |

Placeholders such as `{version_part}` are filled from the `version_data` the caller
passes in.

---

## Rule syntax

### Level / Multi

```python
Level('cache')                        # match a directory named cache, take the first
Level(['cache', 'cache_v2'])          # try several patterns in order
Level('v{version_part}')              # placeholders are allowed in patterns
Multi('v001', 'v002')                 # same as Level([...], mode='multiple')
Multi(['v001', 'v002'], collect=...)  # a list is accepted directly
```

* `mode='first'`: in pattern order, the first entry of the first matching pattern;
* `mode='multiple'`: collect every entry of every matching pattern;
* `mode='latest'`: take the newest match by **natural numeric order** (`v10` sorts
  after `v9`, while plain lexicographic order puts `'v10' < 'v9'`);
* `optional=True`: optional level -- when it does not exist, skip it and keep
  matching below;
* `require_content=True`: skip candidate directories that hold nothing for the next
  level;
* passing a `set` sorts it first, so `mode='first'` stays reproducible.

```python
# Take the newest cache version, and require that it actually has content
Rule(Level('cache'),
     Level('v*', mode='latest', require_content=True),
     Action('*.abc', method='ani', mode='multiple'))

# Support both cache/v001/x.abc and cache/x.abc layouts
Rule(Level('cache'), Level('v*', optional=True),
     Action('*.abc', method='ani'))
```

### Action

```python
Action('*.abc', method='geo')                       # the shortest form
Action(['*_v{version_part}.ma', '*_v{version_part}.mb'],
       method='geo', mode='first', checked=2, mutex='mod_file')
Action('*.exr', method='texture', is_sequence=True, frame_pattern='%')
Action('*.ma', method='geo', files_only=True)        # files only
```

| Argument | Meaning |
| --- | --- |
| `patterns` | file-name pattern(s), `str` or a sequence |
| `method` | import method name (required); the caller resolves it to the real import function |
| `mode` | `'first'` / `'multiple'` / `'latest'` |
| `is_sequence` | match frame sequences (collapse them first) |
| `checked` | default UI check state: `None` / `True` / `False` / `0` / `1` / `2` |
| `mutex` | mutex group ID |
| `collect` | side collector, see below |
| `files_only` | files only, ignore directories of the same name (default `False`) |
| other `**options` | inherited downwards and returned with the results |

### Rule

```python
Rule(
    Level('cache'),
    Level('v{version_part}'),
    Action('*.abc', method='animation', mode='multiple', checked=2),
)
```

The constraints are checked **at definition time**:

* at least one level;
* the last level must be an `Action`;
* an `Action` may only be the final level.

### Group

```python
Group(
    Action('*_v{version_part}.ma', method='animation'),            # bare Action
    Rule(Level('cache'), Level('v{version_part}'), Action(...)),   # full chain
    Group(Action('*.usd', method='geo')),                          # nested
)
```

A bare `Level` inside a `Group` raises immediately (the import method would be
undefined).

`Group(mode='first')` is a **fallback chain**: rules run in order and the first one
producing a non-empty result wins, the rest are skipped -- which expresses "the same
asset has two valid directory layouts depending on the project":

```python
Group(
    Action('*.abc', method='geo', checked=2),                      # layout A: at the root
    Rule(Level('cache'), Level('v*'),                              # layout B: inside cache
         Action('*.abc', method='geo', checked=2)),
    mode='first',
)
```

### options inheritance

`**options` are merged along `Group -> Rule -> Level -> Action`, **child nodes
overriding their parents**:

```python
rules = Group(
    Action('*.exr', method='texture'),
    tag='beauty',                 # inherited by every child node
)
matches = Resolver().resolve(rules, root)
matches[0].options['tag']         # 'beauty'
```

Options the library itself reads:

| option | Effect |
| --- | --- |
| `frame_pattern` | frame placeholder style (`'%'` / `'#'` / `'$'`); any level may override it |
| `mutex` | mutex group ID; may be declared once on `Group` / `Rule` / `Level` |

### check state `checked`

`checked` accepts `None` / `True` / `False` / `0` / `1` / `2` and is normalized by
`to_check_state()` into Qt semantics (`0` unchecked, `1` partially checked,
`2` checked):

```python
from sublevel_rules import to_check_state

to_check_state(None)    # 0
to_check_state(True)    # 2
to_check_state(1)       # 1
```

### mutex

At most one entry per `mutex` group stays checked:

```python
Group(
    Action('*mod_v{version_part}.abc', method='geo', checked=2, mutex='mod_file'),
    Action('*_v{version_part}.ma',     method='geo', checked=2, mutex='mod_file'),
)
```

Rules: the first already-checked entry of the group is kept, the rest are forced to
`0`; when nothing in the group is checked, the first match is checked automatically
(`Resolver(auto_select_first=False)` turns that off).

The mutex may be written on an `Action`, or once on a `Group` / `Rule` / `Level` for
everything below it.

### frame sequences

```python
Action('*.exr', method='texture', is_sequence=True, frame_pattern='%')
```

With `is_sequence=True`, `abc.0001.exr` and `abc.0002.exr` collapse into one
`abc.%04d.exr`; frame numbers land in `Match.frames` and missing ones in
`Match.missing`. Single-frame media (`.mov` / `.mp4` / `.avi` / `.r3d` / `.nk` /
`.ren`) never collapse.

```python
from sublevel_rules import frame_path

frame_path('abc.%04d.exr', 7)     # abc.0007.exr
```

### side collection `collect`

Gather branch resources while walking down:

```python
Rule(
    Level('tex', collect=Action('*.txt', method='readme')),
    Multi('v{version_part}', '*'),
    Action(['*.exr', '*.tx'], method='texture', mode='multiple'),
)
```

`collect_scope` decides where the collection happens:

| Value | Meaning |
| --- | --- |
| `'children'` (default) | inside every subdirectory matched at this level (in the example: the `*.txt` inside `tex`) |
| `'parent'` | inside the directory this level lives in |

### skipping noisy entries

`Resolver(exclude_patterns=...)` skips unwanted names while listing directories
(`.git`, `__pycache__`, backup files...) instead of writing negative patterns into the
rules:

```python
resolver = Resolver(exclude_patterns=('.git', '__pycache__', '*.bak', 'Thumbs.db'))
```

Matching follows the same case rules as the rules themselves (case insensitive by
default) and applies to plain files as well as to collapsed sequences.

### Resolver options at a glance

| Argument | Default | Effect |
| --- | --- | --- |
| `frame_pattern` | `'%'` | frame placeholder style, overridable per `Action(options={'frame_pattern': ...})` |
| `case_sensitive` | `False` | whether file-name matching is case sensitive |
| `dedupe` | `True` | deduplicate by `(path, method)` |
| `auto_select_first` | `True` | check the first entry of a mutex group when nothing in it is checked |
| `strict_format` | `True` | raise `RuleFormatError` on a missing placeholder (when `version_data` is empty the pattern is kept as is and a warning is logged) |
| `single_media_exts` | built in | single-frame media suffixes (never collapsed); pass an empty collection to drop the restriction |
| `exclude_patterns` | `None` | names to skip while listing directories |
| `logger` | package logger | custom logger |

> A `Resolver` instance carries a resolution cache (one directory is listed once per
> resolution), so do not share one instance between threads.

---

## Configuration files (optional YAML)

Rules are **pure data**, so the core offers a format-agnostic conversion:
`rule_to_dict()` <-> `rule_from_dict()`. YAML is a thin shell on top of it, kept in a
single file (`yaml_rules.py`) that can be removed as a whole.

```bash
pip install "sublevel-rules[yaml]"                  # optional dependency; the core stays dependency free

sublevel-rules ./v001 --rules rules.yaml            # the whole file is one rule
sublevel-rules ./v001 --rules rules.yaml:mod        # several rules per file, selected by name
```

```yaml
# rules.yaml
type: group
mode: first
rules:
  - type: action
    patterns: ["*_v{version_part}.ma"]
    method: animation
    checked: 2
  - type: rule
    levels:
      - type: level
        patterns: ["cache"]
      - type: level
        patterns: ["v*"]
        mode: latest              # take the newest version
        require_content: true     # and require that it has content
      - type: action
        patterns: ["*.abc"]
        method: animation
        mode: multiple
        is_sequence: true
```

From code:

```python
from sublevel_rules.rule_dict import rule_from_dict
from sublevel_rules.yaml_rules import dump_rules, load_rules

rules = load_rules('rules.yaml', name='mod')     # or yaml.safe_load it yourself and use rule_from_dict
```

* **Dropping YAML completely**: delete `yaml_rules.py` plus the `yaml` extra in
  `setup.cfg` -- the CLI discovers adapters by looking for `*_rules.py` in the
  package, so no other file changes;
* a wrong structure **fails immediately and points at the location** (for example
  `root.rules[0]: 不认识的键：cheked`); nothing is ignored silently;
* `dump_rules(rule)` / `rule_to_dict(rule)` export existing Python rules as a YAML
  template.

---

## Resolution results: Match

`Resolver.resolve()` returns a list of `Match`. A `Match` also unpacks like a
`(sequence, method, action)` three-tuple:

```python
for sequence, method, action in matches:      # existing code keeps working
    ...

for match in matches:
    match.name          # file name (the pattern name for a sequence)
    match.path          # pathlib.Path
    match.method        # import method
    match.state         # normalized check state 0 / 1 / 2
    match.frames        # frame numbers of the sequence
    match.missing       # missing frame numbers
    match.is_sequence   # whether this is a collapsed sequence
    match.frame_pattern # placeholder style used for this entry ('%' / '#' / '$')
    match.options       # merged, inherited options
    match.action        # the Action that produced this match (read-only)
    match.mutex         # mutex group ID (Action first, then inherited options)
    match.depth         # index of the level that matched (0 = rule starting point)
    match.to_dict()     # plain dict for logging / JSON
```

`resolve()` / `resolve_smart_rule()` / `Resolver.resolve()` also accept
`inherited_options=...`: parameters inherited from above, merged with the rule's own
`options` (in the order `Group -> Rule -> Level -> Action`, children overriding
parents).

To debug a rule itself (without scanning anything), print the rule tree:

```python
from sublevel_rules import describe_rule

print(describe_rule(rules))
# Group(mode='all', options={})
#   Action(patterns=['*.ma'], method='geo', mode='first', checked=2, is_sequence=False, files_only=False, mutex=None)
#   Rule(options={})
#     Level(patterns=['cache'], mode='first')
#     Level(patterns=['v001'], mode='first')
#     Action(patterns=['*.abc'], method='ani', mode='multiple', checked=None, is_sequence=False, files_only=False, mutex=None)
```

---

## Data assembly: build_operations

```python
from sublevel_rules import build_operations, human_size

operations = build_operations(
    matches,
    version_root='/show/asset/ani/v001',
    version_data=version_data,
    op_resolver=lambda method: pipeline.create_api_version(method),  # optional
    size_formatter=human_size,       # optional: byte count -> display string
    size_mode='first',               # 'first' / 'total' / 'none'
    group_mode='flat',               # 'flat' (default) / 'nested' / None
    skip_without_op=False,           # skip entries without an operation function
    extra_fields={'tag': 'beauty'},  # optional: dict or callable(match, asset)
)
```

File entry fields (the first 10 form the stable compatibility set):

| Field | Meaning |
| --- | --- |
| `filename_checked` | check state `0` / `1` / `2` |
| `op_func` | the value returned by `op_resolver(method)` |
| `args` | `(sequence, version_data)`, ready to be forwarded to the operation function |
| `file_stem` | path without the extension (`pathlib.Path`) |
| `path_name` | full path string |
| `filename` | file name relative to the version folder |
| `orm` | `version_data` |
| `size` | human readable size string |
| `type` | extension (with the dot) |
| `options` | reserved field, always `None` |
| `sequence` / `method` / `frames` / `missing` / `is_sequence` / `relative_path` | added for UI display and debugging |

Parent node fields: `filename` (relative directory path), `filename_checked`,
`children`. The parent state is derived from the children: all checked -> `2`, none
checked -> `0`, anything else -> `1`.

`group_mode`:

* `'flat'` (default): one single-level parent node per full directory name;
* `'nested'`: a multi-level tree following the directory hierarchy;
* `None`: no grouping, everything stays flat.

---

## Command line preview

```bash
sublevel-rules <version folder> [--preset ani|mod|rig|tex] [--rules module:attr] [--json]
python -m sublevel_rules <version folder> --preset mod

# print the rule tree only, without scanning (version_path may be omitted)
sublevel-rules --preset ani --describe

# skip noisy directories
sublevel-rules <version folder> --preset ani --exclude .git --exclude __pycache__
```

For example:

```bash
$ python -m sublevel_rules ./v001 --preset ani --version-part 001
root         : ./v001
version_part : 001
matched      : 3

|-- [ ] abc_v001.ma                            animation    0.00MB
|-- [x] abc_cam_v001.abc                       animation    0.00MB
`-- [x] cache/v001/
    `-- [x] abc.%04d.abc                        animation    0.00MB      2 frames
```

`--rules` accepts three spellings:

```bash
--rules mypipeline.rules:get_import_rules      # an installed module
--rules ./project_rules.py:get_import_rules    # a standalone file
--rules ./project_rules.py                     # attr defaults to get_import_rules
```

When hunting "why did nothing match", add `-v` for DEBUG logging (it reports which
level and which pattern missed).

---

## Using it from a pipeline module

A pipeline module drives the library in one call:

```python
from sublevel_rules import get_sub_level_op

asset_operations = get_sub_level_op(pipeline_module, version_data)
```

`pipeline_module` has to provide `get_import_rules()` (returning the rule tree) and
`create_api_version(method)` (returning the operation function for that method);
when either is missing an empty list is returned. The result fields are stable, so
the UI side (tree, check states, double click to import) needs nothing else, and
errors are all catchable through `sublevel_rules.errors`.

## Defaults you may want to change

Every default below is a deliberate choice; these are the six most likely to be
worth revisiting for a given pipeline:

| Item | Default | How to change it |
| --- | --- | --- |
| file-name matching | case insensitive on every platform | `Resolver(case_sensitive=True)` |
| empty mutex group | the first entry is checked automatically | `Resolver(auto_select_first=False)` |
| result deduplication | by `(path, method)` | `Resolver(dedupe=False)` |
| side collection `collect` | inside the directories matched by the level | `Level(..., collect_scope='parent')` |
| `options` of a middle `Level` | inherited along the chain | omit them there, or set them on the `Action` only |
| `mutex` on `Level` / `Multi` | effective (one checked entry per group) | declare it on the `Action` instead |

---

## Compatibility and tests

| Python | How it is covered | Cases |
| --- | --- | --- |
| 3.7.7 | local runs + CI matrix (Linux / Windows / macOS) | 330 |
| 3.8 | CI matrix (`.github/workflows/tests.yml`) | 330 |
| 3.9.7 | local runs + CI matrix | 330 |
| 3.10 | CI matrix | 330 |
| 3.11.8 | local runs + CI matrix | 330 |

The code only uses syntax and standard library features available since Python 3.7;
there are no version branches.

The same suite runs in two ways (CI runs both):

```bash
# unittest (works without any dependency installed; recommended offline)
python scripts/run_tests.py

# every .venv-* environment of the project (bash)
bash scripts/run_tests.sh

# pytest (after installing the test extra)
python -m pytest tests -q
```

The `330` cases = `321` tests under `tests/` plus the `9` docstring examples that
`scripts/run_tests.py` runs as doctests (a bare `pytest tests` collects the 321).

What the tests cover:

| Module | Coverage |
| --- | --- |
| `tests/test_paths.py` | `Entry` / `as_path` / `split_frame` / `list_entries` |
| `tests/test_sequences.py` | sequence collapsing, missing frames, single-frame media, placeholder styles |
| `tests/test_frames.py` | `frame_path` / `frame_tokens` |
| `tests/test_rules.py` | DSL definition-time validation, `to_check_state` |
| `tests/test_resolver.py` | first/multiple, directory chains, `collect`, `mutex`, dedupe, sequence matching, option inheritance, exceptions |
| `tests/test_operations.py` | `build_operations` fields / grouping / parent state, the `get_sub_level_op` compatibility entry |
| `tests/test_presets.py` | the four built-in presets on real directory trees |
| `tests/test_cli.py` | argument parsing, tree rendering, rule loading, text/JSON output, error handling |
| `tests/test_improvements.py` | regressions for the fixes made after the code review (double collapsing, set ordering, `%4d`, `files_only`, `exclude_patterns`, `--describe`...) |
| `tests/test_expressiveness.py` | fallback chain `Group(mode='first')`, `mode='latest'`, `optional`, `require_content`, `Entry` after the scandir change |
| `tests/test_rule_dict.py` | rule <-> dict round-trips, structure errors carrying their location |
| `tests/test_yaml_rules.py` | the YAML adapter and its CLI integration (the whole group is skipped without PyYAML), adapter discovery |
| `tests/test_combinations.py` | semantics **combined**: `mode x optional x require_content`, `collect x collect_scope`, `Group(mode='first')` x mutex/nesting, `size_mode x grouping`, `rule_dict` round-trips |
| `tests/test_edge_branches.py` | error and defensive branches: deleted frame files, adapter import failure, cache hits, case sensitivity, `collect` on the last level |
| docstring examples (doctest) | every `>>>` example in the package docstrings is executed by `scripts/run_tests.py` -- a wrong example turns the suite red |

---

## FAQ

**Q: Why is the distribution called `sublevel-rules` while the import is `sublevel_rules`?**
Python packaging convention: hyphens in the distribution name, underscores for the
import name (like `scikit-learn` -> `import sklearn`). Under PEP 503 the two are
equivalent for pip.

**Q: Nothing matched -- how do I debug that?**
Start with `sublevel-rules <folder> --describe` to see the rule, then add `-v` for
DEBUG logging (it reports which level and which pattern missed in which directory),
and finally double check `version_part` (the CLI reads the digits after `v` from the
folder name; `--version-part` overrides it).

**Q: My project file `mdl_v001.ma` got collapsed into a sequence?**
Only an `Action` with `is_sequence=True` collapses anything. Taking a version number
for a frame number is the classic sequence trap: do not turn that switch on for files
that exist once per version instead of once per frame.

**Q: Can it run inside Maya / Nuke / Houdini?**
Yes. Zero third-party dependencies, pure standard library; put `src` on `sys.path`
and it works.

**Q: Why is matching case insensitive by default?**
For consistent behaviour across platforms: `fnmatch` is insensitive on Windows but
sensitive on Linux, which causes the classic "fine locally, broken on the farm". Use
`Resolver(case_sensitive=True)` for strict matching.

**Q: Directories show up as file entries -- is that a bug?**
Directories are matched as well -- that is how `fnmatch` behaves. Use `Action(..., files_only=True)` to match files only.

**Q: Can rules be written in YAML (or another config format)?**
Yes. Rules are **pure data**, the core offers lossless `rule_to_dict()` /
`rule_from_dict()` conversion, and YAML reading/writing is a **removable adapter**
(`yaml_rules.py`):

```bash
pip install "sublevel-rules[yaml]"
sublevel-rules ./v001 --rules rules.yaml        # the file is one rule
sublevel-rules ./v001 --rules rules.yaml:mod    # several rules per file
```

To drop YAML support, delete `yaml_rules.py` (and the extra line in `setup.cfg`) --
`cli.py` discovers adapters by looking for `*_rules.py` in the package, and nothing
else changes. `rule_to_dict()` exports existing Python rules as a YAML template for
people who prefer not to write code.

**Q: Some directory structure cannot be expressed -- what now?**
Read [docs/limitations.md](docs/limitations.md) first: it lists the capabilities that
are **deliberately not implemented** (recursive `**`, UI logical grouping, Action
level excludes, `min_frames`, logic inside rules) together with the workaround for
each.

---

## Project layout and development

```
sublevel-rules/
├── README.md              English README (this file)
├── README.zh-CN.md        中文说明
├── docs/
│   ├── limitations.md     capabilities deliberately not implemented (English)
│   └── limitations.zh-CN.md  known limits (Chinese)
├── src/sublevel_rules/
│   ├── __init__.py        public API
│   ├── const.py           constants (single-frame media suffixes, check states...)
│   ├── errors.py          exceptions (all deriving from SubLevelRulesError)
│   ├── paths.py           zero-dependency path layer (Entry / as_path / list_entries)
│   ├── sequences.py       frame-sequence scanning and collapsing
│   ├── frames.py          pattern <-> concrete frame path
│   ├── rules.py           the rule DSL
│   ├── resolver.py        the resolution engine (Resolver / Match)
│   ├── operations.py      UI data assembly (build_operations / get_sub_level_op)
│   ├── rule_dict.py       rule <-> dict conversion (format agnostic)
│   ├── yaml_rules.py      YAML adapter (removable: delete it to drop the format)
│   ├── presets.py         built-in preset rules
│   ├── cli.py             command line preview (discovers *_rules.py adapters)
│   └── __main__.py        python -m sublevel_rules
├── tests/                 unit tests (unittest, pytest compatible)
├── examples/              example rules and API usage, both runnable
├── scripts/
│   ├── run_tests.py       cross-platform test entry point
│   └── run_tests.sh       run the tests in every .venv-* environment (bash)
└── .github/workflows/     CI (Python 3.7 ~ 3.11 matrix)
```

### Local development environment

```bash
python -m venv .venv-3.7        # or: C:/Python37/python.exe -m venv .venv-3.7
python -m venv .venv-3.9
python -m venv .venv-3.11
```

### Development commands

```bash
python scripts/run_tests.py          # every test + the docstring doctests, no dependency needed
bash scripts/run_tests.sh            # all .venv-* environments at once (POSIX shell)
python -m pytest tests -q            # after pip install ".[test]"
python -m flake8 src tests           # config lives in the [flake8] section of setup.cfg
python -m coverage run --branch --source=src/sublevel_rules scripts/run_tests.py
python -m coverage report -m
python -m mypy                        # type check (configuration in setup.cfg)
python scripts/benchmark.py           # resolution timings, see docs/benchmark.md
python -m sublevel_rules <version> --preset mod -v      # CLI preview
```

Data flow: `rule tree + version folder` -> `Resolver.resolve()` -> `[Match...]` ->
`build_operations()` -> the hierarchical dict a UI consumes.

### Contribution rules

* **Changing behaviour means updating the tests**: single features go into the matching
  `tests/test_*.py`; semantic **combinations** into `tests/test_combinations.py`;
  error / defensive branches into `tests/test_edge_branches.py`.
* **Changing behaviour or adding a capability means updating `CHANGELOG.md`**, together
  with the test numbers in both READMEs (badge + compatibility table).
* Docstring examples containing `>>>` are executed as **doctests** by
  `scripts/run_tests.py` -- they have to match the real output.
* Keep the language pairs in sync: `README.md` / `README.zh-CN.md` and
  `docs/limitations.md` / `docs/limitations.zh-CN.md`.
* Stay **zero-dependency**: the core library uses the standard library only; optional
  capabilities become extras (such as `[yaml]`).
* 4-space indentation, lines at most 100 characters (`.editorconfig` fixes UTF-8 / LF).
* Docstrings and comments are written in English; runtime messages (exception texts,
  log lines, CLI output) stay Chinese, because the UI consuming this library is
  Chinese. Every public function carries a docstring describing its arguments.
* Never put non-ASCII characters into `setup.cfg`: the older setuptools shipped with
  Python 3.7 / 3.9 raises `UnicodeDecodeError` while parsing it in a GBK environment.

### Gotchas when editing the code

* `collect_scope`: `children` (default) collects inside the directories **matched** by
  the level, `parent` collects inside the directory the level **lives in**.
* `human_size()` defaults to MB, so `human_size(1024)` is `'0.00MB'`.
* `mode='first'` is lexicographic, so `v10` comes before `v9` -- use `mode='latest'` to
  get the newest.
* `options` accumulate level by level (`Group -> Rule -> Level -> Action`, children
  overriding parents), so a `tag` / `frame_pattern` / `mutex` written on a middle
  `Level` is passed down -- do not put it there if it should only affect one level.
* `Entry.size()` always stats again (the `os.scandir` value is only a snapshot, and on
  Windows it is the one taken while listing); `is_file()` / `is_dir()` keep using the
  cache -- the file type does not change, the size does.
* A `Resolver` instance carries a resolution cache -- do not share one between
  threads. With `keep_cache=True` it survives between `resolve()` calls (much
  cheaper for a UI refreshing one folder); call `Resolver.clear_cache()` when the
  directories may have changed.
* On Windows, `Level(Path(...))` yields `a\b`; mind path separators when writing tests.
* `yaml_rules.py` is removable: the CLI discovers adapters by scanning the package for
  `*_rules.py`, so adding or dropping one needs no change anywhere else.

---

## License

[MIT](LICENSE)
