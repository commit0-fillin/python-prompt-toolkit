"""
Completer for a regular grammar.
"""
from __future__ import annotations
from typing import Iterable
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from .compiler import Match, _CompiledGrammar
__all__ = ['GrammarCompleter']

class GrammarCompleter(Completer):
    """
    Completer which can be used for autocompletion according to variables in
    the grammar. Each variable can have a different autocompleter.

    :param compiled_grammar: `GrammarCompleter` instance.
    :param completers: `dict` mapping variable names of the grammar to the
                       `Completer` instances to be used for each variable.
    """

    def __init__(self, compiled_grammar: _CompiledGrammar, completers: dict[str, Completer]) -> None:
        self.compiled_grammar = compiled_grammar
        self.completers = completers

    def _get_completions_for_match(self, match: Match, complete_event: CompleteEvent) -> Iterable[Completion]:
        """
        Yield all the possible completions for this input string.
        (The completer assumes that the cursor position was at the end of the
        input string.)
        """
        for variable in match.end_nodes():
            completer = self.completers.get(variable.varname)
            if completer:
                # Yield all completions.
                for completion in completer.get_completions(
                    Document(variable.value, len(variable.value)),
                    complete_event
                ):
                    yield Completion(
                        text=completion.text,
                        start_position=variable.start - match.string_before_cursor_len,
                        display=completion.display,
                        display_meta=completion.display_meta,
                        style=completion.style,
                    )

    def _remove_duplicates(self, items: Iterable[Completion]) -> list[Completion]:
        """
        Remove duplicates, while keeping the order.
        (Sometimes we have duplicates, because there are several matches of the
        same grammar, each yielding similar completions.)
        """
        result = []
        seen = set()
        for item in items:
            if item.text not in seen:
                result.append(item)
                seen.add(item.text)
        return result
