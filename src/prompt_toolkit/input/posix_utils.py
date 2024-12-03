from __future__ import annotations
import os
import select
from codecs import getincrementaldecoder
__all__ = ['PosixStdinReader']

class PosixStdinReader:
    """
    Wrapper around stdin which reads (nonblocking) the next available 1024
    bytes and decodes it.

    Note that you can't be sure that the input file is closed if the ``read``
    function returns an empty string. When ``errors=ignore`` is passed,
    ``read`` can return an empty string if all malformed input was replaced by
    an empty string. (We can't block here and wait for more input.) So, because
    of that, check the ``closed`` attribute, to be sure that the file has been
    closed.

    :param stdin_fd: File descriptor from which we read.
    :param errors:  Can be 'ignore', 'strict' or 'replace'.
        On Python3, this can be 'surrogateescape', which is the default.

        'surrogateescape' is preferred, because this allows us to transfer
        unrecognized bytes to the key bindings. Some terminals, like lxterminal
        and Guake, use the 'Mxx' notation to send mouse events, where each 'x'
        can be any possible byte.
    """

    def __init__(self, stdin_fd: int, errors: str='surrogateescape', encoding: str='utf-8') -> None:
        self.stdin_fd = stdin_fd
        self.errors = errors
        self._stdin_decoder_cls = getincrementaldecoder(encoding)
        self._stdin_decoder = self._stdin_decoder_cls(errors=errors)
        self.closed = False

    def read(self, count: int=1024) -> str:
        """
        Read the input and return it as a string.

        Return the text. Note that this can return an empty string, even when
        the input stream was not yet closed. This means that something went
        wrong during the decoding.
        """
        # Check if the input is closed
        if self.closed:
            return ''

        # Use select to check if there's data available to read
        r, _, _ = select.select([self.stdin_fd], [], [], 0)
        if not r:
            return ''  # No data available

        # Read raw bytes from stdin
        try:
            data = os.read(self.stdin_fd, count)
        except OSError:
            # Error reading from stdin
            return ''

        if not data:
            # End of file reached
            self.closed = True
            return ''

        # Decode the bytes to a string
        try:
            return self._stdin_decoder.decode(data)
        except UnicodeDecodeError:
            # If decoding fails, reset the decoder and return an empty string
            self._stdin_decoder = self._stdin_decoder_cls(errors=self.errors)
            return ''
