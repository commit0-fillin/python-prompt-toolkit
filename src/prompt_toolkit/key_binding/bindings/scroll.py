"""
Key bindings, for scrolling up and down through pages.

This are separate bindings, because GNU readline doesn't have them, but
they are very useful for navigating through long multiline buffers, like in
Vi, Emacs, etc...
"""
from __future__ import annotations
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
__all__ = ['scroll_forward', 'scroll_backward', 'scroll_half_page_up', 'scroll_half_page_down', 'scroll_one_line_up', 'scroll_one_line_down']
E = KeyPressEvent

def scroll_forward(event: E, half: bool=False) -> None:
    """
    Scroll window down.
    """
    window = event.app.layout.current_window
    info = window.render_info
    if info:
        window.vertical_scroll = min(
            info.full_height - info.window_height,
            window.vertical_scroll + int(info.window_height / (2 if half else 1))
        )

def scroll_backward(event: E, half: bool=False) -> None:
    """
    Scroll window up.
    """
    window = event.app.layout.current_window
    info = window.render_info
    if info:
        window.vertical_scroll = max(
            0,
            window.vertical_scroll - int(info.window_height / (2 if half else 1))
        )

def scroll_half_page_down(event: E) -> None:
    """
    Same as ControlF, but only scroll half a page.
    """
    scroll_forward(event, half=True)

def scroll_half_page_up(event: E) -> None:
    """
    Same as ControlB, but only scroll half a page.
    """
    scroll_backward(event, half=True)

def scroll_one_line_down(event: E) -> None:
    """
    scroll_offset += 1
    """
    window = event.app.layout.current_window
    info = window.render_info
    if info:
        window.vertical_scroll = min(
            info.full_height - info.window_height,
            window.vertical_scroll + 1
        )

def scroll_one_line_up(event: E) -> None:
    """
    scroll_offset -= 1
    """
    window = event.app.layout.current_window
    info = window.render_info
    if info:
        window.vertical_scroll = max(0, window.vertical_scroll - 1)

def scroll_page_down(event: E) -> None:
    """
    Scroll page down. (Prefer the cursor at the top of the page, after scrolling.)
    """
    window = event.app.layout.current_window
    info = window.render_info
    if info:
        # Scroll down one page, but keep one overlap line for context
        window.vertical_scroll = min(
            info.full_height - info.window_height,
            window.vertical_scroll + info.window_height - 1
        )
        
        # Move cursor to the top of the visible area
        buffer = event.app.current_buffer
        cursor_position = buffer.document.translate_row_col_to_index(
            window.vertical_scroll, 0
        )
        buffer.cursor_position = cursor_position

def scroll_page_up(event: E) -> None:
    """
    Scroll page up. (Prefer the cursor at the bottom of the page, after scrolling.)
    """
    window = event.app.layout.current_window
    info = window.render_info
    if info:
        # Scroll up one page, but keep one overlap line for context
        window.vertical_scroll = max(0, window.vertical_scroll - info.window_height + 1)
        
        # Move cursor to the bottom of the visible area
        buffer = event.app.current_buffer
        cursor_position = buffer.document.translate_row_col_to_index(
            window.vertical_scroll + info.window_height - 1, 0
        )
        buffer.cursor_position = cursor_position
