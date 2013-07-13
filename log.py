import os
import sys
import time
import atexit
import functools
import itertools
from .event import Event
from .monad import Result
from .console import Console, move_column_csi
from .dispose import CompDisp

__all__ = ('log', 'LEVEL_DEBUG', 'LEVEL_INFO', 'LEVEL_WARNING', 'LEVEL_ERROR',)

LEVEL_DEBUG = 0
LEVEL_INFO = 1
LEVEL_WARNING = 2
LEVEL_ERROR = 3
LEVEL_TO_NAME = {
    LEVEL_DEBUG: 'debug',
    LEVEL_INFO: 'info',
    LEVEL_WARNING: 'warning',
    LEVEL_ERROR: 'error'
}
LOGGER_TO_TYPE = {
}


class Log(object):
    def __init__(self):
        self.event = Event()
        self.dispose = CompDisp()
        self.uid = itertools.count(1)

    def create(self, name, **kwargs):
        if name is None:
            name = 'console' if sys.stderr.isatty() else 'stream'
        kwargs['log'] = self
        LOGGER_TO_TYPE[name](**kwargs)

    def scope(self, message, source=None, level=None):
        if not self.event.handlers:
            self.create(None)
        return LogScope(self, next(self.uid), message, source,
                        LEVEL_INFO if level is None else level)

    def message(self, message, source=None, level=None):
        if not self.event.handlers:
            self.create(None)
        self.event(LogMessage(0, message, source,
                              LEVEL_INFO if level is None else level))

    def debug(self, message, source=None):
        self.message(message, source, LEVEL_DEBUG)

    def info(self, message, source=None):
        self.message(message, source, LEVEL_INFO)

    def warning(self, message, source=None):
        self.message(message, source, LEVEL_WARNING)

    def error(self, message, source=None):
        self.message(message, source, LEVEL_ERROR)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return 'Log(loggers:{})'.format(self.event.handlers)

    def __repr__(self):
        return str(self)

_log = log = Log()
atexit.register(lambda: log.dispose())


class LogMessage(object):
    __slots__ = ('uid', 'message', 'source', 'level', 'value')

    def __init__(self, uid, message, source, level, value=None):
        self.uid = uid
        self.message = message
        self.source = source
        self.level = level
        self.value = value

    def __str__(self):
        return ('LogMessage(uid:{}, msg:\'{}\', value:{}, source:{}, level:{})'
                .format(self.uid, self.message, self.value, self.source,
                        LEVEL_TO_NAME[self.level]))

    def __repr__(self):
        return str(self)


class LogScope(object):
    """Log scope

    Last message of the scope is identified by its uid, which will be negative.
    """
    __slots__ = ('log', 'uid', 'message', 'source', 'level',)

    def __init__(self, log, uid, message, source, level):
        self.log = log
        self.uid = uid
        self.level = level
        self.message = message
        self.source = source

    def __call__(self, func):
        @functools.wraps(func)
        def logged_func(*args, **kwargs):
            with self:
                return func(*args, **kwargs)
        return logged_func

    def report(self, value, message=None):
        if message is not None:
            self.message = message
        self.log.event(LogMessage(self.uid, self.message, self.source, self.level, value))

    def __enter__(self):
        self.report(None)
        return self.report

    def __exit__(self, et, eo, tb):
        self.log.event(LogMessage(-self.uid, self.message, self.source, self.level,
                                  Result.from_value(None) if et is None else
                                  Result.from_error((et, eo, tb))))
        return False

    def __str__(self):
        return ('LogScope(uid:{}, msg:\'{}\', source:{}, level:{})'
                .format(self.uid, self.message, self.source, LEVEL_TO_NAME[self.level]))

    def __repr__(self):
        return str(self)


class Logger(object):
    def __init__(self, log=None, level=None):
        self.level = LEVEL_INFO if level is None else level
        self.log = log or _log
        self.log.event.on(self)
        self.log.dispose.add(self)

    def __call__(self, message):
        raise NotImplementedError()

    def dispose(self):
        self.log.event.off(self)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return '{}(level:{})'.format(type(self).__name__, LEVEL_TO_NAME[self.level])

    def __repr__(self):
        return str(self)


class StreamLogger(Logger):
    """Stream logger

    Plain text logger compatible with any stream.
    """
    def __init__(self, log=None, level=None, stream=None):
        self.stream = stream or sys.stderr
        self.scopes = {}
        Logger.__init__(self, log, level)

    def __call__(self, message):
        """Process log message
        """
        if message.level < self.level:
            return True

        if message.uid == 0:
            self.draw_message(message, LEVEL_TO_NAME[message.level][:4])
        else:
            if message.uid > 0:
                if message.uid in self.scopes:
                    # report only first message for scope
                    return True
                self.scopes[message.uid] = time.time()
                self.draw_message(message, 'wait')
            else:
                start_time = self.scopes.pop(-message.uid)
                value = message.value
                if value.pair == (None, None):
                    self.draw_message(message, 'done')
                    self.stream.write(' (in {})'.format(
                                      elapsed_fmt(time.time() - start_time)))
                else:
                    self.draw_message(message, 'fail')
                    error_name = value.pair[1][0].__name__
                    error_args = ', '.join(repr(arg) for arg in value.pair[1][1].args)
                    error_msg = (' (error {}({}) in {})'.format(
                                 error_name, error_args,
                                 elapsed_fmt(time.time() - start_time)))
                    self.stream.write(error_msg)
        self.stream.write('\n')
        self.stream.flush()
        return True

    def draw_message(self, message, tag):
        source = '[{}]'.format(message.source) if message.source else ''
        self.stream.write('[{} {}]{} {}'.format(tag, elapsed_fmt(),
                                                source, message.message))

    def __str__(self):
        level = LEVEL_TO_NAME[self.level]
        stream = getattr(self.stream, 'name', self.stream)
        return '{}(level:{}, stream:{})'.format(type(self).__name__, level, stream)

LOGGER_TO_TYPE['stream'] = StreamLogger


class ConsoleLogger(Logger):
    """Console logger

    Multicolor console logger with fancy progress bars.
    """
    default_bar_with = 20
    default_scheme = {
        'debug':     {'fg': 'hsv(0.6,  0.7,  0.8)'},
        'info':      {'fg': 'hsv(0.35, 0.9,  0.6)'},
        'warning':   {'fg': 'hsv(0.1,  0.89, 0.8)'},
        'error':     {'fg': 'hsv(1.0,  0.7,  0.8)'},
        'source':    {'fg': 'hsv(0.6,  0.7,  0.9)'},
        'wait':      {'fg': 'hsv(0.66, 0.45, 0.6)'},
        'wait_dark': {'fg': 'hsv(0.66, 0.45, 0.4)'},
        'done':      {'fg': 'hsv(0.35, 0.9,  0.6)'},
        'fail':      {'fg': 'hsv(1.0,  0.7,  0.8)'},
    }
    default_simple_terms = [
        'linux',
        'rxvt',
    ]
    default_simple_scheme = {
        'debug':     {'fg': 'blue'},
        'info':      {'fg': 'green'},
        'warning':   {'fg': 'yellow'},
        'error':     {'fg': 'red'},
        'source':    {'fg': 'blue'},
        'wait':      {'fg': 'magenta', 'attrs': ('bold',)},
        'wait_dark': {'fg': 'magenta'},
        'done':      {'fg': 'green'},
        'fail':      {'fg': 'red'},
    }

    def __init__(self, log=None, level=None, stream=None, scheme=None,
                 bar_width=None):
        self.console = Console(stream)
        self.scopes = {}
        self.bar_width = bar_width or self.default_bar_with

        # load scheme
        if os.environ.get('TERM') in self.default_simple_terms:
            default_scheme = self.default_simple_scheme
        else:
            default_scheme = self.default_scheme
        for name, color in default_scheme.items():
            self.console.color(name=name, **color)
        if scheme:
            for name, color in scheme.items():
                self.console.color(name=name, **color)

        Logger.__init__(self, log, level)

    def __call__(self, message):
        """Process log message
        """
        if message.level < self.level:
            return True

        if message.uid == 0:
            # plain log message
            with self.console.line():
                self.draw_message(message, LEVEL_TO_NAME[message.level])
        else:
            # scope log message
            label, start_time = self.scopes.get(abs(message.uid), (None, None))
            if label is None:
                label, start_time = self.console.label(), time.time()
                self.scopes[message.uid] = label, start_time

            value = message.value
            if message.uid < 0:
                # last message for this scope
                self.scopes.pop(-message.uid)
                label.dispose()

                if value.pair[1] is None:
                    with self.console.line():
                        done_msg = '[{}]'.format(elapsed_fmt(time.time() - start_time))
                        self.draw_message(message, 'done')
                        self.draw_from_left(len(done_msg))
                        self.console.write(done_msg.encode())
                else:
                    with self.console.line():
                        # error message
                        error = value.pair[1][1]
                        error_name = type(error).__name__
                        error_args = ', '.join(repr(arg) for arg in error.args)
                        error_msg = '[{}({}) {}]'.format(error_name, error_args,
                                                         elapsed_fmt(time.time() - start_time))

                        self.draw_message(message, 'fail')
                        self.draw_from_left(len(error_msg))
                        self.console.write(error_msg.encode())
            else:
                if value is None:
                    # progress is not reported
                    with label.update(erase=True):
                        self.draw_message(message, 'wait')
                else:
                    # progress is reported
                    assert 0 <= value <= 1
                    with label.update(erase=True):
                        time_left = (None if value == 0 else
                                    (time.time() - start_time) * (1 / value - 1))
                        self.draw_message(message, 'wait', time_left)
                        self.draw_from_left(self.bar_width)
                        self.draw_bar(value)
        return True

    def draw_from_left(self, size):
        """Move drawing cursor to size symbols from left
        """
        self.console.write(move_column_csi(max(self.console.size[1] - size, 0)))

    def draw_message(self, message, tag, time=None):
        """Draw message with tag and time
        """
        write = self.console.write
        color = self.console.color
        write(b'[')
        write('{}'.format(tag[:4]).encode(), color[tag])
        write(' {}'.format(elapsed_fmt(time)).encode())
        write(b']')
        if message.source:
            write('[{}]'.format(message.source).encode(), color.source)
        write(' {}'.format(message.message).encode())

    def draw_bar(self, value):
        """Draw progress bar

        Value is a float value representing progress, must be within [0..1].
        """
        write = self.console.write
        color = self.console.color
        with color.wait_dark:
            write(b'[')
            filled = int(round(value * (self.bar_width - 2)))
            write(b'#' * filled, color.wait)
            write(b'-' * (self.bar_width - filled - 2))
            write(b']')

    def dispose(self):
        self.console.dispose()
        Logger.dispose(self)

    def __str__(self):
        return '{}(level:{}, console:{})'.format(type(self).__name__,
                                                 LEVEL_TO_NAME[self.level],
                                                 self.console)

LOGGER_TO_TYPE['console'] = ConsoleLogger


def elapsed(seconds=None):
    """Time elapsed from start of the program
    """
    seconds = time.time() - LOGGER_START_TIME if seconds is None else seconds
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return hours, minutes, seconds


def elapsed_fmt(seconds=None, fmt='{:0>2.0f}:{:0>2.0f}:{:0>4.1f}'):
    return fmt.format(*elapsed(seconds))

LOGGER_START_TIME = time.time()
