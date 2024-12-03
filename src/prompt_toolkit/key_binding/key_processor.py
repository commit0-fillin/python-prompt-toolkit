"""
An :class:`~.KeyProcessor` receives callbacks for the keystrokes parsed from
the input in the :class:`~prompt_toolkit.inputstream.InputStream` instance.

The `KeyProcessor` will according to the implemented keybindings call the
correct callbacks when new key presses are feed through `feed`.
"""
from __future__ import annotations
import weakref
from asyncio import Task, sleep
from collections import deque
from typing import TYPE_CHECKING, Any, Generator
from prompt_toolkit.application.current import get_app
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.filters.app import vi_navigation_mode
from prompt_toolkit.keys import Keys
from prompt_toolkit.utils import Event
from .key_bindings import Binding, KeyBindingsBase
if TYPE_CHECKING:
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
__all__ = ['KeyProcessor', 'KeyPress', 'KeyPressEvent']

class KeyPress:
    """
    :param key: A `Keys` instance or text (one character).
    :param data: The received string on stdin. (Often vt100 escape codes.)
    """

    def __init__(self, key: Keys | str, data: str | None=None) -> None:
        assert isinstance(key, Keys) or len(key) == 1
        if data is None:
            if isinstance(key, Keys):
                data = key.value
            else:
                data = key
        self.key = key
        self.data = data

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(key={self.key!r}, data={self.data!r})'

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, KeyPress):
            return False
        return self.key == other.key and self.data == other.data
'\nHelper object to indicate flush operation in the KeyProcessor.\nNOTE: the implementation is very similar to the VT100 parser.\n'
_Flush = KeyPress('?', data='_Flush')

class KeyProcessor:
    """
    Statemachine that receives :class:`KeyPress` instances and according to the
    key bindings in the given :class:`KeyBindings`, calls the matching handlers.

    ::

        p = KeyProcessor(key_bindings)

        # Send keys into the processor.
        p.feed(KeyPress(Keys.ControlX, '\x18'))
        p.feed(KeyPress(Keys.ControlC, '\x03')

        # Process all the keys in the queue.
        p.process_keys()

        # Now the ControlX-ControlC callback will be called if this sequence is
        # registered in the key bindings.

    :param key_bindings: `KeyBindingsBase` instance.
    """

    def __init__(self, key_bindings: KeyBindingsBase) -> None:
        self._bindings = key_bindings
        self.before_key_press = Event(self)
        self.after_key_press = Event(self)
        self._flush_wait_task: Task[None] | None = None
        self.reset()

    def _get_matches(self, key_presses: list[KeyPress]) -> list[Binding]:
        """
        For a list of :class:`KeyPress` instances. Give the matching handlers
        that would handle this.
        """
        matches = []
        for binding in self._bindings.get_bindings_for_keys(key_presses):
            if binding.filter():
                matches.append(binding)
        return matches

    def _is_prefix_of_longer_match(self, key_presses: list[KeyPress]) -> bool:
        """
        For a list of :class:`KeyPress` instances. Return True if there is any
        handler that is bound to a suffix of this keys.
        """
        for binding in self._bindings.get_bindings_starting_with_keys(key_presses):
            if binding.filter():
                return True
        return False

    def _process(self) -> Generator[None, KeyPress, None]:
        """
        Coroutine implementing the key match algorithm. Key strokes are sent
        into this generator, and it calls the appropriate handlers.
        """
        buffer = []
        retry = False

        while True:
            if retry:
                retry = False
            else:
                key_press = yield

            if key_press is _Flush:
                self._flush()
                continue

            buffer.append(key_press)

            # If we have some key presses, check for matches.
            if buffer:
                matches = self._get_matches(buffer)
                if matches:
                    self._call_handler(matches[-1], key_sequence=buffer)
                    buffer = []
                elif self._is_prefix_of_longer_match(buffer):
                    retry = True
                else:
                    # No match found. Call the `feed_key` handler for the first key.
                    self._call_handler(
                        self._bindings.feed_key,
                        key_sequence=[buffer[0]],
                        first=True,
                    )
                    buffer = buffer[1:]
                    retry = True

    def feed(self, key_press: KeyPress, first: bool=False) -> None:
        """
        Add a new :class:`KeyPress` to the input queue.
        (Don't forget to call `process_keys` in order to process the queue.)

        :param first: If true, insert before everything else.
        """
        if first:
            self.input_queue.appendleft(key_press)
        else:
            self.input_queue.append(key_press)

    def feed_multiple(self, key_presses: list[KeyPress], first: bool=False) -> None:
        """
        :param first: If true, insert before everything else.
        """
        if first:
            self.input_queue.extendleft(reversed(key_presses))
        else:
            self.input_queue.extend(key_presses)

    def process_keys(self) -> None:
        """
        Process all the keys in the `input_queue`.
        (To be called after `feed`.)

        Note: because of the `feed`/`process_keys` separation, it is
              possible to call `feed` from inside a key binding.
              This function keeps looping until the queue is empty.
        """
        while self.input_queue:
            key_press = self.input_queue.popleft()
            self._process().send(key_press)

    def empty_queue(self) -> list[KeyPress]:
        """
        Empty the input queue. Return the unprocessed input.
        """
        key_presses = list(self.input_queue)
        self.input_queue.clear()
        return key_presses

    def _fix_vi_cursor_position(self, event: KeyPressEvent) -> None:
        """
        After every command, make sure that if we are in Vi navigation mode, we
        never put the cursor after the last character of a line. (Unless it's
        an empty line.)
        """
        app = event.app
        buff = app.current_buffer
        preferred_column = buff.preferred_column

        if (app.editing_mode == EditingMode.VI
                and app.vi_state.input_mode == 'navigation'
                and buff.document.is_cursor_at_the_end_of_line
                and len(buff.document.current_line) > 0):
            buff.cursor_position -= 1

        # Remember the preferred_column again.
        buff.preferred_column = preferred_column

    def _leave_vi_temp_navigation_mode(self, event: KeyPressEvent) -> None:
        """
        If we're in Vi temporary navigation (normal) mode, return to
        insert/replace mode after executing one action.
        """
        app = event.app
        if app.editing_mode == EditingMode.VI:
            vi_state = app.vi_state

            if vi_state.temporary_navigation_mode:
                vi_state.temporary_navigation_mode = False

                if vi_state.waiting_for_digraph:
                    vi_state.waiting_for_digraph = False
                elif vi_state.operator_func is None:
                    if vi_state.input_mode == 'replace':
                        event.app.vi_state.input_mode = 'insert'
                    vi_state.input_mode = 'insert'

    def _start_timeout(self) -> None:
        """
        Start auto flush timeout. Similar to Vim's `timeoutlen` option.

        Start a background coroutine with a timer. When this timeout expires
        and no key was pressed in the meantime, we flush all data in the queue
        and call the appropriate key binding handlers.
        """
        app = get_app()
        if app.timeoutlen:
            async def wait() -> None:
                await sleep(app.timeoutlen)
                self._flush_wait_task = None
                self.feed(_Flush)
                app.invalidate()

            if self._flush_wait_task:
                self._flush_wait_task.cancel()
            self._flush_wait_task = app.create_background_task(wait())

    def send_sigint(self) -> None:
        """
        Send SIGINT. Immediately call the SIGINT key handler.
        """
        sigint_key = KeyPress(Keys.ControlC, '\x03')
        self.feed(sigint_key)
        self.process_keys()

class KeyPressEvent:
    """
    Key press event, delivered to key bindings.

    :param key_processor_ref: Weak reference to the `KeyProcessor`.
    :param arg: Repetition argument.
    :param key_sequence: List of `KeyPress` instances.
    :param previouskey_sequence: Previous list of `KeyPress` instances.
    :param is_repeat: True when the previous event was delivered to the same handler.
    """

    def __init__(self, key_processor_ref: weakref.ReferenceType[KeyProcessor], arg: str | None, key_sequence: list[KeyPress], previous_key_sequence: list[KeyPress], is_repeat: bool) -> None:
        self._key_processor_ref = key_processor_ref
        self.key_sequence = key_sequence
        self.previous_key_sequence = previous_key_sequence
        self.is_repeat = is_repeat
        self._arg = arg
        self._app = get_app()

    def __repr__(self) -> str:
        return 'KeyPressEvent(arg={!r}, key_sequence={!r}, is_repeat={!r})'.format(self.arg, self.key_sequence, self.is_repeat)

    @property
    def app(self) -> Application[Any]:
        """
        The current `Application` object.
        """
        return self._app

    @property
    def current_buffer(self) -> Buffer:
        """
        The current buffer.
        """
        return self.app.current_buffer

    @property
    def arg(self) -> int:
        """
        Repetition argument.
        """
        if self._arg is None:
            return 1
        return int(self._arg)

    @property
    def arg_present(self) -> bool:
        """
        True if repetition argument was explicitly provided.
        """
        return self._arg is not None

    def append_to_arg_count(self, data: str) -> None:
        """
        Add digit to the input argument.

        :param data: the typed digit as string
        """
        assert data in '0123456789'
        if self._arg is None:
            self._arg = data
        else:
            self._arg += data

    @property
    def cli(self) -> Application[Any]:
        """For backward-compatibility."""
        return self.app
