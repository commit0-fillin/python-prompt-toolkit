from __future__ import annotations
import errno
import fcntl
import os
import sys
from contextlib import contextmanager
from typing import IO, Iterator, TextIO
__all__ = ['flush_stdout']

@contextmanager
def _blocking_io(io: IO[str]) -> Iterator[None]:
    """
    Ensure that the FD for `io` is set to blocking in here.
    """
    fd = io.fileno()
    old_flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    
    try:
        # Remove O_NONBLOCK flag to set blocking mode
        fcntl.fcntl(fd, fcntl.F_SETFL, old_flags & ~os.O_NONBLOCK)
        yield
    finally:
        # Restore the original flags
        fcntl.fcntl(fd, fcntl.F_SETFL, old_flags)
