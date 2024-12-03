"""
Processors are little transformation blocks that transform the fragments list
from a buffer before the BufferControl will render it to the screen.

They can insert fragments before or after, or highlight fragments by replacing the
fragment types.
"""
from __future__ import annotations
import re
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Callable, Hashable, cast
from prompt_toolkit.application.current import get_app
from prompt_toolkit.cache import SimpleCache
from prompt_toolkit.document import Document
from prompt_toolkit.filters import FilterOrBool, to_filter, vi_insert_multiple_mode
from prompt_toolkit.formatted_text import AnyFormattedText, StyleAndTextTuples, to_formatted_text
from prompt_toolkit.formatted_text.utils import fragment_list_len, fragment_list_to_text
from prompt_toolkit.search import SearchDirection
from prompt_toolkit.utils import to_int, to_str
from .utils import explode_text_fragments
if TYPE_CHECKING:
    from .controls import BufferControl, UIContent
__all__ = ['Processor', 'TransformationInput', 'Transformation', 'DummyProcessor', 'HighlightSearchProcessor', 'HighlightIncrementalSearchProcessor', 'HighlightSelectionProcessor', 'PasswordProcessor', 'HighlightMatchingBracketProcessor', 'DisplayMultipleCursors', 'BeforeInput', 'ShowArg', 'AfterInput', 'AppendAutoSuggestion', 'ConditionalProcessor', 'ShowLeadingWhiteSpaceProcessor', 'ShowTrailingWhiteSpaceProcessor', 'TabsProcessor', 'ReverseSearchProcessor', 'DynamicProcessor', 'merge_processors']

class Processor(metaclass=ABCMeta):
    """
    Manipulate the fragments for a given line in a
    :class:`~prompt_toolkit.layout.controls.BufferControl`.
    """

    @abstractmethod
    def apply_transformation(self, transformation_input: TransformationInput) -> Transformation:
        """
        Apply transformation. Returns a :class:`.Transformation` instance.

        :param transformation_input: :class:`.TransformationInput` object.
        """
        return Transformation(transformation_input.fragments)
SourceToDisplay = Callable[[int], int]
DisplayToSource = Callable[[int], int]

class TransformationInput:
    """
    :param buffer_control: :class:`.BufferControl` instance.
    :param lineno: The number of the line to which we apply the processor.
    :param source_to_display: A function that returns the position in the
        `fragments` for any position in the source string. (This takes
        previous processors into account.)
    :param fragments: List of fragments that we can transform. (Received from the
        previous processor.)
    """

    def __init__(self, buffer_control: BufferControl, document: Document, lineno: int, source_to_display: SourceToDisplay, fragments: StyleAndTextTuples, width: int, height: int) -> None:
        self.buffer_control = buffer_control
        self.document = document
        self.lineno = lineno
        self.source_to_display = source_to_display
        self.fragments = fragments
        self.width = width
        self.height = height

class Transformation:
    """
    Transformation result, as returned by :meth:`.Processor.apply_transformation`.

    Important: Always make sure that the length of `document.text` is equal to
               the length of all the text in `fragments`!

    :param fragments: The transformed fragments. To be displayed, or to pass to
        the next processor.
    :param source_to_display: Cursor position transformation from original
        string to transformed string.
    :param display_to_source: Cursor position transformed from source string to
        original string.
    """

    def __init__(self, fragments: StyleAndTextTuples, source_to_display: SourceToDisplay | None=None, display_to_source: DisplayToSource | None=None) -> None:
        self.fragments = fragments
        self.source_to_display = source_to_display or (lambda i: i)
        self.display_to_source = display_to_source or (lambda i: i)

class DummyProcessor(Processor):
    """
    A `Processor` that doesn't do anything.
    """

class HighlightSearchProcessor(Processor):
    """
    Processor that highlights search matches in the document.
    Note that this doesn't support multiline search matches yet.

    The style classes 'search' and 'search.current' will be applied to the
    content.
    """
    _classname = 'search'
    _classname_current = 'search.current'

    def __init__(self) -> None:
        self._search_text = ''
        self._last_search_position = 0

    def _get_search_text(self, buffer_control: BufferControl) -> str:
        """
        The text we are searching for.
        """
        search_state = buffer_control.search_state
        return search_state.text

class HighlightIncrementalSearchProcessor(HighlightSearchProcessor):
    """
    Highlight the search terms that are used for highlighting the incremental
    search. The style class 'incsearch' will be applied to the content.

    Important: this requires the `preview_search=True` flag to be set for the
    `BufferControl`. Otherwise, the cursor position won't be set to the search
    match while searching, and nothing happens.
    """
    _classname = 'incsearch'
    _classname_current = 'incsearch.current'

    def _get_search_text(self, buffer_control: BufferControl) -> str:
        """
        The text we are searching for.
        """
        search_buffer = get_app().layout.search_buffer
        return search_buffer.text if search_buffer else ''

class HighlightSelectionProcessor(Processor):
    """
    Processor that highlights the selection in the document.
    """

class PasswordProcessor(Processor):
    """
    Processor that masks the input. (For passwords.)

    :param char: (string) Character to be used. "*" by default.
    """

    def __init__(self, char: str='*') -> None:
        self.char = char

class HighlightMatchingBracketProcessor(Processor):
    """
    When the cursor is on or right after a bracket, it highlights the matching
    bracket.

    :param max_cursor_distance: Only highlight matching brackets when the
        cursor is within this distance. (From inside a `Processor`, we can't
        know which lines will be visible on the screen. But we also don't want
        to scan the whole document for matching brackets on each key press, so
        we limit to this value.)
    """
    _closing_braces = '])}>'

    def __init__(self, chars: str='[](){}<>', max_cursor_distance: int=1000) -> None:
        self.chars = chars
        self.max_cursor_distance = max_cursor_distance
        self._positions_cache: SimpleCache[Hashable, list[tuple[int, int]]] = SimpleCache(maxsize=8)

    def _get_positions_to_highlight(self, document: Document) -> list[tuple[int, int]]:
        """
        Return a list of (row, col) tuples that need to be highlighted.
        """
        cursor_row, cursor_col = document.translate_index_to_position(document.cursor_position)
        
        def get_matching_bracket_position(row: int, col: int) -> tuple[int, int] | None:
            line = document.lines[row]
            if col < len(line):
                bracket = line[col]
                if bracket in '([{<':
                    for i in range(row, min(row + self.max_cursor_distance, document.line_count)):
                        for j in range(len(document.lines[i])):
                            if document.lines[i][j] == self._closing_braces[self.chars.index(bracket)]:
                                return i, j
                elif bracket in ')]}>':
                    for i in range(row, max(row - self.max_cursor_distance, -1), -1):
                        for j in range(len(document.lines[i]) - 1, -1, -1):
                            if document.lines[i][j] == self.chars[self._closing_braces.index(bracket)]:
                                return i, j
            return None
        
        positions = []
        cursor_bracket_pos = get_matching_bracket_position(cursor_row, cursor_col)
        if cursor_bracket_pos:
            positions.extend([(cursor_row, cursor_col), cursor_bracket_pos])
        
        return positions

class DisplayMultipleCursors(Processor):
    """
    When we're in Vi block insert mode, display all the cursors.
    """

class BeforeInput(Processor):
    """
    Insert text before the input.

    :param text: This can be either plain text or formatted text
        (or a callable that returns any of those).
    :param style: style to be applied to this prompt/prefix.
    """

    def __init__(self, text: AnyFormattedText, style: str='') -> None:
        self.text = text
        self.style = style

    def __repr__(self) -> str:
        return f'BeforeInput({self.text!r}, {self.style!r})'

class ShowArg(BeforeInput):
    """
    Display the 'arg' in front of the input.

    This was used by the `PromptSession`, but now it uses the
    `Window.get_line_prefix` function instead.
    """

    def __init__(self) -> None:
        super().__init__(self._get_text_fragments)

    def __repr__(self) -> str:
        return 'ShowArg()'

class AfterInput(Processor):
    """
    Insert text after the input.

    :param text: This can be either plain text or formatted text
        (or a callable that returns any of those).
    :param style: style to be applied to this prompt/prefix.
    """

    def __init__(self, text: AnyFormattedText, style: str='') -> None:
        self.text = text
        self.style = style

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.text!r}, style={self.style!r})'

class AppendAutoSuggestion(Processor):
    """
    Append the auto suggestion to the input.
    (The user can then press the right arrow the insert the suggestion.)
    """

    def __init__(self, style: str='class:auto-suggestion') -> None:
        self.style = style

class ShowLeadingWhiteSpaceProcessor(Processor):
    """
    Make leading whitespace visible.

    :param get_char: Callable that returns one character.
    """

    def __init__(self, get_char: Callable[[], str] | None=None, style: str='class:leading-whitespace') -> None:

        def default_get_char() -> str:
            if '·'.encode(get_app().output.encoding(), 'replace') == b'?':
                return '.'
            else:
                return '·'
        self.style = style
        self.get_char = get_char or default_get_char

class ShowTrailingWhiteSpaceProcessor(Processor):
    """
    Make trailing whitespace visible.

    :param get_char: Callable that returns one character.
    """

    def __init__(self, get_char: Callable[[], str] | None=None, style: str='class:training-whitespace') -> None:

        def default_get_char() -> str:
            if '·'.encode(get_app().output.encoding(), 'replace') == b'?':
                return '.'
            else:
                return '·'
        self.style = style
        self.get_char = get_char or default_get_char

class TabsProcessor(Processor):
    """
    Render tabs as spaces (instead of ^I) or make them visible (for instance,
    by replacing them with dots.)

    :param tabstop: Horizontal space taken by a tab. (`int` or callable that
        returns an `int`).
    :param char1: Character or callable that returns a character (text of
        length one). This one is used for the first space taken by the tab.
    :param char2: Like `char1`, but for the rest of the space.
    """

    def __init__(self, tabstop: int | Callable[[], int]=4, char1: str | Callable[[], str]='|', char2: str | Callable[[], str]='┈', style: str='class:tab') -> None:
        self.char1 = char1
        self.char2 = char2
        self.tabstop = tabstop
        self.style = style

class ReverseSearchProcessor(Processor):
    """
    Process to display the "(reverse-i-search)`...`:..." stuff around
    the search buffer.

    Note: This processor is meant to be applied to the BufferControl that
    contains the search buffer, it's not meant for the original input.
    """
    _excluded_input_processors: list[type[Processor]] = [HighlightSearchProcessor, HighlightSelectionProcessor, BeforeInput, AfterInput]

class ConditionalProcessor(Processor):
    """
    Processor that applies another processor, according to a certain condition.
    Example::

        # Create a function that returns whether or not the processor should
        # currently be applied.
        def highlight_enabled():
            return true_or_false

        # Wrapped it in a `ConditionalProcessor` for usage in a `BufferControl`.
        BufferControl(input_processors=[
            ConditionalProcessor(HighlightSearchProcessor(),
                                 Condition(highlight_enabled))])

    :param processor: :class:`.Processor` instance.
    :param filter: :class:`~prompt_toolkit.filters.Filter` instance.
    """

    def __init__(self, processor: Processor, filter: FilterOrBool) -> None:
        self.processor = processor
        self.filter = to_filter(filter)

    def __repr__(self) -> str:
        return '{}(processor={!r}, filter={!r})'.format(self.__class__.__name__, self.processor, self.filter)

class DynamicProcessor(Processor):
    """
    Processor class that dynamically returns any Processor.

    :param get_processor: Callable that returns a :class:`.Processor` instance.
    """

    def __init__(self, get_processor: Callable[[], Processor | None]) -> None:
        self.get_processor = get_processor

def merge_processors(processors: list[Processor]) -> Processor:
    """
    Merge multiple `Processor` objects into one.
    """
    return _MergedProcessor(processors)

class _MergedProcessor(Processor):
    """
    Processor that groups multiple other `Processor` objects, but exposes an
    API as if it is one `Processor`.
    """

    def __init__(self, processors: list[Processor]):
        self.processors = processors
