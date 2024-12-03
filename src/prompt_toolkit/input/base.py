"""
Abstraction of CLI Input.
"""
from __future__ import annotations
from abc import ABCMeta, abstractmethod, abstractproperty
from contextlib import contextmanager
from typing import Callable, ContextManager, Generator
from prompt_toolkit.key_binding import KeyPress
__all__ = ['Input', 'PipeInput', 'DummyInput']

class Input(metaclass=ABCMeta):
    """
    Abstraction for any input.

    An instance of this class can be given to the constructor of a
    :class:`~prompt_toolkit.application.Application` and will also be
    passed to the :class:`~prompt_toolkit.eventloop.base.EventLoop`.
    """

    @abstractmethod
    def fileno(self) -> int:
        """
        Fileno for putting this in an event loop.
        """
        raise NotImplementedError("fileno method must be implemented by subclasses")

    @abstractmethod
    def typeahead_hash(self) -> str:
        """
        Identifier for storing type ahead key presses.
        """
        raise NotImplementedError("typeahead_hash method must be implemented by subclasses")

    @abstractmethod
    def read_keys(self) -> list[KeyPress]:
        """
        Return a list of Key objects which are read/parsed from the input.
        """
        raise NotImplementedError("read_keys method must be implemented by subclasses")

    def flush_keys(self) -> list[KeyPress]:
        """
        Flush the underlying parser. and return the pending keys.
        (Used for vt100 input.)
        """
        return []  # Default implementation returns an empty list

    def flush(self) -> None:
        """The event loop can call this when the input has to be flushed."""
        # Default implementation does nothing

    @property
    @abstractmethod
    def closed(self) -> bool:
        """Should be true when the input stream is closed."""
        raise NotImplementedError("closed property must be implemented by subclasses")

    @abstractmethod
    def raw_mode(self) -> ContextManager[None]:
        """
        Context manager that turns the input into raw mode.
        """
        raise NotImplementedError("raw_mode method must be implemented by subclasses")

    @abstractmethod
    def cooked_mode(self) -> ContextManager[None]:
        """
        Context manager that turns the input into cooked mode.
        """
        raise NotImplementedError("cooked_mode method must be implemented by subclasses")

    @abstractmethod
    def attach(self, input_ready_callback: Callable[[], None]) -> ContextManager[None]:
        """
        Return a context manager that makes this input active in the current
        event loop.
        """
        raise NotImplementedError("attach method must be implemented by subclasses")

    @abstractmethod
    def detach(self) -> ContextManager[None]:
        """
        Return a context manager that makes sure that this input is not active
        in the current event loop.
        """
        raise NotImplementedError("detach method must be implemented by subclasses")

    def close(self) -> None:
        """Close input."""
        # Default implementation does nothing

class PipeInput(Input):
    """
    Abstraction for pipe input.
    """

    @abstractmethod
    def send_bytes(self, data: bytes) -> None:
        """Feed byte string into the pipe"""
        raise NotImplementedError("send_bytes method must be implemented by subclasses")

    @abstractmethod
    def send_text(self, data: str) -> None:
        """Feed a text string into the pipe"""
        raise NotImplementedError("send_text method must be implemented by subclasses")

class DummyInput(Input):
    """
    Input for use in a `DummyApplication`

    If used in an actual application, it will make the application render
    itself once and exit immediately, due to an `EOFError`.
    """
