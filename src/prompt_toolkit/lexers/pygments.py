"""
Adaptor classes for using Pygments lexers within prompt_toolkit.

This includes syntax synchronization code, so that we don't have to start
lexing at the beginning of a document, when displaying a very large text.
"""
from __future__ import annotations
import re
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Callable, Dict, Generator, Iterable, Tuple
from prompt_toolkit.document import Document
from prompt_toolkit.filters import FilterOrBool, to_filter
from prompt_toolkit.formatted_text.base import StyleAndTextTuples
from prompt_toolkit.formatted_text.utils import split_lines
from prompt_toolkit.styles.pygments import pygments_token_to_classname
from .base import Lexer, SimpleLexer
if TYPE_CHECKING:
    from pygments.lexer import Lexer as PygmentsLexerCls
__all__ = ['PygmentsLexer', 'SyntaxSync', 'SyncFromStart', 'RegexSync']

class SyntaxSync(metaclass=ABCMeta):
    """
    Syntax synchronizer. This is a tool that finds a start position for the
    lexer. This is especially important when editing big documents; we don't
    want to start the highlighting by running the lexer from the beginning of
    the file. That is very slow when editing.
    """

    @abstractmethod
    def get_sync_start_position(self, document: Document, lineno: int) -> tuple[int, int]:
        """
        Return the position from where we can start lexing as a (row, column)
        tuple.

        :param document: `Document` instance that contains all the lines.
        :param lineno: The line that we want to highlight. (We need to return
            this line, or an earlier position.)
        """
        pass

class SyncFromStart(SyntaxSync):
    """
    Always start the syntax highlighting from the beginning.
    """

class RegexSync(SyntaxSync):
    """
    Synchronize by starting at a line that matches the given regex pattern.
    """
    MAX_BACKWARDS = 500
    FROM_START_IF_NO_SYNC_POS_FOUND = 100

    def __init__(self, pattern: str) -> None:
        self._compiled_pattern = re.compile(pattern)

    def get_sync_start_position(self, document: Document, lineno: int) -> tuple[int, int]:
        """
        Scan backwards, and find a possible position to start.
        """
        text = document.text
        lines = text.splitlines()
        
        # Start searching from the given line number
        for i in range(lineno, max(-1, lineno - self.MAX_BACKWARDS), -1):
            match = self._compiled_pattern.search(lines[i])
            if match:
                return i, 0
        
        # If no match found, return a position close to the beginning
        return max(0, lineno - self.FROM_START_IF_NO_SYNC_POS_FOUND), 0

    @classmethod
    def from_pygments_lexer_cls(cls, lexer_cls: PygmentsLexerCls) -> RegexSync:
        """
        Create a :class:`.RegexSync` instance for this Pygments lexer class.
        """
        patterns = []
        for attr in dir(lexer_cls):
            value = getattr(lexer_cls, attr)
            if isinstance(value, str) and attr.startswith('regex_'):
                patterns.append(f'(?:{value})')
        
        if patterns:
            return cls('|'.join(patterns))
        else:
            return cls('.*')

class _TokenCache(Dict[Tuple[str, ...], str]):
    """
    Cache that converts Pygments tokens into `prompt_toolkit` style objects.

    ``Token.A.B.C`` will be converted into:
    ``class:pygments,pygments.A,pygments.A.B,pygments.A.B.C``
    """

    def __missing__(self, key: tuple[str, ...]) -> str:
        result = 'class:' + pygments_token_to_classname(key)
        self[key] = result
        return result
_token_cache = _TokenCache()

class PygmentsLexer(Lexer):
    """
    Lexer that calls a pygments lexer.

    Example::

        from pygments.lexers.html import HtmlLexer
        lexer = PygmentsLexer(HtmlLexer)

    Note: Don't forget to also load a Pygments compatible style. E.g.::

        from prompt_toolkit.styles.from_pygments import style_from_pygments_cls
        from pygments.styles import get_style_by_name
        style = style_from_pygments_cls(get_style_by_name('monokai'))

    :param pygments_lexer_cls: A `Lexer` from Pygments.
    :param sync_from_start: Start lexing at the start of the document. This
        will always give the best results, but it will be slow for bigger
        documents. (When the last part of the document is display, then the
        whole document will be lexed by Pygments on every key stroke.) It is
        recommended to disable this for inputs that are expected to be more
        than 1,000 lines.
    :param syntax_sync: `SyntaxSync` object.
    """
    MIN_LINES_BACKWARDS = 50
    REUSE_GENERATOR_MAX_DISTANCE = 100

    def __init__(self, pygments_lexer_cls: type[PygmentsLexerCls], sync_from_start: FilterOrBool=True, syntax_sync: SyntaxSync | None=None) -> None:
        self.pygments_lexer_cls = pygments_lexer_cls
        self.sync_from_start = to_filter(sync_from_start)
        self.pygments_lexer = pygments_lexer_cls(stripnl=False, stripall=False, ensurenl=False)
        self.syntax_sync = syntax_sync or RegexSync.from_pygments_lexer_cls(pygments_lexer_cls)

    @classmethod
    def from_filename(cls, filename: str, sync_from_start: FilterOrBool=True) -> Lexer:
        """
        Create a `Lexer` from a filename.
        """
        from pygments.lexers import get_lexer_for_filename
        from pygments.util import ClassNotFound

        try:
            pygments_lexer = get_lexer_for_filename(filename)
        except ClassNotFound:
            return SimpleLexer()
        
        return cls(pygments_lexer.__class__, sync_from_start=sync_from_start)

    def lex_document(self, document: Document) -> Callable[[int], StyleAndTextTuples]:
        """
        Create a lexer function that takes a line number and returns the list
        of (style_str, text) tuples as the Pygments lexer returns for that line.
        """
        text = document.text

        def get_line(lineno: int) -> StyleAndTextTuples:
            if self.sync_from_start():
                start_pos = 0
            else:
                start_pos, _ = self.syntax_sync.get_sync_start_position(document, lineno)

            start = document.translate_row_col_to_index(start_pos, 0)
            end = document.translate_row_col_to_index(lineno + 1, 0)

            tokens = list(self.pygments_lexer.get_tokens_unprocessed(text[start:end]))
            return [(pygments_token_to_classname(token), value) for _, token, value in tokens]

        return get_line
