from __future__ import annotations
import sys
assert sys.platform != 'win32'
import contextlib
import io
import termios
import tty
from asyncio import AbstractEventLoop, get_running_loop
from typing import Callable, ContextManager, Generator, TextIO
from ..key_binding import KeyPress
from .base import Input
from .posix_utils import PosixStdinReader
from .vt100_parser import Vt100Parser
__all__ = ['Vt100Input', 'raw_mode', 'cooked_mode']

class Vt100Input(Input):
    """
    Vt100 input for Posix systems.
    (This uses a posix file descriptor that can be registered in the event loop.)
    """
    _fds_not_a_terminal: set[int] = set()

    def __init__(self, stdin: TextIO) -> None:
        try:
            stdin.fileno()
        except io.UnsupportedOperation as e:
            if 'idlelib.run' in sys.modules:
                raise io.UnsupportedOperation('Stdin is not a terminal. Running from Idle is not supported.') from e
            else:
                raise io.UnsupportedOperation('Stdin is not a terminal.') from e
        isatty = stdin.isatty()
        fd = stdin.fileno()
        if not isatty and fd not in Vt100Input._fds_not_a_terminal:
            msg = 'Warning: Input is not a terminal (fd=%r).\n'
            sys.stderr.write(msg % fd)
            sys.stderr.flush()
            Vt100Input._fds_not_a_terminal.add(fd)
        self.stdin = stdin
        self._fileno = stdin.fileno()
        self._buffer: list[KeyPress] = []
        self.stdin_reader = PosixStdinReader(self._fileno, encoding=stdin.encoding)
        self.vt100_parser = Vt100Parser(lambda key_press: self._buffer.append(key_press))

    def attach(self, input_ready_callback: Callable[[], None]) -> ContextManager[None]:
        """
        Return a context manager that makes this input active in the current
        event loop.
        """
        return _attached_input(self, input_ready_callback)

    def detach(self) -> ContextManager[None]:
        """
        Return a context manager that makes sure that this input is not active
        in the current event loop.
        """
        return _attached_input(self, None)

    def read_keys(self) -> list[KeyPress]:
        """Read list of KeyPress."""
        data = self.stdin_reader.read()
        self.vt100_parser.feed(data)
        result = self._buffer
        self._buffer = []
        return result

    def flush_keys(self) -> list[KeyPress]:
        """
        Flush pending keys and return them.
        (Used for flushing the 'escape' key.)
        """
        self.vt100_parser.flush()
        result = self._buffer
        self._buffer = []
        return result
_current_callbacks: dict[tuple[AbstractEventLoop, int], Callable[[], None] | None] = {}

@contextlib.contextmanager
def _attached_input(input: Vt100Input, callback: Callable[[], None]) -> Generator[None, None, None]:
    """
    Context manager that makes this input active in the current event loop.

    :param input: :class:`~prompt_toolkit.input.Input` object.
    :param callback: Called when the input is ready to read.
    """
    loop = get_running_loop()
    previous = _current_callbacks.get((loop, input._fileno))

    _current_callbacks[(loop, input._fileno)] = callback

    if callback is not None:
        loop.add_reader(input._fileno, callback)
    else:
        loop.remove_reader(input._fileno)

    try:
        yield
    finally:
        _current_callbacks[(loop, input._fileno)] = previous

        if callback is not None:
            loop.remove_reader(input._fileno)
        if previous:
            loop.add_reader(input._fileno, previous)

class raw_mode:
    """
    ::

        with raw_mode(stdin):
            ''' the pseudo-terminal stdin is now used in raw mode '''

    We ignore errors when executing `tcgetattr` fails.
    """

    def __init__(self, fileno: int) -> None:
        self.fileno = fileno
        self.attrs_before: list[int | list[bytes | int]] | None
        try:
            self.attrs_before = termios.tcgetattr(fileno)
        except termios.error:
            self.attrs_before = None

    def __enter__(self) -> None:
        try:
            newattr = termios.tcgetattr(self.fileno)
        except termios.error:
            pass
        else:
            newattr[tty.LFLAG] = self._patch_lflag(newattr[tty.LFLAG])
            newattr[tty.IFLAG] = self._patch_iflag(newattr[tty.IFLAG])
            newattr[tty.CC][termios.VMIN] = 1
            newattr[tty.CC][termios.VTIME] = 0
            try:
                termios.tcsetattr(self.fileno, termios.TCSADRAIN, newattr)
            except termios.error:
                pass

    def __exit__(self, *a: object) -> None:
        if self.attrs_before is not None:
            try:
                termios.tcsetattr(self.fileno, termios.TCSADRAIN, self.attrs_before)
            except termios.error:
                pass

class cooked_mode(raw_mode):
    """
    The opposite of ``raw_mode``, used when we need cooked mode inside a
    `raw_mode` block.  Used in `Application.run_in_terminal`.::

        with cooked_mode(stdin):
            ''' the pseudo-terminal stdin is now used in cooked mode. '''
    """
