"""
Nestedcompleter for completion of hierarchical data structures.
"""
from __future__ import annotations
from typing import Any, Iterable, Mapping, Set, Union
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.completion.word_completer import WordCompleter
from prompt_toolkit.document import Document
__all__ = ['NestedCompleter']
NestedDict = Mapping[str, Union[Any, Set[str], None, Completer]]

class NestedCompleter(Completer):
    """
    Completer which wraps around several other completers, and calls any the
    one that corresponds with the first word of the input.

    By combining multiple `NestedCompleter` instances, we can achieve multiple
    hierarchical levels of autocompletion. This is useful when `WordCompleter`
    is not sufficient.

    If you need multiple levels, check out the `from_nested_dict` classmethod.
    """

    def __init__(self, options: dict[str, Completer | None], ignore_case: bool=True) -> None:
        self.options = options
        self.ignore_case = ignore_case

    def __repr__(self) -> str:
        return f'NestedCompleter({self.options!r}, ignore_case={self.ignore_case!r})'

    @classmethod
    def from_nested_dict(cls, data: NestedDict) -> NestedCompleter:
        """
        Create a `NestedCompleter`, starting from a nested dictionary data
        structure, like this:

        .. code::

            data = {
                'show': {
                    'version': None,
                    'interfaces': None,
                    'clock': None,
                    'ip': {'interface': {'brief'}}
                },
                'exit': None
                'enable': None
            }

        The value should be `None` if there is no further completion at some
        point. If all values in the dictionary are None, it is also possible to
        use a set instead.

        Values in this data structure can be completers as well.
        """
        def get_completer(data: Any) -> Completer | None:
            if isinstance(data, Completer):
                return data
            elif isinstance(data, dict):
                return cls.from_nested_dict(data)
            elif isinstance(data, set):
                return WordCompleter(list(data))
            elif data is None:
                return None
            else:
                raise TypeError(f"Invalid data type: {type(data)}")

        options = {}
        for key, value in data.items():
            if isinstance(key, str):
                options[key] = get_completer(value)
            else:
                raise TypeError(f"Key should be a string, got: {type(key)}")

        return cls(options)
