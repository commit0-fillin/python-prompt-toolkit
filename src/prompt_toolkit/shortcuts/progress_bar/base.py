"""
Progress bar implementation on top of prompt_toolkit.

::

    with ProgressBar(...) as pb:
        for item in pb(data):
            ...
"""
from __future__ import annotations
import contextvars
import datetime
import functools
import os
import signal
import threading
import traceback
from typing import Callable, Generic, Iterable, Iterator, Sequence, Sized, TextIO, TypeVar, cast
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app_session
from prompt_toolkit.filters import Condition, is_done, renderer_height_is_known
from prompt_toolkit.formatted_text import AnyFormattedText, StyleAndTextTuples, to_formatted_text
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.layout import ConditionalContainer, FormattedTextControl, HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.layout.dimension import AnyDimension, D
from prompt_toolkit.output import ColorDepth, Output
from prompt_toolkit.styles import BaseStyle
from prompt_toolkit.utils import in_main_thread
from .formatters import Formatter, create_default_formatters
__all__ = ['ProgressBar']
E = KeyPressEvent
_SIGWINCH = getattr(signal, 'SIGWINCH', None)

def create_key_bindings(cancel_callback: Callable[[], None] | None) -> KeyBindings:
    """
    Key bindings handled by the progress bar.
    (The main thread is not supposed to handle any key bindings.)
    """
    kb = KeyBindings()

    @kb.add('c-c')
    def _(event: E) -> None:
        " Abort. "
        if cancel_callback:
            cancel_callback()

    return kb
_T = TypeVar('_T')

class ProgressBar:
    """
    Progress bar context manager.

    Usage ::

        with ProgressBar(...) as pb:
            for item in pb(data):
                ...

    :param title: Text to be displayed above the progress bars. This can be a
        callable or formatted text as well.
    :param formatters: List of :class:`.Formatter` instances.
    :param bottom_toolbar: Text to be displayed in the bottom toolbar. This
        can be a callable or formatted text.
    :param style: :class:`prompt_toolkit.styles.BaseStyle` instance.
    :param key_bindings: :class:`.KeyBindings` instance.
    :param cancel_callback: Callback function that's called when control-c is
        pressed by the user. This can be used for instance to start "proper"
        cancellation if the wrapped code supports it.
    :param file: The file object used for rendering, by default `sys.stderr` is used.

    :param color_depth: `prompt_toolkit` `ColorDepth` instance.
    :param output: :class:`~prompt_toolkit.output.Output` instance.
    :param input: :class:`~prompt_toolkit.input.Input` instance.
    """

    def __init__(self, title: AnyFormattedText=None, formatters: Sequence[Formatter] | None=None, bottom_toolbar: AnyFormattedText=None, style: BaseStyle | None=None, key_bindings: KeyBindings | None=None, cancel_callback: Callable[[], None] | None=None, file: TextIO | None=None, color_depth: ColorDepth | None=None, output: Output | None=None, input: Input | None=None) -> None:
        self.title = title
        self.formatters = formatters or create_default_formatters()
        self.bottom_toolbar = bottom_toolbar
        self.counters: list[ProgressBarCounter[object]] = []
        self.style = style
        self.key_bindings = key_bindings
        self.cancel_callback = cancel_callback
        if self.cancel_callback is None and in_main_thread():

            def keyboard_interrupt_to_main_thread() -> None:
                os.kill(os.getpid(), signal.SIGINT)
            self.cancel_callback = keyboard_interrupt_to_main_thread
        self.color_depth = color_depth
        self.output = output or get_app_session().output
        self.input = input or get_app_session().input
        self._thread: threading.Thread | None = None
        self._has_sigwinch = False
        self._app_started = threading.Event()

    def __enter__(self) -> ProgressBar:
        title_toolbar = ConditionalContainer(Window(FormattedTextControl(lambda: self.title), height=1, style='class:progressbar,title'), filter=Condition(lambda: self.title is not None))
        bottom_toolbar = ConditionalContainer(Window(FormattedTextControl(lambda: self.bottom_toolbar, style='class:bottom-toolbar.text'), style='class:bottom-toolbar', height=1), filter=~is_done & renderer_height_is_known & Condition(lambda: self.bottom_toolbar is not None))

        def width_for_formatter(formatter: Formatter) -> AnyDimension:
            return formatter.get_width(progress_bar=self)
        progress_controls = [Window(content=_ProgressControl(self, f, self.cancel_callback), width=functools.partial(width_for_formatter, f)) for f in self.formatters]
        self.app: Application[None] = Application(min_redraw_interval=0.05, layout=Layout(HSplit([title_toolbar, VSplit(progress_controls, height=lambda: D(preferred=len(self.counters), max=len(self.counters))), Window(), bottom_toolbar])), style=self.style, key_bindings=self.key_bindings, refresh_interval=0.3, color_depth=self.color_depth, output=self.output, input=self.input)

        def run() -> None:
            try:
                self.app.run(pre_run=self._app_started.set)
            except BaseException as e:
                traceback.print_exc()
                print(e)
        ctx: contextvars.Context = contextvars.copy_context()
        self._thread = threading.Thread(target=ctx.run, args=(run,))
        self._thread.start()
        return self

    def __exit__(self, *a: object) -> None:
        self._app_started.wait()
        if self.app.is_running and self.app.loop is not None:
            self.app.loop.call_soon_threadsafe(self.app.exit)
        if self._thread is not None:
            self._thread.join()

    def __call__(self, data: Iterable[_T] | None=None, label: AnyFormattedText='', remove_when_done: bool=False, total: int | None=None) -> ProgressBarCounter[_T]:
        """
        Start a new counter.

        :param label: Title text or description for this progress. (This can be
            formatted text as well).
        :param remove_when_done: When `True`, hide this progress bar.
        :param total: Specify the maximum value if it can't be calculated by
            calling ``len``.
        """
        counter = ProgressBarCounter(self, data, label=label, remove_when_done=remove_when_done, total=total)
        self.counters.append(counter)
        return counter

class _ProgressControl(UIControl):
    """
    User control for the progress bar.
    """

    def __init__(self, progress_bar: ProgressBar, formatter: Formatter, cancel_callback: Callable[[], None] | None) -> None:
        self.progress_bar = progress_bar
        self.formatter = formatter
        self._key_bindings = create_key_bindings(cancel_callback)
_CounterItem = TypeVar('_CounterItem', covariant=True)

class ProgressBarCounter(Generic[_CounterItem]):
    """
    An individual counter (A progress bar can have multiple counters).
    """

    def __init__(self, progress_bar: ProgressBar, data: Iterable[_CounterItem] | None=None, label: AnyFormattedText='', remove_when_done: bool=False, total: int | None=None) -> None:
        self.start_time = datetime.datetime.now()
        self.stop_time: datetime.datetime | None = None
        self.progress_bar = progress_bar
        self.data = data
        self.items_completed = 0
        self.label = label
        self.remove_when_done = remove_when_done
        self._done = False
        self.total: int | None
        if total is None:
            try:
                self.total = len(cast(Sized, data))
            except TypeError:
                self.total = None
        else:
            self.total = total

    def __iter__(self) -> Iterator[_CounterItem]:
        if self.data is not None:
            try:
                for item in self.data:
                    yield item
                    self.item_completed()
                self.done = True
            finally:
                self.stopped = True
        else:
            raise NotImplementedError('No data defined to iterate over.')

    def item_completed(self) -> None:
        """
        Start handling the next item.

        (Can be called manually in case we don't have a collection to loop through.)
        """
        self.items_completed += 1
        if self.total is not None and self.items_completed >= self.total:
            self.done = True

    @property
    def done(self) -> bool:
        """Whether a counter has been completed.

        Done counter have been stopped (see stopped) and removed depending on
        remove_when_done value.

        Contrast this with stopped. A stopped counter may be terminated before
        100% completion. A done counter has reached its 100% completion.
        """
        return self._done

    @done.setter
    def done(self, value: bool) -> None:
        self._done = value
        if value:
            self.stopped = True

    @property
    def stopped(self) -> bool:
        """Whether a counter has been stopped.

        Stopped counters no longer have increasing time_elapsed. This distinction is
        also used to prevent the Bar formatter with unknown totals from continuing to run.

        A stopped counter (but not done) can be used to signal that a given counter has
        encountered an error but allows other counters to continue
        (e.g. download X of Y failed). Given how only done counters are removed
        (see remove_when_done) this can help aggregate failures from a large number of
        successes.

        Contrast this with done. A done counter has reached its 100% completion.
        A stopped counter may be terminated before 100% completion.
        """
        return self.stop_time is not None

    @stopped.setter
    def stopped(self, value: bool) -> None:
        if value and self.stop_time is None:
            self.stop_time = datetime.datetime.now()
        elif not value:
            self.stop_time = None

    @property
    def time_elapsed(self) -> datetime.timedelta:
        """
        Return how much time has been elapsed since the start.
        """
        if self.stop_time is not None:
            return self.stop_time - self.start_time
        return datetime.datetime.now() - self.start_time

    @property
    def time_left(self) -> datetime.timedelta | None:
        """
        Timedelta representing the time left.
        """
        if self.done:
            return datetime.timedelta(0)
        if self.total is None or self.items_completed == 0:
            return None
        
        elapsed = self.time_elapsed
        rate = self.items_completed / elapsed.total_seconds()
        remaining_items = self.total - self.items_completed
        seconds_left = remaining_items / rate if rate > 0 else 0
        
        return datetime.timedelta(seconds=int(seconds_left))
