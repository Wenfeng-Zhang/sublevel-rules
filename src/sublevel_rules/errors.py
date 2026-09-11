# -*- coding: utf-8 -*-
"""Exception types raised by sublevel_rules.

Every exception derives from :class:`SubLevelRulesError`, so callers can catch
that single base class.
"""


class SubLevelRulesError(Exception):
    """Base class of every exception raised by sublevel_rules."""


class RuleDefinitionError(SubLevelRulesError):
    """The rule definition is invalid.

    For example an empty pattern list, a wrong ``mode`` value or a missing
    ``method``.
    """


class RuleStructureError(RuleDefinitionError):
    """The rule structure is invalid.

    For example the last level of a ``Rule`` is not an
    :class:`~sublevel_rules.rules.Action`, or an ``Action`` appears in the middle
    of a chain (an ``Action`` may only be the final level).
    """


class RuleFormatError(SubLevelRulesError):
    """A pattern string could not be formatted.

    Usually a placeholder such as ``{version_part}`` is missing from
    ``version_data``, or the pattern contains braces that cannot be parsed.
    """


class PathError(SubLevelRulesError):
    """A path cannot be resolved (``None``, an empty string, ...)."""


class ParameterError(SubLevelRulesError, ValueError):
    """A function argument has an invalid value (e.g. an unknown ``size_mode`` / ``group_mode``).

    It also derives from :class:`ValueError`, so callers can either catch it
    through ``except SubLevelRulesError`` or follow the Python convention of
    catching ``ValueError`` for bad argument values.
    """
