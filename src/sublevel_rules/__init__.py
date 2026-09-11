# -*- coding: utf-8 -*-
"""sublevel_rules -- a declarative "version folder -> resource list" rule engine.

In one sentence: given a version folder, which resources live at which level,
how they are imported and whether they are checked by default is described by a
declarative rule; this library scans the folder, collapses frame sequences,
deduplicates, applies mutual exclusion and assembles the hierarchical data a UI
can consume directly.
"""

import logging

from .const import (
    CHECKED_CHECKED,
    CHECKED_PARTIAL,
    CHECKED_UNCHECKED,
    DEFAULT_FRAME_PATTERN,
    FRAME_PATTERN_STYLES,
    MODE_FIRST,
    MODE_MULTIPLE,
    SINGLE_MEDIA_EXTS,
)
from .errors import (
    PathError,
    RuleDefinitionError,
    RuleFormatError,
    RuleStructureError,
    SubLevelRulesError,
)
from .frames import frame_path, frame_tokens
from .operations import build_operations, get_sub_level_op, human_size, parent_check_state
from .paths import Entry, as_path, list_entries
from .presets import ani_rules, mod_rules, rig_rules, tex_rules
from .resolver import Match, Resolver, format_pattern, resolve, resolve_smart_rule
from .rules import (
    Action,
    COLLECT_SCOPE_CHILDREN,
    COLLECT_SCOPE_PARENT,
    COLLECT_SCOPES,
    Group,
    Level,
    Multi,
    Rule,
    describe_rule,
    to_check_state,
)
from .sequences import SequentialFiles, is_sequence_name, scan_sequences

__version__ = '0.1.0'

# A library must not write into the root logger: adding a NullHandler keeps
# "No handlers could be found" noise away from callers that do not configure
# logging themselves.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    # rule DSL
    'Action', 'Group', 'Level', 'Multi', 'Rule', 'describe_rule',
    'COLLECT_SCOPE_CHILDREN', 'COLLECT_SCOPE_PARENT', 'COLLECT_SCOPES',
    # resolving
    'Resolver', 'Match', 'resolve', 'resolve_smart_rule', 'format_pattern',
    # data assembly
    'build_operations', 'get_sub_level_op', 'human_size', 'parent_check_state',
    # paths / sequences
    'Entry', 'as_path', 'list_entries', 'SequentialFiles', 'scan_sequences',
    'is_sequence_name', 'frame_path', 'frame_tokens',
    # preset rules
    'mod_rules', 'rig_rules', 'ani_rules', 'tex_rules',
    # constants and exceptions
    'CHECKED_UNCHECKED', 'CHECKED_PARTIAL', 'CHECKED_CHECKED',
    'DEFAULT_FRAME_PATTERN', 'FRAME_PATTERN_STYLES', 'MODE_FIRST', 'MODE_MULTIPLE',
    'SINGLE_MEDIA_EXTS', 'to_check_state',
    'SubLevelRulesError', 'RuleDefinitionError', 'RuleStructureError',
    'RuleFormatError', 'PathError',
    '__version__',
]
