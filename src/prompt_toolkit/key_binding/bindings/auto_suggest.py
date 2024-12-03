"""
Key bindings for auto suggestion (for fish-style auto suggestion).
"""
from __future__ import annotations

from prompt_toolkit.application.current import get_app
from prompt_toolkit.filters import Condition, emacs_mode, has_selection
from prompt_toolkit.key_binding.key_bindings import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent

__all__ = ['load_auto_suggest_bindings']

E = KeyPressEvent

def suggestion_available() -> bool:
    """Check if a suggestion is available."""
    return get_app().current_buffer.suggestion is not None

def load_auto_suggest_bindings() -> KeyBindings:
    """
    Key bindings for accepting auto suggestion text.

    (This has to come after the Vi bindings, because they also have an
    implementation for the "right arrow", but we really want the suggestion
    binding when a suggestion is available.)
    """
    key_bindings = KeyBindings()
    handle = key_bindings.add

    @handle('right', filter=~has_selection & suggestion_available)
    @handle('c-e', filter=~has_selection & suggestion_available)
    def _(event: E) -> None:
        """
        Accept suggestion.
        """
        b = event.current_buffer
        suggestion = b.suggestion

        if suggestion:
            b.insert_text(suggestion.text)

    @handle('right', filter=has_selection & suggestion_available)
    def _(event: E) -> None:
        """
        Accept suggestion, but keep selection.
        """
        b = event.current_buffer
        suggestion = b.suggestion

        if suggestion:
            b.insert_text(suggestion.text, move_cursor=False)

    return key_bindings
