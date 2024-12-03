"""
The `Document` that implements all the text operations/querying.
"""
from __future__ import annotations
import bisect
import re
import string
import weakref
from typing import Callable, Dict, Iterable, List, NoReturn, Pattern, cast
from .clipboard import ClipboardData
from .filters import vi_mode
from .selection import PasteMode, SelectionState, SelectionType
__all__ = ['Document']
_FIND_WORD_RE = re.compile('([a-zA-Z0-9_]+|[^a-zA-Z0-9_\\s]+)')
_FIND_CURRENT_WORD_RE = re.compile('^([a-zA-Z0-9_]+|[^a-zA-Z0-9_\\s]+)')
_FIND_CURRENT_WORD_INCLUDE_TRAILING_WHITESPACE_RE = re.compile('^(([a-zA-Z0-9_]+|[^a-zA-Z0-9_\\s]+)\\s*)')
_FIND_BIG_WORD_RE = re.compile('([^\\s]+)')
_FIND_CURRENT_BIG_WORD_RE = re.compile('^([^\\s]+)')
_FIND_CURRENT_BIG_WORD_INCLUDE_TRAILING_WHITESPACE_RE = re.compile('^([^\\s]+\\s*)')
_text_to_document_cache: dict[str, _DocumentCache] = cast(Dict[str, '_DocumentCache'], weakref.WeakValueDictionary())

class _ImmutableLineList(List[str]):
    """
    Some protection for our 'lines' list, which is assumed to be immutable in the cache.
    (Useful for detecting obvious bugs.)
    """
    __setitem__ = _error
    append = _error
    clear = _error
    extend = _error
    insert = _error
    pop = _error
    remove = _error
    reverse = _error
    sort = _error

class _DocumentCache:

    def __init__(self) -> None:
        self.lines: _ImmutableLineList | None = None
        self.line_indexes: list[int] | None = None

class Document:
    """
    This is a immutable class around the text and cursor position, and contains
    methods for querying this data, e.g. to give the text before the cursor.

    This class is usually instantiated by a :class:`~prompt_toolkit.buffer.Buffer`
    object, and accessed as the `document` property of that class.

    :param text: string
    :param cursor_position: int
    :param selection: :class:`.SelectionState`
    """
    __slots__ = ('_text', '_cursor_position', '_selection', '_cache')

    def __init__(self, text: str='', cursor_position: int | None=None, selection: SelectionState | None=None) -> None:
        assert cursor_position is None or cursor_position <= len(text), AssertionError(f'cursor_position={cursor_position!r}, len_text={len(text)!r}')
        if cursor_position is None:
            cursor_position = len(text)
        self._text = text
        self._cursor_position = cursor_position
        self._selection = selection
        try:
            self._cache = _text_to_document_cache[self.text]
        except KeyError:
            self._cache = _DocumentCache()
            _text_to_document_cache[self.text] = self._cache

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.text!r}, {self.cursor_position!r})'

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Document):
            return False
        return self.text == other.text and self.cursor_position == other.cursor_position and (self.selection == other.selection)

    @property
    def text(self) -> str:
        """The document text."""
        return self._text

    @property
    def cursor_position(self) -> int:
        """The document cursor position."""
        return self._cursor_position

    @property
    def selection(self) -> SelectionState | None:
        """:class:`.SelectionState` object."""
        return self._selection

    @property
    def current_char(self) -> str:
        """Return character under cursor or an empty string."""
        return self._text[self._cursor_position] if self._cursor_position < len(self._text) else ''

    @property
    def char_before_cursor(self) -> str:
        """Return character before the cursor or an empty string."""
        return self._text[self._cursor_position - 1] if self._cursor_position > 0 else ''

    @property
    def current_line_before_cursor(self) -> str:
        """Text from the start of the line until the cursor."""
        return self._text[:self._cursor_position].split('\n')[-1]

    @property
    def current_line_after_cursor(self) -> str:
        """Text from the cursor until the end of the line."""
        return self._text[self._cursor_position:].split('\n')[0]

    @property
    def lines(self) -> list[str]:
        """
        Array of all the lines.
        """
        if self._cache.lines is None:
            self._cache.lines = _ImmutableLineList(self._text.split('\n'))
        return self._cache.lines

    @property
    def _line_start_indexes(self) -> list[int]:
        """
        Array pointing to the start indexes of all the lines.
        """
        if self._cache.line_indexes is None:
            indexes = [0]
            for line in self.lines[:-1]:
                indexes.append(indexes[-1] + len(line) + 1)
            self._cache.line_indexes = indexes
        return self._cache.line_indexes

    @property
    def lines_from_current(self) -> list[str]:
        """
        Array of the lines starting from the current line, until the last line.
        """
        return self.lines[self.cursor_position_row:]

    @property
    def line_count(self) -> int:
        """Return the number of lines in this document. If the document ends
        with a trailing \\n, that counts as the beginning of a new line."""
        return len(self.lines)

    @property
    def current_line(self) -> str:
        """Return the text on the line where the cursor is. (when the input
        consists of just one line, it equals `text`."""
        return self.lines[self.cursor_position_row]

    @property
    def leading_whitespace_in_current_line(self) -> str:
        """The leading whitespace in the left margin of the current line."""
        return self.current_line[:len(self.current_line) - len(self.current_line.lstrip())]

    def _get_char_relative_to_cursor(self, offset: int=0) -> str:
        """
        Return character relative to cursor position, or empty string
        """
        try:
            return self._text[self._cursor_position + offset]
        except IndexError:
            return ''

    @property
    def on_first_line(self) -> bool:
        """
        True when we are at the first line.
        """
        return self.cursor_position_row == 0

    @property
    def on_last_line(self) -> bool:
        """
        True when we are at the last line.
        """
        return self.cursor_position_row == self.line_count - 1

    @property
    def cursor_position_row(self) -> int:
        """
        Current row. (0-based.)
        """
        return bisect.bisect_right(self._line_start_indexes, self._cursor_position) - 1

    @property
    def cursor_position_col(self) -> int:
        """
        Current column. (0-based.)
        """
        return self._cursor_position - self._line_start_indexes[self.cursor_position_row]

    def _find_line_start_index(self, index: int) -> tuple[int, int]:
        """
        For the index of a character at a certain line, calculate the index of
        the first character on that line.

        Return (row, index) tuple.
        """
        pass

    def translate_index_to_position(self, index: int) -> tuple[int, int]:
        """
        Given an index for the text, return the corresponding (row, col) tuple.
        (0-based. Returns (0, 0) for index=0.)
        """
        pass

    def translate_row_col_to_index(self, row: int, col: int) -> int:
        """
        Given a (row, col) tuple, return the corresponding index.
        (Row and col params are 0-based.)

        Negative row/col values are turned into zero.
        """
        pass

    @property
    def is_cursor_at_the_end(self) -> bool:
        """True when the cursor is at the end of the text."""
        pass

    @property
    def is_cursor_at_the_end_of_line(self) -> bool:
        """True when the cursor is at the end of this line."""
        pass

    def has_match_at_current_position(self, sub: str) -> bool:
        """
        `True` when this substring is found at the cursor position.
        """
        pass

    def find(self, sub: str, in_current_line: bool=False, include_current_position: bool=False, ignore_case: bool=False, count: int=1) -> int | None:
        """
        Find `text` after the cursor, return position relative to the cursor
        position. Return `None` if nothing was found.

        :param count: Find the n-th occurrence.
        """
        pass

    def find_all(self, sub: str, ignore_case: bool=False) -> list[int]:
        """
        Find all occurrences of the substring. Return a list of absolute
        positions in the document.
        """
        pass

    def find_backwards(self, sub: str, in_current_line: bool=False, ignore_case: bool=False, count: int=1) -> int | None:
        """
        Find `text` before the cursor, return position relative to the cursor
        position. Return `None` if nothing was found.

        :param count: Find the n-th occurrence.
        """
        pass

    def get_word_before_cursor(self, WORD: bool=False, pattern: Pattern[str] | None=None) -> str:
        """
        Give the word before the cursor.
        If we have whitespace before the cursor this returns an empty string.

        :param pattern: (None or compiled regex). When given, use this regex
            pattern.
        """
        pass

    def find_start_of_previous_word(self, count: int=1, WORD: bool=False, pattern: Pattern[str] | None=None) -> int | None:
        """
        Return an index relative to the cursor position pointing to the start
        of the previous word. Return `None` if nothing was found.

        :param pattern: (None or compiled regex). When given, use this regex
            pattern.
        """
        pass

    def find_boundaries_of_current_word(self, WORD: bool=False, include_leading_whitespace: bool=False, include_trailing_whitespace: bool=False) -> tuple[int, int]:
        """
        Return the relative boundaries (startpos, endpos) of the current word under the
        cursor. (This is at the current line, because line boundaries obviously
        don't belong to any word.)
        If not on a word, this returns (0,0)
        """
        pass

    def get_word_under_cursor(self, WORD: bool=False) -> str:
        """
        Return the word, currently below the cursor.
        This returns an empty string when the cursor is on a whitespace region.
        """
        pass

    def find_next_word_beginning(self, count: int=1, WORD: bool=False) -> int | None:
        """
        Return an index relative to the cursor position pointing to the start
        of the next word. Return `None` if nothing was found.
        """
        pass

    def find_next_word_ending(self, include_current_position: bool=False, count: int=1, WORD: bool=False) -> int | None:
        """
        Return an index relative to the cursor position pointing to the end
        of the next word. Return `None` if nothing was found.
        """
        pass

    def find_previous_word_beginning(self, count: int=1, WORD: bool=False) -> int | None:
        """
        Return an index relative to the cursor position pointing to the start
        of the previous word. Return `None` if nothing was found.
        """
        pass

    def find_previous_word_ending(self, count: int=1, WORD: bool=False) -> int | None:
        """
        Return an index relative to the cursor position pointing to the end
        of the previous word. Return `None` if nothing was found.
        """
        pass

    def find_next_matching_line(self, match_func: Callable[[str], bool], count: int=1) -> int | None:
        """
        Look downwards for empty lines.
        Return the line index, relative to the current line.
        """
        pass

    def find_previous_matching_line(self, match_func: Callable[[str], bool], count: int=1) -> int | None:
        """
        Look upwards for empty lines.
        Return the line index, relative to the current line.
        """
        pass

    def get_cursor_left_position(self, count: int=1) -> int:
        """
        Relative position for cursor left.
        """
        pass

    def get_cursor_right_position(self, count: int=1) -> int:
        """
        Relative position for cursor_right.
        """
        pass

    def get_cursor_up_position(self, count: int=1, preferred_column: int | None=None) -> int:
        """
        Return the relative cursor position (character index) where we would be if the
        user pressed the arrow-up button.

        :param preferred_column: When given, go to this column instead of
                                 staying at the current column.
        """
        pass

    def get_cursor_down_position(self, count: int=1, preferred_column: int | None=None) -> int:
        """
        Return the relative cursor position (character index) where we would be if the
        user pressed the arrow-down button.

        :param preferred_column: When given, go to this column instead of
                                 staying at the current column.
        """
        pass

    def find_enclosing_bracket_right(self, left_ch: str, right_ch: str, end_pos: int | None=None) -> int | None:
        """
        Find the right bracket enclosing current position. Return the relative
        position to the cursor position.

        When `end_pos` is given, don't look past the position.
        """
        pass

    def find_enclosing_bracket_left(self, left_ch: str, right_ch: str, start_pos: int | None=None) -> int | None:
        """
        Find the left bracket enclosing current position. Return the relative
        position to the cursor position.

        When `start_pos` is given, don't look past the position.
        """
        pass

    def find_matching_bracket_position(self, start_pos: int | None=None, end_pos: int | None=None) -> int:
        """
        Return relative cursor position of matching [, (, { or < bracket.

        When `start_pos` or `end_pos` are given. Don't look past the positions.
        """
        pass

    def get_start_of_document_position(self) -> int:
        """Relative position for the start of the document."""
        pass

    def get_end_of_document_position(self) -> int:
        """Relative position for the end of the document."""
        pass

    def get_start_of_line_position(self, after_whitespace: bool=False) -> int:
        """Relative position for the start of this line."""
        pass

    def get_end_of_line_position(self) -> int:
        """Relative position for the end of this line."""
        pass

    def last_non_blank_of_current_line_position(self) -> int:
        """
        Relative position for the last non blank character of this line.
        """
        pass

    def get_column_cursor_position(self, column: int) -> int:
        """
        Return the relative cursor position for this column at the current
        line. (It will stay between the boundaries of the line in case of a
        larger number.)
        """
        pass

    def selection_range(self) -> tuple[int, int]:
        """
        Return (from, to) tuple of the selection.
        start and end position are included.

        This doesn't take the selection type into account. Use
        `selection_ranges` instead.
        """
        pass

    def selection_ranges(self) -> Iterable[tuple[int, int]]:
        """
        Return a list of `(from, to)` tuples for the selection or none if
        nothing was selected. The upper boundary is not included.

        This will yield several (from, to) tuples in case of a BLOCK selection.
        This will return zero ranges, like (8,8) for empty lines in a block
        selection.
        """
        pass

    def selection_range_at_line(self, row: int) -> tuple[int, int] | None:
        """
        If the selection spans a portion of the given line, return a (from, to) tuple.

        The returned upper boundary is not included in the selection, so
        `(0, 0)` is an empty selection.  `(0, 1)`, is a one character selection.

        Returns None if the selection doesn't cover this line at all.
        """
        pass

    def cut_selection(self) -> tuple[Document, ClipboardData]:
        """
        Return a (:class:`.Document`, :class:`.ClipboardData`) tuple, where the
        document represents the new document when the selection is cut, and the
        clipboard data, represents whatever has to be put on the clipboard.
        """
        pass

    def paste_clipboard_data(self, data: ClipboardData, paste_mode: PasteMode=PasteMode.EMACS, count: int=1) -> Document:
        """
        Return a new :class:`.Document` instance which contains the result if
        we would paste this data at the current cursor position.

        :param paste_mode: Where to paste. (Before/after/emacs.)
        :param count: When >1, Paste multiple times.
        """
        pass

    def empty_line_count_at_the_end(self) -> int:
        """
        Return number of empty lines at the end of the document.
        """
        pass

    def start_of_paragraph(self, count: int=1, before: bool=False) -> int:
        """
        Return the start of the current paragraph. (Relative cursor position.)
        """
        pass

    def end_of_paragraph(self, count: int=1, after: bool=False) -> int:
        """
        Return the end of the current paragraph. (Relative cursor position.)
        """
        pass

    def insert_after(self, text: str) -> Document:
        """
        Create a new document, with this text inserted after the buffer.
        It keeps selection ranges and cursor position in sync.
        """
        pass

    def insert_before(self, text: str) -> Document:
        """
        Create a new document, with this text inserted before the buffer.
        It keeps selection ranges and cursor position in sync.
        """
        pass
