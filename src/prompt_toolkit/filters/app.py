"""
Filters that accept a `Application` as argument.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, cast
from prompt_toolkit.application.current import get_app
from prompt_toolkit.cache import memoized
from prompt_toolkit.enums import EditingMode
from .base import Condition
if TYPE_CHECKING:
    from prompt_toolkit.layout.layout import FocusableElement
__all__ = ['has_arg', 'has_completions', 'completion_is_selected', 'has_focus', 'buffer_has_focus', 'has_selection', 'has_suggestion', 'has_validation_error', 'is_done', 'is_read_only', 'is_multiline', 'renderer_height_is_known', 'in_editing_mode', 'in_paste_mode', 'vi_mode', 'vi_navigation_mode', 'vi_insert_mode', 'vi_insert_multiple_mode', 'vi_replace_mode', 'vi_selection_mode', 'vi_waiting_for_text_object_mode', 'vi_digraph_mode', 'vi_recording_macro', 'emacs_mode', 'emacs_insert_mode', 'emacs_selection_mode', 'shift_selection_mode', 'is_searching', 'control_is_searchable', 'vi_search_direction_reversed']

def has_focus(value: FocusableElement) -> Condition:
    """
    Enable when this buffer has the focus.
    """
    @Condition
    def has_focus_filter() -> bool:
        return get_app().layout.current_control == value
    return has_focus_filter

@Condition
def buffer_has_focus() -> bool:
    """
    Enabled when the currently focused control is a `BufferControl`.
    """
    return hasattr(get_app().layout.current_control, 'buffer')

@Condition
def has_selection() -> bool:
    """
    Enable when the current buffer has a selection.
    """
    return bool(get_app().current_buffer.selection_state)

@Condition
def has_suggestion() -> bool:
    """
    Enable when the current buffer has a suggestion.
    """
    return get_app().current_buffer.suggestion is not None

@Condition
def has_completions() -> bool:
    """
    Enable when the current buffer has completions.
    """
    return bool(get_app().current_buffer.completer)

@Condition
def completion_is_selected() -> bool:
    """
    True when the user selected a completion.
    """
    return get_app().current_buffer.complete_state is not None and \
           get_app().current_buffer.complete_state.current_completion is not None

@Condition
def is_read_only() -> bool:
    """
    True when the current buffer is read only.
    """
    return get_app().current_buffer.read_only()

@Condition
def is_multiline() -> bool:
    """
    True when the current buffer has been marked as multiline.
    """
    return get_app().current_buffer.multiline

@Condition
def has_validation_error() -> bool:
    """Current buffer has validation error."""
    return get_app().current_buffer.validation_error is not None

@Condition
def has_arg() -> bool:
    """Enable when the input processor has an 'arg'."""
    return get_app().key_processor.arg is not None

@Condition
def is_done() -> bool:
    """
    True when the CLI is returning, aborting or exiting.
    """
    return get_app().is_done

@Condition
def renderer_height_is_known() -> bool:
    """
    Only True when the renderer knows it's real height.

    (On VT100 terminals, we have to wait for a CPR response, before we can be
    sure of the available height between the cursor position and the bottom of
    the terminal. And usually it's nicer to wait with drawing bottom toolbars
    until we receive the height, in order to avoid flickering -- first drawing
    somewhere in the middle, and then again at the bottom.)
    """
    return get_app().renderer.height_is_known

@memoized()
def in_editing_mode(editing_mode: EditingMode) -> Condition:
    """
    Check whether a given editing mode is active. (Vi or Emacs.)
    """
    @Condition
    def in_editing_mode_filter() -> bool:
        return get_app().editing_mode == editing_mode
    return in_editing_mode_filter

@Condition
def vi_navigation_mode() -> bool:
    """
    Active when the set for Vi navigation key bindings are active.
    """
    app = get_app()
    return app.editing_mode == EditingMode.VI and not app.vi_state.input_mode

@Condition
def vi_recording_macro() -> bool:
    """When recording a Vi macro."""
    return get_app().vi_state.recording_macro

@Condition
def emacs_mode() -> bool:
    """When the Emacs bindings are active."""
    return get_app().editing_mode == EditingMode.EMACS

@Condition
def is_searching() -> bool:
    """When we are searching."""
    return get_app().layout.is_searching

@Condition
def control_is_searchable() -> bool:
    """When the current UIControl is searchable."""
    return hasattr(get_app().layout.current_control, 'search_buffer')

@Condition
def vi_search_direction_reversed() -> bool:
    """When the '/' and '?' key bindings for Vi-style searching have been reversed."""
    return get_app().vi_search_direction_reversed
