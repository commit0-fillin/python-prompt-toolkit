"""
Layout dimensions are used to give the minimum, maximum and preferred
dimensions for containers and controls.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable, Union
__all__ = ['Dimension', 'D', 'sum_layout_dimensions', 'max_layout_dimensions', 'AnyDimension', 'to_dimension', 'is_dimension']
if TYPE_CHECKING:
    from typing_extensions import TypeGuard

class Dimension:
    """
    Specified dimension (width/height) of a user control or window.

    The layout engine tries to honor the preferred size. If that is not
    possible, because the terminal is larger or smaller, it tries to keep in
    between min and max.

    :param min: Minimum size.
    :param max: Maximum size.
    :param weight: For a VSplit/HSplit, the actual size will be determined
                   by taking the proportion of weights from all the children.
                   E.g. When there are two children, one with a weight of 1,
                   and the other with a weight of 2, the second will always be
                   twice as big as the first, if the min/max values allow it.
    :param preferred: Preferred size.
    """

    def __init__(self, min: int | None=None, max: int | None=None, weight: int | None=None, preferred: int | None=None) -> None:
        if weight is not None:
            assert weight >= 0
        assert min is None or min >= 0
        assert max is None or max >= 0
        assert preferred is None or preferred >= 0
        self.min_specified = min is not None
        self.max_specified = max is not None
        self.preferred_specified = preferred is not None
        self.weight_specified = weight is not None
        if min is None:
            min = 0
        if max is None:
            max = 1000 ** 10
        if preferred is None:
            preferred = min
        if weight is None:
            weight = 1
        self.min = min
        self.max = max
        self.preferred = preferred
        self.weight = weight
        if max < min:
            raise ValueError('Invalid Dimension: max < min.')
        if self.preferred < self.min:
            self.preferred = self.min
        if self.preferred > self.max:
            self.preferred = self.max

    @classmethod
    def exact(cls, amount: int) -> Dimension:
        """
        Return a :class:`.Dimension` with an exact size. (min, max and
        preferred set to ``amount``).
        """
        return cls(min=amount, max=amount, preferred=amount)

    @classmethod
    def zero(cls) -> Dimension:
        """
        Create a dimension that represents a zero size. (Used for 'invisible'
        controls.)
        """
        return cls(min=0, max=0, preferred=0)

    def is_zero(self) -> bool:
        """True if this `Dimension` represents a zero size."""
        return self.max == 0

    def __repr__(self) -> str:
        fields = []
        if self.min_specified:
            fields.append('min=%r' % self.min)
        if self.max_specified:
            fields.append('max=%r' % self.max)
        if self.preferred_specified:
            fields.append('preferred=%r' % self.preferred)
        if self.weight_specified:
            fields.append('weight=%r' % self.weight)
        return 'Dimension(%s)' % ', '.join(fields)

def sum_layout_dimensions(dimensions: list[Dimension]) -> Dimension:
    """
    Sum a list of :class:`.Dimension` instances.
    """
    min_sum = sum(d.min for d in dimensions)
    max_sum = sum(d.max for d in dimensions)
    preferred_sum = sum(d.preferred for d in dimensions)
    weight_sum = sum(d.weight for d in dimensions)

    return Dimension(
        min=min_sum,
        max=max_sum,
        preferred=preferred_sum,
        weight=weight_sum
    )

def max_layout_dimensions(dimensions: list[Dimension]) -> Dimension:
    """
    Take the maximum of a list of :class:`.Dimension` instances.
    Used when we have a HSplit/VSplit, and we want to get the best width/height.)
    """
    if not dimensions:
        return Dimension.zero()

    return Dimension(
        min=max(d.min for d in dimensions),
        max=max(d.max for d in dimensions),
        preferred=max(d.preferred for d in dimensions),
        weight=max(d.weight for d in dimensions)
    )
AnyDimension = Union[None, int, Dimension, Callable[[], Any]]

def to_dimension(value: AnyDimension) -> Dimension:
    """
    Turn the given object into a `Dimension` object.
    """
    if value is None:
        return Dimension()
    if isinstance(value, int):
        return Dimension.exact(value)
    if isinstance(value, Dimension):
        return value
    if callable(value):
        return to_dimension(value())
    raise TypeError(f"Invalid dimension value: {value}")

def is_dimension(value: object) -> TypeGuard[AnyDimension]:
    """
    Test whether the given value could be a valid dimension.
    (For usage in an assertion. It's not guaranteed in case of a callable.)
    """
    return value is None or isinstance(value, (int, Dimension)) or callable(value)
D = Dimension
LayoutDimension = Dimension
