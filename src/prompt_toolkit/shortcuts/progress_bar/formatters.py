"""
Formatter classes for the progress bar.
Each progress bar consists of a list of these formatters.
"""
from __future__ import annotations
import datetime
import time
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING
from prompt_toolkit.formatted_text import HTML, AnyFormattedText, StyleAndTextTuples, to_formatted_text
from prompt_toolkit.formatted_text.utils import fragment_list_width
from prompt_toolkit.layout.dimension import AnyDimension, D
from prompt_toolkit.layout.utils import explode_text_fragments
from prompt_toolkit.utils import get_cwidth
if TYPE_CHECKING:
    from .base import ProgressBar, ProgressBarCounter
__all__ = ['Formatter', 'Text', 'Label', 'Percentage', 'Bar', 'Progress', 'TimeElapsed', 'TimeLeft', 'IterationsPerSecond', 'SpinningWheel', 'Rainbow', 'create_default_formatters']

class Formatter(metaclass=ABCMeta):
    """
    Base class for any formatter.
    """

class Text(Formatter):
    """
    Display plain text.
    """

    def __init__(self, text: AnyFormattedText, style: str='') -> None:
        self.text = to_formatted_text(text, style=style)

class Label(Formatter):
    """
    Display the name of the current task.

    :param width: If a `width` is given, use this width. Scroll the text if it
        doesn't fit in this width.
    :param suffix: String suffix to be added after the task name, e.g. ': '.
        If no task name was given, no suffix will be added.
    """

    def __init__(self, width: AnyDimension=None, suffix: str='') -> None:
        self.width = width
        self.suffix = suffix

class Percentage(Formatter):
    """
    Display the progress as a percentage.
    """
    template = '<percentage>{percentage:>5}%</percentage>'

class Bar(Formatter):
    """
    Display the progress bar itself.
    """
    template = '<bar>{start}<bar-a>{bar_a}</bar-a><bar-b>{bar_b}</bar-b><bar-c>{bar_c}</bar-c>{end}</bar>'

    def __init__(self, start: str='[', end: str=']', sym_a: str='=', sym_b: str='>', sym_c: str=' ', unknown: str='#') -> None:
        assert len(sym_a) == 1 and get_cwidth(sym_a) == 1
        assert len(sym_c) == 1 and get_cwidth(sym_c) == 1
        self.start = start
        self.end = end
        self.sym_a = sym_a
        self.sym_b = sym_b
        self.sym_c = sym_c
        self.unknown = unknown

class Progress(Formatter):
    """
    Display the progress as text.  E.g. "8/20"
    """
    template = '<current>{current:>3}</current>/<total>{total:>3}</total>'

def _format_timedelta(timedelta: datetime.timedelta) -> str:
    """
    Return hh:mm:ss, or mm:ss if the amount of hours is zero.
    """
    hours, remainder = divmod(int(timedelta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

class TimeElapsed(Formatter):
    """
    Display the elapsed time.
    """

class TimeLeft(Formatter):
    """
    Display the time left.
    """
    template = '<time-left>{time_left}</time-left>'
    unknown = '?:??:??'

class IterationsPerSecond(Formatter):
    """
    Display the iterations per second.
    """
    template = '<iterations-per-second>{iterations_per_second:.2f}</iterations-per-second>'

class SpinningWheel(Formatter):
    """
    Display a spinning wheel.
    """
    characters = '/-\\|'

def _hue_to_rgb(hue: float) -> tuple[int, int, int]:
    """
    Take hue between 0 and 1, return (r, g, b).
    """
    hue *= 6
    if hue < 1:
        return (255, int(255 * hue), 0)
    elif hue < 2:
        return (int(255 * (2 - hue)), 255, 0)
    elif hue < 3:
        return (0, 255, int(255 * (hue - 2)))
    elif hue < 4:
        return (0, int(255 * (4 - hue)), 255)
    elif hue < 5:
        return (int(255 * (hue - 4)), 0, 255)
    else:
        return (255, 0, int(255 * (6 - hue)))

class Rainbow(Formatter):
    """
    For the fun. Add rainbow colors to any of the other formatters.
    """
    colors = ['#%.2x%.2x%.2x' % _hue_to_rgb(h / 100.0) for h in range(0, 100)]

    def __init__(self, formatter: Formatter) -> None:
        self.formatter = formatter

def create_default_formatters() -> list[Formatter]:
    """
    Return the list of default formatters.
    """
    return [
        Label(),
        Text(' '),
        Percentage(),
        Text(' '),
        Bar(),
        Text(' '),
        Progress(),
        Text(' '),
        Text('eta [', style='class:time-left'),
        TimeLeft(),
        Text(']', style='class:time-left'),
        Text(' '),
    ]
