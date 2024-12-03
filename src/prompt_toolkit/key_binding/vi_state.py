from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING, Callable
from prompt_toolkit.clipboard import ClipboardData
if TYPE_CHECKING:
    from .key_bindings.vi import TextObject
    from .key_processor import KeyPressEvent
__all__ = ['InputMode', 'CharacterFind', 'ViState']

class InputMode(str, Enum):
    value: str
    INSERT = 'vi-insert'
    INSERT_MULTIPLE = 'vi-insert-multiple'
    NAVIGATION = 'vi-navigation'
    REPLACE = 'vi-replace'
    REPLACE_SINGLE = 'vi-replace-single'

class CharacterFind:

    def __init__(self, character: str, backwards: bool=False) -> None:
        self.character = character
        self.backwards = backwards

class ViState:
    """
    Mutable class to hold the state of the Vi navigation.
    """

    def __init__(self) -> None:
        self.last_character_find: CharacterFind | None = None
        self.operator_func: None | Callable[[KeyPressEvent, TextObject], None] = None
        self.operator_arg: int | None = None
        self.named_registers: dict[str, ClipboardData] = {}
        self.__input_mode = InputMode.INSERT
        self.waiting_for_digraph = False
        self.digraph_symbol1: str | None = None
        self.tilde_operator = False
        self.recording_register: str | None = None
        self.current_recording: str = ''
        self.temporary_navigation_mode = False

    @property
    def input_mode(self) -> InputMode:
        """Get `InputMode`."""
        return self.__input_mode

    @input_mode.setter
    def input_mode(self, value: InputMode) -> None:
        """Set `InputMode`."""
        self.__input_mode = value

    def reset(self) -> None:
        """
        Reset state, go back to the given mode. INSERT by default.
        """
        self.__input_mode = InputMode.INSERT
        self.last_character_find = None
        self.operator_func = None
        self.operator_arg = None
        self.named_registers.clear()
        self.waiting_for_digraph = False
        self.digraph_symbol1 = None
        self.tilde_operator = False
        self.recording_register = None
        self.current_recording = ''
        self.temporary_navigation_mode = False
