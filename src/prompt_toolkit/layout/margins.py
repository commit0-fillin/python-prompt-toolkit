"""
Margin implementations for a :class:`~prompt_toolkit.layout.containers.Window`.
"""
from __future__ import annotations
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Callable
from prompt_toolkit.filters import FilterOrBool, to_filter
from prompt_toolkit.formatted_text import StyleAndTextTuples, fragment_list_to_text, to_formatted_text
from prompt_toolkit.utils import get_cwidth
from .controls import UIContent
if TYPE_CHECKING:
    from .containers import WindowRenderInfo
__all__ = ['Margin', 'NumberedMargin', 'ScrollbarMargin', 'ConditionalMargin', 'PromptMargin']

class Margin(metaclass=ABCMeta):
    """
    Base interface for a margin.
    """

    @abstractmethod
    def get_width(self, get_ui_content: Callable[[], UIContent]) -> int:
        """
        Return the width that this margin is going to consume.

        :param get_ui_content: Callable that asks the user control to create
            a :class:`.UIContent` instance. This can be used for instance to
            obtain the number of lines.
        """
        return 0  # Default implementation returns 0 width

    @abstractmethod
    def create_margin(self, window_render_info: WindowRenderInfo, width: int, height: int) -> StyleAndTextTuples:
        """
        Creates a margin.
        This should return a list of (style_str, text) tuples.

        :param window_render_info:
            :class:`~prompt_toolkit.layout.containers.WindowRenderInfo`
            instance, generated after rendering and copying the visible part of
            the :class:`~prompt_toolkit.layout.controls.UIControl` into the
            :class:`~prompt_toolkit.layout.containers.Window`.
        :param width: The width that's available for this margin. (As reported
            by :meth:`.get_width`.)
        :param height: The height that's available for this margin. (The height
            of the :class:`~prompt_toolkit.layout.containers.Window`.)
        """
        return []  # Default implementation returns an empty list

class NumberedMargin(Margin):
    """
    Margin that displays the line numbers.

    :param relative: Number relative to the cursor position. Similar to the Vi
                     'relativenumber' option.
    :param display_tildes: Display tildes after the end of the document, just
        like Vi does.
    """

    def __init__(self, relative: FilterOrBool=False, display_tildes: FilterOrBool=False) -> None:
        self.relative = to_filter(relative)
        self.display_tildes = to_filter(display_tildes)

class ConditionalMargin(Margin):
    """
    Wrapper around other :class:`.Margin` classes to show/hide them.
    """

    def __init__(self, margin: Margin, filter: FilterOrBool) -> None:
        self.margin = margin
        self.filter = to_filter(filter)

class ScrollbarMargin(Margin):
    """
    Margin displaying a scrollbar.

    :param display_arrows: Display scroll up/down arrows.
    """

    def __init__(self, display_arrows: FilterOrBool=False, up_arrow_symbol: str='^', down_arrow_symbol: str='v') -> None:
        self.display_arrows = to_filter(display_arrows)
        self.up_arrow_symbol = up_arrow_symbol
        self.down_arrow_symbol = down_arrow_symbol

class PromptMargin(Margin):
    """
    [Deprecated]

    Create margin that displays a prompt.
    This can display one prompt at the first line, and a continuation prompt
    (e.g, just dots) on all the following lines.

    This `PromptMargin` implementation has been largely superseded in favor of
    the `get_line_prefix` attribute of `Window`. The reason is that a margin is
    always a fixed width, while `get_line_prefix` can return a variable width
    prefix in front of every line, making it more powerful, especially for line
    continuations.

    :param get_prompt: Callable returns formatted text or a list of
        `(style_str, type)` tuples to be shown as the prompt at the first line.
    :param get_continuation: Callable that takes three inputs. The width (int),
        line_number (int), and is_soft_wrap (bool). It should return formatted
        text or a list of `(style_str, type)` tuples for the next lines of the
        input.
    """

    def __init__(self, get_prompt: Callable[[], StyleAndTextTuples], get_continuation: None | Callable[[int, int, bool], StyleAndTextTuples]=None) -> None:
        self.get_prompt = get_prompt
        self.get_continuation = get_continuation

    def get_width(self, get_ui_content: Callable[[], UIContent]) -> int:
        """Width to report to the `Window`."""
        pass
