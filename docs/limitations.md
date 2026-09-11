# Known limits (capabilities deliberately not implemented)

**English** | [简体中文](limitations.zh-CN.md)

The goal of `sublevel-rules` is to **describe the structure of "which resources live
below a version folder" clearly**, not to be a Turing-complete rule language. The
items below are **explicitly out of scope** -- written down so nobody has to probe
for them again, and so the rule semantics stay at a complexity you can grasp at a
glance.

The test is simple: **every new semantic adds one dimension to the state space of
`_walk`**, and the number of combinations the tests have to cover multiplies.
Extensions you actually need are worth adding; "we might need it later" extensions
only become burdens you cannot delete later.

---

## 1. Recursive intermediate levels (`**`)

**What you would want**: ignore the depth and match `cache/**/abc.abc` directly.

**Why not**:

* directory depth in a pipeline is essentially always fixed; genuine "any depth"
  cases are rare;
* allowing recursion means handling **symlink cycles**, extremely deep directories
  and an uncontrollable traversal volume on NFS;
* a `Rule` is a linear chain today, so the depth is **visible** in the rule, which is
  very valuable when debugging (`--describe` tells you instantly how deep it goes).

**What to do instead**: write out the real depth; if a directory really is of
variable depth, collect along the way with `Level(..., collect=Action(...))` on every
level, or walk it yourself in the caller.

---

## 2. UI logical grouping (not directory grouping)

**What you would want**: files from one directory shown in the UI grouped as
"textures / geometry / cache".

**Why not**: it is a pure UI concern, and demands differ a lot between DCCs and
project groups -- implementing it now means guessing an interface for the caller.
Rules only answer "which resources exist and how they are imported"; how the display
layer organises them is up to the display layer.

**What to do instead**: the entries returned by `build_operations()` carry `method` /
`type` / `relative_path` and friends, so the UI can group them by any dimension; you
can also attach a custom option to an `Action` (for example `ui_group='textures'`),
which is returned with the results (`Match.options`) for the UI to read.

---

## 3. Action level exclude lists

**What you would want**: `Action('*.exr', exclude='*_tmp*.exr')`.

**Why not**: `Resolver(exclude_patterns=...)` already covers the vast majority of
cases (skipping `.git`, `__pycache__`, backup files), and an exclude that applies to
one single Action can be expressed with a **more precise positive pattern**, which
reads more clearly:

```python
Action(['*_beauty.exr', '*_diffuse.exr'], method='texture')   # clearer than a blacklist
```

**What to do instead**: write positive patterns, or use the global
`exclude_patterns`.

---

## 4. Minimum frame count for a sequence (`min_frames`)

**What you would want**: only sequences with >= 2 frames count as sequences, a single
frame file counts as a plain file.

**Why not**: **a single frame sequence is still a sequence** -- a brand new shot, a
test render with one frame, are sequences by nature (`abc.%04d.exr` with
`frames=[1001]`). Downgrading them to plain files misleads everything downstream (the
information "this is part of a sequence" is lost).

**What to do instead**: when you need to distinguish, look at the length of
`Match.frames`:

```python
for match in matches:
    if match.is_sequence and len(match.frames) < 2:
        ...    # single frame sequence, handle it per your downstream convention
```

---

## 5. Rules that need functions / conditional expressions

**What you would want**: `if`, regular expressions, custom comparisons inside rules.

**Why not**: as soon as rules can hold logic they degrade into "Python written in
YAML" -- without Python's completion and debugging, and having given up everything
that made "rules are data" valuable.

**What to do instead**:

* rules still contain **nothing** that needs a function -- only strings / booleans /
  numbers -- which is exactly why `rule_from_dict()` can convert between dict and rule
  objects losslessly;
* when custom matching logic is genuinely needed, use a **named extension point**
  rather than stuffing expressions in: implement it on the Python side and wrap the
  `Resolver` (resolve by rule first, then filter the results per your business rules),
  which is far easier to maintain than logic hidden in configuration.

---

## 6. Frame-number detection is deliberately simple

A frame number is whatever the **last run of digits** in the file name says
(`paths.split_frame()`); there is no further guard. So `mdl_v001.ma` reports
`frame = 1`, and a single digit such as `abc.1.exr` reports `frame = 1` as well. This
is only observable for an `Action(..., is_sequence=True)`: such a file would be
collapsed into `mdl_v%03d.ma`.

**Why it is left like that**: a stricter rule (for example "at least two digits, not
preceded by `v` / `V`") would silently stop collapsing sequences that a pipeline may
legitimately have. The sequence switch is explicit anyway -- `is_sequence=True` is
opt-in per `Action`, so nothing collapses unless a rule asks for it.

**What to do instead**: do not switch `is_sequence=True` on for files that exist once
per version (project files). If a stricter frame-number rule is ever needed, it is a
targeted change to `split_frame()` plus tests.

---

## 7. `require_content` only probes one level down

`Level(..., require_content=True)` looks **one level** into a candidate directory: that
is enough to drop completely empty candidates without walking whole subtrees (the
listing cache means repeated probes cost no extra IO). When the next level *does* match
something, the candidate is accepted even if the level below *that* is empty -- the
branch then simply yields nothing.

**Why it is left alone**: probing deeper would mean walking subtrees that the rule may
never visit, which is exactly the cost the flag exists to avoid.

**What to do instead**: declare `require_content=True` on the next level as well when
you need to check two levels, or add an `optional` level plus a fallback branch so a
dead end still produces something.

---

## 8. Entry order when the case is mixed

`list_entries()` sorts by `entry.name` with a plain **case sensitive** string
comparison, while name matching itself is case insensitive by default. When one
directory mixes cases, for example `B.ma` and `a.ma`, the order is therefore plain
ASCII order (`B.ma` first), which may not be what a human expects.

**Why it is left like that**: it only shows up when a single directory mixes cases,
`mode='latest'` (natural numeric order) is unaffected, and any other rule would simply
be a different surprise.

**What to do instead**: if order matters, make it explicit -- use `mode='latest'`,
write an exact pattern, or sort the results yourself after resolution.

---

## See also

* the "path selection" semantics already supported are documented in the
  [README rule syntax](../README.md#rule-syntax): `Level.mode` (`first` /
  `multiple` / `latest`), the `Group(mode='first')` fallback chain, the `optional`
  level and `require_content` skipping empty directories;
* the defaults that are most likely worth revisiting are listed in the README section
  "Defaults you may want to change";
* to see what a version folder would actually import:
  `sublevel-rules <version folder> -v`.
