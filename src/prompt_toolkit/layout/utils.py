from __future__ import annotations
from typing import TYPE_CHECKING, Iterable, List, TypeVar, cast, overload
from prompt_toolkit.formatted_text.base import OneStyleAndTextTuple
if TYPE_CHECKING:
    from typing_extensions import SupportsIndex
__all__ = ['explode_text_fragments']
_T = TypeVar('_T', bound=OneStyleAndTextTuple)

class _ExplodedList(List[_T]):
    """
    Wrapper around a list, that marks it as 'exploded'.

    As soon as items are added or the list is extended, the new items are
    automatically exploded as well.
    """
    exploded = True

    @overload
    def __setitem__(self, index: SupportsIndex, value: _T) -> None:
        ...

    @overload
    def __setitem__(self, index: slice, value: Iterable[_T]) -> None:
        ...

    def __setitem__(self, index: SupportsIndex | slice, value: _T | Iterable[_T]) -> None:
        """
        Ensure that when `(style_str, 'long string')` is set, the string will be
        exploded.
        """
        if not isinstance(index, slice):
            int_index = index.__index__()
            index = slice(int_index, int_index + 1)
        if isinstance(value, tuple):
            value = cast('List[_T]', [value])
        super().__setitem__(index, explode_text_fragments(value))

def explode_text_fragments(fragments: Iterable[_T]) -> _ExplodedList[_T]:
    """
    Turn a list of (style_str, text) tuples into another list where each string is
    exactly one character.

    It should be fine to call this function several times. Calling this on a
    list that is already exploded, is a null operation.

    :param fragments: List of (style, text) tuples.
    """
    result = _ExplodedList()

    for style, text, *rest in fragments:
        if isinstance(text, str):
            for c in text:
                result.append((style, c, *rest))
        else:
            # If it's already exploded, just add it to the result
            result.append((style, text, *rest))

    return result
