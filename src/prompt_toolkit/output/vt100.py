"""
Output for vt100 terminals.

A lot of thanks, regarding outputting of colors, goes to the Pygments project:
(We don't rely on Pygments anymore, because many things are very custom, and
everything has been highly optimized.)
http://pygments.org/
"""
from __future__ import annotations
import io
import os
import sys
from typing import Callable, Dict, Hashable, Iterable, Sequence, TextIO, Tuple
from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.data_structures import Size
from prompt_toolkit.output import Output
from prompt_toolkit.styles import ANSI_COLOR_NAMES, Attrs
from prompt_toolkit.utils import is_dumb_terminal
from .color_depth import ColorDepth
from .flush_stdout import flush_stdout
__all__ = ['Vt100_Output']
FG_ANSI_COLORS = {'ansidefault': 39, 'ansiblack': 30, 'ansired': 31, 'ansigreen': 32, 'ansiyellow': 33, 'ansiblue': 34, 'ansimagenta': 35, 'ansicyan': 36, 'ansigray': 37, 'ansibrightblack': 90, 'ansibrightred': 91, 'ansibrightgreen': 92, 'ansibrightyellow': 93, 'ansibrightblue': 94, 'ansibrightmagenta': 95, 'ansibrightcyan': 96, 'ansiwhite': 97}
BG_ANSI_COLORS = {'ansidefault': 49, 'ansiblack': 40, 'ansired': 41, 'ansigreen': 42, 'ansiyellow': 43, 'ansiblue': 44, 'ansimagenta': 45, 'ansicyan': 46, 'ansigray': 47, 'ansibrightblack': 100, 'ansibrightred': 101, 'ansibrightgreen': 102, 'ansibrightyellow': 103, 'ansibrightblue': 104, 'ansibrightmagenta': 105, 'ansibrightcyan': 106, 'ansiwhite': 107}
ANSI_COLORS_TO_RGB = {'ansidefault': (0, 0, 0), 'ansiblack': (0, 0, 0), 'ansigray': (229, 229, 229), 'ansibrightblack': (127, 127, 127), 'ansiwhite': (255, 255, 255), 'ansired': (205, 0, 0), 'ansigreen': (0, 205, 0), 'ansiyellow': (205, 205, 0), 'ansiblue': (0, 0, 205), 'ansimagenta': (205, 0, 205), 'ansicyan': (0, 205, 205), 'ansibrightred': (255, 0, 0), 'ansibrightgreen': (0, 255, 0), 'ansibrightyellow': (255, 255, 0), 'ansibrightblue': (0, 0, 255), 'ansibrightmagenta': (255, 0, 255), 'ansibrightcyan': (0, 255, 255)}
assert set(FG_ANSI_COLORS) == set(ANSI_COLOR_NAMES)
assert set(BG_ANSI_COLORS) == set(ANSI_COLOR_NAMES)
assert set(ANSI_COLORS_TO_RGB) == set(ANSI_COLOR_NAMES)

def _get_closest_ansi_color(r: int, g: int, b: int, exclude: Sequence[str]=()) -> str:
    """
    Find closest ANSI color. Return it by name.

    :param r: Red (Between 0 and 255.)
    :param g: Green (Between 0 and 255.)
    :param b: Blue (Between 0 and 255.)
    :param exclude: A tuple of color names to exclude. (E.g. ``('ansired', )``.)
    """
    def distance(color):
        return sum((a - b) ** 2 for a, b in zip((r, g, b), color))

    colors = {name: rgb for name, rgb in ANSI_COLORS_TO_RGB.items() if name not in exclude}
    return min(colors, key=lambda name: distance(colors[name]))
_ColorCodeAndName = Tuple[int, str]

class _16ColorCache:
    """
    Cache which maps (r, g, b) tuples to 16 ansi colors.

    :param bg: Cache for background colors, instead of foreground.
    """

    def __init__(self, bg: bool=False) -> None:
        self.bg = bg
        self._cache: dict[Hashable, _ColorCodeAndName] = {}

    def get_code(self, value: tuple[int, int, int], exclude: Sequence[str]=()) -> _ColorCodeAndName:
        """
        Return a (ansi_code, ansi_name) tuple. (E.g. ``(44, 'ansiblue')``.) for
        a given (r,g,b) value.
        """
        r, g, b = value
        
        # Check cache first
        cache_key = (r, g, b, tuple(exclude))
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Find the closest color
        color_name = _get_closest_ansi_color(r, g, b, exclude)
        
        # Get the code based on whether it's foreground or background
        code = (BG_ANSI_COLORS if self.bg else FG_ANSI_COLORS)[color_name]
        
        result = (code, color_name)
        self._cache[cache_key] = result
        return result

class _256ColorCache(Dict[Tuple[int, int, int], int]):
    """
    Cache which maps (r, g, b) tuples to 256 colors.
    """

    def __init__(self) -> None:
        colors: list[tuple[int, int, int]] = []
        colors.append((0, 0, 0))
        colors.append((205, 0, 0))
        colors.append((0, 205, 0))
        colors.append((205, 205, 0))
        colors.append((0, 0, 238))
        colors.append((205, 0, 205))
        colors.append((0, 205, 205))
        colors.append((229, 229, 229))
        colors.append((127, 127, 127))
        colors.append((255, 0, 0))
        colors.append((0, 255, 0))
        colors.append((255, 255, 0))
        colors.append((92, 92, 255))
        colors.append((255, 0, 255))
        colors.append((0, 255, 255))
        colors.append((255, 255, 255))
        valuerange = (0, 95, 135, 175, 215, 255)
        for i in range(217):
            r = valuerange[i // 36 % 6]
            g = valuerange[i // 6 % 6]
            b = valuerange[i % 6]
            colors.append((r, g, b))
        for i in range(1, 22):
            v = 8 + i * 10
            colors.append((v, v, v))
        self.colors = colors

    def __missing__(self, value: tuple[int, int, int]) -> int:
        r, g, b = value
        distance = 257 * 257 * 3
        match = 0
        for i, (r2, g2, b2) in enumerate(self.colors):
            if i >= 16:
                d = (r - r2) ** 2 + (g - g2) ** 2 + (b - b2) ** 2
                if d < distance:
                    match = i
                    distance = d
        self[value] = match
        return match
_16_fg_colors = _16ColorCache(bg=False)
_16_bg_colors = _16ColorCache(bg=True)
_256_colors = _256ColorCache()

class _EscapeCodeCache(Dict[Attrs, str]):
    """
    Cache for VT100 escape codes. It maps
    (fgcolor, bgcolor, bold, underline, strike, reverse) tuples to VT100
    escape sequences.

    :param true_color: When True, use 24bit colors instead of 256 colors.
    """

    def __init__(self, color_depth: ColorDepth) -> None:
        self.color_depth = color_depth

    def __missing__(self, attrs: Attrs) -> str:
        fgcolor, bgcolor, bold, underline, strike, italic, blink, reverse, hidden = attrs
        parts: list[str] = []
        parts.extend(self._colors_to_code(fgcolor or '', bgcolor or ''))
        if bold:
            parts.append('1')
        if italic:
            parts.append('3')
        if blink:
            parts.append('5')
        if underline:
            parts.append('4')
        if reverse:
            parts.append('7')
        if hidden:
            parts.append('8')
        if strike:
            parts.append('9')
        if parts:
            result = '\x1b[0;' + ';'.join(parts) + 'm'
        else:
            result = '\x1b[0m'
        self[attrs] = result
        return result

    def _color_name_to_rgb(self, color: str) -> tuple[int, int, int]:
        """Turn 'ffffff', into (0xff, 0xff, 0xff)."""
        if color in ANSI_COLORS_TO_RGB:
            return ANSI_COLORS_TO_RGB[color]
        
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        return (r, g, b)

    def _colors_to_code(self, fg_color: str, bg_color: str) -> Iterable[str]:
        """
        Return a tuple with the vt100 values  that represent this color.
        """
        result = []

        def color_to_code(color: str, offset: int) -> None:
            if color:
                try:
                    rgb = self._color_name_to_rgb(color)
                except ValueError:
                    pass
                else:
                    if self.color_depth == ColorDepth.DEPTH_24_BIT:
                        result.extend([str(offset + 8), '2', str(rgb[0]), str(rgb[1]), str(rgb[2])])
                    elif self.color_depth == ColorDepth.DEPTH_8_BIT:
                        result.extend([str(offset + 8), '5', str(_256_colors[rgb])])
                    elif self.color_depth == ColorDepth.DEPTH_4_BIT:
                        if offset == 30:  # foreground
                            code, name = _16_fg_colors.get_code(rgb)
                        else:  # background
                            code, name = _16_bg_colors.get_code(rgb)
                        result.append(str(code))

        color_to_code(fg_color, 30)
        color_to_code(bg_color, 40)

        return result

def _get_size(fileno: int) -> tuple[int, int]:
    """
    Get the size of this pseudo terminal.

    :param fileno: stdout.fileno()
    :returns: A (rows, cols) tuple.
    """
    import fcntl
    import termios
    import array

    buf = array.array('H', [0, 0, 0, 0])
    try:
        fcntl.ioctl(fileno, termios.TIOCGWINSZ, buf)
        return (buf[0], buf[1])
    except:
        return (24, 80)

class Vt100_Output(Output):
    """
    :param get_size: A callable which returns the `Size` of the output terminal.
    :param stdout: Any object with has a `write` and `flush` method + an 'encoding' property.
    :param term: The terminal environment variable. (xterm, xterm-256color, linux, ...)
    :param enable_cpr: When `True` (the default), send "cursor position
        request" escape sequences to the output in order to detect the cursor
        position. That way, we can properly determine how much space there is
        available for the UI (especially for drop down menus) to render. The
        `Renderer` will still try to figure out whether the current terminal
        does respond to CPR escapes. When `False`, never attempt to send CPR
        requests.
    """
    _fds_not_a_terminal: set[int] = set()

    def __init__(self, stdout: TextIO, get_size: Callable[[], Size], term: str | None=None, default_color_depth: ColorDepth | None=None, enable_bell: bool=True, enable_cpr: bool=True) -> None:
        assert all((hasattr(stdout, a) for a in ('write', 'flush')))
        self._buffer: list[str] = []
        self.stdout: TextIO = stdout
        self.default_color_depth = default_color_depth
        self._get_size = get_size
        self.term = term
        self.enable_bell = enable_bell
        self.enable_cpr = enable_cpr
        self._escape_code_caches: dict[ColorDepth, _EscapeCodeCache] = {ColorDepth.DEPTH_1_BIT: _EscapeCodeCache(ColorDepth.DEPTH_1_BIT), ColorDepth.DEPTH_4_BIT: _EscapeCodeCache(ColorDepth.DEPTH_4_BIT), ColorDepth.DEPTH_8_BIT: _EscapeCodeCache(ColorDepth.DEPTH_8_BIT), ColorDepth.DEPTH_24_BIT: _EscapeCodeCache(ColorDepth.DEPTH_24_BIT)}
        self._cursor_shape_changed = False

    @classmethod
    def from_pty(cls, stdout: TextIO, term: str | None=None, default_color_depth: ColorDepth | None=None, enable_bell: bool=True) -> Vt100_Output:
        """
        Create an Output class from a pseudo terminal.
        (This will take the dimensions by reading the pseudo
        terminal attributes.)
        """
        def get_size() -> Size:
            rows, columns = _get_size(stdout.fileno())
            return Size(rows=rows, columns=columns)

        return cls(stdout, get_size, term=term, default_color_depth=default_color_depth, enable_bell=enable_bell)

    def fileno(self) -> int:
        """Return file descriptor."""
        return self.stdout.fileno()

    def encoding(self) -> str:
        """Return encoding used for stdout."""
        return getattr(self.stdout, 'encoding', None) or 'utf-8'

    def write_raw(self, data: str) -> None:
        """
        Write raw data to output.
        """
        self._buffer.append(data)

    def write(self, data: str) -> None:
        """
        Write text to output.
        (Removes vt100 escape codes. -- used for safely writing text.)
        """
        self._buffer.append(data.replace('\x1b', '?'))

    def set_title(self, title: str) -> None:
        """
        Set terminal title.
        """
        if self.term not in ('linux', 'eterm-color'):
            self.write_raw(f'\x1b]2;{title}\x07')

    def erase_screen(self) -> None:
        """
        Erases the screen with the background color and moves the cursor to
        home.
        """
        self.write_raw('\x1b[2J')

    def erase_end_of_line(self) -> None:
        """
        Erases from the current cursor position to the end of the current line.
        """
        self.write_raw('\x1b[K')

    def erase_down(self) -> None:
        """
        Erases the screen from the current line down to the bottom of the
        screen.
        """
        self.write_raw('\x1b[J')

    def set_attributes(self, attrs: Attrs, color_depth: ColorDepth) -> None:
        """
        Create new style and output.

        :param attrs: `Attrs` instance.
        """
        escape_code_cache = self._escape_code_caches[color_depth]
        self.write_raw(escape_code_cache[attrs])

    def reset_cursor_key_mode(self) -> None:
        """
        For vt100 only.
        Put the terminal in cursor mode (instead of application mode).
        """
        self.write_raw('\x1b[?1l')

    def cursor_goto(self, row: int=0, column: int=0) -> None:
        """
        Move cursor position.
        """
        self.write_raw(f'\x1b[{row + 1};{column + 1}H')

    def reset_cursor_shape(self) -> None:
        """Reset cursor shape."""
        if self._cursor_shape_changed:
            self.write_raw('\x1b[0 q')
            self._cursor_shape_changed = False

    def flush(self) -> None:
        """
        Write to output stream and flush.
        """
        if not self._buffer:
            return

        data = ''.join(self._buffer)
        self._buffer = []

        try:
            self.stdout.write(data)
            self.stdout.flush()
        except OSError as e:
            if e.args and e.args[0] == errno.EINTR:
                # Interrupted system call. Can happen in case of a window
                # resize signal. (Just ignore and retry.)
                self.flush()
            else:
                raise

    def ask_for_cpr(self) -> None:
        """
        Asks for a cursor position report (CPR).
        """
        if self.enable_cpr:
            self.write_raw('\x1b[6n')
            self.flush()

    def bell(self) -> None:
        """Sound bell."""
        if self.enable_bell:
            self.write_raw('\a')
            self.flush()

    def get_default_color_depth(self) -> ColorDepth:
        """
        Return the default color depth for a vt100 terminal, according to the
        our term value.

        We prefer 256 colors almost always, because this is what most terminals
        support these days, and is a good default.
        """
        if self.default_color_depth is not None:
            return self.default_color_depth

        if self.term in ('linux', 'eterm-color'):
            return ColorDepth.DEPTH_4_BIT

        if is_dumb_terminal(self.term):
            return ColorDepth.DEPTH_1_BIT

        return ColorDepth.DEPTH_8_BIT
