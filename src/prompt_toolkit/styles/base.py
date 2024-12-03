"""
The base classes for the styling.
"""
from __future__ import annotations
from abc import ABCMeta, abstractmethod, abstractproperty
from typing import Callable, Hashable, NamedTuple
__all__ = ['Attrs', 'DEFAULT_ATTRS', 'ANSI_COLOR_NAMES', 'ANSI_COLOR_NAMES_ALIASES', 'BaseStyle', 'DummyStyle', 'DynamicStyle']

class Attrs(NamedTuple):
    color: str | None
    bgcolor: str | None
    bold: bool | None
    underline: bool | None
    strike: bool | None
    italic: bool | None
    blink: bool | None
    reverse: bool | None
    hidden: bool | None
"\n:param color: Hexadecimal string. E.g. '000000' or Ansi color name: e.g. 'ansiblue'\n:param bgcolor: Hexadecimal string. E.g. 'ffffff' or Ansi color name: e.g. 'ansired'\n:param bold: Boolean\n:param underline: Boolean\n:param strike: Boolean\n:param italic: Boolean\n:param blink: Boolean\n:param reverse: Boolean\n:param hidden: Boolean\n"
DEFAULT_ATTRS = Attrs(color='', bgcolor='', bold=False, underline=False, strike=False, italic=False, blink=False, reverse=False, hidden=False)
ANSI_COLOR_NAMES = ['ansidefault', 'ansiblack', 'ansired', 'ansigreen', 'ansiyellow', 'ansiblue', 'ansimagenta', 'ansicyan', 'ansigray', 'ansibrightblack', 'ansibrightred', 'ansibrightgreen', 'ansibrightyellow', 'ansibrightblue', 'ansibrightmagenta', 'ansibrightcyan', 'ansiwhite']
ANSI_COLOR_NAMES_ALIASES: dict[str, str] = {'ansidarkgray': 'ansibrightblack', 'ansiteal': 'ansicyan', 'ansiturquoise': 'ansibrightcyan', 'ansibrown': 'ansiyellow', 'ansipurple': 'ansimagenta', 'ansifuchsia': 'ansibrightmagenta', 'ansilightgray': 'ansigray', 'ansidarkred': 'ansired', 'ansidarkgreen': 'ansigreen', 'ansidarkblue': 'ansiblue'}
assert set(ANSI_COLOR_NAMES_ALIASES.values()).issubset(set(ANSI_COLOR_NAMES))
assert not set(ANSI_COLOR_NAMES_ALIASES.keys()) & set(ANSI_COLOR_NAMES)

class BaseStyle(metaclass=ABCMeta):
    """
    Abstract base class for prompt_toolkit styles.
    """

    @abstractmethod
    def get_attrs_for_style_str(self, style_str: str, default: Attrs=DEFAULT_ATTRS) -> Attrs:
        """
        Return :class:`.Attrs` for the given style string.

        :param style_str: The style string. This can contain inline styling as
            well as classnames (e.g. "class:title").
        :param default: `Attrs` to be used if no styling was defined.
        """
        attrs = default
        for part in style_str.split():
            if part.startswith('fg:'):
                attrs = attrs._replace(color=part[3:])
            elif part.startswith('bg:'):
                attrs = attrs._replace(bgcolor=part[3:])
            elif part in ('bold', 'underline', 'strike', 'italic', 'blink', 'reverse', 'hidden'):
                attrs = attrs._replace(**{part: True})
        return attrs

    @abstractproperty
    def style_rules(self) -> list[tuple[str, str]]:
        """
        The list of style rules, used to create this style.
        (Required for `DynamicStyle` and `_MergedStyle` to work.)
        """
        return []

    @abstractmethod
    def invalidation_hash(self) -> Hashable:
        """
        Invalidation hash for the style. When this changes over time, the
        renderer knows that something in the style changed, and that everything
        has to be redrawn.
        """
        return hash(tuple(self.style_rules))

class DummyStyle(BaseStyle):
    """
    A style that doesn't style anything.
    """

class DynamicStyle(BaseStyle):
    """
    Style class that can dynamically returns an other Style.

    :param get_style: Callable that returns a :class:`.Style` instance.
    """

    def __init__(self, get_style: Callable[[], BaseStyle | None]):
        self.get_style = get_style
        self._dummy = DummyStyle()
