"""
Key bindings registry.

A `KeyBindings` object is a container that holds a list of key bindings. It has a
very efficient internal data structure for checking which key bindings apply
for a pressed key.

Typical usage::

    kb = KeyBindings()

    @kb.add(Keys.ControlX, Keys.ControlC, filter=INSERT)
    def handler(event):
        # Handle ControlX-ControlC key sequence.
        pass

It is also possible to combine multiple KeyBindings objects. We do this in the
default key bindings. There are some KeyBindings objects that contain the Emacs
bindings, while others contain the Vi bindings. They are merged together using
`merge_key_bindings`.

We also have a `ConditionalKeyBindings` object that can enable/disable a group of
key bindings at once.


It is also possible to add a filter to a function, before a key binding has
been assigned, through the `key_binding` decorator.::

    # First define a key handler with the `filter`.
    @key_binding(filter=condition)
    def my_key_binding(event):
        ...

    # Later, add it to the key bindings.
    kb.add(Keys.A, my_key_binding)
"""
from __future__ import annotations
from abc import ABCMeta, abstractmethod, abstractproperty
from inspect import isawaitable
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Hashable, Sequence, Tuple, TypeVar, Union, cast
from prompt_toolkit.cache import SimpleCache
from prompt_toolkit.filters import FilterOrBool, Never, to_filter
from prompt_toolkit.keys import KEY_ALIASES, Keys
if TYPE_CHECKING:
    from .key_processor import KeyPressEvent
    NotImplementedOrNone = object
__all__ = ['NotImplementedOrNone', 'Binding', 'KeyBindingsBase', 'KeyBindings', 'ConditionalKeyBindings', 'merge_key_bindings', 'DynamicKeyBindings', 'GlobalOnlyKeyBindings']
KeyHandlerCallable = Callable[['KeyPressEvent'], Union['NotImplementedOrNone', Coroutine[Any, Any, 'NotImplementedOrNone']]]

class Binding:
    """
    Key binding: (key sequence + handler + filter).
    (Immutable binding class.)

    :param record_in_macro: When True, don't record this key binding when a
        macro is recorded.
    """

    def __init__(self, keys: tuple[Keys | str, ...], handler: KeyHandlerCallable, filter: FilterOrBool=True, eager: FilterOrBool=False, is_global: FilterOrBool=False, save_before: Callable[[KeyPressEvent], bool]=lambda e: True, record_in_macro: FilterOrBool=True) -> None:
        self.keys = keys
        self.handler = handler
        self.filter = to_filter(filter)
        self.eager = to_filter(eager)
        self.is_global = to_filter(is_global)
        self.save_before = save_before
        self.record_in_macro = to_filter(record_in_macro)

    def __repr__(self) -> str:
        return '{}(keys={!r}, handler={!r})'.format(self.__class__.__name__, self.keys, self.handler)
KeysTuple = Tuple[Union[Keys, str], ...]

class KeyBindingsBase(metaclass=ABCMeta):
    """
    Interface for a KeyBindings.
    """

    @abstractproperty
    @property
    def _version(self) -> Hashable:
        """
        For cache invalidation. - This should increase every time that
        something changes.
        """
        return hash(tuple(self.bindings))

    @abstractmethod
    def get_bindings_for_keys(self, keys: KeysTuple) -> list[Binding]:
        """
        Return a list of key bindings that can handle these keys.
        (This return also inactive bindings, so the `filter` still has to be
        called, for checking it.)

        :param keys: tuple of keys.
        """
        return [binding for binding in self.bindings if binding.keys == keys]

    @abstractmethod
    def get_bindings_starting_with_keys(self, keys: KeysTuple) -> list[Binding]:
        """
        Return a list of key bindings that handle a key sequence starting with
        `keys`. (It does only return bindings for which the sequences are
        longer than `keys`. And like `get_bindings_for_keys`, it also includes
        inactive bindings.)

        :param keys: tuple of keys.
        """
        return [binding for binding in self.bindings if binding.keys[:len(keys)] == keys and len(binding.keys) > len(keys)]

    @abstractproperty
    @property
    def bindings(self) -> list[Binding]:
        """
        List of `Binding` objects.
        (These need to be exposed, so that `KeyBindings` objects can be merged
        together.)
        """
        return self._bindings
T = TypeVar('T', bound=Union[KeyHandlerCallable, Binding])

class KeyBindings(KeyBindingsBase):
    """
    A container for a set of key bindings.

    Example usage::

        kb = KeyBindings()

        @kb.add('c-t')
        def _(event):
            print('Control-T pressed')

        @kb.add('c-a', 'c-b')
        def _(event):
            print('Control-A pressed, followed by Control-B')

        @kb.add('c-x', filter=is_searching)
        def _(event):
            print('Control-X pressed')  # Works only if we are searching.

    """

    def __init__(self) -> None:
        self._bindings: list[Binding] = []
        self._get_bindings_for_keys_cache: SimpleCache[KeysTuple, list[Binding]] = SimpleCache(maxsize=10000)
        self._get_bindings_starting_with_keys_cache: SimpleCache[KeysTuple, list[Binding]] = SimpleCache(maxsize=1000)
        self.__version = 0

    def add(self, *keys: Keys | str, filter: FilterOrBool=True, eager: FilterOrBool=False, is_global: FilterOrBool=False, save_before: Callable[[KeyPressEvent], bool]=lambda e: True, record_in_macro: FilterOrBool=True) -> Callable[[T], T]:
        """
        Decorator for adding a key bindings.

        :param filter: :class:`~prompt_toolkit.filters.Filter` to determine
            when this key binding is active.
        :param eager: :class:`~prompt_toolkit.filters.Filter` or `bool`.
            When True, ignore potential longer matches when this key binding is
            hit. E.g. when there is an active eager key binding for Ctrl-X,
            execute the handler immediately and ignore the key binding for
            Ctrl-X Ctrl-E of which it is a prefix.
        :param is_global: When this key bindings is added to a `Container` or
            `Control`, make it a global (always active) binding.
        :param save_before: Callable that takes an `Event` and returns True if
            we should save the current buffer, before handling the event.
            (That's the default.)
        :param record_in_macro: Record these key bindings when a macro is
            being recorded. (True by default.)
        """
        def decorator(func: T) -> T:
            self._bindings.append(
                Binding(keys=keys, handler=func, filter=filter, eager=eager,
                        is_global=is_global, save_before=save_before,
                        record_in_macro=record_in_macro)
            )
            self.__version += 1  # Increase version to invalidate cache
            return func
        return decorator

    def remove(self, *args: Keys | str | KeyHandlerCallable) -> None:
        """
        Remove a key binding.

        This expects either a function that was given to `add` method as
        parameter or a sequence of key bindings.

        Raises `ValueError` when no bindings was found.

        Usage::

            remove(handler)  # Pass handler.
            remove('c-x', 'c-a')  # Or pass the key bindings.
        """
        if len(args) == 1 and callable(args[0]):
            handler = args[0]
            self._bindings = [b for b in self._bindings if b.handler != handler]
        else:
            keys = tuple(_parse_key(k) for k in args)
            self._bindings = [b for b in self._bindings if b.keys != keys]
        
        if len(self._bindings) == len(args):
            raise ValueError("Binding not found")
        
        self.__version += 1  # Increase version to invalidate cache
    add_binding = add
    remove_binding = remove

    def get_bindings_for_keys(self, keys: KeysTuple) -> list[Binding]:
        """
        Return a list of key bindings that can handle this key.
        (This return also inactive bindings, so the `filter` still has to be
        called, for checking it.)

        :param keys: tuple of keys.
        """
        pass

    def get_bindings_starting_with_keys(self, keys: KeysTuple) -> list[Binding]:
        """
        Return a list of key bindings that handle a key sequence starting with
        `keys`. (It does only return bindings for which the sequences are
        longer than `keys`. And like `get_bindings_for_keys`, it also includes
        inactive bindings.)

        :param keys: tuple of keys.
        """
        pass

def _parse_key(key: Keys | str) -> str | Keys:
    """
    Replace key by alias and verify whether it's a valid one.
    """
    if isinstance(key, Keys):
        return key
    
    if key in KEY_ALIASES:
        return KEY_ALIASES[key]
    
    if len(key) != 1:
        raise ValueError(f"Invalid key: {key}")
    
    return key

def key_binding(filter: FilterOrBool=True, eager: FilterOrBool=False, is_global: FilterOrBool=False, save_before: Callable[[KeyPressEvent], bool]=lambda event: True, record_in_macro: FilterOrBool=True) -> Callable[[KeyHandlerCallable], Binding]:
    """
    Decorator that turn a function into a `Binding` object. This can be added
    to a `KeyBindings` object when a key binding is assigned.
    """
    def decorator(func: KeyHandlerCallable) -> Binding:
        return Binding(keys=(), handler=func, filter=filter, eager=eager,
                       is_global=is_global, save_before=save_before,
                       record_in_macro=record_in_macro)
    return decorator

class _Proxy(KeyBindingsBase):
    """
    Common part for ConditionalKeyBindings and _MergedKeyBindings.
    """

    def __init__(self) -> None:
        self._bindings2: KeyBindingsBase = KeyBindings()
        self._last_version: Hashable = ()

    def _update_cache(self) -> None:
        """
        If `self._last_version` is outdated, then this should update
        the version and `self._bindings2`.
        """
        current_version = self._get_version()
        if self._last_version != current_version:
            self._last_version = current_version
            self._bindings2 = self._get_bindings()

class ConditionalKeyBindings(_Proxy):
    """
    Wraps around a `KeyBindings`. Disable/enable all the key bindings according to
    the given (additional) filter.::

        @Condition
        def setting_is_true():
            return True  # or False

        registry = ConditionalKeyBindings(key_bindings, setting_is_true)

    When new key bindings are added to this object. They are also
    enable/disabled according to the given `filter`.

    :param registries: List of :class:`.KeyBindings` objects.
    :param filter: :class:`~prompt_toolkit.filters.Filter` object.
    """

    def __init__(self, key_bindings: KeyBindingsBase, filter: FilterOrBool=True) -> None:
        _Proxy.__init__(self)
        self.key_bindings = key_bindings
        self.filter = to_filter(filter)

    def _update_cache(self) -> None:
        """If the original key bindings was changed. Update our copy version."""
        current_version = self.key_bindings._version
        if self._last_version != current_version:
            self._last_version = current_version
            self._bindings2 = KeyBindings()
            for b in self.key_bindings.bindings:
                self._bindings2.add(*b.keys, filter=self.filter & b.filter,
                                    eager=b.eager, is_global=b.is_global,
                                    save_before=b.save_before,
                                    record_in_macro=b.record_in_macro)(b.handler)

class _MergedKeyBindings(_Proxy):
    """
    Merge multiple registries of key bindings into one.

    This class acts as a proxy to multiple :class:`.KeyBindings` objects, but
    behaves as if this is just one bigger :class:`.KeyBindings`.

    :param registries: List of :class:`.KeyBindings` objects.
    """

    def __init__(self, registries: Sequence[KeyBindingsBase]) -> None:
        _Proxy.__init__(self)
        self.registries = registries

    def _update_cache(self) -> None:
        """
        If one of the original registries was changed. Update our merged
        version.
        """
        current_version = tuple(r._version for r in self.registries)
        if self._last_version != current_version:
            self._last_version = current_version
            self._bindings2 = KeyBindings()
            for registry in self.registries:
                for b in registry.bindings:
                    self._bindings2.add(*b.keys, filter=b.filter, eager=b.eager,
                                        is_global=b.is_global, save_before=b.save_before,
                                        record_in_macro=b.record_in_macro)(b.handler)

def merge_key_bindings(bindings: Sequence[KeyBindingsBase]) -> _MergedKeyBindings:
    """
    Merge multiple :class:`.Keybinding` objects together.

    Usage::

        bindings = merge_key_bindings([bindings1, bindings2, ...])
    """
    return _MergedKeyBindings(bindings)

class DynamicKeyBindings(_Proxy):
    """
    KeyBindings class that can dynamically returns any KeyBindings.

    :param get_key_bindings: Callable that returns a :class:`.KeyBindings` instance.
    """

    def __init__(self, get_key_bindings: Callable[[], KeyBindingsBase | None]) -> None:
        self.get_key_bindings = get_key_bindings
        self.__version = 0
        self._last_child_version = None
        self._dummy = KeyBindings()

class GlobalOnlyKeyBindings(_Proxy):
    """
    Wrapper around a :class:`.KeyBindings` object that only exposes the global
    key bindings.
    """

    def __init__(self, key_bindings: KeyBindingsBase) -> None:
        _Proxy.__init__(self)
        self.key_bindings = key_bindings

    def _update_cache(self) -> None:
        """
        If one of the original registries was changed. Update our merged
        version.
        """
        current_version = self.key_bindings._version
        if self._last_version != current_version:
            self._last_version = current_version
            self._bindings2 = KeyBindings()
            for b in self.key_bindings.bindings:
                if b.is_global():
                    self._bindings2.add(*b.keys, filter=b.filter, eager=b.eager,
                                        is_global=True, save_before=b.save_before,
                                        record_in_macro=b.record_in_macro)(b.handler)
