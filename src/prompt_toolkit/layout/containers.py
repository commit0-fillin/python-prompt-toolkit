"""
Container for the layout.
(Containers can contain other containers or user interface controls.)
"""
from __future__ import annotations
from abc import ABCMeta, abstractmethod
from enum import Enum
from functools import partial
from typing import TYPE_CHECKING, Callable, Sequence, Union, cast
from prompt_toolkit.application.current import get_app
from prompt_toolkit.cache import SimpleCache
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import FilterOrBool, emacs_insert_mode, to_filter, vi_insert_mode
from prompt_toolkit.formatted_text import AnyFormattedText, StyleAndTextTuples, to_formatted_text
from prompt_toolkit.formatted_text.utils import fragment_list_to_text, fragment_list_width
from prompt_toolkit.key_binding import KeyBindingsBase
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.utils import get_cwidth, take_using_weights, to_int, to_str
from .controls import DummyControl, FormattedTextControl, GetLinePrefixCallable, UIContent, UIControl
from .dimension import AnyDimension, Dimension, max_layout_dimensions, sum_layout_dimensions, to_dimension
from .margins import Margin
from .mouse_handlers import MouseHandlers
from .screen import _CHAR_CACHE, Screen, WritePosition
from .utils import explode_text_fragments
if TYPE_CHECKING:
    from typing_extensions import Protocol, TypeGuard
    from prompt_toolkit.key_binding.key_bindings import NotImplementedOrNone
__all__ = ['AnyContainer', 'Container', 'HorizontalAlign', 'VerticalAlign', 'HSplit', 'VSplit', 'FloatContainer', 'Float', 'WindowAlign', 'Window', 'WindowRenderInfo', 'ConditionalContainer', 'ScrollOffsets', 'ColorColumn', 'to_container', 'to_window', 'is_container', 'DynamicContainer']

class Container(metaclass=ABCMeta):
    """
    Base class for user interface layout.
    """

    @abstractmethod
    def reset(self) -> None:
        """
        Reset the state of this container and all the children.
        (E.g. reset scroll offsets, etc...)
        """
        for child in self.get_children():
            child.reset()

    @abstractmethod
    def preferred_width(self, max_available_width: int) -> Dimension:
        """
        Return a :class:`~prompt_toolkit.layout.Dimension` that represents the
        desired width for this container.
        """
        return Dimension()

    @abstractmethod
    def preferred_height(self, width: int, max_available_height: int) -> Dimension:
        """
        Return a :class:`~prompt_toolkit.layout.Dimension` that represents the
        desired height for this container.
        """
        return Dimension()

    @abstractmethod
    def write_to_screen(self, screen: Screen, mouse_handlers: MouseHandlers, write_position: WritePosition, parent_style: str, erase_bg: bool, z_index: int | None) -> None:
        """
        Write the actual content to the screen.

        :param screen: :class:`~prompt_toolkit.layout.screen.Screen`
        :param mouse_handlers: :class:`~prompt_toolkit.layout.mouse_handlers.MouseHandlers`.
        :param parent_style: Style string to pass to the :class:`.Window`
            object. This will be applied to all content of the windows.
            :class:`.VSplit` and :class:`.HSplit` can use it to pass their
            style down to the windows that they contain.
        :param z_index: Used for propagating z_index from parent to child.
        """
        for child in self.get_children():
            child.write_to_screen(screen, mouse_handlers, write_position, parent_style, erase_bg, z_index)

    def is_modal(self) -> bool:
        """
        When this container is modal, key bindings from parent containers are
        not taken into account if a user control in this container is focused.
        """
        return False

    def get_key_bindings(self) -> KeyBindingsBase | None:
        """
        Returns a :class:`.KeyBindings` object. These bindings become active when any
        user control in this container has the focus, except if any containers
        between this container and the focused user control is modal.
        """
        return None

    @abstractmethod
    def get_children(self) -> list[Container]:
        """
        Return the list of child :class:`.Container` objects.
        """
        return []
if TYPE_CHECKING:

    class MagicContainer(Protocol):
        """
        Any object that implements ``__pt_container__`` represents a container.
        """

        def __pt_container__(self) -> AnyContainer:
            ...
AnyContainer = Union[Container, 'MagicContainer']

def _window_too_small() -> Window:
    """Create a `Window` that displays the 'Window too small' text."""
    return Window(FormattedTextControl("Window too small..."))

class VerticalAlign(Enum):
    """Alignment for `HSplit`."""
    TOP = 'TOP'
    CENTER = 'CENTER'
    BOTTOM = 'BOTTOM'
    JUSTIFY = 'JUSTIFY'

class HorizontalAlign(Enum):
    """Alignment for `VSplit`."""
    LEFT = 'LEFT'
    CENTER = 'CENTER'
    RIGHT = 'RIGHT'
    JUSTIFY = 'JUSTIFY'

class _Split(Container):
    """
    The common parts of `VSplit` and `HSplit`.
    """

    def __init__(self, children: Sequence[AnyContainer], window_too_small: Container | None=None, padding: AnyDimension=Dimension.exact(0), padding_char: str | None=None, padding_style: str='', width: AnyDimension=None, height: AnyDimension=None, z_index: int | None=None, modal: bool=False, key_bindings: KeyBindingsBase | None=None, style: str | Callable[[], str]='') -> None:
        self.children = [to_container(c) for c in children]
        self.window_too_small = window_too_small or _window_too_small()
        self.padding = padding
        self.padding_char = padding_char
        self.padding_style = padding_style
        self.width = width
        self.height = height
        self.z_index = z_index
        self.modal = modal
        self.key_bindings = key_bindings
        self.style = style

class HSplit(_Split):
    """
    Several layouts, one stacked above/under the other. ::

        +--------------------+
        |                    |
        +--------------------+
        |                    |
        +--------------------+

    By default, this doesn't display a horizontal line between the children,
    but if this is something you need, then create a HSplit as follows::

        HSplit(children=[ ... ], padding_char='-',
               padding=1, padding_style='#ffff00')

    :param children: List of child :class:`.Container` objects.
    :param window_too_small: A :class:`.Container` object that is displayed if
        there is not enough space for all the children. By default, this is a
        "Window too small" message.
    :param align: `VerticalAlign` value.
    :param width: When given, use this width instead of looking at the children.
    :param height: When given, use this height instead of looking at the children.
    :param z_index: (int or None) When specified, this can be used to bring
        element in front of floating elements.  `None` means: inherit from parent.
    :param style: A style string.
    :param modal: ``True`` or ``False``.
    :param key_bindings: ``None`` or a :class:`.KeyBindings` object.

    :param padding: (`Dimension` or int), size to be used for the padding.
    :param padding_char: Character to be used for filling in the padding.
    :param padding_style: Style to applied to the padding.
    """

    def __init__(self, children: Sequence[AnyContainer], window_too_small: Container | None=None, align: VerticalAlign=VerticalAlign.JUSTIFY, padding: AnyDimension=0, padding_char: str | None=None, padding_style: str='', width: AnyDimension=None, height: AnyDimension=None, z_index: int | None=None, modal: bool=False, key_bindings: KeyBindingsBase | None=None, style: str | Callable[[], str]='') -> None:
        super().__init__(children=children, window_too_small=window_too_small, padding=padding, padding_char=padding_char, padding_style=padding_style, width=width, height=height, z_index=z_index, modal=modal, key_bindings=key_bindings, style=style)
        self.align = align
        self._children_cache: SimpleCache[tuple[Container, ...], list[Container]] = SimpleCache(maxsize=1)
        self._remaining_space_window = Window()

    @property
    def _all_children(self) -> list[Container]:
        """
        List of child objects, including padding.
        """
        pass

    def write_to_screen(self, screen: Screen, mouse_handlers: MouseHandlers, write_position: WritePosition, parent_style: str, erase_bg: bool, z_index: int | None) -> None:
        """
        Render the prompt to a `Screen` instance.

        :param screen: The :class:`~prompt_toolkit.layout.screen.Screen` class
            to which the output has to be written.
        """
        pass

    def _divide_heights(self, write_position: WritePosition) -> list[int] | None:
        """
        Return the heights for all rows.
        Or None when there is not enough space.
        """
        pass

class VSplit(_Split):
    """
    Several layouts, one stacked left/right of the other. ::

        +---------+----------+
        |         |          |
        |         |          |
        +---------+----------+

    By default, this doesn't display a vertical line between the children, but
    if this is something you need, then create a HSplit as follows::

        VSplit(children=[ ... ], padding_char='|',
               padding=1, padding_style='#ffff00')

    :param children: List of child :class:`.Container` objects.
    :param window_too_small: A :class:`.Container` object that is displayed if
        there is not enough space for all the children. By default, this is a
        "Window too small" message.
    :param align: `HorizontalAlign` value.
    :param width: When given, use this width instead of looking at the children.
    :param height: When given, use this height instead of looking at the children.
    :param z_index: (int or None) When specified, this can be used to bring
        element in front of floating elements.  `None` means: inherit from parent.
    :param style: A style string.
    :param modal: ``True`` or ``False``.
    :param key_bindings: ``None`` or a :class:`.KeyBindings` object.

    :param padding: (`Dimension` or int), size to be used for the padding.
    :param padding_char: Character to be used for filling in the padding.
    :param padding_style: Style to applied to the padding.
    """

    def __init__(self, children: Sequence[AnyContainer], window_too_small: Container | None=None, align: HorizontalAlign=HorizontalAlign.JUSTIFY, padding: AnyDimension=0, padding_char: str | None=None, padding_style: str='', width: AnyDimension=None, height: AnyDimension=None, z_index: int | None=None, modal: bool=False, key_bindings: KeyBindingsBase | None=None, style: str | Callable[[], str]='') -> None:
        super().__init__(children=children, window_too_small=window_too_small, padding=padding, padding_char=padding_char, padding_style=padding_style, width=width, height=height, z_index=z_index, modal=modal, key_bindings=key_bindings, style=style)
        self.align = align
        self._children_cache: SimpleCache[tuple[Container, ...], list[Container]] = SimpleCache(maxsize=1)
        self._remaining_space_window = Window()

    @property
    def _all_children(self) -> list[Container]:
        """
        List of child objects, including padding.
        """
        pass

    def _divide_widths(self, width: int) -> list[int] | None:
        """
        Return the widths for all columns.
        Or None when there is not enough space.
        """
        pass

    def write_to_screen(self, screen: Screen, mouse_handlers: MouseHandlers, write_position: WritePosition, parent_style: str, erase_bg: bool, z_index: int | None) -> None:
        """
        Render the prompt to a `Screen` instance.

        :param screen: The :class:`~prompt_toolkit.layout.screen.Screen` class
            to which the output has to be written.
        """
        pass

class FloatContainer(Container):
    """
    Container which can contain another container for the background, as well
    as a list of floating containers on top of it.

    Example Usage::

        FloatContainer(content=Window(...),
                       floats=[
                           Float(xcursor=True,
                                ycursor=True,
                                content=CompletionsMenu(...))
                       ])

    :param z_index: (int or None) When specified, this can be used to bring
        element in front of floating elements.  `None` means: inherit from parent.
        This is the z_index for the whole `Float` container as a whole.
    """

    def __init__(self, content: AnyContainer, floats: list[Float], modal: bool=False, key_bindings: KeyBindingsBase | None=None, style: str | Callable[[], str]='', z_index: int | None=None) -> None:
        self.content = to_container(content)
        self.floats = floats
        self.modal = modal
        self.key_bindings = key_bindings
        self.style = style
        self.z_index = z_index

    def preferred_height(self, width: int, max_available_height: int) -> Dimension:
        """
        Return the preferred height of the float container.
        (We don't care about the height of the floats, they should always fit
        into the dimensions provided by the container.)
        """
        pass

    def _draw_float(self, fl: Float, screen: Screen, mouse_handlers: MouseHandlers, write_position: WritePosition, style: str, erase_bg: bool, z_index: int | None) -> None:
        """Draw a single Float."""
        pass

    def _area_is_empty(self, screen: Screen, write_position: WritePosition) -> bool:
        """
        Return True when the area below the write position is still empty.
        (For floats that should not hide content underneath.)
        """
        pass

class Float:
    """
    Float for use in a :class:`.FloatContainer`.
    Except for the `content` parameter, all other options are optional.

    :param content: :class:`.Container` instance.

    :param width: :class:`.Dimension` or callable which returns a :class:`.Dimension`.
    :param height: :class:`.Dimension` or callable which returns a :class:`.Dimension`.

    :param left: Distance to the left edge of the :class:`.FloatContainer`.
    :param right: Distance to the right edge of the :class:`.FloatContainer`.
    :param top: Distance to the top of the :class:`.FloatContainer`.
    :param bottom: Distance to the bottom of the :class:`.FloatContainer`.

    :param attach_to_window: Attach to the cursor from this window, instead of
        the current window.
    :param hide_when_covering_content: Hide the float when it covers content underneath.
    :param allow_cover_cursor: When `False`, make sure to display the float
        below the cursor. Not on top of the indicated position.
    :param z_index: Z-index position. For a Float, this needs to be at least
        one. It is relative to the z_index of the parent container.
    :param transparent: :class:`.Filter` indicating whether this float needs to be
        drawn transparently.
    """

    def __init__(self, content: AnyContainer, top: int | None=None, right: int | None=None, bottom: int | None=None, left: int | None=None, width: int | Callable[[], int] | None=None, height: int | Callable[[], int] | None=None, xcursor: bool=False, ycursor: bool=False, attach_to_window: AnyContainer | None=None, hide_when_covering_content: bool=False, allow_cover_cursor: bool=False, z_index: int=1, transparent: bool=False) -> None:
        assert z_index >= 1
        self.left = left
        self.right = right
        self.top = top
        self.bottom = bottom
        self.width = width
        self.height = height
        self.xcursor = xcursor
        self.ycursor = ycursor
        self.attach_to_window = to_window(attach_to_window) if attach_to_window else None
        self.content = to_container(content)
        self.hide_when_covering_content = hide_when_covering_content
        self.allow_cover_cursor = allow_cover_cursor
        self.z_index = z_index
        self.transparent = to_filter(transparent)

    def __repr__(self) -> str:
        return 'Float(content=%r)' % self.content

class WindowRenderInfo:
    """
    Render information for the last render time of this control.
    It stores mapping information between the input buffers (in case of a
    :class:`~prompt_toolkit.layout.controls.BufferControl`) and the actual
    render position on the output screen.

    (Could be used for implementation of the Vi 'H' and 'L' key bindings as
    well as implementing mouse support.)

    :param ui_content: The original :class:`.UIContent` instance that contains
        the whole input, without clipping. (ui_content)
    :param horizontal_scroll: The horizontal scroll of the :class:`.Window` instance.
    :param vertical_scroll: The vertical scroll of the :class:`.Window` instance.
    :param window_width: The width of the window that displays the content,
        without the margins.
    :param window_height: The height of the window that displays the content.
    :param configured_scroll_offsets: The scroll offsets as configured for the
        :class:`Window` instance.
    :param visible_line_to_row_col: Mapping that maps the row numbers on the
        displayed screen (starting from zero for the first visible line) to
        (row, col) tuples pointing to the row and column of the :class:`.UIContent`.
    :param rowcol_to_yx: Mapping that maps (row, column) tuples representing
        coordinates of the :class:`UIContent` to (y, x) absolute coordinates at
        the rendered screen.
    """

    def __init__(self, window: Window, ui_content: UIContent, horizontal_scroll: int, vertical_scroll: int, window_width: int, window_height: int, configured_scroll_offsets: ScrollOffsets, visible_line_to_row_col: dict[int, tuple[int, int]], rowcol_to_yx: dict[tuple[int, int], tuple[int, int]], x_offset: int, y_offset: int, wrap_lines: bool) -> None:
        self.window = window
        self.ui_content = ui_content
        self.vertical_scroll = vertical_scroll
        self.window_width = window_width
        self.window_height = window_height
        self.configured_scroll_offsets = configured_scroll_offsets
        self.visible_line_to_row_col = visible_line_to_row_col
        self.wrap_lines = wrap_lines
        self._rowcol_to_yx = rowcol_to_yx
        self._x_offset = x_offset
        self._y_offset = y_offset

    @property
    def cursor_position(self) -> Point:
        """
        Return the cursor position coordinates, relative to the left/top corner
        of the rendered screen.
        """
        pass

    @property
    def applied_scroll_offsets(self) -> ScrollOffsets:
        """
        Return a :class:`.ScrollOffsets` instance that indicates the actual
        offset. This can be less than or equal to what's configured. E.g, when
        the cursor is completely at the top, the top offset will be zero rather
        than what's configured.
        """
        pass

    @property
    def displayed_lines(self) -> list[int]:
        """
        List of all the visible rows. (Line numbers of the input buffer.)
        The last line may not be entirely visible.
        """
        pass

    @property
    def input_line_to_visible_line(self) -> dict[int, int]:
        """
        Return the dictionary mapping the line numbers of the input buffer to
        the lines of the screen. When a line spans several rows at the screen,
        the first row appears in the dictionary.
        """
        pass

    def first_visible_line(self, after_scroll_offset: bool=False) -> int:
        """
        Return the line number (0 based) of the input document that corresponds
        with the first visible line.
        """
        pass

    def last_visible_line(self, before_scroll_offset: bool=False) -> int:
        """
        Like `first_visible_line`, but for the last visible line.
        """
        pass

    def center_visible_line(self, before_scroll_offset: bool=False, after_scroll_offset: bool=False) -> int:
        """
        Like `first_visible_line`, but for the center visible line.
        """
        pass

    @property
    def content_height(self) -> int:
        """
        The full height of the user control.
        """
        pass

    @property
    def full_height_visible(self) -> bool:
        """
        True when the full height is visible (There is no vertical scroll.)
        """
        pass

    @property
    def top_visible(self) -> bool:
        """
        True when the top of the buffer is visible.
        """
        pass

    @property
    def bottom_visible(self) -> bool:
        """
        True when the bottom of the buffer is visible.
        """
        pass

    @property
    def vertical_scroll_percentage(self) -> int:
        """
        Vertical scroll as a percentage. (0 means: the top is visible,
        100 means: the bottom is visible.)
        """
        pass

    def get_height_for_line(self, lineno: int) -> int:
        """
        Return the height of the given line.
        (The height that it would take, if this line became visible.)
        """
        pass

class ScrollOffsets:
    """
    Scroll offsets for the :class:`.Window` class.

    Note that left/right offsets only make sense if line wrapping is disabled.
    """

    def __init__(self, top: int | Callable[[], int]=0, bottom: int | Callable[[], int]=0, left: int | Callable[[], int]=0, right: int | Callable[[], int]=0) -> None:
        self._top = top
        self._bottom = bottom
        self._left = left
        self._right = right

    def __repr__(self) -> str:
        return 'ScrollOffsets(top={!r}, bottom={!r}, left={!r}, right={!r})'.format(self._top, self._bottom, self._left, self._right)

class ColorColumn:
    """
    Column for a :class:`.Window` to be colored.
    """

    def __init__(self, position: int, style: str='class:color-column') -> None:
        self.position = position
        self.style = style
_in_insert_mode = vi_insert_mode | emacs_insert_mode

class WindowAlign(Enum):
    """
    Alignment of the Window content.

    Note that this is different from `HorizontalAlign` and `VerticalAlign`,
    which are used for the alignment of the child containers in respectively
    `VSplit` and `HSplit`.
    """
    LEFT = 'LEFT'
    RIGHT = 'RIGHT'
    CENTER = 'CENTER'

class Window(Container):
    """
    Container that holds a control.

    :param content: :class:`.UIControl` instance.
    :param width: :class:`.Dimension` instance or callable.
    :param height: :class:`.Dimension` instance or callable.
    :param z_index: When specified, this can be used to bring element in front
        of floating elements.
    :param dont_extend_width: When `True`, don't take up more width then the
                              preferred width reported by the control.
    :param dont_extend_height: When `True`, don't take up more width then the
                               preferred height reported by the control.
    :param ignore_content_width: A `bool` or :class:`.Filter` instance. Ignore
        the :class:`.UIContent` width when calculating the dimensions.
    :param ignore_content_height: A `bool` or :class:`.Filter` instance. Ignore
        the :class:`.UIContent` height when calculating the dimensions.
    :param left_margins: A list of :class:`.Margin` instance to be displayed on
        the left. For instance: :class:`~prompt_toolkit.layout.NumberedMargin`
        can be one of them in order to show line numbers.
    :param right_margins: Like `left_margins`, but on the other side.
    :param scroll_offsets: :class:`.ScrollOffsets` instance, representing the
        preferred amount of lines/columns to be always visible before/after the
        cursor. When both top and bottom are a very high number, the cursor
        will be centered vertically most of the time.
    :param allow_scroll_beyond_bottom: A `bool` or
        :class:`.Filter` instance. When True, allow scrolling so far, that the
        top part of the content is not visible anymore, while there is still
        empty space available at the bottom of the window. In the Vi editor for
        instance, this is possible. You will see tildes while the top part of
        the body is hidden.
    :param wrap_lines: A `bool` or :class:`.Filter` instance. When True, don't
        scroll horizontally, but wrap lines instead.
    :param get_vertical_scroll: Callable that takes this window
        instance as input and returns a preferred vertical scroll.
        (When this is `None`, the scroll is only determined by the last and
        current cursor position.)
    :param get_horizontal_scroll: Callable that takes this window
        instance as input and returns a preferred vertical scroll.
    :param always_hide_cursor: A `bool` or
        :class:`.Filter` instance. When True, never display the cursor, even
        when the user control specifies a cursor position.
    :param cursorline: A `bool` or :class:`.Filter` instance. When True,
        display a cursorline.
    :param cursorcolumn: A `bool` or :class:`.Filter` instance. When True,
        display a cursorcolumn.
    :param colorcolumns: A list of :class:`.ColorColumn` instances that
        describe the columns to be highlighted, or a callable that returns such
        a list.
    :param align: :class:`.WindowAlign` value or callable that returns an
        :class:`.WindowAlign` value. alignment of content.
    :param style: A style string. Style to be applied to all the cells in this
        window. (This can be a callable that returns a string.)
    :param char: (string) Character to be used for filling the background. This
        can also be a callable that returns a character.
    :param get_line_prefix: None or a callable that returns formatted text to
        be inserted before a line. It takes a line number (int) and a
        wrap_count and returns formatted text. This can be used for
        implementation of line continuations, things like Vim "breakindent" and
        so on.
    """

    def __init__(self, content: UIControl | None=None, width: AnyDimension=None, height: AnyDimension=None, z_index: int | None=None, dont_extend_width: FilterOrBool=False, dont_extend_height: FilterOrBool=False, ignore_content_width: FilterOrBool=False, ignore_content_height: FilterOrBool=False, left_margins: Sequence[Margin] | None=None, right_margins: Sequence[Margin] | None=None, scroll_offsets: ScrollOffsets | None=None, allow_scroll_beyond_bottom: FilterOrBool=False, wrap_lines: FilterOrBool=False, get_vertical_scroll: Callable[[Window], int] | None=None, get_horizontal_scroll: Callable[[Window], int] | None=None, always_hide_cursor: FilterOrBool=False, cursorline: FilterOrBool=False, cursorcolumn: FilterOrBool=False, colorcolumns: None | list[ColorColumn] | Callable[[], list[ColorColumn]]=None, align: WindowAlign | Callable[[], WindowAlign]=WindowAlign.LEFT, style: str | Callable[[], str]='', char: None | str | Callable[[], str]=None, get_line_prefix: GetLinePrefixCallable | None=None) -> None:
        self.allow_scroll_beyond_bottom = to_filter(allow_scroll_beyond_bottom)
        self.always_hide_cursor = to_filter(always_hide_cursor)
        self.wrap_lines = to_filter(wrap_lines)
        self.cursorline = to_filter(cursorline)
        self.cursorcolumn = to_filter(cursorcolumn)
        self.content = content or DummyControl()
        self.dont_extend_width = to_filter(dont_extend_width)
        self.dont_extend_height = to_filter(dont_extend_height)
        self.ignore_content_width = to_filter(ignore_content_width)
        self.ignore_content_height = to_filter(ignore_content_height)
        self.left_margins = left_margins or []
        self.right_margins = right_margins or []
        self.scroll_offsets = scroll_offsets or ScrollOffsets()
        self.get_vertical_scroll = get_vertical_scroll
        self.get_horizontal_scroll = get_horizontal_scroll
        self.colorcolumns = colorcolumns or []
        self.align = align
        self.style = style
        self.char = char
        self.get_line_prefix = get_line_prefix
        self.width = width
        self.height = height
        self.z_index = z_index
        self._ui_content_cache: SimpleCache[tuple[int, int, int], UIContent] = SimpleCache(maxsize=8)
        self._margin_width_cache: SimpleCache[tuple[Margin, int], int] = SimpleCache(maxsize=1)
        self.reset()

    def __repr__(self) -> str:
        return 'Window(content=%r)' % self.content

    def _get_margin_width(self, margin: Margin) -> int:
        """
        Return the width for this margin.
        (Calculate only once per render time.)
        """
        pass

    def _get_total_margin_width(self) -> int:
        """
        Calculate and return the width of the margin (left + right).
        """
        pass

    def preferred_width(self, max_available_width: int) -> Dimension:
        """
        Calculate the preferred width for this window.
        """
        pass

    def preferred_height(self, width: int, max_available_height: int) -> Dimension:
        """
        Calculate the preferred height for this window.
        """
        pass

    @staticmethod
    def _merge_dimensions(dimension: Dimension | None, get_preferred: Callable[[], int | None], dont_extend: bool=False) -> Dimension:
        """
        Take the Dimension from this `Window` class and the received preferred
        size from the `UIControl` and return a `Dimension` to report to the
        parent container.
        """
        pass

    def _get_ui_content(self, width: int, height: int) -> UIContent:
        """
        Create a `UIContent` instance.
        """
        pass

    def _get_digraph_char(self) -> str | None:
        """Return `False`, or the Digraph symbol to be used."""
        pass

    def write_to_screen(self, screen: Screen, mouse_handlers: MouseHandlers, write_position: WritePosition, parent_style: str, erase_bg: bool, z_index: int | None) -> None:
        """
        Write window to screen. This renders the user control, the margins and
        copies everything over to the absolute position at the given screen.
        """
        pass

    def _copy_body(self, ui_content: UIContent, new_screen: Screen, write_position: WritePosition, move_x: int, width: int, vertical_scroll: int=0, horizontal_scroll: int=0, wrap_lines: bool=False, highlight_lines: bool=False, vertical_scroll_2: int=0, always_hide_cursor: bool=False, has_focus: bool=False, align: WindowAlign=WindowAlign.LEFT, get_line_prefix: Callable[[int, int], AnyFormattedText] | None=None) -> tuple[dict[int, tuple[int, int]], dict[tuple[int, int], tuple[int, int]]]:
        """
        Copy the UIContent into the output screen.
        Return (visible_line_to_row_col, rowcol_to_yx) tuple.

        :param get_line_prefix: None or a callable that takes a line number
            (int) and a wrap_count (int) and returns formatted text.
        """
        pass

    def _fill_bg(self, screen: Screen, write_position: WritePosition, erase_bg: bool) -> None:
        """
        Erase/fill the background.
        (Useful for floats and when a `char` has been given.)
        """
        pass

    def _highlight_digraph(self, new_screen: Screen) -> None:
        """
        When we are in Vi digraph mode, put a question mark underneath the
        cursor.
        """
        pass

    def _show_key_processor_key_buffer(self, new_screen: Screen) -> None:
        """
        When the user is typing a key binding that consists of several keys,
        display the last pressed key if the user is in insert mode and the key
        is meaningful to be displayed.
        E.g. Some people want to bind 'jj' to escape in Vi insert mode. But the
             first 'j' needs to be displayed in order to get some feedback.
        """
        pass

    def _highlight_cursorlines(self, new_screen: Screen, cpos: Point, x: int, y: int, width: int, height: int) -> None:
        """
        Highlight cursor row/column.
        """
        pass

    def _copy_margin(self, margin_content: UIContent, new_screen: Screen, write_position: WritePosition, move_x: int, width: int) -> None:
        """
        Copy characters from the margin screen to the real screen.
        """
        pass

    def _scroll(self, ui_content: UIContent, width: int, height: int) -> None:
        """
        Scroll body. Ensure that the cursor is visible.
        """
        pass

    def _scroll_when_linewrapping(self, ui_content: UIContent, width: int, height: int) -> None:
        """
        Scroll to make sure the cursor position is visible and that we maintain
        the requested scroll offset.

        Set `self.horizontal_scroll/vertical_scroll`.
        """
        pass

    def _scroll_without_linewrapping(self, ui_content: UIContent, width: int, height: int) -> None:
        """
        Scroll to make sure the cursor position is visible and that we maintain
        the requested scroll offset.

        Set `self.horizontal_scroll/vertical_scroll`.
        """
        pass

    def _mouse_handler(self, mouse_event: MouseEvent) -> NotImplementedOrNone:
        """
        Mouse handler. Called when the UI control doesn't handle this
        particular event.

        Return `NotImplemented` if nothing was done as a consequence of this
        key binding (no UI invalidate required in that case).
        """
        pass

    def _scroll_down(self) -> None:
        """Scroll window down."""
        pass

    def _scroll_up(self) -> None:
        """Scroll window up."""
        pass

class ConditionalContainer(Container):
    """
    Wrapper around any other container that can change the visibility. The
    received `filter` determines whether the given container should be
    displayed or not.

    :param content: :class:`.Container` instance.
    :param filter: :class:`.Filter` instance.
    """

    def __init__(self, content: AnyContainer, filter: FilterOrBool) -> None:
        self.content = to_container(content)
        self.filter = to_filter(filter)

    def __repr__(self) -> str:
        return f'ConditionalContainer({self.content!r}, filter={self.filter!r})'

class DynamicContainer(Container):
    """
    Container class that dynamically returns any Container.

    :param get_container: Callable that returns a :class:`.Container` instance
        or any widget with a ``__pt_container__`` method.
    """

    def __init__(self, get_container: Callable[[], AnyContainer]) -> None:
        self.get_container = get_container

    def _get_container(self) -> Container:
        """
        Return the current container object.

        We call `to_container`, because `get_container` can also return a
        widget with a ``__pt_container__`` method.
        """
        pass

def to_container(container: AnyContainer) -> Container:
    """
    Make sure that the given object is a :class:`.Container`.
    """
    pass

def to_window(container: AnyContainer) -> Window:
    """
    Make sure that the given argument is a :class:`.Window`.
    """
    pass

def is_container(value: object) -> TypeGuard[AnyContainer]:
    """
    Checks whether the given value is a container object
    (for use in assert statements).
    """
    pass
