"""Console utility functions
"""
import io
import re
import sys
import math
import fcntl
import struct
import termios
import colorsys
import functools

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
        self.labels_stack = []
        self.color_stack = []
        self.flag_stack = []

        # Create color scoping function here for two reasons, first caching
        # must be applied on object level (not class level), second cached
        # decorator cannot handle optional arguments
        @cached
        def _color(fg, bg, attrs):
            color_push = lambda: self.color_push(fg, bg, attrs)
            return ConsoleScope(color_push, self.color_pop)
        self._color = _color

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

    def color(self, fg=None, bg=None, attrs=None):
        """Returns scope which sets specified colors
        """
        return self._color(fg, bg, attrs)

    def color_push(self, fg=None, bg=None, attrs=None):
        """Apply color and push it on color stack
        """
        self.color_stack.append(color_csi(fg, bg, attrs))
        self.stream.write(color_reset_csi())
        self.stream.write(self.color_stack[-1])

    def color_pop(self):
        """Restore color previously stored on color stack
        """
        self.stream.write(color_reset_csi())
        if self.color_stack:
            self.color_stack.pop()
            if self.color_stack:
                self.stream.write(self.color_stack[-1])

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
        labels, self.labels_stack = self.labels_stack, []
        for label in labels:
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


def cached(func):
    """Cached function
    """
    @functools.wraps(func)
    def cached_func(*args):
        val = cache.get(args, cache_tag)
        if val is cache_tag:
            val = func(*args)
            cache[args] = val
        return val
    cache = {}
    cache_tag = object()
    return cached_func


## ANSI Escape Codes
CSI = b'\x1b['  # Control Sequence Introducer
COLOR_HTML_RE = re.compile(r'#([a-f0-9]{2})([a-f0-9]{2})([a-f0-9]{2})')
COLOR_VECTOR_RE = re.compile(r'([a-z]+)\(([^,]+),\s?([^,]+),\s?([^,]+)\)')
COLOR_BY_NAME = {
    'black':   b'0',
    'red':     b'1',
    'green':   b'2',
    'yellow':  b'3',
    'brown':   b'3',
    'blue':    b'4',
    'magenta': b'5',
    'cyan':    b'6',
    'white':   b'7',
    'default': b'8',
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


@cached_csi
def color_reset_csi():
    """Reset color settings
    """
    return b'm'


@cached
def _color_parser_csi(color):
    """Parse color

    Returns CSI suffix for specified color.
    """
    def rgb_to_col(red, green, blue):
        if(not (0 <= red <= 1) or
           not (0 <= green <= 1) or
           not (0 <= blue <= 1)):
            raise ValueError('color out of range rgb{}'.format((red, green, blue)))
        red_index = math.floor(red * 5.99)
        green_index = math.floor(green * 5.99)
        blue_index = math.floor(blue * 5.99)
        if red_index == green_index == blue_index:
            return int(232 + math.floor(red * 23.99))
        else:
            return int(16 + 36 * red_index + 6 * green_index + blue_index)

    try:
        index = color if isinstance(color, int) else int(color)
        if 0 <= index <= 255:
            return '8;5;{}m'.format(index).encode()
    except ValueError:
        pass

    color = color.lower()
    match = COLOR_HTML_RE.match(color)
    if match:
        red, green, blue = (int(val, 16) for val in match.groups())
        return '8;5;{}m'.format(rgb_to_col(red / 256., green / 256., blue / 256.)).encode()

    match = COLOR_VECTOR_RE.match(color)
    if match:
        space = match.groups()[0]
        vals = (float(val) for val in match.groups()[1:])
        if space == 'rgb':
            col = rgb_to_col(*vals)
        elif space == 'hsv':
            col = rgb_to_col(*colorsys.hsv_to_rgb(*vals))
        return '8;5;{}m'.format(col).encode()

    match = COLOR_BY_NAME.get(color)
    if match:
        return match + b'm'

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

    with Console(io.open(sys.stderr.fileno(), 'wb', closefd=False)) as console:
        for color in colors:
            console.write(b'  ', console.color(bg=color))
        console.write(b'\n')

if __name__ == '__main__':
    main()
