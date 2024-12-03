from __future__ import annotations
from string import Formatter
from typing import Generator
from prompt_toolkit.output.vt100 import BG_ANSI_COLORS, FG_ANSI_COLORS
from prompt_toolkit.output.vt100 import _256_colors as _256_colors_table
from .base import StyleAndTextTuples
__all__ = ['ANSI', 'ansi_escape']

class ANSI:
    """
    ANSI formatted text.
    Take something ANSI escaped text, for use as a formatted string. E.g.

    ::

        ANSI('\\x1b[31mhello \\x1b[32mworld')

    Characters between ``\\001`` and ``\\002`` are supposed to have a zero width
    when printed, but these are literally sent to the terminal output. This can
    be used for instance, for inserting Final Term prompt commands.  They will
    be translated into a prompt_toolkit '[ZeroWidthEscape]' fragment.
    """

    def __init__(self, value: str) -> None:
        self.value = value
        self._formatted_text: StyleAndTextTuples = []
        self._color: str | None = None
        self._bgcolor: str | None = None
        self._bold = False
        self._underline = False
        self._strike = False
        self._italic = False
        self._blink = False
        self._reverse = False
        self._hidden = False
        parser = self._parse_corot()
        parser.send(None)
        for c in value:
            parser.send(c)

    def _parse_corot(self) -> Generator[None, str, None]:
        """
        Coroutine that parses the ANSI escape sequences.
        """
        formatted_text = self._formatted_text
        style = ''
        text = ''
        in_escape_sequence = False
        escape_sequence = ''
        zero_width_escape_sequence = False
        while True:
            char = yield
            if in_escape_sequence:
                escape_sequence += char
                if char.isalpha() or char == '~':
                    in_escape_sequence = False
                    self._select_graphic_rendition(escape_sequence)
                    escape_sequence = ''
            elif zero_width_escape_sequence:
                if char == '\002':
                    zero_width_escape_sequence = False
                    formatted_text.append(('[ZeroWidthEscape]', text))
                    text = ''
                else:
                    text += char
            elif char == '\001':
                if text:
                    formatted_text.append((style, text))
                    text = ''
                zero_width_escape_sequence = True
            elif char == '\033':
                if text:
                    formatted_text.append((style, text))
                    text = ''
                in_escape_sequence = True
            else:
                text += char
        if text:
            formatted_text.append((style, text))

    def _select_graphic_rendition(self, attrs: str) -> None:
        """
        Take a list of graphics attributes and apply changes.
        """
        if attrs.startswith('[') and attrs.endswith('m'):
            attrs = attrs[1:-1]
        
        for attr in attrs.split(';'):
            if not attr:
                continue
            attr = int(attr)
            if attr == 0:
                self._color = None
                self._bgcolor = None
                self._bold = False
                self._underline = False
                self._strike = False
                self._italic = False
                self._blink = False
                self._reverse = False
                self._hidden = False
            elif attr == 1:
                self._bold = True
            elif attr == 3:
                self._italic = True
            elif attr == 4:
                self._underline = True
            elif attr == 5:
                self._blink = True
            elif attr == 7:
                self._reverse = True
            elif attr == 8:
                self._hidden = True
            elif attr == 9:
                self._strike = True
            elif 30 <= attr <= 37:
                self._color = f'ansi{ANSI_COLOR_NAMES[attr - 30]}'
            elif 40 <= attr <= 47:
                self._bgcolor = f'ansi{ANSI_COLOR_NAMES[attr - 40]}'
            elif 90 <= attr <= 97:
                self._color = f'ansibright{ANSI_COLOR_NAMES[attr - 90]}'
            elif 100 <= attr <= 107:
                self._bgcolor = f'ansibright{ANSI_COLOR_NAMES[attr - 100]}'

    def _create_style_string(self) -> str:
        """
        Turn current style flags into a string for usage in a formatted text.
        """
        parts = []
        if self._color:
            parts.append(self._color)
        if self._bgcolor:
            parts.append('bg:' + self._bgcolor)
        if self._bold:
            parts.append('bold')
        if self._underline:
            parts.append('underline')
        if self._italic:
            parts.append('italic')
        if self._blink:
            parts.append('blink')
        if self._reverse:
            parts.append('reverse')
        if self._hidden:
            parts.append('hidden')
        if self._strike:
            parts.append('strike')
        return ' '.join(parts)

    def __repr__(self) -> str:
        return f'ANSI({self.value!r})'

    def __pt_formatted_text__(self) -> StyleAndTextTuples:
        return self._formatted_text

    def format(self, *args: str, **kwargs: str) -> ANSI:
        """
        Like `str.format`, but make sure that the arguments are properly
        escaped. (No ANSI escapes can be injected.)
        """
        escaped_args = tuple(ansi_escape(a) for a in args)
        escaped_kwargs = {k: ansi_escape(v) for k, v in kwargs.items()}
        return ANSI(self.value.format(*escaped_args, **escaped_kwargs))

    def __mod__(self, value: object) -> ANSI:
        """
        ANSI('<b>%s</b>') % value
        """
        if not isinstance(value, tuple):
            value = (value,)
        value = tuple((ansi_escape(i) for i in value))
        return ANSI(self.value % value)
_fg_colors = {v: k for k, v in FG_ANSI_COLORS.items()}
_bg_colors = {v: k for k, v in BG_ANSI_COLORS.items()}
_256_colors = {}
for i, (r, g, b) in enumerate(_256_colors_table.colors):
    _256_colors[i] = f'#{r:02x}{g:02x}{b:02x}'

def ansi_escape(text: object) -> str:
    """
    Replace characters with a special meaning.
    """
    if not isinstance(text, str):
        text = str(text)
    return text.replace('\x1b', '?').replace('\b', '?')

class ANSIFormatter(Formatter):
    pass
FORMATTER = ANSIFormatter()
