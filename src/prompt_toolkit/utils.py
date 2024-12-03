from __future__ import annotations
import os
import signal
import sys
import threading
from collections import deque
from typing import Callable, ContextManager, Dict, Generator, Generic, TypeVar, Union
from wcwidth import wcwidth
__all__ = ['Event', 'DummyContext', 'get_cwidth', 'suspend_to_background_supported', 'is_conemu_ansi', 'is_windows', 'in_main_thread', 'get_bell_environment_variable', 'get_term_environment_variable', 'take_using_weights', 'to_str', 'to_int', 'AnyFloat', 'to_float', 'is_dumb_terminal']
SPHINX_AUTODOC_RUNNING = 'sphinx.ext.autodoc' in sys.modules
_Sender = TypeVar('_Sender', covariant=True)

class Event(Generic[_Sender]):
    """
    Simple event to which event handlers can be attached. For instance::

        class Cls:
            def __init__(self):
                # Define event. The first parameter is the sender.
                self.event = Event(self)

        obj = Cls()

        def handler(sender):
            pass

        # Add event handler by using the += operator.
        obj.event += handler

        # Fire event.
        obj.event()
    """

    def __init__(self, sender: _Sender, handler: Callable[[_Sender], None] | None=None) -> None:
        self.sender = sender
        self._handlers: list[Callable[[_Sender], None]] = []
        if handler is not None:
            self += handler

    def __call__(self) -> None:
        """Fire event."""
        for handler in self._handlers:
            handler(self.sender)

    def fire(self) -> None:
        """Alias for just calling the event."""
        self()

    def add_handler(self, handler: Callable[[_Sender], None]) -> None:
        """
        Add another handler to this callback.
        (Handler should be a callable that takes exactly one parameter: the
        sender object.)
        """
        if handler not in self._handlers:
            self._handlers.append(handler)

    def remove_handler(self, handler: Callable[[_Sender], None]) -> None:
        """
        Remove a handler from this callback.
        """
        if handler in self._handlers:
            self._handlers.remove(handler)

    def __iadd__(self, handler: Callable[[_Sender], None]) -> Event[_Sender]:
        """
        `event += handler` notation for adding a handler.
        """
        self.add_handler(handler)
        return self

    def __isub__(self, handler: Callable[[_Sender], None]) -> Event[_Sender]:
        """
        `event -= handler` notation for removing a handler.
        """
        self.remove_handler(handler)
        return self

class DummyContext(ContextManager[None]):
    """
    (contextlib.nested is not available on Py3)
    """

    def __enter__(self) -> None:
        return None

    def __exit__(self, *a: object) -> None:
        return None

class _CharSizesCache(Dict[str, int]):
    """
    Cache for wcwidth sizes.
    """
    LONG_STRING_MIN_LEN = 64
    MAX_LONG_STRINGS = 16

    def __init__(self) -> None:
        super().__init__()
        self._long_strings: deque[str] = deque()

    def __missing__(self, string: str) -> int:
        result: int
        if len(string) == 1:
            result = max(0, wcwidth(string))
        else:
            result = sum((self[c] for c in string))
        self[string] = result
        if len(string) > self.LONG_STRING_MIN_LEN:
            long_strings = self._long_strings
            long_strings.append(string)
            if len(long_strings) > self.MAX_LONG_STRINGS:
                key_to_remove = long_strings.popleft()
                if key_to_remove in self:
                    del self[key_to_remove]
        return result
_CHAR_SIZES_CACHE = _CharSizesCache()

def get_cwidth(string: str) -> int:
    """
    Return width of a string. Wrapper around ``wcwidth``.
    """
    return _CHAR_SIZES_CACHE[string]

def suspend_to_background_supported() -> bool:
    """
    Returns `True` when the Python implementation supports
    suspend-to-background. This is typically `False' on Windows systems.
    """
    return hasattr(signal, 'SIGTSTP')

def is_windows() -> bool:
    """
    True when we are using Windows.
    """
    return sys.platform.startswith('win')

def is_windows_vt100_supported() -> bool:
    """
    True when we are using Windows, but VT100 escape sequences are supported.
    """
    if not is_windows():
        return False
    return 'prompt_toolkit.output.windows10.Windows10_Output' in sys.modules

def is_conemu_ansi() -> bool:
    """
    True when the ConEmu Windows console is used.
    """
    return is_windows() and 'ConEmuANSI' in os.environ

def in_main_thread() -> bool:
    """
    True when the current thread is the main thread.
    """
    return threading.current_thread() is threading.main_thread()

def get_bell_environment_variable() -> bool:
    """
    True if env variable is set to true (true, TRUE, True, 1).
    """
    return os.environ.get('PROMPT_TOOLKIT_BELL', '').lower() in ('1', 'true', 'yes', 'on')

def get_term_environment_variable() -> str:
    """Return the $TERM environment variable."""
    return os.environ.get('TERM', '')
_T = TypeVar('_T')

def take_using_weights(items: list[_T], weights: list[int]) -> Generator[_T, None, None]:
    """
    Generator that keeps yielding items from the items list, in proportion to
    their weight. For instance::

        # Getting the first 70 items from this generator should have yielded 10
        # times A, 20 times B and 40 times C, all distributed equally..
        take_using_weights(['A', 'B', 'C'], [5, 10, 20])

    :param items: List of items to take from.
    :param weights: Integers representing the weight. (Numbers have to be
                    integers, not floats.)
    """
    assert len(items) == len(weights)
    total_weight = sum(weights)
    
    while True:
        for item, weight in zip(items, weights):
            for _ in range(weight):
                yield item

def to_str(value: Callable[[], str] | str) -> str:
    """Turn callable or string into string."""
    return value() if callable(value) else value

def to_int(value: Callable[[], int] | int) -> int:
    """Turn callable or int into int."""
    return value() if callable(value) else value
AnyFloat = Union[Callable[[], float], float]

def to_float(value: AnyFloat) -> float:
    """Turn callable or float into float."""
    return value() if callable(value) else value

def is_dumb_terminal(term: str | None=None) -> bool:
    """
    True if this terminal type is considered "dumb".

    If so, we should fall back to the simplest possible form of line editing,
    without cursor positioning and color support.
    """
    if term is None:
        term = get_term_environment_variable()
    return term.lower() in ('dumb', 'unknown')
