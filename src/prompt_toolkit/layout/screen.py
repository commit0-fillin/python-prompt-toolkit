from __future__ import annotations
from collections import defaultdict
from typing import TYPE_CHECKING, Callable
from prompt_toolkit.cache import FastDictCache
from prompt_toolkit.data_structures import Point
from prompt_toolkit.utils import get_cwidth
if TYPE_CHECKING:
    from .containers import Window
__all__ = ['Screen', 'Char']

class Char:
    """
    Represent a single character in a :class:`.Screen`.

    This should be considered immutable.

    :param char: A single character (can be a double-width character).
    :param style: A style string. (Can contain classnames.)
    """
    __slots__ = ('char', 'style', 'width')
    display_mappings: dict[str, str] = {'\x00': '^@', '\x01': '^A', '\x02': '^B', '\x03': '^C', '\x04': '^D', '\x05': '^E', '\x06': '^F', '\x07': '^G', '\x08': '^H', '\t': '^I', '\n': '^J', '\x0b': '^K', '\x0c': '^L', '\r': '^M', '\x0e': '^N', '\x0f': '^O', '\x10': '^P', '\x11': '^Q', '\x12': '^R', '\x13': '^S', '\x14': '^T', '\x15': '^U', '\x16': '^V', '\x17': '^W', '\x18': '^X', '\x19': '^Y', '\x1a': '^Z', '\x1b': '^[', '\x1c': '^\\', '\x1d': '^]', '\x1e': '^^', '\x1f': '^_', '\x7f': '^?', '\x80': '<80>', '\x81': '<81>', '\x82': '<82>', '\x83': '<83>', '\x84': '<84>', '\x85': '<85>', '\x86': '<86>', '\x87': '<87>', '\x88': '<88>', '\x89': '<89>', '\x8a': '<8a>', '\x8b': '<8b>', '\x8c': '<8c>', '\x8d': '<8d>', '\x8e': '<8e>', '\x8f': '<8f>', '\x90': '<90>', '\x91': '<91>', '\x92': '<92>', '\x93': '<93>', '\x94': '<94>', '\x95': '<95>', '\x96': '<96>', '\x97': '<97>', '\x98': '<98>', '\x99': '<99>', '\x9a': '<9a>', '\x9b': '<9b>', '\x9c': '<9c>', '\x9d': '<9d>', '\x9e': '<9e>', '\x9f': '<9f>', '\xa0': ' '}

    def __init__(self, char: str=' ', style: str='') -> None:
        if char in self.display_mappings:
            if char == '\xa0':
                style += ' class:nbsp '
            else:
                style += ' class:control-character '
            char = self.display_mappings[char]
        self.char = char
        self.style = style
        self.width = get_cwidth(char)
    if not TYPE_CHECKING:
        __eq__ = _equal
        __ne__ = _not_equal

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.char!r}, {self.style!r})'
_CHAR_CACHE: FastDictCache[tuple[str, str], Char] = FastDictCache(Char, size=1000 * 1000)
Transparent = '[transparent]'

class Screen:
    """
    Two dimensional buffer of :class:`.Char` instances.
    """

    def __init__(self, default_char: Char | None=None, initial_width: int=0, initial_height: int=0) -> None:
        if default_char is None:
            default_char2 = _CHAR_CACHE[' ', Transparent]
        else:
            default_char2 = default_char
        self.data_buffer: defaultdict[int, defaultdict[int, Char]] = defaultdict(lambda: defaultdict(lambda: default_char2))
        self.zero_width_escapes: defaultdict[int, defaultdict[int, str]] = defaultdict(lambda: defaultdict(lambda: ''))
        self.cursor_positions: dict[Window, Point] = {}
        self.show_cursor = True
        self.menu_positions: dict[Window, Point] = {}
        self.width = initial_width or 0
        self.height = initial_height or 0
        self.visible_windows_to_write_positions: dict[Window, WritePosition] = {}
        self._draw_float_functions: list[tuple[int, Callable[[], None]]] = []

    def set_cursor_position(self, window: Window, position: Point) -> None:
        """
        Set the cursor position for a given window.
        """
        self.cursor_positions[window] = position

    def set_menu_position(self, window: Window, position: Point) -> None:
        """
        Set the menu position for a given window.
        """
        self.menu_positions[window] = position

    def get_cursor_position(self, window: Window) -> Point:
        """
        Get the cursor position for a given window.
        Returns a `Point`.
        """
        return self.cursor_positions.get(window, Point(x=0, y=0))

    def get_menu_position(self, window: Window) -> Point:
        """
        Get the menu position for a given window.
        (This falls back to the cursor position if no menu position was set.)
        """
        return self.menu_positions.get(window, self.get_cursor_position(window))

    def draw_with_z_index(self, z_index: int, draw_func: Callable[[], None]) -> None:
        """
        Add a draw-function for a `Window` which has a >= 0 z_index.
        This will be postponed until `draw_all_floats` is called.
        """
        self._draw_float_functions.append((z_index, draw_func))

    def draw_all_floats(self) -> None:
        """
        Draw all float functions in order of z-index.
        """
        for _, draw_func in sorted(self._draw_float_functions):
            draw_func()
        self._draw_float_functions = []

    def append_style_to_content(self, style_str: str) -> None:
        """
        For all the characters in the screen.
        Set the style string to the given `style_str`.
        """
        for row in self.data_buffer.values():
            for char in row.values():
                char.style += style_str

    def fill_area(self, write_position: WritePosition, style: str='', after: bool=False) -> None:
        """
        Fill the content of this area, using the given `style`.
        The style is prepended before whatever was here before.
        """
        for y in range(write_position.ypos, write_position.ypos + write_position.height):
            row = self.data_buffer[y]
            for x in range(write_position.xpos, write_position.xpos + write_position.width):
                cell = row[x]
                if after:
                    cell.style += style
                else:
                    cell.style = style + cell.style

class WritePosition:

    def __init__(self, xpos: int, ypos: int, width: int, height: int) -> None:
        assert height >= 0
        assert width >= 0
        self.xpos = xpos
        self.ypos = ypos
        self.width = width
        self.height = height

    def __repr__(self) -> str:
        return '{}(x={!r}, y={!r}, width={!r}, height={!r})'.format(self.__class__.__name__, self.xpos, self.ypos, self.width, self.height)
