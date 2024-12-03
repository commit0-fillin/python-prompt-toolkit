"""
Dummy layout. Used when somebody creates an `Application` without specifying a
`Layout`.
"""
from __future__ import annotations
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from .containers import Window
from .controls import FormattedTextControl
from .dimension import D
from .layout import Layout
__all__ = ['create_dummy_layout']

def create_dummy_layout() -> Layout:
    """
    Create a dummy layout for use in an 'Application' that doesn't have a
    layout specified. When ENTER is pressed, the application quits.
    """
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, Window
    from prompt_toolkit.layout.controls import FormattedTextControl

    kb = KeyBindings()

    @kb.add('enter')
    def _(event):
        event.app.exit()

    text = HTML('<reverse>No layout specified. Press <b>ENTER</b> to quit.</reverse>')
    control = FormattedTextControl(text, key_bindings=kb)
    window = Window(content=control)
    return Layout(window)
