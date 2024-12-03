"""
Data structures for the Buffer.
It holds the text, cursor position, history, etc...
"""
from __future__ import annotations
import asyncio
import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections import deque
from enum import Enum
from functools import wraps
from typing import Any, Callable, Coroutine, Iterable, TypeVar, cast
from .application.current import get_app
from .application.run_in_terminal import run_in_terminal
from .auto_suggest import AutoSuggest, Suggestion
from .cache import FastDictCache
from .clipboard import ClipboardData
from .completion import CompleteEvent, Completer, Completion, DummyCompleter, get_common_complete_suffix
from .document import Document
from .eventloop import aclosing
from .filters import FilterOrBool, to_filter
from .history import History, InMemoryHistory
from .search import SearchDirection, SearchState
from .selection import PasteMode, SelectionState, SelectionType
from .utils import Event, to_str
from .validation import ValidationError, Validator
__all__ = ['EditReadOnlyBuffer', 'Buffer', 'CompletionState', 'indent', 'unindent', 'reshape_text']
logger = logging.getLogger(__name__)

class EditReadOnlyBuffer(Exception):
    """Attempt editing of read-only :class:`.Buffer`."""

class ValidationState(Enum):
    """The validation state of a buffer. This is set after the validation."""
    VALID = 'VALID'
    INVALID = 'INVALID'
    UNKNOWN = 'UNKNOWN'

class CompletionState:
    """
    Immutable class that contains a completion state.
    """

    def __init__(self, original_document: Document, completions: list[Completion] | None=None, complete_index: int | None=None) -> None:
        self.original_document = original_document
        self.completions = completions or []
        self.complete_index = complete_index

    def __repr__(self) -> str:
        return '{}({!r}, <{!r}> completions, index={!r})'.format(self.__class__.__name__, self.original_document, len(self.completions), self.complete_index)

    def go_to_index(self, index: int | None) -> None:
        """
        Create a new :class:`.CompletionState` object with the new index.

        When `index` is `None` deselect the completion.
        """
        if self.completions:
            self.complete_index = index
            if index is not None:
                self.complete_index = max(0, min(index, len(self.completions) - 1))

    def new_text_and_position(self) -> tuple[str, int]:
        """
        Return (new_text, new_cursor_position) for this completion.
        """
        if self.current_completion:
            completed = self.current_completion.text
            position = self.original_document.cursor_position - len(self.current_completion.start_position) + len(completed)
            new_text = self.original_document.text[:self.current_completion.start_position] + completed + self.original_document.text[self.original_document.cursor_position:]
            return new_text, position
        return self.original_document.text, self.original_document.cursor_position

    @property
    def current_completion(self) -> Completion | None:
        """
        Return the current completion, or return `None` when no completion is
        selected.
        """
        if self.complete_index is not None and self.completions:
            return self.completions[self.complete_index]
        return None
_QUOTED_WORDS_RE = re.compile('(\\s+|".*?"|\'.*?\')')

class YankNthArgState:
    """
    For yank-last-arg/yank-nth-arg: Keep track of where we are in the history.
    """

    def __init__(self, history_position: int=0, n: int=-1, previous_inserted_word: str='') -> None:
        self.history_position = history_position
        self.previous_inserted_word = previous_inserted_word
        self.n = n

    def __repr__(self) -> str:
        return '{}(history_position={!r}, n={!r}, previous_inserted_word={!r})'.format(self.__class__.__name__, self.history_position, self.n, self.previous_inserted_word)
BufferEventHandler = Callable[['Buffer'], None]
BufferAcceptHandler = Callable[['Buffer'], bool]

class Buffer:
    """
    The core data structure that holds the text and cursor position of the
    current input line and implements all text manipulations on top of it. It
    also implements the history, undo stack and the completion state.

    :param completer: :class:`~prompt_toolkit.completion.Completer` instance.
    :param history: :class:`~prompt_toolkit.history.History` instance.
    :param tempfile_suffix: The tempfile suffix (extension) to be used for the
        "open in editor" function. For a Python REPL, this would be ".py", so
        that the editor knows the syntax highlighting to use. This can also be
        a callable that returns a string.
    :param tempfile: For more advanced tempfile situations where you need
        control over the subdirectories and filename. For a Git Commit Message,
        this would be ".git/COMMIT_EDITMSG", so that the editor knows the syntax
        highlighting to use. This can also be a callable that returns a string.
    :param name: Name for this buffer. E.g. DEFAULT_BUFFER. This is mostly
        useful for key bindings where we sometimes prefer to refer to a buffer
        by their name instead of by reference.
    :param accept_handler: Called when the buffer input is accepted. (Usually
        when the user presses `enter`.) The accept handler receives this
        `Buffer` as input and should return True when the buffer text should be
        kept instead of calling reset.

        In case of a `PromptSession` for instance, we want to keep the text,
        because we will exit the application, and only reset it during the next
        run.

    Events:

    :param on_text_changed: When the buffer text changes. (Callable or None.)
    :param on_text_insert: When new text is inserted. (Callable or None.)
    :param on_cursor_position_changed: When the cursor moves. (Callable or None.)
    :param on_completions_changed: When the completions were changed. (Callable or None.)
    :param on_suggestion_set: When an auto-suggestion text has been set. (Callable or None.)

    Filters:

    :param complete_while_typing: :class:`~prompt_toolkit.filters.Filter`
        or `bool`. Decide whether or not to do asynchronous autocompleting while
        typing.
    :param validate_while_typing: :class:`~prompt_toolkit.filters.Filter`
        or `bool`. Decide whether or not to do asynchronous validation while
        typing.
    :param enable_history_search: :class:`~prompt_toolkit.filters.Filter` or
        `bool` to indicate when up-arrow partial string matching is enabled. It
        is advised to not enable this at the same time as
        `complete_while_typing`, because when there is an autocompletion found,
        the up arrows usually browse through the completions, rather than
        through the history.
    :param read_only: :class:`~prompt_toolkit.filters.Filter`. When True,
        changes will not be allowed.
    :param multiline: :class:`~prompt_toolkit.filters.Filter` or `bool`. When
        not set, pressing `Enter` will call the `accept_handler`.  Otherwise,
        pressing `Esc-Enter` is required.
    """

    def __init__(self, completer: Completer | None=None, auto_suggest: AutoSuggest | None=None, history: History | None=None, validator: Validator | None=None, tempfile_suffix: str | Callable[[], str]='', tempfile: str | Callable[[], str]='', name: str='', complete_while_typing: FilterOrBool=False, validate_while_typing: FilterOrBool=False, enable_history_search: FilterOrBool=False, document: Document | None=None, accept_handler: BufferAcceptHandler | None=None, read_only: FilterOrBool=False, multiline: FilterOrBool=True, on_text_changed: BufferEventHandler | None=None, on_text_insert: BufferEventHandler | None=None, on_cursor_position_changed: BufferEventHandler | None=None, on_completions_changed: BufferEventHandler | None=None, on_suggestion_set: BufferEventHandler | None=None):
        enable_history_search = to_filter(enable_history_search)
        complete_while_typing = to_filter(complete_while_typing)
        validate_while_typing = to_filter(validate_while_typing)
        read_only = to_filter(read_only)
        multiline = to_filter(multiline)
        self.completer = completer or DummyCompleter()
        self.auto_suggest = auto_suggest
        self.validator = validator
        self.tempfile_suffix = tempfile_suffix
        self.tempfile = tempfile
        self.name = name
        self.accept_handler = accept_handler
        self.complete_while_typing = complete_while_typing
        self.validate_while_typing = validate_while_typing
        self.enable_history_search = enable_history_search
        self.read_only = read_only
        self.multiline = multiline
        self.text_width = 0
        self.history = InMemoryHistory() if history is None else history
        self.__cursor_position = 0
        self.on_text_changed: Event[Buffer] = Event(self, on_text_changed)
        self.on_text_insert: Event[Buffer] = Event(self, on_text_insert)
        self.on_cursor_position_changed: Event[Buffer] = Event(self, on_cursor_position_changed)
        self.on_completions_changed: Event[Buffer] = Event(self, on_completions_changed)
        self.on_suggestion_set: Event[Buffer] = Event(self, on_suggestion_set)
        self._document_cache: FastDictCache[tuple[str, int, SelectionState | None], Document] = FastDictCache(Document, size=10)
        self._async_suggester = self._create_auto_suggest_coroutine()
        self._async_completer = self._create_completer_coroutine()
        self._async_validator = self._create_auto_validate_coroutine()
        self._load_history_task: asyncio.Future[None] | None = None
        self.reset(document=document)

    def __repr__(self) -> str:
        if len(self.text) < 15:
            text = self.text
        else:
            text = self.text[:12] + '...'
        return f'<Buffer(name={self.name!r}, text={text!r}) at {id(self)!r}>'

    def reset(self, document: Document | None=None, append_to_history: bool=False) -> None:
        """
        :param append_to_history: Append current input to history first.
        """
        if append_to_history:
            self.append_to_history()

        if document is None:
            document = Document()

        self.document = document
        self._undo_stack = []
        self._redo_stack = []

        self.selection_state = None
        self.suggestion = None
        self.complete_state = None
        self.yank_nth_arg_state = None
        self.validation_state = ValidationState.UNKNOWN
        self.validation_error = None

        self.on_text_changed.fire()
        self.on_cursor_position_changed.fire()

    def load_history_if_not_yet_loaded(self) -> None:
        """
        Create task for populating the buffer history (if not yet done).

        Note::

            This needs to be called from within the event loop of the
            application, because history loading is async, and we need to be
            sure the right event loop is active. Therefor, we call this method
            in the `BufferControl.create_content`.

            There are situations where prompt_toolkit applications are created
            in one thread, but will later run in a different thread (Ptpython
            is one example. The REPL runs in a separate thread, in order to
            prevent interfering with a potential different event loop in the
            main thread. The REPL UI however is still created in the main
            thread.) We could decide to not support creating prompt_toolkit
            objects in one thread and running the application in a different
            thread, but history loading is the only place where it matters, and
            this solves it.
        """
        if self._load_history_task is None:
            self._load_history_task = asyncio.create_task(self.history.load())

    def _set_text(self, value: str) -> bool:
        """set text at current working_index. Return whether it changed."""
        original_value = self.text
        self._text = value
        return value != original_value

    def _set_cursor_position(self, value: int) -> bool:
        """Set cursor position. Return whether it changed."""
        original_position = self.__cursor_position
        self.__cursor_position = max(0, min(value, len(self.text)))
        return self.__cursor_position != original_position

    @text.setter
    def text(self, value: str) -> None:
        """
        Setting text. (When doing this, make sure that the cursor_position is
        valid for this text. text/cursor_position should be consistent at any time,
        otherwise set a Document instead.)
        """
        if self._set_text(value):
            self.cursor_position = min(self.cursor_position, len(value))
            self.on_text_changed.fire()

    @cursor_position.setter
    def cursor_position(self, value: int) -> None:
        """
        Setting cursor position.
        """
        if self._set_cursor_position(value):
            self.on_cursor_position_changed.fire()

    @property
    def document(self) -> Document:
        """
        Return :class:`~prompt_toolkit.document.Document` instance from the
        current text, cursor position and selection state.
        """
        return self._document_cache.get((self.text, self.cursor_position, self.selection_state))

    @document.setter
    def document(self, value: Document) -> None:
        """
        Set :class:`~prompt_toolkit.document.Document` instance.

        This will set both the text and cursor position at the same time, but
        atomically. (Change events will be triggered only after both have been set.)
        """
        self.set_document(value)

    def set_document(self, value: Document, bypass_readonly: bool=False) -> None:
        """
        Set :class:`~prompt_toolkit.document.Document` instance. Like the
        ``document`` property, but accept an ``bypass_readonly`` argument.

        :param bypass_readonly: When True, don't raise an
                                :class:`.EditReadOnlyBuffer` exception, even
                                when the buffer is read-only.

        .. warning::

            When this buffer is read-only and `bypass_readonly` was not passed,
            the `EditReadOnlyBuffer` exception will be caught by the
            `KeyProcessor` and is silently suppressed. This is important to
            keep in mind when writing key bindings, because it won't do what
            you expect, and there won't be a stack trace. Use try/finally
            around this function if you need some cleanup code.
        """
        if not bypass_readonly and self.read_only():
            raise EditReadOnlyBuffer()

        text_changed = self._set_text(value.text)
        cursor_position_changed = self._set_cursor_position(value.cursor_position)

        if text_changed:
            self.on_text_changed.fire()
        if cursor_position_changed:
            self.on_cursor_position_changed.fire()

    @property
    def is_returnable(self) -> bool:
        """
        True when there is something handling accept.
        """
        pass

    def save_to_undo_stack(self, clear_redo_stack: bool=True) -> None:
        """
        Safe current state (input text and cursor position), so that we can
        restore it by calling undo.
        """
        pass

    def transform_lines(self, line_index_iterator: Iterable[int], transform_callback: Callable[[str], str]) -> str:
        """
        Transforms the text on a range of lines.
        When the iterator yield an index not in the range of lines that the
        document contains, it skips them silently.

        To uppercase some lines::

            new_text = transform_lines(range(5,10), lambda text: text.upper())

        :param line_index_iterator: Iterator of line numbers (int)
        :param transform_callback: callable that takes the original text of a
                                   line, and return the new text for this line.

        :returns: The new text.
        """
        pass

    def transform_current_line(self, transform_callback: Callable[[str], str]) -> None:
        """
        Apply the given transformation function to the current line.

        :param transform_callback: callable that takes a string and return a new string.
        """
        pass

    def transform_region(self, from_: int, to: int, transform_callback: Callable[[str], str]) -> None:
        """
        Transform a part of the input string.

        :param from_: (int) start position.
        :param to: (int) end position.
        :param transform_callback: Callable which accepts a string and returns
            the transformed string.
        """
        pass

    def cursor_up(self, count: int=1) -> None:
        """(for multiline edit). Move cursor to the previous line."""
        pass

    def cursor_down(self, count: int=1) -> None:
        """(for multiline edit). Move cursor to the next line."""
        pass

    def auto_up(self, count: int=1, go_to_start_of_line_if_history_changes: bool=False) -> None:
        """
        If we're not on the first line (of a multiline input) go a line up,
        otherwise go back in history. (If nothing is selected.)
        """
        pass

    def auto_down(self, count: int=1, go_to_start_of_line_if_history_changes: bool=False) -> None:
        """
        If we're not on the last line (of a multiline input) go a line down,
        otherwise go forward in history. (If nothing is selected.)
        """
        pass

    def delete_before_cursor(self, count: int=1) -> str:
        """
        Delete specified number of characters before cursor and return the
        deleted text.
        """
        pass

    def delete(self, count: int=1) -> str:
        """
        Delete specified number of characters and Return the deleted text.
        """
        pass

    def join_next_line(self, separator: str=' ') -> None:
        """
        Join the next line to the current one by deleting the line ending after
        the current line.
        """
        pass

    def join_selected_lines(self, separator: str=' ') -> None:
        """
        Join the selected lines.
        """
        pass

    def swap_characters_before_cursor(self) -> None:
        """
        Swap the last two characters before the cursor.
        """
        pass

    def go_to_history(self, index: int) -> None:
        """
        Go to this item in the history.
        """
        pass

    def complete_next(self, count: int=1, disable_wrap_around: bool=False) -> None:
        """
        Browse to the next completions.
        (Does nothing if there are no completion.)
        """
        pass

    def complete_previous(self, count: int=1, disable_wrap_around: bool=False) -> None:
        """
        Browse to the previous completions.
        (Does nothing if there are no completion.)
        """
        pass

    def cancel_completion(self) -> None:
        """
        Cancel completion, go back to the original text.
        """
        pass

    def _set_completions(self, completions: list[Completion]) -> CompletionState:
        """
        Start completions. (Generate list of completions and initialize.)

        By default, no completion will be selected.
        """
        pass

    def start_history_lines_completion(self) -> None:
        """
        Start a completion based on all the other lines in the document and the
        history.
        """
        pass

    def go_to_completion(self, index: int | None) -> None:
        """
        Select a completion from the list of current completions.
        """
        pass

    def apply_completion(self, completion: Completion) -> None:
        """
        Insert a given completion.
        """
        pass

    def _set_history_search(self) -> None:
        """
        Set `history_search_text`.
        (The text before the cursor will be used for filtering the history.)
        """
        pass

    def _history_matches(self, i: int) -> bool:
        """
        True when the current entry matches the history search.
        (when we don't have history search, it's also True.)
        """
        pass

    def history_forward(self, count: int=1) -> None:
        """
        Move forwards through the history.

        :param count: Amount of items to move forward.
        """
        pass

    def history_backward(self, count: int=1) -> None:
        """
        Move backwards through history.
        """
        pass

    def yank_nth_arg(self, n: int | None=None, _yank_last_arg: bool=False) -> None:
        """
        Pick nth word from previous history entry (depending on current
        `yank_nth_arg_state`) and insert it at current position. Rotate through
        history if called repeatedly. If no `n` has been given, take the first
        argument. (The second word.)

        :param n: (None or int), The index of the word from the previous line
            to take.
        """
        pass

    def yank_last_arg(self, n: int | None=None) -> None:
        """
        Like `yank_nth_arg`, but if no argument has been given, yank the last
        word by default.
        """
        pass

    def start_selection(self, selection_type: SelectionType=SelectionType.CHARACTERS) -> None:
        """
        Take the current cursor position as the start of this selection.
        """
        pass

    def copy_selection(self, _cut: bool=False) -> ClipboardData:
        """
        Copy selected text and return :class:`.ClipboardData` instance.

        Notice that this doesn't store the copied data on the clipboard yet.
        You can store it like this:

        .. code:: python

            data = buffer.copy_selection()
            get_app().clipboard.set_data(data)
        """
        pass

    def cut_selection(self) -> ClipboardData:
        """
        Delete selected text and return :class:`.ClipboardData` instance.
        """
        pass

    def paste_clipboard_data(self, data: ClipboardData, paste_mode: PasteMode=PasteMode.EMACS, count: int=1) -> None:
        """
        Insert the data from the clipboard.
        """
        pass

    def newline(self, copy_margin: bool=True) -> None:
        """
        Insert a line ending at the current position.
        """
        pass

    def insert_line_above(self, copy_margin: bool=True) -> None:
        """
        Insert a new line above the current one.
        """
        pass

    def insert_line_below(self, copy_margin: bool=True) -> None:
        """
        Insert a new line below the current one.
        """
        pass

    def insert_text(self, data: str, overwrite: bool=False, move_cursor: bool=True, fire_event: bool=True) -> None:
        """
        Insert characters at cursor position.

        :param fire_event: Fire `on_text_insert` event. This is mainly used to
            trigger autocompletion while typing.
        """
        pass

    def validate(self, set_cursor: bool=False) -> bool:
        """
        Returns `True` if valid.

        :param set_cursor: Set the cursor position, if an error was found.
        """
        pass

    async def _validate_async(self) -> None:
        """
        Asynchronous version of `validate()`.
        This one doesn't set the cursor position.

        We have both variants, because a synchronous version is required.
        Handling the ENTER key needs to be completely synchronous, otherwise
        stuff like type-ahead is going to give very weird results. (People
        could type input while the ENTER key is still processed.)

        An asynchronous version is required if we have `validate_while_typing`
        enabled.
        """
        pass

    def append_to_history(self) -> None:
        """
        Append the current input to the history.
        """
        pass

    def _search(self, search_state: SearchState, include_current_position: bool=False, count: int=1) -> tuple[int, int] | None:
        """
        Execute search. Return (working_index, cursor_position) tuple when this
        search is applied. Returns `None` when this text cannot be found.
        """
        pass

    def document_for_search(self, search_state: SearchState) -> Document:
        """
        Return a :class:`~prompt_toolkit.document.Document` instance that has
        the text/cursor position for this search, if we would apply it. This
        will be used in the
        :class:`~prompt_toolkit.layout.BufferControl` to display feedback while
        searching.
        """
        pass

    def get_search_position(self, search_state: SearchState, include_current_position: bool=True, count: int=1) -> int:
        """
        Get the cursor position for this search.
        (This operation won't change the `working_index`. It's won't go through
        the history. Vi text objects can't span multiple items.)
        """
        pass

    def apply_search(self, search_state: SearchState, include_current_position: bool=True, count: int=1) -> None:
        """
        Apply search. If something is found, set `working_index` and
        `cursor_position`.
        """
        pass

    def _editor_simple_tempfile(self) -> tuple[str, Callable[[], None]]:
        """
        Simple (file) tempfile implementation.
        Return (tempfile, cleanup_func).
        """
        pass

    def open_in_editor(self, validate_and_handle: bool=False) -> asyncio.Task[None]:
        """
        Open code in editor.

        This returns a future, and runs in a thread executor.
        """
        pass

    def _open_file_in_editor(self, filename: str) -> bool:
        """
        Call editor executable.

        Return True when we received a zero return code.
        """
        pass

    def start_completion(self, select_first: bool=False, select_last: bool=False, insert_common_part: bool=False, complete_event: CompleteEvent | None=None) -> None:
        """
        Start asynchronous autocompletion of this buffer.
        (This will do nothing if a previous completion was still in progress.)
        """
        pass

    def _create_completer_coroutine(self) -> Callable[..., Coroutine[Any, Any, None]]:
        """
        Create function for asynchronous autocompletion.

        (This consumes the asynchronous completer generator, which possibly
        runs the completion algorithm in another thread.)
        """
        pass

    def _create_auto_suggest_coroutine(self) -> Callable[[], Coroutine[Any, Any, None]]:
        """
        Create function for asynchronous auto suggestion.
        (This can be in another thread.)
        """
        pass

    def _create_auto_validate_coroutine(self) -> Callable[[], Coroutine[Any, Any, None]]:
        """
        Create a function for asynchronous validation while typing.
        (This can be in another thread.)
        """
        pass

    def validate_and_handle(self) -> None:
        """
        Validate buffer and handle the accept action.
        """
        pass
_T = TypeVar('_T', bound=Callable[..., Coroutine[Any, Any, None]])

def _only_one_at_a_time(coroutine: _T) -> _T:
    """
    Decorator that only starts the coroutine only if the previous call has
    finished. (Used to make sure that we have only one autocompleter, auto
    suggestor and validator running at a time.)

    When the coroutine raises `_Retry`, it is restarted.
    """
    pass

class _Retry(Exception):
    """Retry in `_only_one_at_a_time`."""

def indent(buffer: Buffer, from_row: int, to_row: int, count: int=1) -> None:
    """
    Indent text of a :class:`.Buffer` object.
    """
    pass

def unindent(buffer: Buffer, from_row: int, to_row: int, count: int=1) -> None:
    """
    Unindent text of a :class:`.Buffer` object.
    """
    pass

def reshape_text(buffer: Buffer, from_row: int, to_row: int) -> None:
    """
    Reformat text, taking the width into account.
    `to_row` is included.
    (Vi 'gq' operator.)
    """
    pass
