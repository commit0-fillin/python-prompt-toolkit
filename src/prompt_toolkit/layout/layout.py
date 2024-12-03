"""
Wrapper for the layout.
"""
from __future__ import annotations
from typing import Generator, Iterable, Union
from prompt_toolkit.buffer import Buffer
from .containers import AnyContainer, ConditionalContainer, Container, Window, to_container
from .controls import BufferControl, SearchBufferControl, UIControl
__all__ = ['Layout', 'InvalidLayoutError', 'walk']
FocusableElement = Union[str, Buffer, UIControl, AnyContainer]

class Layout:
    """
    The layout for a prompt_toolkit
    :class:`~prompt_toolkit.application.Application`.
    This also keeps track of which user control is focused.

    :param container: The "root" container for the layout.
    :param focused_element: element to be focused initially. (Can be anything
        the `focus` function accepts.)
    """

    def __init__(self, container: AnyContainer, focused_element: FocusableElement | None=None) -> None:
        self.container = to_container(container)
        self._stack: list[Window] = []
        self.search_links: dict[SearchBufferControl, BufferControl] = {}
        self._child_to_parent: dict[Container, Container] = {}
        if focused_element is None:
            try:
                self._stack.append(next(self.find_all_windows()))
            except StopIteration as e:
                raise InvalidLayoutError('Invalid layout. The layout does not contain any Window object.') from e
        else:
            self.focus(focused_element)
        self.visible_windows: list[Window] = []

    def __repr__(self) -> str:
        return f'Layout({self.container!r}, current_window={self.current_window!r})'

    def find_all_windows(self) -> Generator[Window, None, None]:
        """
        Find all the :class:`.UIControl` objects in this layout.
        """
        for item in self.walk():
            if isinstance(item, Window):
                yield item

    def focus(self, value: FocusableElement) -> None:
        """
        Focus the given UI element.

        `value` can be either:

        - a :class:`.UIControl`
        - a :class:`.Buffer` instance or the name of a :class:`.Buffer`
        - a :class:`.Window`
        - Any container object. In this case we will focus the :class:`.Window`
          from this container that was focused most recent, or the very first
          focusable :class:`.Window` of the container.
        """
        if isinstance(value, str):
            # Focus buffer by name.
            for w in self.find_all_windows():
                if isinstance(w.content, BufferControl) and w.content.buffer.name == value:
                    self._stack.append(w)
                    return
        elif isinstance(value, Buffer):
            # Focus buffer.
            for w in self.find_all_windows():
                if isinstance(w.content, BufferControl) and w.content.buffer == value:
                    self._stack.append(w)
                    return
        elif isinstance(value, UIControl):
            # Focus UIControl.
            for w in self.find_all_windows():
                if w.content == value:
                    self._stack.append(w)
                    return
        elif isinstance(value, Window):
            # Focus Window.
            self._stack.append(value)
        else:
            # Focus Container.
            for w in self.walk_through_modal_area():
                if isinstance(w, Window) and w.content.is_focusable():
                    self._stack.append(w)
                    return

        # If we're here, it means that we couldn't find a window to focus.
        self._stack = []

    def has_focus(self, value: FocusableElement) -> bool:
        """
        Check whether the given control has the focus.
        :param value: :class:`.UIControl` or :class:`.Window` instance.
        """
        if isinstance(value, Window):
            return self._stack and self._stack[-1] == value
        else:
            return self._stack and self._stack[-1].content == value

    @property
    def current_control(self) -> UIControl:
        """
        Get the :class:`.UIControl` to currently has the focus.
        """
        if self._stack:
            return self._stack[-1].content
        return self.container.content

    @current_control.setter
    def current_control(self, control: UIControl) -> None:
        """
        Set the :class:`.UIControl` to receive the focus.
        """
        self.focus(control)

    @property
    def current_window(self) -> Window:
        """Return the :class:`.Window` object that is currently focused."""
        if self._stack:
            return self._stack[-1]
        return next(self.find_all_windows())

    @current_window.setter
    def current_window(self, value: Window) -> None:
        """Set the :class:`.Window` object to be currently focused."""
        self.focus(value)

    @property
    def is_searching(self) -> bool:
        """True if we are searching right now."""
        return any(
            isinstance(c, SearchBufferControl)
            for c in self.search_links
        )

    @property
    def search_target_buffer_control(self) -> BufferControl | None:
        """
        Return the :class:`.BufferControl` in which we are searching or `None`.
        """
        if self.is_searching:
            for search_control, buffer_control in self.search_links.items():
                if search_control.buffer.text:
                    return buffer_control
        return None

    def get_focusable_windows(self) -> Iterable[Window]:
        """
        Return all the :class:`.Window` objects which are focusable (in the
        'modal' area).
        """
        for w in self.walk_through_modal_area():
            if isinstance(w, Window) and w.content.is_focusable():
                yield w

    def get_visible_focusable_windows(self) -> list[Window]:
        """
        Return a list of :class:`.Window` objects that are focusable.
        """
        return [w for w in self.visible_windows if w.content.is_focusable()]

    @property
    def current_buffer(self) -> Buffer | None:
        """
        The currently focused :class:`~.Buffer` or `None`.
        """
        if isinstance(self.current_control, BufferControl):
            return self.current_control.buffer
        return None

    def get_buffer_by_name(self, buffer_name: str) -> Buffer | None:
        """
        Look in the layout for a buffer with the given name.
        Return `None` when nothing was found.
        """
        for w in self.find_all_windows():
            if isinstance(w.content, BufferControl):
                if w.content.buffer.name == buffer_name:
                    return w.content.buffer
        return None

    @property
    def buffer_has_focus(self) -> bool:
        """
        Return `True` if the currently focused control is a
        :class:`.BufferControl`. (For instance, used to determine whether the
        default key bindings should be active or not.)
        """
        return isinstance(self.current_control, BufferControl)

    @property
    def previous_control(self) -> UIControl:
        """
        Get the :class:`.UIControl` to previously had the focus.
        """
        if len(self._stack) > 1:
            return self._stack[-2].content
        return self.container.content

    def focus_last(self) -> None:
        """
        Give the focus to the last focused control.
        """
        if len(self._stack) > 1:
            self._stack.pop()

    def focus_next(self) -> None:
        """
        Focus the next visible/focusable Window.
        """
        windows = self.get_visible_focusable_windows()
        if not windows:
            return

        try:
            index = windows.index(self.current_window)
            self.focus(windows[(index + 1) % len(windows)])
        except ValueError:
            # If the current window is not in the list, focus the first one.
            self.focus(windows[0])

    def focus_previous(self) -> None:
        """
        Focus the previous visible/focusable Window.
        """
        windows = self.get_visible_focusable_windows()
        if not windows:
            return

        try:
            index = windows.index(self.current_window)
            self.focus(windows[(index - 1) % len(windows)])
        except ValueError:
            # If the current window is not in the list, focus the last one.
            self.focus(windows[-1])

    def walk(self) -> Iterable[Container]:
        """
        Walk through all the layout nodes (and their children) and yield them.
        """
        def walk_recursive(container):
            yield container
            for c in container.get_children():
                yield from walk_recursive(c)

        yield from walk_recursive(self.container)

    def walk_through_modal_area(self) -> Iterable[Container]:
        """
        Walk through all the containers which are in the current 'modal' part
        of the layout.
        """
        for container in self.walk():
            if container.is_modal():
                yield from container.get_children()
                return
        yield from self.walk()

    def update_parents_relations(self) -> None:
        """
        Update child->parent relationships mapping.
        """
        self._child_to_parent = {}

        def walk(container):
            for child in container.get_children():
                self._child_to_parent[child] = container
                walk(child)

        walk(self.container)

    def get_parent(self, container: Container) -> Container | None:
        """
        Return the parent container for the given container, or ``None``, if it
        wasn't found.
        """
        try:
            return self._child_to_parent[container]
        except KeyError:
            return None

class InvalidLayoutError(Exception):
    pass

def walk(container: Container, skip_hidden: bool=False) -> Iterable[Container]:
    """
    Walk through layout, starting at this container.
    """
    pass
