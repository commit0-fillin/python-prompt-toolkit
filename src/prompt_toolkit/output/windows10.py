from __future__ import annotations
import sys
assert sys.platform == 'win32'
from ctypes import byref, windll
from ctypes.wintypes import DWORD, HANDLE
from typing import Any, TextIO
from prompt_toolkit.data_structures import Size
from prompt_toolkit.win32_types import STD_OUTPUT_HANDLE
from .base import Output
from .color_depth import ColorDepth
from .vt100 import Vt100_Output
from .win32 import Win32Output
__all__ = ['Windows10_Output']
ENABLE_PROCESSED_INPUT = 1
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 4

class Windows10_Output:
    """
    Windows 10 output abstraction. This enables and uses vt100 escape sequences.
    """

    def __init__(self, stdout: TextIO, default_color_depth: ColorDepth | None=None) -> None:
        self.default_color_depth = default_color_depth
        self.win32_output = Win32Output(stdout, default_color_depth=default_color_depth)
        self.vt100_output = Vt100_Output(stdout, lambda: Size(0, 0), default_color_depth=default_color_depth)
        self._hconsole = HANDLE(windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE))

    def flush(self) -> None:
        """
        Write to output stream and flush.
        """
        self.win32_output.flush()
        self.vt100_output.flush()

    def __getattr__(self, name: str) -> Any:
        if name in ('get_size', 'get_rows_below_cursor_position', 'enable_mouse_support', 'disable_mouse_support', 'scroll_buffer_to_prompt', 'get_win32_screen_buffer_info', 'enable_bracketed_paste', 'disable_bracketed_paste'):
            return getattr(self.win32_output, name)
        else:
            return getattr(self.vt100_output, name)

    def get_default_color_depth(self) -> ColorDepth:
        """
        Return the default color depth for a windows terminal.

        Contrary to the Vt100 implementation, this doesn't depend on a $TERM
        variable.
        """
        if self.default_color_depth is not None:
            return self.default_color_depth
        return self.win32_output.get_default_color_depth()
Output.register(Windows10_Output)

def is_win_vt100_enabled() -> bool:
    """
    Returns True when we're running Windows and VT100 escape sequences are
    supported.
    """
    if not sys.platform.startswith('win'):
        return False

    hconsole = HANDLE(windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE))
    mode = DWORD()
    
    if windll.kernel32.GetConsoleMode(hconsole, byref(mode)):
        return bool(mode.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    
    return False
