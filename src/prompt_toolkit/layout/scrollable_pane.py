from __future__ import annotations
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import FilterOrBool, to_filter
from prompt_toolkit.key_binding import KeyBindingsBase
from prompt_toolkit.mouse_events import MouseEvent
from .containers import Container, ScrollOffsets
from .dimension import AnyDimension, Dimension, sum_layout_dimensions, to_dimension
from .mouse_handlers import MouseHandler, MouseHandlers
from .screen import Char, Screen, WritePosition
__all__ = ['ScrollablePane']
MAX_AVAILABLE_HEIGHT = 10000

class ScrollablePane(Container):
    """
    Container widget that exposes a larger virtual screen to its content and
    displays it in a vertical scrollbale region.

    Typically this is wrapped in a large `HSplit` container. Make sure in that
    case to not specify a `height` dimension of the `HSplit`, so that it will
    scale according to the content.

    .. note::

        If you want to display a completion menu for widgets in this
        `ScrollablePane`, then it's still a good practice to use a
        `FloatContainer` with a `CompletionsMenu` in a `Float` at the top-level
        of the layout hierarchy, rather then nesting a `FloatContainer` in this
        `ScrollablePane`. (Otherwise, it's possible that the completion menu
        is clipped.)

    :param content: The content container.
    :param scrolloffset: Try to keep the cursor within this distance from the
        top/bottom (left/right offset is not used).
    :param keep_cursor_visible: When `True`, automatically scroll the pane so
        that the cursor (of the focused window) is always visible.
    :param keep_focused_window_visible: When `True`, automatically scroll the
        pane so that the focused window is visible, or as much visible as
        possible if it doesn't completely fit the screen.
    :param max_available_height: Always constraint the height to this amount
        for performance reasons.
    :param width: When given, use this width instead of looking at the children.
    :param height: When given, use this height instead of looking at the children.
    :param show_scrollbar: When `True` display a scrollbar on the right.
    """

    def __init__(self, content: Container, scroll_offsets: ScrollOffsets | None=None, keep_cursor_visible: FilterOrBool=True, keep_focused_window_visible: FilterOrBool=True, max_available_height: int=MAX_AVAILABLE_HEIGHT, width: AnyDimension=None, height: AnyDimension=None, show_scrollbar: FilterOrBool=True, display_arrows: FilterOrBool=True, up_arrow_symbol: str='^', down_arrow_symbol: str='v') -> None:
        self.content = content
        self.scroll_offsets = scroll_offsets or ScrollOffsets(top=1, bottom=1)
        self.keep_cursor_visible = to_filter(keep_cursor_visible)
        self.keep_focused_window_visible = to_filter(keep_focused_window_visible)
        self.max_available_height = max_available_height
        self.width = width
        self.height = height
        self.show_scrollbar = to_filter(show_scrollbar)
        self.display_arrows = to_filter(display_arrows)
        self.up_arrow_symbol = up_arrow_symbol
        self.down_arrow_symbol = down_arrow_symbol
        self.vertical_scroll = 0

    def __repr__(self) -> str:
        return f'ScrollablePane({self.content!r})'

    def write_to_screen(self, screen: Screen, mouse_handlers: MouseHandlers, write_position: WritePosition, parent_style: str, erase_bg: bool, z_index: int | None) -> None:
        """
        Render scrollable pane content.

        This works by rendering on an off-screen canvas, and copying over the
        visible region.
        """
        temp_screen = Screen()
        temp_mouse_handlers = MouseHandlers()

        # Render content to temp_screen
        self.content.write_to_screen(
            temp_screen,
            temp_mouse_handlers,
            WritePosition(0, 0, write_position.width, self.max_available_height),
            parent_style,
            erase_bg,
            z_index,
        )

        # Calculate visible area
        visible_height = min(write_position.height, temp_screen.height - self.vertical_scroll)

        # Copy visible area to main screen
        self._copy_over_screen(screen, temp_screen, write_position, write_position.width)
        self._copy_over_mouse_handlers(mouse_handlers, temp_mouse_handlers, write_position, write_position.width)
        self._copy_over_write_positions(screen, temp_screen, write_position)

        # Draw scrollbar if needed
        if self.show_scrollbar() and temp_screen.height > write_position.height:
            self._draw_scrollbar(write_position, temp_screen.height, screen)

        # Make sure the cursor is visible
        cursor_position = temp_screen.get_cursor_position(self.content)
        self._make_window_visible(visible_height, temp_screen.height, write_position, cursor_position)

    def _clip_point_to_visible_area(self, point: Point, write_position: WritePosition) -> Point:
        """
        Ensure that the cursor and menu positions are always reported within the visible area.
        """
        x = max(0, min(point.x, write_position.width - 1))
        y = max(0, min(point.y - self.vertical_scroll, write_position.height - 1))
        return Point(x=x, y=y)

    def _copy_over_screen(self, screen: Screen, temp_screen: Screen, write_position: WritePosition, virtual_width: int) -> None:
        """
        Copy over visible screen content and "zero width escape sequences".
        """
        for y in range(min(write_position.height, temp_screen.height - self.vertical_scroll)):
            for x in range(min(write_position.width, virtual_width)):
                screen_y = write_position.ypos + y
                screen_x = write_position.xpos + x
                temp_y = y + self.vertical_scroll
                temp_x = x

                screen.data_buffer[screen_y][screen_x] = temp_screen.data_buffer[temp_y][temp_x]
                screen.zero_width_escapes[screen_y][screen_x] = temp_screen.zero_width_escapes[temp_y][temp_x]

    def _copy_over_mouse_handlers(self, mouse_handlers: MouseHandlers, temp_mouse_handlers: MouseHandlers, write_position: WritePosition, virtual_width: int) -> None:
        """
        Copy over mouse handlers from virtual screen to real screen.

        Note: we take `virtual_width` because we don't want to copy over mouse
              handlers that we possibly have behind the scrollbar.
        """
        for y in range(min(write_position.height, len(temp_mouse_handlers.mouse_handlers))):
            for x in range(min(write_position.width, virtual_width)):
                screen_y = write_position.ypos + y
                screen_x = write_position.xpos + x
                temp_y = y + self.vertical_scroll
                temp_x = x

                mouse_handlers.mouse_handlers[screen_y][screen_x] = temp_mouse_handlers.mouse_handlers[temp_y][temp_x]

    def _copy_over_write_positions(self, screen: Screen, temp_screen: Screen, write_position: WritePosition) -> None:
        """
        Copy over window write positions.
        """
        for window, position in temp_screen.visible_windows_to_write_positions.items():
            new_position = WritePosition(
                xpos=position.xpos + write_position.xpos,
                ypos=position.ypos - self.vertical_scroll + write_position.ypos,
                width=position.width,
                height=position.height
            )
            screen.visible_windows_to_write_positions[window] = new_position

    def _make_window_visible(self, visible_height: int, virtual_height: int, visible_win_write_pos: WritePosition, cursor_position: Point | None) -> None:
        """
        Scroll the scrollable pane, so that this window becomes visible.

        :param visible_height: Height of this `ScrollablePane` that is rendered.
        :param virtual_height: Height of the virtual, temp screen.
        :param visible_win_write_pos: `WritePosition` of the nested window on the
            temp screen.
        :param cursor_position: The location of the cursor position of this
            window on the temp screen.
        """
        if cursor_position is None:
            return

        cursor_y = cursor_position.y

        if self.keep_cursor_visible():
            top = self.scroll_offsets.top
            bottom = self.scroll_offsets.bottom

            if cursor_y < self.vertical_scroll + top:
                self.vertical_scroll = max(0, cursor_y - top)
            elif cursor_y >= self.vertical_scroll + visible_height - bottom:
                self.vertical_scroll = min(
                    virtual_height - visible_height,
                    cursor_y - visible_height + bottom + 1
                )

        if self.keep_focused_window_visible():
            win_top = visible_win_write_pos.ypos
            win_bottom = visible_win_write_pos.ypos + visible_win_write_pos.height

            if win_top < self.vertical_scroll:
                self.vertical_scroll = win_top
            elif win_bottom > self.vertical_scroll + visible_height:
                self.vertical_scroll = win_bottom - visible_height

    def _draw_scrollbar(self, write_position: WritePosition, content_height: int, screen: Screen) -> None:
        """
        Draw the scrollbar on the screen.

        Note: There is some code duplication with the `ScrollbarMargin`
              implementation.
        """
        if not self.show_scrollbar():
            return

        scrollbar_height = write_position.height
        scrollbar_width = 1

        if content_height > write_position.height:
            fraction_visible = write_position.height / float(content_height)
            scrollbar_size = int(fraction_visible * scrollbar_height)
            scrollbar_size = max(1, scrollbar_size)

            fraction_above = self.vertical_scroll / float(content_height)
            scrollbar_start = int(fraction_above * scrollbar_height)

            x = write_position.xpos + write_position.width - 1
            y = write_position.ypos + scrollbar_start

            # Draw scrollbar background
            for i in range(scrollbar_height):
                screen.data_buffer[write_position.ypos + i][x] = Char('|', 'class:scrollbar.background')

            # Draw scrollbar itself
            for i in range(scrollbar_size):
                screen.data_buffer[y + i][x] = Char('|', 'class:scrollbar')

            # Draw arrows
            if self.display_arrows():
                screen.data_buffer[write_position.ypos][x] = Char(self.up_arrow_symbol, 'class:scrollbar.arrow')
                screen.data_buffer[write_position.ypos + scrollbar_height - 1][x] = Char(self.down_arrow_symbol, 'class:scrollbar.arrow')
