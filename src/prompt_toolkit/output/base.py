"""
Interface for an output.
"""
from __future__ import annotations
from abc import ABCMeta, abstractmethod
from typing import TextIO
from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.data_structures import Size
from prompt_toolkit.styles import Attrs
from .color_depth import ColorDepth
__all__ = ['Output', 'DummyOutput']

class Output(metaclass=ABCMeta):
    """
    Base class defining the output interface for a
    :class:`~prompt_toolkit.renderer.Renderer`.

    Actual implementations are
    :class:`~prompt_toolkit.output.vt100.Vt100_Output` and
    :class:`~prompt_toolkit.output.win32.Win32Output`.
    """
    stdout: TextIO | None = None

    @abstractmethod
    def fileno(self) -> int:
        """Return the file descriptor to which we can write for the output."""
        if self.stdout:
            return self.stdout.fileno()
        raise NotImplementedError("fileno() is not implemented for this output")

    @abstractmethod
    def encoding(self) -> str:
        """
        Return the encoding for this output, e.g. 'utf-8'.
        (This is used mainly to know which characters are supported by the
        output the data, so that the UI can provide alternatives, when
        required.)
        """
        if self.stdout:
            return self.stdout.encoding
        return 'utf-8'

    @abstractmethod
    def write(self, data: str) -> None:
        """Write text (Terminal escape sequences will be removed/escaped.)"""
        if self.stdout:
            self.stdout.write(data)

    @abstractmethod
    def write_raw(self, data: str) -> None:
        """Write text."""
        if self.stdout:
            self.stdout.write(data)

    @abstractmethod
    def set_title(self, title: str) -> None:
        """Set terminal title."""
        # This is a stub. The actual implementation would depend on the terminal type.
        pass

    @abstractmethod
    def clear_title(self) -> None:
        """Clear title again. (or restore previous title.)"""
        # This is a stub. The actual implementation would depend on the terminal type.
        pass

    @abstractmethod
    def flush(self) -> None:
        """Write to output stream and flush."""
        if self.stdout:
            self.stdout.flush()

    @abstractmethod
    def erase_screen(self) -> None:
        """
        Erases the screen with the background color and moves the cursor to
        home.
        """
        self.write_raw("\x1b[2J\x1b[H")

    @abstractmethod
    def enter_alternate_screen(self) -> None:
        """Go to the alternate screen buffer. (For full screen applications)."""
        self.write_raw("\x1b[?1049h")

    @abstractmethod
    def quit_alternate_screen(self) -> None:
        """Leave the alternate screen buffer."""
        self.write_raw("\x1b[?1049l")

    @abstractmethod
    def enable_mouse_support(self) -> None:
        """Enable mouse."""
        self.write_raw("\x1b[?1000h")

    @abstractmethod
    def disable_mouse_support(self) -> None:
        """Disable mouse."""
        self.write_raw("\x1b[?1000l")

    @abstractmethod
    def erase_end_of_line(self) -> None:
        """
        Erases from the current cursor position to the end of the current line.
        """
        self.write_raw("\x1b[K")

    @abstractmethod
    def erase_down(self) -> None:
        """
        Erases the screen from the current line down to the bottom of the
        screen.
        """
        self.write_raw("\x1b[J")

    @abstractmethod
    def reset_attributes(self) -> None:
        """Reset color and styling attributes."""
        self.write_raw("\x1b[0m")

    @abstractmethod
    def set_attributes(self, attrs: Attrs, color_depth: ColorDepth) -> None:
        """Set new color and styling attributes."""
        # This is a stub. The actual implementation would depend on the attributes and color depth.
        pass

    @abstractmethod
    def disable_autowrap(self) -> None:
        """Disable auto line wrapping."""
        self.write_raw("\x1b[?7l")

    @abstractmethod
    def enable_autowrap(self) -> None:
        """Enable auto line wrapping."""
        self.write_raw("\x1b[?7h")

    @abstractmethod
    def cursor_goto(self, row: int=0, column: int=0) -> None:
        """Move cursor position."""
        self.write_raw(f"\x1b[{row+1};{column+1}H")

    @abstractmethod
    def cursor_up(self, amount: int) -> None:
        """Move cursor `amount` place up."""
        if amount > 0:
            self.write_raw(f"\x1b[{amount}A")

    @abstractmethod
    def cursor_down(self, amount: int) -> None:
        """Move cursor `amount` place down."""
        if amount > 0:
            self.write_raw(f"\x1b[{amount}B")

    @abstractmethod
    def cursor_forward(self, amount: int) -> None:
        """Move cursor `amount` place forward."""
        if amount > 0:
            self.write_raw(f"\x1b[{amount}C")

    @abstractmethod
    def cursor_backward(self, amount: int) -> None:
        """Move cursor `amount` place backward."""
        if amount > 0:
            self.write_raw(f"\x1b[{amount}D")

    @abstractmethod
    def hide_cursor(self) -> None:
        """Hide cursor."""
        self.write_raw("\x1b[?25l")

    @abstractmethod
    def show_cursor(self) -> None:
        """Show cursor."""
        self.write_raw("\x1b[?25h")

    @abstractmethod
    def set_cursor_shape(self, cursor_shape: CursorShape) -> None:
        """Set cursor shape to block, beam or underline."""
        shape_codes = {
            CursorShape.BLOCK: 2,
            CursorShape.BEAM: 6,
            CursorShape.UNDERLINE: 4,
            CursorShape.BLINKING_BLOCK: 1,
            CursorShape.BLINKING_BEAM: 5,
            CursorShape.BLINKING_UNDERLINE: 3,
        }
        if cursor_shape in shape_codes:
            self.write_raw(f"\x1b[{shape_codes[cursor_shape]} q")

    @abstractmethod
    def reset_cursor_shape(self) -> None:
        """Reset cursor shape."""
        self.write_raw("\x1b[0 q")

    def ask_for_cpr(self) -> None:
        """
        Asks for a cursor position report (CPR).
        (VT100 only.)
        """
        self.write_raw("\x1b[6n")

    @property
    def responds_to_cpr(self) -> bool:
        """
        `True` if the `Application` can expect to receive a CPR response after
        calling `ask_for_cpr` (this will come back through the corresponding
        `Input`).

        This is used to determine the amount of available rows we have below
        the cursor position. In the first place, we have this so that the drop
        down autocompletion menus are sized according to the available space.

        On Windows, we don't need this, there we have
        `get_rows_below_cursor_position`.
        """
        return True  # Assuming VT100 compatibility by default

    @abstractmethod
    def get_size(self) -> Size:
        """Return the size of the output window."""
        # This is a stub. The actual implementation would depend on the system.
        return Size(rows=24, columns=80)

    def bell(self) -> None:
        """Sound bell."""
        self.write('\a')

    def enable_bracketed_paste(self) -> None:
        """For vt100 only."""
        self.write_raw("\x1b[?2004h")

    def disable_bracketed_paste(self) -> None:
        """For vt100 only."""
        self.write_raw("\x1b[?2004l")

    def reset_cursor_key_mode(self) -> None:
        """
        For vt100 only.
        Put the terminal in normal cursor mode (instead of application mode).

        See: https://vt100.net/docs/vt100-ug/chapter3.html
        """
        self.write_raw("\x1b[?1l")

    def scroll_buffer_to_prompt(self) -> None:
        """For Win32 only."""
        # This is a no-op for non-Windows systems
        pass

    def get_rows_below_cursor_position(self) -> int:
        """For Windows only."""
        # This is a stub. The actual implementation would be different for Windows.
        return 0

    @abstractmethod
    def get_default_color_depth(self) -> ColorDepth:
        """
        Get default color depth for this output.

        This value will be used if no color depth was explicitly passed to the
        `Application`.

        .. note::

            If the `$PROMPT_TOOLKIT_COLOR_DEPTH` environment variable has been
            set, then `outputs.defaults.create_output` will pass this value to
            the implementation as the default_color_depth, which is returned
            here. (This is not used when the output corresponds to a
            prompt_toolkit SSH/Telnet session.)
        """
        return ColorDepth.default()

class DummyOutput(Output):
    """
    For testing. An output class that doesn't render anything.
    """

    def fileno(self) -> int:
        """
        DummyOutput doesn't have a real file descriptor, so we return a dummy value.
        This method is implemented to satisfy the abstract method requirement.
        """
        return -1
