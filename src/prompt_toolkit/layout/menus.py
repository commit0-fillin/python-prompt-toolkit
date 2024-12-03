from __future__ import annotations
import math
from itertools import zip_longest
from typing import TYPE_CHECKING, Callable, Iterable, Sequence, TypeVar, cast
from weakref import WeakKeyDictionary
from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import CompletionState
from prompt_toolkit.completion import Completion
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition, FilterOrBool, has_completions, is_done, to_filter
from prompt_toolkit.formatted_text import StyleAndTextTuples, fragment_list_width, to_formatted_text
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout.utils import explode_text_fragments
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from prompt_toolkit.utils import get_cwidth
from .containers import ConditionalContainer, HSplit, ScrollOffsets, Window
from .controls import GetLinePrefixCallable, UIContent, UIControl
from .dimension import Dimension
from .margins import ScrollbarMargin
if TYPE_CHECKING:
    from prompt_toolkit.key_binding.key_bindings import KeyBindings, NotImplementedOrNone
__all__ = ['CompletionsMenu', 'MultiColumnCompletionsMenu']
E = KeyPressEvent

class CompletionsMenuControl(UIControl):
    """
    Helper for drawing the complete menu to the screen.

    :param scroll_offset: Number (integer) representing the preferred amount of
        completions to be displayed before and after the current one. When this
        is a very high number, the current completion will be shown in the
        middle most of the time.
    """
    MIN_WIDTH = 7

    def create_content(self, width: int, height: int) -> UIContent:
        """
        Create a UIContent object for this control.
        """
        app = get_app()
        complete_state = app.current_buffer.complete_state
        if complete_state is None:
            return UIContent()

        def get_line(i: int) -> StyleAndTextTuples:
            if i >= len(complete_state.completions):
                return []
            completion = complete_state.completions[i]
            is_current = i == complete_state.complete_index

            menu_width = self._get_menu_width(width, complete_state)
            menu_meta_width = self._get_menu_meta_width(width, complete_state)

            fragments = _get_menu_item_fragments(completion, is_current, menu_width)

            if menu_meta_width:
                fragments += _get_menu_item_fragments(completion, is_current, menu_meta_width, space_after=True)

            return fragments

        return UIContent(
            get_line=get_line,
            line_count=len(complete_state.completions),
            show_cursor=False,
        )

    def _show_meta(self, complete_state: CompletionState) -> bool:
        """
        Return ``True`` if we need to show a column with meta information.
        """
        return any(c.display_meta for c in complete_state.completions)

    def _get_menu_width(self, max_width: int, complete_state: CompletionState) -> int:
        """
        Return the width of the main column.
        """
        if complete_state.completions:
            max_completion_width = max(get_cwidth(c.display_text) for c in complete_state.completions)
            return min(max_completion_width, max_width)
        return 0

    def _get_menu_meta_width(self, max_width: int, complete_state: CompletionState) -> int:
        """
        Return the width of the meta column.
        """
        if self._show_meta(complete_state):
            max_meta_width = max(get_cwidth(c.display_meta or '') for c in complete_state.completions)
            return min(max_meta_width, max_width // 2)
        return 0

    def mouse_handler(self, mouse_event: MouseEvent) -> NotImplementedOrNone:
        """
        Handle mouse events: clicking and scrolling.
        """
        app = get_app()
        complete_state = app.current_buffer.complete_state

        if complete_state is None:
            return NotImplemented

        if mouse_event.event_type == MouseEventType.MOUSE_UP:
            index = mouse_event.position.y

            if 0 <= index < len(complete_state.completions):
                complete_state.go_to_index(index)
                app.current_buffer.apply_completion(complete_state.current_completion)
                return None

        elif mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            complete_state.complete_next()
            return None

        elif mouse_event.event_type == MouseEventType.SCROLL_UP:
            complete_state.complete_previous()
            return None

        return NotImplemented

def _get_menu_item_fragments(completion: Completion, is_current_completion: bool, width: int, space_after: bool=False) -> StyleAndTextTuples:
    """
    Get the style/text tuples for a menu item, styled and trimmed to the given
    width.
    """
    style = 'class:completion-menu.completion'
    if is_current_completion:
        style += '.current'

    text = completion.display_text
    if len(text) > width:
        text = text[:width - 3] + '...'
    else:
        text = text.ljust(width)

    fragments = [(style, text)]

    if space_after:
        fragments.append(('', ' '))

    return fragments

def _trim_formatted_text(formatted_text: StyleAndTextTuples, max_width: int) -> tuple[StyleAndTextTuples, int]:
    """
    Trim the text to `max_width`, append dots when the text is too long.
    Returns (text, width) tuple.
    """
    total_width = 0
    result: StyleAndTextTuples = []

    for style, text in formatted_text:
        # Calculate new width.
        new_width = total_width + get_cwidth(text)

        if new_width < max_width:
            result.append((style, text))
            total_width = new_width
        else:
            # Trim.
            result.append((style, text[:max_width - total_width - 3] + '...'))
            total_width = max_width
            break

    return result, total_width

class CompletionsMenu(ConditionalContainer):

    def __init__(self, max_height: int | None=None, scroll_offset: int | Callable[[], int]=0, extra_filter: FilterOrBool=True, display_arrows: FilterOrBool=False, z_index: int=10 ** 8) -> None:
        extra_filter = to_filter(extra_filter)
        display_arrows = to_filter(display_arrows)
        super().__init__(content=Window(content=CompletionsMenuControl(), width=Dimension(min=8), height=Dimension(min=1, max=max_height), scroll_offsets=ScrollOffsets(top=scroll_offset, bottom=scroll_offset), right_margins=[ScrollbarMargin(display_arrows=display_arrows)], dont_extend_width=True, style='class:completion-menu', z_index=z_index), filter=extra_filter & has_completions & ~is_done)

class MultiColumnCompletionMenuControl(UIControl):
    """
    Completion menu that displays all the completions in several columns.
    When there are more completions than space for them to be displayed, an
    arrow is shown on the left or right side.

    `min_rows` indicates how many rows will be available in any possible case.
    When this is larger than one, it will try to use less columns and more
    rows until this value is reached.
    Be careful passing in a too big value, if less than the given amount of
    rows are available, more columns would have been required, but
    `preferred_width` doesn't know about that and reports a too small value.
    This results in less completions displayed and additional scrolling.
    (It's a limitation of how the layout engine currently works: first the
    widths are calculated, then the heights.)

    :param suggested_max_column_width: The suggested max width of a column.
        The column can still be bigger than this, but if there is place for two
        columns of this width, we will display two columns. This to avoid that
        if there is one very wide completion, that it doesn't significantly
        reduce the amount of columns.
    """
    _required_margin = 3

    def __init__(self, min_rows: int=3, suggested_max_column_width: int=30) -> None:
        assert min_rows >= 1
        self.min_rows = min_rows
        self.suggested_max_column_width = suggested_max_column_width
        self.scroll = 0
        self._column_width_for_completion_state: WeakKeyDictionary[CompletionState, tuple[int, int]] = WeakKeyDictionary()
        self._rendered_rows = 0
        self._rendered_columns = 0
        self._total_columns = 0
        self._render_pos_to_completion: dict[tuple[int, int], Completion] = {}
        self._render_left_arrow = False
        self._render_right_arrow = False
        self._render_width = 0

    def preferred_width(self, max_available_width: int) -> int | None:
        """
        Preferred width: prefer to use at least min_rows, but otherwise as much
        as possible horizontally.
        """
        complete_state = get_app().current_buffer.complete_state
        if complete_state is None:
            return 0

        column_width = self._get_column_width(complete_state)
        result = int(column_width * min(len(complete_state.completions), self.min_rows))
        return min(result, max_available_width)

    def preferred_height(self, width: int, max_available_height: int, wrap_lines: bool, get_line_prefix: GetLinePrefixCallable | None) -> int | None:
        """
        Preferred height: as much as needed in order to display all the completions.
        """
        complete_state = get_app().current_buffer.complete_state
        if complete_state is None:
            return 0

        column_width = self._get_column_width(complete_state)
        column_count = max(1, width // column_width)
        row_count = int(ceil(len(complete_state.completions) / float(column_count)))
        return min(row_count, max_available_height)

    def create_content(self, width: int, height: int) -> UIContent:
        """
        Create a UIContent object for this menu.
        """
        complete_state = get_app().current_buffer.complete_state
        if complete_state is None:
            return UIContent()

        column_width = self._get_column_width(complete_state)
        column_count = max(1, width // column_width)

        visible_columns = min(column_count, int(ceil(len(complete_state.completions) / float(height))))
        visible_width = visible_columns * column_width

        def get_line(i: int) -> StyleAndTextTuples:
            result: StyleAndTextTuples = []
            for c in range(visible_columns):
                index = c * height + i
                if index >= len(complete_state.completions):
                    return result

                completion = complete_state.completions[index]
                style = 'class:completion-menu.completion'
                if index == complete_state.complete_index:
                    style += '.current'

                text = completion.display_text
                text = text[:column_width].ljust(column_width)

                result.append((style, text))
            return result

        return UIContent(
            get_line=get_line,
            line_count=height,
            show_cursor=False,
        )

    def _get_column_width(self, completion_state: CompletionState) -> int:
        """
        Return the width of each column.
        """
        max_width = max(get_cwidth(c.display_text) for c in completion_state.completions)
        return max(self.suggested_max_column_width, max_width)

    def mouse_handler(self, mouse_event: MouseEvent) -> NotImplementedOrNone:
        """
        Handle scroll and click events.
        """
        app = get_app()
        completion_state = app.current_buffer.complete_state
        if completion_state is None:
            return NotImplemented

        if mouse_event.event_type == MouseEventType.MOUSE_UP:
            column_width = self._get_column_width(completion_state)
            column_count = mouse_event.position.x // column_width
            row_count = mouse_event.position.y

            index = column_count * self._rendered_rows + row_count

            if 0 <= index < len(completion_state.completions):
                completion_state.go_to_index(index)
                app.current_buffer.apply_completion(completion_state.current_completion)
                return None

        elif mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            self._scroll_down()
            return None

        elif mouse_event.event_type == MouseEventType.SCROLL_UP:
            self._scroll_up()
            return None

        return NotImplemented

    def get_key_bindings(self) -> KeyBindings:
        """
        Expose key bindings that handle the left/right arrow keys when the menu
        is displayed.
        """
        kb = KeyBindings()

        @kb.add('left', filter=~has_completions)
        def _(event: E) -> None:
            self._scroll_left()

        @kb.add('right', filter=~has_completions)
        def _(event: E) -> None:
            self._scroll_right()

        return kb

class MultiColumnCompletionsMenu(HSplit):
    """
    Container that displays the completions in several columns.
    When `show_meta` (a :class:`~prompt_toolkit.filters.Filter`) evaluates
    to True, it shows the meta information at the bottom.
    """

    def __init__(self, min_rows: int=3, suggested_max_column_width: int=30, show_meta: FilterOrBool=True, extra_filter: FilterOrBool=True, z_index: int=10 ** 8) -> None:
        show_meta = to_filter(show_meta)
        extra_filter = to_filter(extra_filter)
        full_filter = extra_filter & has_completions & ~is_done

        @Condition
        def any_completion_has_meta() -> bool:
            complete_state = get_app().current_buffer.complete_state
            return complete_state is not None and any((c.display_meta for c in complete_state.completions))
        completions_window = ConditionalContainer(content=Window(content=MultiColumnCompletionMenuControl(min_rows=min_rows, suggested_max_column_width=suggested_max_column_width), width=Dimension(min=8), height=Dimension(min=1)), filter=full_filter)
        meta_window = ConditionalContainer(content=Window(content=_SelectedCompletionMetaControl()), filter=full_filter & show_meta & any_completion_has_meta)
        super().__init__([completions_window, meta_window], z_index=z_index)

class _SelectedCompletionMetaControl(UIControl):
    """
    Control that shows the meta information of the selected completion.
    """

    def preferred_width(self, max_available_width: int) -> int | None:
        """
        Report the width of the longest meta text as the preferred width of this control.

        It could be that we use less width, but this way, we're sure that the
        layout doesn't change when we select another completion (E.g. that
        completions are suddenly shown in more or fewer columns.)
        """
        pass
