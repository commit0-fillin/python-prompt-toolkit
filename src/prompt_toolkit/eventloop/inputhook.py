"""
Similar to `PyOS_InputHook` of the Python API, we can plug in an input hook in
the asyncio event loop.

The way this works is by using a custom 'selector' that runs the other event
loop until the real selector is ready.

It's the responsibility of this event hook to return when there is input ready.
There are two ways to detect when input is ready:

The inputhook itself is a callable that receives an `InputHookContext`. This
callable should run the other event loop, and return when the main loop has
stuff to do. There are two ways to detect when to return:

- Call the `input_is_ready` method periodically. Quit when this returns `True`.

- Add the `fileno` as a watch to the external eventloop. Quit when file descriptor
  becomes readable. (But don't read from it.)

  Note that this is not the same as checking for `sys.stdin.fileno()`. The
  eventloop of prompt-toolkit allows thread-based executors, for example for
  asynchronous autocompletion. When the completion for instance is ready, we
  also want prompt-toolkit to gain control again in order to display that.
"""
from __future__ import annotations
import asyncio
import os
import select
import selectors
import sys
import threading
from asyncio import AbstractEventLoop, get_running_loop
from selectors import BaseSelector, SelectorKey
from typing import TYPE_CHECKING, Any, Callable, Mapping
__all__ = ['new_eventloop_with_inputhook', 'set_eventloop_with_inputhook', 'InputHookSelector', 'InputHookContext', 'InputHook']
if TYPE_CHECKING:
    from _typeshed import FileDescriptorLike
    from typing_extensions import TypeAlias
    _EventMask = int

class InputHookContext:
    """
    Given as a parameter to the inputhook.
    """

    def __init__(self, fileno: int, input_is_ready: Callable[[], bool]) -> None:
        self._fileno = fileno
        self.input_is_ready = input_is_ready
InputHook: TypeAlias = Callable[[InputHookContext], None]

def new_eventloop_with_inputhook(inputhook: Callable[[InputHookContext], None]) -> AbstractEventLoop:
    """
    Create a new event loop with the given inputhook.
    """
    selector = selectors.SelectSelector()
    loop = asyncio.SelectorEventLoop(InputHookSelector(selector, inputhook))
    return loop

def set_eventloop_with_inputhook(inputhook: Callable[[InputHookContext], None]) -> AbstractEventLoop:
    """
    Create a new event loop with the given inputhook, and activate it.
    """
    loop = new_eventloop_with_inputhook(inputhook)
    asyncio.set_event_loop(loop)
    return loop

class InputHookSelector(BaseSelector):
    """
    Usage:

        selector = selectors.SelectSelector()
        loop = asyncio.SelectorEventLoop(InputHookSelector(selector, inputhook))
        asyncio.set_event_loop(loop)
    """

    def __init__(self, selector: BaseSelector, inputhook: Callable[[InputHookContext], None]) -> None:
        self.selector = selector
        self.inputhook = inputhook
        self._r, self._w = os.pipe()

    def close(self) -> None:
        """
        Clean up resources.
        """
        self.selector.close()
        os.close(self._r)
        os.close(self._w)
