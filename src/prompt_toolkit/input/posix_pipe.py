from __future__ import annotations
import sys
assert sys.platform != 'win32'
import os
from contextlib import contextmanager
from typing import ContextManager, Iterator, TextIO, cast
from ..utils import DummyContext
from .base import PipeInput
from .vt100 import Vt100Input
__all__ = ['PosixPipeInput']

class _Pipe:
    """Wrapper around os.pipe, that ensures we don't double close any end."""

    def __init__(self) -> None:
        self.read_fd, self.write_fd = os.pipe()
        self._read_closed = False
        self._write_closed = False

    def close_read(self) -> None:
        """Close read-end if not yet closed."""
        if not self._read_closed:
            os.close(self.read_fd)
            self._read_closed = True

    def close_write(self) -> None:
        """Close write-end if not yet closed."""
        if not self._write_closed:
            os.close(self.write_fd)
            self._write_closed = True

    def close(self) -> None:
        """Close both read and write ends."""
        self.close_read()
        self.close_write()

class PosixPipeInput(Vt100Input, PipeInput):
    """
    Input that is send through a pipe.
    This is useful if we want to send the input programmatically into the
    application. Mostly useful for unit testing.

    Usage::

        with PosixPipeInput.create() as input:
            input.send_text('inputdata')
    """
    _id = 0

    def __init__(self, _pipe: _Pipe, _text: str='') -> None:
        self.pipe = _pipe

        class Stdin:
            encoding = 'utf-8'

            def isatty(stdin) -> bool:
                return True

            def fileno(stdin) -> int:
                return self.pipe.read_fd
        super().__init__(cast(TextIO, Stdin()))
        self.send_text(_text)
        self.__class__._id += 1
        self._id = self.__class__._id

    def send_text(self, data: str) -> None:
        """Send text to the input."""
        os.write(self.pipe.write_fd, data.encode(self.stdin.encoding))

    def close(self) -> None:
        """Close pipe fds."""
        self.pipe.close()

    def typeahead_hash(self) -> str:
        """
        This needs to be unique for every `PipeInput`.
        """
        return f'pipe-input-{self._id}'
