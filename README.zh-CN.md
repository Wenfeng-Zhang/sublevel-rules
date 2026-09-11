# sublevel-rules

[English](README.md) | **简体中文**

[![Python](https://img.shields.io/badge/python-3.7%20%7C%203.8%20%7C%203.9%20%7C%203.10%20%7C%203.11-blue.svg)](#兼容性与测试)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#特性)
[![Tests](https://img.shields.io/badge/tests-330%20passed-brightgreen.svg)](#兼容性与测试)

> **把"版本目录里有哪些资源、用什么方法导入、默认勾没勾"从代码里搬进一份声明式规则。**

`sublevel-rules`（import 名 `sublevel_rules`）是一个**零第三方依赖**的 Python 库：
给它一个版本目录和一份规则，它把目录扫一遍 —— 折叠序列帧、处理互斥、去重、
算好父节点勾选状态 —— 最后交给你一份可以直接喂给 UI 的分级数据。

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

## 能带来什么

| 原来的痛点 | 用了 `sublevel-rules` 之后 |
| --- | --- |
| 每个环节（mod / rig / ani / tex…）的目录约定散落在导入器代码里，多支持一种格式就要改代码 | 约定变成**规则数据**，改规则即可，导入逻辑一行不动 |
| 序列帧要自己折叠、算缺帧、拼 `%04d` | 声明 `is_sequence=True`，帧号 / 缺帧 / pattern 都在结果里 |
| "abc 和 ma 只能导一个"只能靠 `if` 判断 | 用 `mutex` 组声明互斥，勾选状态自动算 |
| 父目录的"半选"状态要自己统计 | `build_operations()` 直接给出 `0` / `1` / `2` |
| 想确认"这个版本目录会导入什么"，得开 DCC 才知道 | 命令行 `sublevel-rules <版本目录>` 秒出目录树 |
| 引第三方库进 DCC 环境容易和 studio 的包管理打架 | **零依赖**，只用标准库（`pathlib` / `fnmatch`） |
| 目录约定散落在导入器代码里，多支持一种格式就要改代码 | 约定变成**规则数据**，导入层只需要一个 `method` 名字 |

## 特性

* **零第三方依赖**：纯标准库实现，直接塞进 Maya / Nuke / Houdini 的 Python 环境也不会打架；
* **声明式规则 DSL**：`Level` / `Multi` / `Action` / `Rule` / `Group`，四种节点表达任意层级；
* **序列帧折叠**：`%04d` / `####` / `$F4` 三种占位符风格，自动算帧号与缺帧；
* **互斥勾选**：同一 `mutex` 组至多保留一个勾选项，父节点状态自动推导；
* **旁路收集**：往下走的同时顺手把旁支资源收进来（`collect`）；
* **分组可选**：单层父节点 / 多层树 / 不分组；
* **命令行预览**：`sublevel-rules` / `python -m sublevel_rules`，支持 `--describe` / `--json`；
* **零依赖路径层**：接受 `str` / `pathlib.Path` / `bytes` 以及任何实现 `__fspath__` 的对象；
* **规则可配置化（可选）**：规则能在「Python 对象 ⇄ dict ⇄ YAML」之间无损互转；
  YAML 支持是**可拆卸**的独立适配器，不想要就删掉那个文件；
* **公开 API 稳定**：节点类名、参数与返回字段属于契约的一部分；
* **带类型标注**：包内带 `py.typed`（PEP 561）与完整类型注解，CI 里跑 mypy；

---

## 目录

- [能带来什么](#能带来什么)
- [快速开始](#快速开始)
- [安装](#安装)
- [概念：什么是 sub level](#概念什么是-sub-level)
- [规则语法](#规则语法)
- [解析结果 Match](#解析结果-match)
- [数据组装 build_operations](#数据组装-build_operations)
- [配置文件（可选 YAML）](#配置文件可选-yaml)
- [命令行预览](#命令行预览)
- [从 pipeline 模块调用](#从-pipeline-模块调用)
- [可能需要调整的默认值](#可能需要调整的默认值)
- [兼容性与测试](#兼容性与测试)
- [常见问题](#常见问题)
- [项目结构与开发](#项目结构与开发)
- [许可](#许可)

---

## 快速开始

### 30 秒版本

```bash
# 先看看某个版本目录在规则下会导入什么（内置预设规则）
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

### 代码里用

```python
from sublevel_rules import Action, Group, Level, Resolver, Rule, build_operations

rules = Group(
    # ① 版本目录根下：ma / mb 优先，只取一个，默认勾选
    Action(['*_v{version_part}.ma', '*_v{version_part}.mb'],
           method='animation', mode='first', checked=2),
    # ② 相机文件
    Action('*cam_v{version_part}.abc', method='animation', mode='first', checked=2),
    # ③ 分支：cache/v001/*.abc，折叠序列帧，全部勾选
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

`operations` 里每一项要么是文件条目，要么是带 `children` 的目录父节点，
字段见 [数据组装](#数据组装-build_operations)。

---

## 安装

```bash
pip install -e .                # 开发/本地
pip install ".[test]"           # 连测试依赖（pytest）一起装
pip install ".[yaml]"           # 想用 YAML 写规则时才需要（PyYAML）
```

> 核心库是**零依赖**的；`yaml` 只是可选 extra —— 不装它就只是没有 YAML 规则支持，
> 其余功能照常（对应的适配器 `yaml_rules.py` 也可以直接删掉）。

也可以不安装，直接把 `src` 放进 `PYTHONPATH`：

```bash
PYTHONPATH=src python -c "import sublevel_rules; print(sublevel_rules.__version__)"
```

内网 / 离线环境走镜像；若系统里配了 pip 会读取但连不通的代理，显式置空即可：

```bash
pip install -e ".[test]" \
    -i https://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn --proxy ""
```

---

## 概念：什么是 sub level

一条资产的某个环节（例如模型、绑定、动画），发布时会落到一个**版本目录**里：

```
.../asset/mod/mdl/v001/
├── mdl_v001.abc                 # 版本目录根下的文件
├── mdl_v001.ma
├── cache/
│   └── v001/
│       ├── abc.0001.abc         # 再往下的内部资源
│       └── abc.0002.abc
```

"从某个统一能生成的父目录往下，之后所有的内部资源都属于 **sub level**"——
再往下已经没有统一约定，每个项目、每个环节都可能不一样。这段结构不适合硬编码，
于是用一份**声明式规则**描述它：

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

规则节点只有四种：

| 节点 | 含义 |
| --- | --- |
| `Level` / `Multi` | 中间目录层级（`Multi` = `mode='multiple'` 的语法糖） |
| `Action` | 最后一层文件 + 导入方法 `method` |
| `Rule` | 把若干层串成一条完整链，**必须以 `Action` 结尾** |
| `Group` | 把多条 `Rule` / `Action` 组合成"分支集合" |

`{version_part}` 之类的占位符由调用方通过 `version_data` 传入。

---

## 规则语法

### Level / Multi

```python
Level('cache')                        # 匹配名为 cache 的目录，只取第一个
Level(['cache', 'cache_v2'])          # 依次尝试多个模式
Level('v{version_part}')              # 模式里可用占位符
Multi('v001', 'v002')                 # 等价于 Level([...], mode='multiple')
Multi(['v001', 'v002'], collect=...)  # 允许直接传列表
```

* `mode='first'`：按模式顺序，命中第一个模式里的第一个条目；
* `mode='multiple'`：收集所有模式命中的全部条目；
* `mode='latest'`：在命中项里按**自然数字序**取最新的那个
  （`v10` 排在 `v9` 之后；纯字典序里 `'v10' < 'v9'`，容易踩坑）；
* `optional=True`：可选层 —— 本层不存在就跳过、继续匹配下一层；
* `require_content=True`：候选目录里没有下一层要的东西就跳过它；
* 传 `set` 时会**先排序**，保证 `mode='first'` 的结果可复现。

```python
# 取 cache 下最新的一版，且要求那一版里真的有东西
Rule(Level('cache'),
     Level('v*', mode='latest', require_content=True),
     Action('*.abc', method='ani', mode='multiple'))

# cache/v001/x.abc 和 cache/x.abc 两种布局都要吃得下
Rule(Level('cache'), Level('v*', optional=True),
     Action('*.abc', method='ani'))
```

### Action

```python
Action('*.abc', method='geo')                       # 最简写法
Action(['*_v{version_part}.ma', '*_v{version_part}.mb'],
       method='geo', mode='first', checked=2, mutex='mod_file')
Action('*.exr', method='texture', is_sequence=True, frame_pattern='%')
Action('*.ma', method='geo', files_only=True)        # 只匹配文件
```

| 参数 | 说明 |
| --- | --- |
| `patterns` | 文件名模式，`str` 或序列 |
| `method` | 导入方法名（必填）。调用方据此找到真正的导入函数 |
| `mode` | `'first'` / `'multiple'` / `'latest'`（取最新一份） |
| `is_sequence` | 是否按序列帧匹配（先折叠序列） |
| `checked` | UI 默认勾选状态：`None` / `True` / `False` / `0` / `1` / `2` |
| `mutex` | 互斥组 ID |
| `collect` | 旁路收集器，见下文 |
| `files_only` | 只匹配文件、忽略同名目录（默认 `False`） |
| 其它 `**options` | 向下继承、随结果一起返回 |

### Rule

```python
Rule(
    Level('cache'),
    Level('v{version_part}'),
    Action('*.abc', method='animation', mode='multiple', checked=2),
)
```

约束会在**定义时**就检查：

* 至少一层；
* 最后一层必须是 `Action`；
* `Action` 只能出现在最后一层。

### Group

```python
Group(
    Action('*_v{version_part}.ma', method='animation'),           # 裸 Action
    Rule(Level('cache'), Level('v{version_part}'), Action(...)),  # 完整链
    Group(Action('*.usd', method='geo')),                         # 嵌套
)
```

`Group` 里放裸 `Level` 会直接报错（无法确定导入方法）。

`Group(mode='first')` 表示**备选链**：按顺序执行，第一个产出非空结果的子规则胜出，
后面的直接跳过 —— 用来表达"同一份资源在不同项目里有两种合法的目录布局":

```python
Group(
    Action('*.abc', method='geo', checked=2),                      # 布局 A：根目录下
    Rule(Level('cache'), Level('v*'),                              # 布局 B：cache 里
         Action('*.abc', method='geo', checked=2)),
    mode='first',
)
```

### options 继承

`**options` 会沿着 `Group -> Rule -> Level -> Action` 逐层合并，**子节点覆盖父节点**：

```python
rules = Group(
    Action('*.exr', method='texture'),
    tag='beauty',                 # 被所有子节点继承
)
matches = Resolver().resolve(rules, root)
matches[0].options['tag']         # 'beauty'
```

内置会读取的 option：

| option | 作用 |
| --- | --- |
| `frame_pattern` | 序列帧占位符风格（`'%'` / `'#'` / `'$'`），任何一层都能覆盖 |
| `mutex` | 互斥组 ID，可在 `Group` / `Rule` / `Level` 上统一指定 |

### 勾选状态 checked

`checked` 支持 `None` / `True` / `False` / `0` / `1` / `2`，内部统一用
`to_check_state()` 归一化成 Qt 语义（`0` 未勾选、`1` 半选、`2` 已勾选）：

```python
from sublevel_rules import to_check_state

to_check_state(None)    # 0
to_check_state(True)    # 2
to_check_state(1)       # 1
```

### 互斥 mutex

同一个 `mutex` 组内**至多保留一个勾选项**：

```python
Group(
    Action('*mod_v{version_part}.abc', method='geo', checked=2, mutex='mod_file'),
    Action('*_v{version_part}.ma',     method='geo', checked=2, mutex='mod_file'),
)
```

规则：组内第一个已勾选的条目保留，其余强制置为 `0`；
如果组内一个都没勾选，默认**自动勾选第一个**匹配项
（`Resolver(auto_select_first=False)` 可关闭）。

### 序列帧

```python
Action('*.exr', method='texture', is_sequence=True, frame_pattern='%')
```

`is_sequence=True` 时，目录里的 `abc.0001.exr`、`abc.0002.exr` 会被折叠成一条
`abc.%04d.exr`，帧号放在 `Match.frames`，缺失帧放在 `Match.missing`。
单帧媒体（`.mov` / `.mp4` / `.avi` / `.r3d` / `.nk` / `.ren`）不参与折叠。

```python
from sublevel_rules import frame_path

frame_path('abc.%04d.exr', 7)     # abc.0007.exr
```

### 旁路收集 collect

在往下走的同时，顺手把旁支资源也收进来：

```python
Rule(
    Level('tex', collect=Action('*.txt', method='readme')),
    Multi('v{version_part}', '*'),
    Action(['*.exr', '*.tx'], method='texture', mode='multiple'),
)
```

`collect_scope` 决定在哪里收集：

| 取值 | 含义 |
| --- | --- |
| `'children'`（默认） | 在本层匹配到的每个子目录里收集（上例 = `tex` 目录里的 `*.txt`） |
| `'parent'` | 在本层所在的目录里收集 |

### 跳过噪声条目

`Resolver(exclude_patterns=...)` 在列举目录时就跳过不想要的名字
（`.git`、`__pycache__`、备份文件……），比在规则里写负向匹配干净：

```python
resolver = Resolver(exclude_patterns=('.git', '__pycache__', '*.bak', 'Thumbs.db'))
```

匹配走与规则相同的大小写规则（默认不区分），对普通文件和折叠后的序列都生效。

### Resolver 选项一览

| 参数 | 默认 | 作用 |
| --- | --- | --- |
| `frame_pattern` | `'%'` | 序列帧占位符风格，可被 `Action(options={'frame_pattern': ...})` 覆盖 |
| `case_sensitive` | `False` | 文件名匹配是否区分大小写 |
| `dedupe` | `True` | 按 `(路径, method)` 去重 |
| `auto_select_first` | `True` | 互斥组内没有已勾选项时自动勾选第一个 |
| `strict_format` | `True` | 占位符缺失时抛 `RuleFormatError`；关掉则保留 `{占位符}` 原文（`version_data` 为空时一律保留原文并打 warning） |
| `single_media_exts` | 内置 | 单帧媒体后缀（不参与序列折叠）；传空集合即取消这个限制 |
| `exclude_patterns` | `None` | 列举目录时跳过的名字模式 |
| `logger` | 包内 logger | 自定义 logger |

> `Resolver` 实例内部带解析缓存（同一次解析里一个目录只列一次），
> 所以不要在多个线程之间共享同一个实例。

---

## 配置文件（可选 YAML）

规则本身是**纯数据**，所以核心提供了格式无关的互转：
`rule_to_dict()` ⇄ `rule_from_dict()`。YAML 只是架在它上面的一层**薄壳**，
而且是一个能整体删掉的独立文件（`yaml_rules.py`）。

```bash
pip install "sublevel-rules[yaml]"                  # 可选依赖；核心依然零依赖

sublevel-rules ./v001 --rules rules.yaml            # 整个文件就是一份规则
sublevel-rules ./v001 --rules rules.yaml:mod        # 一个文件里放多套规则，按名字选
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
        mode: latest              # 取最新的一版
        require_content: true     # 而且那一版里得有东西
      - type: action
        patterns: ["*.abc"]
        method: animation
        mode: multiple
        is_sequence: true
```

代码里用：

```python
from sublevel_rules.rule_dict import rule_from_dict
from sublevel_rules.yaml_rules import dump_rules, load_rules

rules = load_rules('rules.yaml', name='mod')     # 也可以自己 yaml.safe_load 后交给 rule_from_dict
```

* **想彻底去掉 YAML**：删 `yaml_rules.py` + `setup.cfg` 里那行 extra 即可 ——
  CLI 是按"包里有没有 `*_rules.py`"自动发现适配器的，其它文件一行都不用改；
* 结构写错会**当场报错并指出位置**（例如 `root.rules[0]: 不认识的键：cheked`），
  不会静默忽略；
* 现有的 Python 规则可以用 `dump_rules(rule)` / `rule_to_dict(rule)` 一键导成 YAML 模板。

---

## 解析结果 Match

`Resolver.resolve()` 返回 `Match` 列表。`Match` 也可以按 `(sequence, method, action)` 三元组解包：

```python
for sequence, method, action in matches:      # 也可以按三元组解包
    ...

for match in matches:
    match.name          # 文件名（序列帧时是 pattern 名）
    match.path          # pathlib.Path
    match.method        # 导入方法
    match.state         # 归一化后的勾选状态 0 / 1 / 2
    match.frames        # 序列帧的帧号
    match.missing       # 缺失帧号
    match.is_sequence   # 是否折叠出来的序列
    match.frame_pattern # 该条目使用的占位符风格（'%' / '#' / '$'）
    match.options       # 继承合并后的参数
    match.action        # 产生这条结果的 Action（只读，不会被解析过程篡改）
    match.mutex         # 互斥组 ID（Action 上的优先，其次继承的 options）
    match.depth         # 命中所在的层级下标（0 = 规则起点那一层）
    match.to_dict()     # 转成便于日志 / JSON 的普通字典
```

`resolve()` / `resolve_smart_rule()` / `Resolver.resolve()` 还接受
`inherited_options=...` —— 从更上层继承下来的参数，会和规则树自己的 `options`
合并（合并顺序 `Group -> Rule -> Level -> Action`，子节点覆盖父节点）。

调试规则本身（不扫描目录）可以直接把规则树打印出来：

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

## 数据组装 build_operations

```python
from sublevel_rules import build_operations, human_size

operations = build_operations(
    matches,
    version_root='/show/asset/ani/v001',
    version_data=version_data,
    op_resolver=lambda method: pipeline.create_api_version(method),  # 可选
    size_formatter=human_size,       # 可选：字节数 -> 展示字符串
    size_mode='first',               # 'first' / 'total' / 'none'
    group_mode='flat',               # 'flat'（默认）/ 'nested' / None
    skip_without_op=False,           # op_resolver 找不到函数时是否跳过该条目
    extra_fields={'tag': 'beauty'},  # 可选：dict 或 callable(match, asset)
)
```

文件条目的字段（前 10 个是稳定的兼容字段集）：

| 字段 | 说明 |
| --- | --- |
| `filename_checked` | 勾选状态 `0` / `1` / `2` |
| `op_func` | `op_resolver(method)` 的返回值 |
| `args` | `(sequence, version_data)`，可直接透传给操作函数 |
| `file_stem` | 无后缀的路径（`pathlib.Path`） |
| `path_name` | 完整路径字符串 |
| `filename` | 相对版本目录的文件名 |
| `orm` | `version_data` |
| `size` | 人性化大小字符串 |
| `type` | 后缀（带点） |
| `options` | 保留字段，恒为 `None` |
| `sequence` / `method` / `frames` / `missing` / `is_sequence` / `relative_path` | 新增，便于 UI 展示与调试 |

父节点条目的字段：`filename`（相对目录路径）、`filename_checked`、
`children`。父节点状态由子节点推出：全选 -> `2`，全不选 -> `0`，其余 -> `1`。

`group_mode`：

* `'flat'`（默认）：按完整目录名做**单层**父节点；
* `'nested'`：按目录层级生成**多层**树；
* `None`：不分组，全部平铺。

---

## 命令行预览

```bash
sublevel-rules <版本目录> [--preset ani|mod|rig|tex] [--rules module:attr] [--json]
python -m sublevel_rules <版本目录> --preset mod

# 只打印规则树结构，不扫描目录（此时 version_path 可省略）
sublevel-rules --preset ani --describe

# 跳过噪声目录
sublevel-rules <版本目录> --preset ani --exclude .git --exclude __pycache__
```

例如：

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

`--rules` 支持三种写法：

```bash
--rules mypipeline.rules:get_import_rules      # 已安装的模块
--rules ./project_rules.py:get_import_rules    # 独立文件
--rules ./project_rules.py                     # attr 默认 get_import_rules
```

排查"为什么没匹配到"时加 `-v` 看 DEBUG 日志（会指出哪一层、哪个模式没命中）。

---

## 从 pipeline 模块调用

pipeline 模块这样驱动本库：

```python
asset_operations = sub_level.get_sub_level_op(pipeline_module, version_data)
```

调用方式：

```python
from sublevel_rules import get_sub_level_op

asset_operations = get_sub_level_op(pipeline_module, version_data)
```

`pipeline_module` 需要提供 `get_import_rules()` 和 `create_api_version(method)`，
（缺失任一则返回空列表）。返回值字段稳定，
UI 侧（树、勾选、双击导入）不用改。

模块需要提供：

1. 规则文件里从 `sublevel_rules` 导入节点（`Level` / `Action` / `Rule` / `Group`）；
2. `get_sub_level_op(pipeline_module, version_data)`：`pipeline_module` 需要提供
   `get_import_rules()` 与 `create_api_version(method)`；
3. 异常统一从 `sublevel_rules.errors` 捕获（全部继承 `SubLevelRulesError`；
   参数取值非法抛 `ParameterError`，它同时是 `ValueError`）；
4. 下面[默认值](#可能需要调整的默认值)不满意时，用对应的开关调整。

## 可能需要调整的默认值

下面每个默认值都是有意的选择；这六个最可能因管线不同而需要调整：

| 项 | 默认 | 怎么改 |
| --- | --- | --- |
| 文件名匹配 | 所有平台都不区分大小写 | `Resolver(case_sensitive=True)` |
| 互斥组为空 | 自动勾选第一个 | `Resolver(auto_select_first=False)` |
| 结果去重 | 按 `(路径, method)` 去重 | `Resolver(dedupe=False)` |
| 旁路收集 `collect` | 在本层匹配到的子目录里收集 | `Level(..., collect_scope='parent')` |
| 中间层 `Level` 的 `options` | 随链继承 | 不写在那里，或只写在 `Action` 上 |
| `Level` / `Multi` 上的 `mutex` | 生效（同组只勾一个） | 改写到 `Action` 上 |

---

## 兼容性与测试

| Python | 覆盖方式 | 用例 |
| --- | --- | --- |
| 3.7.7 | 本地实测 + CI 矩阵（Linux / Windows / macOS） | 330 |
| 3.8 | CI 矩阵（`.github/workflows/tests.yml`） | 330 |
| 3.9.7 | 本地实测 + CI 矩阵 | 330 |
| 3.10 | CI 矩阵 | 330 |
| 3.11.8 | 本地实测 + CI 矩阵 | 330 |

代码只使用 Python 3.7 起可用的语法与标准库，没有按版本分支的逻辑。

同一套用例支持两种跑法（CI 里两种都会跑）：

```bash
# unittest（不装任何依赖也能跑，推荐离线环境）
python scripts/run_tests.py

# 一次跑完项目里所有 .venv-* 环境（bash）
bash scripts/run_tests.sh

# pytest（装了 test extra 之后）
python -m pytest tests -q
```

测试覆盖范围：

| 模块 | 覆盖内容 |
| --- | --- |
| `tests/test_paths.py` | `Entry` / `as_path` / `split_frame` / `list_entries` |
| `tests/test_sequences.py` | 序列折叠、缺帧统计、单帧媒体、占位符风格 |
| `tests/test_frames.py` | `frame_path` / `frame_tokens` |
| `tests/test_rules.py` | DSL 定义期校验、`to_check_state` |
| `tests/test_resolver.py` | first/multiple、目录链、`collect`、`mutex`、去重、序列匹配、选项继承、异常 |
| `tests/test_operations.py` | `build_operations` 字段/分组/父节点状态、`get_sub_level_op` 兼容入口 |
| `tests/test_presets.py` | 四个内置预设规则在真实目录树上的行为 |
| `tests/test_cli.py` | 参数解析、目录树渲染、规则加载、文本/JSON 输出、错误处理 |
| `tests/test_improvements.py` | 代码审查后的修复与新功能回归（重复折叠、set 顺序、`%4d`、`files_only`、`exclude_patterns`、`--describe` 等） |
| `tests/test_expressiveness.py` | 备选链 `Group(mode='first')`、`mode='latest'`、`optional`、`require_content`、scandir 后的 `Entry` 行为 |
| `tests/test_rule_dict.py` | 规则 ⇄ dict 双向互转、往返一致、结构错误提示带位置 |
| `tests/test_yaml_rules.py` | YAML 适配器读写与 CLI 集成（没装 PyYAML 时整组自动跳过）、适配器发现机制 |
| `tests/test_combinations.py` | 语义**组合**：`mode × optional × require_content`、`collect × collect_scope`、`Group(mode='first')` × mutex/嵌套、`size_mode × 分组`、`rule_dict` 全字段往返 |
| `tests/test_edge_branches.py` | 错误与防御分支：帧文件被删、适配器导入失败、缓存命中、大小写敏感、末层 `collect` 等 |
| docstring 示例（doctest） | 各模块 docstring 里带 `>>>` 的例子会被 `scripts/run_tests.py` 一起跑 —— 示例写错就会红 |

---

## 常见问题

**Q：为什么装的是 `sublevel-rules`，import 的却是 `sublevel_rules`？**
Python 生态惯例：分发名用连字符、import 名用下划线（如 `scikit-learn` → `import sklearn`）。
PEP 503 里两者在 pip 层面本来就是等价的。

**Q：一个都没匹配到，怎么排查？**
先 `sublevel-rules <目录> --describe` 确认规则长什么样，再加 `-v` 看 DEBUG 日志
（会指出哪一层、哪个模式在哪个目录下没有命中），最后确认 `version_part` 传对了
（CLI 默认从目录名里取 `v` 后面的数字，可用 `--version-part` 覆盖）。

**Q：工程文件 `mdl_v001.ma` 被折叠成序列了？**
只有声明了 `is_sequence=True` 的 `Action` 才会折叠。版本号被当成帧号是序列折叠的经典陷阱，
工程文件这类"每个版本一个、不是帧序列"的文件不要开这个开关。

**Q：能跑在 Maya / Nuke / Houdini 里吗？**
可以，零第三方依赖、纯标准库，`sys.path` 挂上 `src` 就能用。

**Q：为什么默认不区分大小写？**
为了跨平台一致：Windows 的 `fnmatch` 本来就不区分、Linux 区分，容易造成"本机好的、farm 上坏的"。
要严格区分用 `Resolver(case_sensitive=True)`。

**Q：结果里出现了目录，被当成文件条目了？**
目录也会被匹配（这是 `fnmatch` 的语义）。用 `Action(..., files_only=True)` 只匹配文件。

**Q：能不能用 YAML（或别的配置文件）写规则？**
能。规则本身就是**纯数据**，核心提供 `rule_to_dict()` / `rule_from_dict()` 做无损互转；
YAML 的读写是一个**可拆卸的独立适配器** `yaml_rules.py`：

```bash
pip install "sublevel-rules[yaml]"
sublevel-rules ./v001 --rules rules.yaml        # 整个文件就是一份规则
sublevel-rules ./v001 --rules rules.yaml:mod    # 一个文件里放多套规则
```

不想要 YAML 时，删掉 `yaml_rules.py`（和 `setup.cfg` 里那行 extra）就行 ——
`cli.py` 是靠"包里有没有 `*_rules.py`"**自动发现**适配器的，一行都不用改。
`rule_to_dict()` 还能把现有 Python 规则一键导成 YAML 模板，方便给不写代码的人改。

**Q：有些目录结构规则表达不出来，怎么办？**
先看 [docs/limitations.zh-CN.md](docs/limitations.zh-CN.md) —— 那里列了**有意不做**的能力
（递归 `**`、UI 逻辑分组、Action 级排除、`min_frames`、在规则里写逻辑），
以及每一种的替代做法。

---

## 项目结构与开发

```
sublevel-rules/
├── README.md              English README
├── README.zh-CN.md        中文说明（本文件）
├── docs/
│   ├── limitations.md     已知边界（英文）
│   └── limitations.zh-CN.md  已知边界（中文）
├── src/sublevel_rules/
│   ├── __init__.py        公共 API
│   ├── const.py           常量（单帧媒体后缀、勾选状态…）
│   ├── errors.py          异常（统一继承 SubLevelRulesError）
│   ├── paths.py           零依赖路径适配层（Entry / as_path / list_entries）
│   ├── sequences.py       序列帧扫描与折叠
│   ├── frames.py          pattern <-> 具体帧路径
│   ├── rules.py           规则 DSL
│   ├── resolver.py        解析引擎（Resolver / Match）
│   ├── operations.py      UI 数据组装（build_operations / get_sub_level_op）
│   ├── rule_dict.py       规则 ⇄ dict 互转（格式无关的中间层）
│   ├── yaml_rules.py      YAML 适配器（可拆卸：删掉即去掉该格式支持）
│   ├── presets.py         内置预设规则
│   ├── cli.py             命令行预览（按约定自动发现 *_rules.py 适配器）
│   └── __main__.py        python -m sublevel_rules
├── tests/                 单元测试（unittest 编写，兼容 pytest）
├── examples/              示例规则与 API 用法可直接运行
├── scripts/
│   ├── run_tests.py       跨平台测试入口
│   └── run_tests.sh       依次在 .venv-* 环境里跑测试（bash）
└── .github/workflows/     CI（Python 3.7 ~ 3.11 矩阵）
```

### 本地开发环境

```bash
python -m venv .venv-3.7        # 或 C:/Python37/python.exe -m venv .venv-3.7
python -m venv .venv-3.9
python -m venv .venv-3.11
```

### 开发命令

```bash
python scripts/run_tests.py          # 全部用例 + docstring doctest，不依赖任何第三方包
bash scripts/run_tests.sh            # 一次跑完所有 .venv-* 环境（POSIX shell）
python -m pytest tests -q            # 需要先 pip install ".[test]"
python -m flake8 src tests           # 配置在 setup.cfg 的 [flake8] 段
python -m coverage run --branch --source=src/sublevel_rules scripts/run_tests.py
python -m coverage report -m
python -m mypy                        # 类型检查（配置在 setup.cfg）
python scripts/benchmark.py           # 解析耗时基准，见 docs/benchmark.md
python -m sublevel_rules <版本目录> --preset mod -v      # 命令行预览
```

数据流：`规则树 + 版本目录` → `Resolver.resolve()` → `[Match...]` →
`build_operations()` → UI 直接消费的分级 dict。

### 贡献约定

* **改了行为就要同步测试**：单点功能放对应的 `tests/test_*.py`；语义**组合**放
  `tests/test_combinations.py`；错误 / 防御分支放 `tests/test_edge_branches.py`。
* **改了行为或新增能力就要同步 `CHANGELOG.md`**，以及两份 README 里的测试数字
  （徽章 + 兼容性表）。
* docstring 里带 `>>>` 的示例会被 `scripts/run_tests.py` 当 **doctest** 跑 ——
  必须与真实输出一致。
* 语言成对的文件要保持同步：`README.md` / `README.zh-CN.md`，
  `docs/limitations.md` / `docs/limitations.zh-CN.md`。
* 保持**零第三方依赖**：核心库只用标准库；可选能力做成 extra（如 `[yaml]`）。
* 4 空格缩进、单行不超过 100 字符（`.editorconfig` 统一 UTF-8 / LF）。
* docstring 与注释用英文；运行期文案（异常消息、日志、CLI 输出）保持中文 ——
  消费这个库的界面是中文的。所有公开函数都要带 docstring（说明参数含义）。
* `setup.cfg` 里不要出现非 ASCII 字符：Python 3.7 / 3.9 自带的老 setuptools 在 GBK
  环境下解析会抛 `UnicodeDecodeError`。

### 改代码时容易踩的坑

* `collect_scope`：`children`（默认）在**本层匹配到的目录**里收集，`parent` 在
  **本层所在目录**里收集。
* `human_size()` 默认单位是 MB，所以 `human_size(1024)` 是 `'0.00MB'`。
* `mode='first'` 走字典序，`v10` 排在 `v9` 前面 —— 要"取最新"用 `mode='latest'`。
* `options` 是逐层累积的（`Group -> Rule -> Level -> Action`，子节点覆盖父节点），
  写在中间层 `Level` 上的 `tag` / `frame_pattern` / `mutex` 都会传下去 ——
  只想作用于某一层就别写在中间层上。
* `Entry.size()` 每次都会重新 `stat`（`os.scandir` 的值只是快照，Windows 上更是列目录
  那一刻的）；`is_file()` / `is_dir()` 仍走缓存 —— 文件类型不会变，大小会变。
* `Resolver` 实例内部带解析缓存，不要在多线程之间共享同一个实例；用
  `keep_cache=True` 可以让缓存跨 `resolve()` 保留（UI 反复刷新同一个目录时便宜很多），
  目录可能变化时调 `Resolver.clear_cache()`。
* Windows 上 `Level(Path(...))` 会得到 `a\b`，写测试注意路径分隔符。
* `yaml_rules.py` 是可拆卸的：CLI 靠扫描包内的 `*_rules.py` 发现适配器，
  加/删适配器都不需要改其它文件。

---

## 许可

[MIT](LICENSE)
