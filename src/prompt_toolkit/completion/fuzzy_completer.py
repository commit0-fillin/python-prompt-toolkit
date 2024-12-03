from __future__ import annotations
import re
from typing import Callable, Iterable, NamedTuple
from prompt_toolkit.document import Document
from prompt_toolkit.filters import FilterOrBool, to_filter
from prompt_toolkit.formatted_text import AnyFormattedText, StyleAndTextTuples
from .base import CompleteEvent, Completer, Completion
from .word_completer import WordCompleter
__all__ = ['FuzzyCompleter', 'FuzzyWordCompleter']

class FuzzyCompleter(Completer):
    """
    Fuzzy completion.
    This wraps any other completer and turns it into a fuzzy completer.

    If the list of words is: ["leopard" , "gorilla", "dinosaur", "cat", "bee"]
    Then trying to complete "oar" would yield "leopard" and "dinosaur", but not
    the others, because they match the regular expression 'o.*a.*r'.
    Similar, in another application "djm" could expand to "django_migrations".

    The results are sorted by relevance, which is defined as the start position
    and the length of the match.

    Notice that this is not really a tool to work around spelling mistakes,
    like what would be possible with difflib. The purpose is rather to have a
    quicker or more intuitive way to filter the given completions, especially
    when many completions have a common prefix.

    Fuzzy algorithm is based on this post:
    https://blog.amjith.com/fuzzyfinder-in-10-lines-of-python

    :param completer: A :class:`~.Completer` instance.
    :param WORD: When True, use WORD characters.
    :param pattern: Regex pattern which selects the characters before the
        cursor that are considered for the fuzzy matching.
    :param enable_fuzzy: (bool or `Filter`) Enabled the fuzzy behavior. For
        easily turning fuzzyness on or off according to a certain condition.
    """

    def __init__(self, completer: Completer, WORD: bool=False, pattern: str | None=None, enable_fuzzy: FilterOrBool=True) -> None:
        assert pattern is None or pattern.startswith('^')
        self.completer = completer
        self.pattern = pattern
        self.WORD = WORD
        self.pattern = pattern
        self.enable_fuzzy = to_filter(enable_fuzzy)

    def _get_display(self, fuzzy_match: _FuzzyMatch, word_before_cursor: str) -> AnyFormattedText:
        """
        Generate formatted text for the display label.
        """
        from prompt_toolkit.formatted_text import merge_formatted_text, FormattedText

        match_start = fuzzy_match.start_pos
        match_end = match_start + fuzzy_match.match_length
        result = []

        # Text before match
        if match_start > 0:
            result.append(('', fuzzy_match.completion.display_text[:match_start]))

        # Matched text
        result.append(('[SetColor]', fuzzy_match.completion.display_text[match_start:match_end]))

        # Text after match
        if match_end < len(fuzzy_match.completion.display_text):
            result.append(('', fuzzy_match.completion.display_text[match_end:]))

        return merge_formatted_text([
            FormattedText(result),
            ('', ' '),
            fuzzy_match.completion.display_meta
        ])

class FuzzyWordCompleter(Completer):
    """
    Fuzzy completion on a list of words.

    (This is basically a `WordCompleter` wrapped in a `FuzzyCompleter`.)

    :param words: List of words or callable that returns a list of words.
    :param meta_dict: Optional dict mapping words to their meta-information.
    :param WORD: When True, use WORD characters.
    """

    def __init__(self, words: list[str] | Callable[[], list[str]], meta_dict: dict[str, str] | None=None, WORD: bool=False) -> None:
        self.words = words
        self.meta_dict = meta_dict or {}
        self.WORD = WORD
        self.word_completer = WordCompleter(words=self.words, WORD=self.WORD, meta_dict=self.meta_dict)
        self.fuzzy_completer = FuzzyCompleter(self.word_completer, WORD=self.WORD)

class _FuzzyMatch(NamedTuple):
    match_length: int
    start_pos: int
    completion: Completion
