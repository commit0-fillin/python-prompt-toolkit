from __future__ import annotations
from .key_processor import KeyPress
__all__ = ['EmacsState']

class EmacsState:
    """
    Mutable class to hold Emacs specific state.
    """

    def __init__(self) -> None:
        self.macro: list[KeyPress] | None = []
        self.current_recording: list[KeyPress] | None = None

    @property
    def is_recording(self) -> bool:
        """Tell whether we are recording a macro."""
        return self.current_recording is not None

    def start_macro(self) -> None:
        """Start recording macro."""
        if not self.is_recording:
            self.current_recording = []

    def end_macro(self) -> None:
        """End recording macro."""
        if self.is_recording:
            self.macro = self.current_recording
            self.current_recording = None
