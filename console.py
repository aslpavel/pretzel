"""Console utility functions
"""
from __future__ import division
import io
import re
import sys
import math
import fcntl
import struct
import termios
import colorsys
import functools
from bisect import bisect
from .utils import cached, call

__all__ = ('Console', 'move_up_csi', 'move_down_csi', 'move_column_csi',
           'delete_csi', 'insert_csi', 'erase_csi', 'save_csi', 'restore_csi',
           'scroll_up_csi', 'scroll_down_csi', 'visibility_csi',
           'color_csi', 'color_reset_csi',)


class Console(object):
    """Console object

    Default position of cursor is at the end of all frames.
    """
    default_size = (80, 40)

    def __init__(self, stream=None):
        self.stream = (stream if stream is not None else
                       io.open(sys.stderr.fileno(), 'wb', closefd=False))
        self.color = ConsoleColors(self)
        self.labels_stack = []

    def write(self, data, *scopes):
        """Write data to stream and inside provided scopes
        """
        if scopes:
            try:
                for scope in scopes:
                    scope.__enter__()
                return self.stream.write(data)
            finally:
                for scope in scopes:
                    scope.__exit__(None, None, None)
        else:
            return self.stream.write(data)

    def line(self):
        """Returns scope which inserts line above all labels
        """
        def enter():
            position = len(self.labels_stack) + 1
            write(b'\n')
            write(move_up_csi(position))
            write(insert_csi(1))

        def exit():
            write(move_down_csi(position))
            write(move_column_csi(0))
            self.stream.flush()

        position = len(self.labels_stack) + 1
        write = self.stream.write
        return ConsoleScope(enter, exit)

    def label(self):
        """Create console label
        """
        return ConsoleLabel(self)

    @property
    def size(self):
        """Get console size
        """
        if not self.stream.isatty():
            return self.default_size
        ioctl_arg = struct.pack('4H', 0, 0, 0, 0)
        rows, columns = (struct.unpack('4H', fcntl.ioctl(self.stream.fileno(),
                         termios.TIOCGWINSZ, ioctl_arg)))[:2]
        return rows, columns

    def flush(self):
        return self.stream.flush()

    def dispose(self):
        for label in tuple(self.labels_stack):
            label.dispose()
        self.stream.write(visibility_csi(True))
        self.stream.write(color_reset_csi())
        self.stream.flush()

    def __enter__(self):
        self.stream.write(visibility_csi(False))
        self.stream.flush()
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return 'Console(height:{}, width:{})'.format(*self.size)

    def __repr__(self):
        return str(self)


class ConsoleLabel(object):
    def __init__(self, console):
        self.console = console
        self.index = len(console.labels_stack)
        console.labels_stack.append(self)
        console.stream.write(b'\n')

    def update(self, erase=None):
        """Returns scope which positions cursor to update label
        """
        if self.index < 0:
            raise RuntimeError('label has already been disposed')

        def enter():
            write(move_up_csi(position))
            write(move_column_csi(0))
            if erase is None or erase:
                write(erase_csi())

        def exit():
            write(move_down_csi(position))
            write(move_column_csi(0))
            self.console.stream.flush()

        position = len(self.console.labels_stack) - self.index
        write = self.console.stream.write
        return ConsoleScope(enter, exit)

    def dispose(self):
        index, self.index = self.index, -1
        if index < 0:
            return

        # delete label
        del self.console.labels_stack[index]
        for label in self.console.labels_stack[index:]:
            label.index -= 1

        # erase label
        position = len(self.console.labels_stack) - index + 1
        write = self.console.stream.write
        write(move_up_csi(position))
        write(move_column_csi(0))
        write(delete_csi(1))
        write(move_down_csi(position - 1))
        self.console.stream.flush()

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return 'ConsoleLabel(index:{}, height:{})'.format(self.index, self.height)

    def __repr__(self):
        return str(self)


class ConsoleColors(object):
    def __init__(self, console):
        self.console = console
        self.colors = {}
        self.stack = []

        @cached
        def color(fg, bg, attrs):
            def enter():
                """Apply color and push it on color stack
                """
                stack.append(color_csi(fg, bg, attrs))
                write(color_reset_csi())
                write(stack[-1])

            def exit():
                """Restore color previously stored on color stack
                """
                write(color_reset_csi())
                if not stack:
                    return
                stack.pop()
                if stack:
                    write(stack[-1])

            return ConsoleScope(enter, exit)
        write = console.stream.write
        stack = []
        self.color = color

    def __call__(self, fg=None, bg=None, attrs=None, name=None):
        """Returns scope which sets specified colors
        """
        color = self.color(fg, bg, attrs)
        if name is not None:
            self.colors[name] = color
        return color

    def __getattr__(self, color):
        """Get named color
        """
        try:
            return self.colors[color]
        except KeyError:
            raise AttributeError()

    def __getitem__(self, color):
        """Get named color
        """
        return self.colors[color]


class ConsoleScope(object):
    __slots__ = ('enter', 'exit',)

    def __init__(self, enter=None, exit=None):
        self.enter = enter
        self.exit = exit

    def __call__(self, func):
        """Use scope as decorator
        """
        @functools.wraps(func)
        def scoped_func(*args, **kwargs):
            with self:
                return func(*args, **kwargs)
        return scoped_func

    def __enter__(self):
        if self.enter is not None:
            self.enter()
        return self

    def __exit__(self, et, eo, tb):
        if self.exit is not None:
            self.exit()
        return False


## ANSI Escape Codes
CSI = b'\x1b['  # Control Sequence Introducer
COLOR_HTML_RE = re.compile(r'#([a-f0-9]{2})([a-f0-9]{2})([a-f0-9]{2})')
COLOR_VECTOR_RE = re.compile(r'([a-z]+)\(([^,]+),\s?([^,]+),\s?([^,]+)\)')
COLOR_BY_NAME = {
    'black':   0,
    'red':     1,
    'green':   2,
    'yellow':  3,
    'brown':   3,
    'blue':    4,
    'magenta': 5,
    'cyan':    6,
    'white':   7,
    'default': 8,
}
ATTR_BY_NAME = {
    'bold':      b'01',
    'italic':    b'03',
    'underline': b'04',
    'blink':     b'05',
    'negative':  b'07',
}


def cached_csi(func):
    """Cached CSI function
    """
    @functools.wraps(func)
    def cached_csi_func(*args):
        code = cached_func(*args)
        return CSI + code if code else b''
    cached_func = cached(func)
    return cached_csi_func


@cached_csi
def move_up_csi(count):
    """Move cursor up
    """
    assert isinstance(count, int)
    if count == 0:
        return
    elif count > 0:
        return '{}A'.format(count).encode()
    else:
        return '{}B'.format(-count).encode()


def move_down_csi(count):
    """Move cursor down
    """
    return move_up_csi(-count)


@cached_csi
def move_column_csi(column):
    """Move cursor to specified column
    """
    assert isinstance(column, int)
    if column == 0:
        return b'G'
    elif column > 0:
        return '{}G'.format(column).encode()
    else:
        raise ValueError('column must be positive: {}'.format(column))


@cached_csi
def delete_csi(count):
    """Delete count lines
    """
    assert isinstance(count, int)
    if count == 0:
        return
    elif count > 0:
        return '{}M'.format(count).encode()
    else:
        raise ValueError('delete count must be positive: {}'.format(count))


@cached_csi
def insert_csi(count):
    """Insert count lines
    """
    assert isinstance(count, int)
    if count == 0:
        return
    elif count > 0:
        return '{}L'.format(count).encode()
    raise ValueError('insert count must be positive: {}'.format(count))


@cached_csi
def erase_csi():
    """Erase current line
    """
    return b'2K'


@cached_csi
def save_csi():
    """Save state
    """
    return b's'


@cached_csi
def restore_csi():
    """Restore state
    """
    return b'u'


@cached_csi
def scroll_up_csi(count):
    """Scroll up count lines
    """
    assert isinstance(count, int)
    if count == 0:
        return
    elif count > 0:
        return '{}S'.format(count).encode()
    else:
        return '{}T'.format(-count).encode()


def scroll_down_csi(count):
    """Scroll down count lines
    """
    return scroll_up_csi(-count)


@cached_csi
def visibility_csi(visible):
    """Set currsor visibility
    """
    if visible:
        return b'?25h'
    else:
        return b'?25l'


def color_csi(fg=None, bg=None, attrs=None):
    """Set color

    Returns color CSI for specified foreground, background and attributes.
    """
    csi = []
    if attrs:
        csi.append(CSI)
        for index, attr in enumerate(attrs):
            attr_code = ATTR_BY_NAME.get(attr)
            if attr_code is None:
                raise ValueError('unknown attribute: {}'.format(attr))
            if index != 0:
                csi.append(b';')
            csi.append(attr_code)
        csi.append(b'm')
    if fg:
        csi.extend((CSI, b'3', _color_parser_csi(fg)))
    if bg:
        csi.extend((CSI, b'4', _color_parser_csi(bg)))
    return b''.join(csi)


@cached
def _color_parser_csi(color):
    """Parse color

    Returns CSI suffix for specified color.
    """
    index = color_str_to_idx(color)
    if index < 8:
        return '{}m'.format(index).encode()
    else:
        return '8;5;{}m'.format(index).encode()


@cached_csi
def color_reset_csi():
    """Reset color settings
    """
    return b'm'


@call
def color_rgb_to_idx():
    def rgb_to_col(r, g, b):
        """Convert rgb color to color index
        """
        if(not (0 <= r <= 1) or
           not (0 <= g <= 1) or
           not (0 <= b <= 1)):
            raise ValueError('color out of range rgb{}'.format((r, g, b)))
        ri = color_idx[bisect(color_val, r)]
        gi = color_idx[bisect(color_val, g)]
        bi = color_idx[bisect(color_val, b)]
        if ri == gi == bi:
            return grey_idx[bisect(grey_val, math.sqrt((r*r + g*g + b*b)/3))]
        else:
            return 16 + ri * 36 + gi * 6 + bi
    color_val = tuple(i / 6 for i in range(1, 6))
    color_idx = tuple(range(6))
    grey_val = tuple(i / 24 for i in range(1, 24))
    grey_idx = tuple(range(232, 232 + 24))
    return rgb_to_col


@call
def color_idx_to_rgb():
    def idx_to_rgb(col):
        """Convert color index to rgb
        """
        if not (0 <= col <= 255):
            raise ValueError('invalid color index: {}'.format(col))
        elif col > 231:
            val = (col - 232) / 23
            return (val, val, val)
        elif col > 15:
            r, col = divmod(col - 16, 36)
            g, b = divmod(col, 6)
            return (r / 5, g / 5, b / 5)
        else:
            return ansi_col[col]
    ansi_col = ((0, 0, 0), (0.5, 0, 0), (0, 0.5, 0), (0, 0, 0.5), (0.5, 0.5, 0),
                (0.5, 0, 0.5), (0, 0.5, 0.5), (0.75, 0.75, 0.75), (0.5, 0.5, 0.5),
                (1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (1, 0, 1), (0, 1, 1),
                (1, 1, 1))
    return idx_to_rgb


def color_str_to_idx(color):
    """Convert color string representation to color index
    """
    try:
        index = color if isinstance(color, int) else int(color)
        if 0 <= index <= 255:
            return index
    except ValueError:
        pass

    color = color.lower()
    match = COLOR_HTML_RE.match(color)
    if match:
        r, g, b = (int(val, 16) for val in match.groups())
        return color_rgb_to_idx(r / 255, g / 255, b / 255)

    match = COLOR_VECTOR_RE.match(color)
    if match:
        space = match.groups()[0]
        vals = (float(val) for val in match.groups()[1:])
        if space == 'rgb':
            return color_rgb_to_idx(*vals)
        elif space == 'hsv':
            return color_rgb_to_idx(*colorsys.hsv_to_rgb(*vals))

    match = COLOR_BY_NAME.get(color)
    if match:
        return match

    raise ValueError('bad color: {}'.format(color))


def main():
    """Show colored squares according to passed arguments
    """
    import os
    colors = sys.argv[1:]
    if not colors:
        sys.stderr.write('usage: {} <color> [... <color>]\n'
                         .format(os.path.basename(sys.argv[0])))
        sys.exit(1)

    with Console(io.open(sys.stdout.fileno(), 'wb', closefd=False)) as console:
        for color in colors:
            index = color_str_to_idx(color)
            r, g, b = color_idx_to_rgb(index)
            console.write(b'  ', console.color(bg=color))
            console.write(' {:>03}'.format(index).encode())
            console.write(' #{:>02x}{:>02x}{:>02x}'.format(
                          *(int(v * 255) for v in (r, g, b))).encode())
            console.write(' hsv({:.3f}, {:.3f}, {:.3f})'.format(
                          *colorsys.rgb_to_hsv(r, g, b)).encode())
            console.write(b'\n')

if __name__ == '__main__':
    main()
