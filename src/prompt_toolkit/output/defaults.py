from __future__ import annotations
import sys
from typing import TextIO, cast
from prompt_toolkit.utils import get_bell_environment_variable, get_term_environment_variable, is_conemu_ansi
from .base import DummyOutput, Output
from .color_depth import ColorDepth
from .plain_text import PlainTextOutput
__all__ = ['create_output']

def create_output(stdout: TextIO | None=None, always_prefer_tty: bool=False) -> Output:
    """
    Return an :class:`~prompt_toolkit.output.Output` instance for the command
    line.

    :param stdout: The stdout object
    :param always_prefer_tty: When set, look for `sys.stderr` if `sys.stdout`
        is not a TTY. Useful if `sys.stdout` is redirected to a file, but we
        still want user input and output on the terminal.

        By default, this is `False`. If `sys.stdout` is not a terminal (maybe
        it's redirected to a file), then a `PlainTextOutput` will be returned.
        That way, tools like `print_formatted_text` will write plain text into
        that file.
    """
    if stdout is None:
        stdout = sys.stdout

    # Check if the given `stdout` is a tty.
    if not stdout.isatty() and always_prefer_tty:
        stdout = sys.stderr if sys.stderr.isatty() else stdout

    # Decide what kind of output we want to create.
    if stdout.isatty():
        term = get_term_environment_variable()
        
        if term in ('xterm', 'xterm-256color', 'linux', 'screen'):
            from .vt100 import Vt100_Output
            return Vt100_Output.from_pty(stdout, term=term)
        elif term == 'win32':
            from .win32 import Win32Output
            return Win32Output(stdout)
        elif is_conemu_ansi():
            from .conemu import ConEmuOutput
            return ConEmuOutput(stdout)
    
    # If no other output is found, return PlainTextOutput
    return PlainTextOutput(stdout)
