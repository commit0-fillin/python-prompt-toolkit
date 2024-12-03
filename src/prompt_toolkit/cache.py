from __future__ import annotations
from collections import deque
from functools import wraps
from typing import Any, Callable, Dict, Generic, Hashable, Tuple, TypeVar, cast
__all__ = ['SimpleCache', 'FastDictCache', 'memoized']
_T = TypeVar('_T', bound=Hashable)
_U = TypeVar('_U')

class SimpleCache(Generic[_T, _U]):
    """
    Very simple cache that discards the oldest item when the cache size is
    exceeded.

    :param maxsize: Maximum size of the cache. (Don't make it too big.)
    """

    def __init__(self, maxsize: int=8) -> None:
        assert maxsize > 0
        self._data: dict[_T, _U] = {}
        self._keys: deque[_T] = deque()
        self.maxsize: int = maxsize

    def get(self, key: _T, getter_func: Callable[[], _U]) -> _U:
        """
        Get object from the cache.
        If not found, call `getter_func` to resolve it, and put that on the top
        of the cache instead.
        """
        if key in self._data:
            # Move the accessed key to the end of the deque (most recently used)
            self._keys.remove(key)
            self._keys.append(key)
            return self._data[key]
        
        # Key not found, call getter_func
        value = getter_func()
        
        # If cache is full, remove the oldest item
        if len(self._data) >= self.maxsize:
            oldest = self._keys.popleft()
            del self._data[oldest]
        
        # Add new item to cache
        self._data[key] = value
        self._keys.append(key)
        
        return value

    def clear(self) -> None:
        """Clear cache."""
        self._data.clear()
        self._keys.clear()
_K = TypeVar('_K', bound=Tuple[Hashable, ...])
_V = TypeVar('_V')

class FastDictCache(Dict[_K, _V]):
    """
    Fast, lightweight cache which keeps at most `size` items.
    It will discard the oldest items in the cache first.

    The cache is a dictionary, which doesn't keep track of access counts.
    It is perfect to cache little immutable objects which are not expensive to
    create, but where a dictionary lookup is still much faster than an object
    instantiation.

    :param get_value: Callable that's called in case of a missing key.
    """

    def __init__(self, get_value: Callable[..., _V], size: int=1000000) -> None:
        assert size > 0
        self._keys: deque[_K] = deque()
        self.get_value = get_value
        self.size = size

    def __missing__(self, key: _K) -> _V:
        if len(self) > self.size:
            key_to_remove = self._keys.popleft()
            if key_to_remove in self:
                del self[key_to_remove]
        result = self.get_value(*key)
        self[key] = result
        self._keys.append(key)
        return result
_F = TypeVar('_F', bound=Callable[..., object])

def memoized(maxsize: int=1024) -> Callable[[_F], _F]:
    """
    Memoization decorator for immutable classes and pure functions.
    """
    def decorator(func: _F) -> _F:
        cache = SimpleCache(maxsize)
        
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = (args, frozenset(kwargs.items()))
            return cache.get(key, lambda: func(*args, **kwargs))
        
        return cast(_F, wrapper)
    
    return decorator
