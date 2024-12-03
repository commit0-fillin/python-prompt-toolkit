"""
Search operations.

For the key bindings implementation with attached filters, check
`prompt_toolkit.key_binding.bindings.search`. (Use these for new key bindings
instead of calling these function directly.)
"""
from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING
from .application.current import get_app
from .filters import FilterOrBool, is_searching, to_filter
from .key_binding.vi_state import InputMode
if TYPE_CHECKING:
    from prompt_toolkit.layout.controls import BufferControl, SearchBufferControl
    from prompt_toolkit.layout.layout import Layout
__all__ = ['SearchDirection', 'start_search', 'stop_search']

class SearchDirection(Enum):
    FORWARD = 'FORWARD'
    BACKWARD = 'BACKWARD'

class SearchState:
    """
    A search 'query', associated with a search field (like a SearchToolbar).

    Every searchable `BufferControl` points to a `search_buffer_control`
    (another `BufferControls`) which represents the search field. The
    `SearchState` attached to that search field is used for storing the current
    search query.

    It is possible to have one searchfield for multiple `BufferControls`. In
    that case, they'll share the same `SearchState`.
    If there are multiple `BufferControls` that display the same `Buffer`, then
    they can have a different `SearchState` each (if they have a different
    search control).
    """
    __slots__ = ('text', 'direction', 'ignore_case')

    def __init__(self, text: str='', direction: SearchDirection=SearchDirection.FORWARD, ignore_case: FilterOrBool=False) -> None:
        self.text = text
        self.direction = direction
        self.ignore_case = to_filter(ignore_case)

    def __repr__(self) -> str:
        return '{}({!r}, direction={!r}, ignore_case={!r})'.format(self.__class__.__name__, self.text, self.direction, self.ignore_case)

    def __invert__(self) -> SearchState:
        """
        Create a new SearchState where backwards becomes forwards and the other
        way around.
        """
        if self.direction == SearchDirection.BACKWARD:
            direction = SearchDirection.FORWARD
        else:
            direction = SearchDirection.BACKWARD
        return SearchState(text=self.text, direction=direction, ignore_case=self.ignore_case)

def start_search(buffer_control: BufferControl | None=None, direction: SearchDirection=SearchDirection.FORWARD) -> None:
    """
    Start search through the given `buffer_control` using the
    `search_buffer_control`.

    :param buffer_control: Start search for this `BufferControl`. If not given,
        search through the current control.
    """
    app = get_app()
    layout = app.layout

    if buffer_control is None:
        buffer_control = layout.current_control
        if not isinstance(buffer_control, BufferControl):
            return

    search_control = buffer_control._search_buffer_control
    if callable(search_control):
        search_control = search_control()

    if not isinstance(search_control, SearchBufferControl):
        return

    # Remember the original search state.
    search_state = search_control.searcher_search_state
    search_state.direction = direction

    # Focus search buffer
    layout.focus(search_control)

    # Remember search link
    layout.search_links[search_control] = buffer_control

def stop_search(buffer_control: BufferControl | None=None) -> None:
    """
    Stop search through the given `buffer_control`.
    """
    app = get_app()
    layout = app.layout

    if buffer_control is None:
        buffer_control = layout.current_control
        if not isinstance(buffer_control, BufferControl):
            return

    search_control = buffer_control._search_buffer_control
    if callable(search_control):
        search_control = search_control()

    if not isinstance(search_control, SearchBufferControl):
        return

    # Focus the original buffer again.
    layout.focus(buffer_control)

    # Remove search link
    if search_control in layout.search_links:
        del layout.search_links[search_control]

    # Reset content of search control.
    search_control.buffer.reset()

def do_incremental_search(direction: SearchDirection, count: int=1) -> None:
    """
    Apply search, but keep search buffer focused.
    """
    app = get_app()
    layout = app.layout
    search_control = layout.current_control

    if not isinstance(search_control, SearchBufferControl):
        return

    if search_control not in layout.search_links:
        return

    buffer_control = layout.search_links[search_control]
    search_state = search_control.searcher_search_state

    # Update search_state
    search_state.direction = direction
    search_state.text = search_control.buffer.text

    # Apply search to current buffer.
    if search_state.text:
        buffer_control.buffer.apply_search(
            search_state, include_current_position=False, count=count
        )

def accept_search() -> None:
    """
    Accept current search query. Focus original `BufferControl` again.
    """
    app = get_app()
    layout = app.layout
    search_control = layout.current_control

    if not isinstance(search_control, SearchBufferControl):
        return

    if search_control not in layout.search_links:
        return

    buffer_control = layout.search_links[search_control]
    search_state = search_control.searcher_search_state

    # Update search state.
    search_state.text = search_control.buffer.text

    # Apply search.
    buffer_control.buffer.apply_search(
        search_state, include_current_position=True, count=1
    )

    # Add query to history of search line.
    search_control.buffer.append_to_history()

    # Focus original buffer again.
    layout.focus(buffer_control)

def _get_reverse_search_links(layout: Layout) -> dict[BufferControl, SearchBufferControl]:
    """
    Return mapping from BufferControl to SearchBufferControl.
    """
    return {
        buffer_control: search_control
        for search_control, buffer_control in layout.search_links.items()
    }
