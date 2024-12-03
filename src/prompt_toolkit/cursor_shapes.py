from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Union
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.key_binding.vi_state import InputMode
if TYPE_CHECKING:
    from .application import Application
__all__ = ['CursorShape', 'CursorShapeConfig', 'SimpleCursorShapeConfig', 'ModalCursorShapeConfig', 'DynamicCursorShapeConfig', 'to_cursor_shape_config']

class CursorShape(Enum):
    _NEVER_CHANGE = '_NEVER_CHANGE'
    BLOCK = 'BLOCK'
    BEAM = 'BEAM'
    UNDERLINE = 'UNDERLINE'
    BLINKING_BLOCK = 'BLINKING_BLOCK'
    BLINKING_BEAM = 'BLINKING_BEAM'
    BLINKING_UNDERLINE = 'BLINKING_UNDERLINE'

class CursorShapeConfig(ABC):

    @abstractmethod
    def get_cursor_shape(self, application: Application[Any]) -> CursorShape:
        """
        Return the cursor shape to be used in the current state.
        """
        return self.cursor_shape
AnyCursorShapeConfig = Union[CursorShape, CursorShapeConfig, None]

class SimpleCursorShapeConfig(CursorShapeConfig):
    """
    Always show the given cursor shape.
    """

    def __init__(self, cursor_shape: CursorShape=CursorShape._NEVER_CHANGE) -> None:
        self.cursor_shape = cursor_shape

class ModalCursorShapeConfig(CursorShapeConfig):
    """
    Show cursor shape according to the current input mode.
    """

class DynamicCursorShapeConfig(CursorShapeConfig):

    def __init__(self, get_cursor_shape_config: Callable[[], AnyCursorShapeConfig]) -> None:
        self.get_cursor_shape_config = get_cursor_shape_config

def to_cursor_shape_config(value: AnyCursorShapeConfig) -> CursorShapeConfig:
    """
    Take a `CursorShape` instance or `CursorShapeConfig` and turn it into a
    `CursorShapeConfig`.
    """
    if isinstance(value, CursorShapeConfig):
        return value
    elif isinstance(value, CursorShape):
        return SimpleCursorShapeConfig(value)
    elif value is None:
        return SimpleCursorShapeConfig(CursorShape._NEVER_CHANGE)
    else:
        raise TypeError(f"Invalid cursor shape config: {value}")
