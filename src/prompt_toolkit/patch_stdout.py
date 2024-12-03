"""
patch_stdout
============

This implements a context manager that ensures that print statements within
it won't destroy the user interface. The context manager will replace
`sys.stdout` by something that draws the output above the current prompt,
rather than overwriting the UI.

Usage::

    with patch_stdout(application):
        ...
        application.run()
        ...

Multiple applications can run in the body of the context manager, one after the
other.
"""
from __future__ import annotations
import asyncio
import queue
import sys
import threading
import time
from contextlib import contextmanager
from typing import Generator, TextIO, cast
from .application import get_app_session, run_in_terminal
from .output import Output
__all__ = ['patch_stdout', 'StdoutProxy']

@contextmanager
def patch_stdout(raw: bool=False) -> Generator[None, None, None]:
    """
    Replace `sys.stdout` by an :class:`_StdoutProxy` instance.

    Writing to this proxy will make sure that the text appears above the
    prompt, and that it doesn't destroy the output from the renderer.  If no
    application is curring, the behavior should be identical to writing to
    `sys.stdout` directly.

    Warning: If a new event loop is installed using `asyncio.set_event_loop()`,
        then make sure that the context manager is applied after the event loop
        is changed. Printing to stdout will be scheduled in the event loop
        that's active when the context manager is created.

    :param raw: (`bool`) When True, vt100 terminal escape sequences are not
                removed/escaped.
    """
    original_stdout = sys.stdout
    try:
        proxy = StdoutProxy(raw=raw)
        sys.stdout = proxy
        yield
    finally:
        proxy.close()
        sys.stdout = original_stdout

class _Done:
    """Sentinel value for stopping the stdout proxy."""

class StdoutProxy:
    """
    File-like object, which prints everything written to it, output above the
    current application/prompt. This class is compatible with other file
    objects and can be used as a drop-in replacement for `sys.stdout` or can
    for instance be passed to `logging.StreamHandler`.

    The current application, above which we print, is determined by looking
    what application currently runs in the `AppSession` that is active during
    the creation of this instance.

    This class can be used as a context manager.

    In order to avoid having to repaint the prompt continuously for every
    little write, a short delay of `sleep_between_writes` seconds will be added
    between writes in order to bundle many smaller writes in a short timespan.
    """

    def __init__(self, sleep_between_writes: float=0.2, raw: bool=False) -> None:
        self.sleep_between_writes = sleep_between_writes
        self.raw = raw
        self._lock = threading.RLock()
        self._buffer: list[str] = []
        self.app_session = get_app_session()
        self._output: Output = self.app_session.output
        self._flush_queue: queue.Queue[str | _Done] = queue.Queue()
        self._flush_thread = self._start_write_thread()
        self.closed = False

    def __enter__(self) -> StdoutProxy:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        """
        Stop `StdoutProxy` proxy.

        This will terminate the write thread, make sure everything is flushed
        and wait for the write thread to finish.
        """
        if not self.closed:
            self._flush_queue.put(_Done())
            self._flush_thread.join()
            self.flush()
            self.closed = True

    def _get_app_loop(self) -> asyncio.AbstractEventLoop | None:
        """
        Return the event loop for the application currently running in our
        `AppSession`.
        """
        app = self.app_session.app
        if app and app.is_running:
            return app.loop
        return None

    def _write_and_flush(self, loop: asyncio.AbstractEventLoop | None, text: str) -> None:
        """
        Write the given text to stdout and flush.
        If an application is running, use `run_in_terminal`.
        """
        def write_and_flush() -> None:
            self._output.write_raw(text)
            self._output.flush()

        if loop is None:
            write_and_flush()
        else:
            run_in_terminal(write_and_flush)

    def _write(self, data: str) -> None:
        """
        Note: print()-statements cause to multiple write calls.
              (write('line') and write('
')). Of course we don't want to call
              `run_in_terminal` for every individual call, because that's too
              expensive, and as long as the newline hasn't been written, the
              text itself is again overwritten by the rendering of the input
              command line. Therefor, we have a little buffer which holds the
              text until a newline is written to stdout.
        """
        if not self.raw:
            data = data.replace('\001', '').replace('\002', '')

        with self._lock:
            self._buffer.append(data)

            if '\n' in data:
                text = ''.join(self._buffer)
                self._buffer = []
                self._flush_queue.put(text)

    def flush(self) -> None:
        """
        Flush buffered output.
        """
        with self._lock:
            text = ''.join(self._buffer)
            self._buffer = []

        if text:
            self._flush_queue.put(text)

        # Wait for the flush to happen.
        self._flush_queue.join()
