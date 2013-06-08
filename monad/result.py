"""Result monad (Haskell's Either monad)
"""
import os
import sys
import pdb
import socket
import textwrap
import traceback
import linecache
from .monad import Monad
from ..common import reraise, StringIO, PY2

__all__ = ('Result', 'result_excepthook', 'callsite_banner',)


class Result(Monad):
    """Result monad (Haskell's Either monad)
    """
    __slots__ = ('pair',)

    def __init__(self, pair):
        self.pair = pair

    @classmethod
    def from_value(cls, val):
        """From value factory
        """
        return cls.unit(val)

    @classmethod
    def from_error(cls, error):
        """From error factory
        """
        return cls((None, error))

    @classmethod
    def from_current_error(cls):
        """From current error factory
        """
        return cls((None, sys.exc_info()))

    @classmethod
    def from_exception(cls, exc):
        """From exception
        """
        try:
            raise exc
        except Exception:
            return cls.from_current_error()

    @property
    def error(self):
        return self.pair[1]

    @property
    def value(self):
        if self.pair[1] is None:
            return self.pair[0]
        else:
            reraise(*self.pair[1])

    def trace(self, debug=None, file=None, banner=None):
        """Show traceback

        Arguments:
            debug: weather start debugger on error or not
            file: output file object
            banner: callable object or None, if callable returns banner string
        """
        if self.pair[1] is not None:
            result_excepthook(*self.pair[1], file=file, banner=banner)
            if debug:
                pdb.post_mortem(self.pair[1][2])
        return self

    @classmethod
    def unit(cls, val):
        return cls((val, None))

    def bind(self, func):
        result, error = self.pair
        if error is None:
            try:
                return func(result)
            except Exception:
                return Result.from_current_error()
        else:
            return self

    def __eq__(self, other):
        if not isinstance(other, Result):
            return False
        if self.pair[1] is None:
            return self.pair == other.pair
        elif other.pair[1] is None:
            return False
        else:
            # compare only exception values in case of exception
            return self.pair[1][1] == other.pair[1][1]

    def __hash__(self):
        return hash(self.pair[0] if self.pair[1] is None else self.pair[1][1])

    def __reduce__(self):
        val, err = self.pair
        if err is None:
            return _from_value, (val,)
        else:
            tb = (self.tb_fmt.format(name=err[0].__name__, message=str(err[1]),
                                     tb=''.join(traceback.format_exception(*err))))
            tb += getattr(err[1], '_saved_traceback', '')
            exc = err[1]
            exc._saved_traceback = tb
            return _from_exc, (exc,)

    tb_fmt = textwrap.dedent("""\
        `-------------------------------------------------------------------------------
        Location : {host}/{pid}
        Error    : {{name}}: {{message}}

        {{tb}}""".format(host=socket.gethostname(), pid=os.getpid()))

    def __str__(self):
        return ('Result({})'.format(
                'val:{}'.format(self.pair[0]) if self.pair[1] is None else
                'err:{}'.format(repr(self.pair[1][1]))))

    def __repr__(self):
        return str(self)


def _from_value(val):
    return Result.from_value(val)


def _from_exc(exc):
    return Result.from_exception(exc)


def result_excepthook(et, eo, tb, file=None, banner=None):
    """Result specific exception hook

    Correctly shows embedded traceback if any.

    Arguments:
        file: output file object
        banner: callable object or None, if callable returns banner string
    """
    stream = file or StringIO()
    if banner:
        stream.write(banner())
        stream.write('\n')

    tb = ''.join(traceback.format_exception(et, eo, tb))
    stream.write(tb.encode('utf-8') if PY2 else tb)

    tb_saved = getattr(eo, '_saved_traceback', None)
    if tb_saved is not None:
        stream.write(tb_saved)

    if file is None:
        sys.stderr.write(stream.getvalue())
        sys.stderr.flush()

# install result exception hook
sys.excepthook = result_excepthook


def callsite_banner(msg=None, depth=2):
    """Call site banner

    Returns banner function from current call site
    """
    frame = sys._getframe(depth)
    code = frame.f_code
    lineno = frame.f_lineno
    globals = frame.f_globals
    del frame

    def banner():
        filename = code.co_filename
        line = linecache.getline(filename, lineno, globals)
        if line:
            line = '\n    {}'.format(line.strip())
        return textwrap.dedent("""\
            {msg}
              File "{filename}", line {lineno}, in {name}{line}
            """).format(msg=msg or 'Error caused by call:',
                        filename=filename,
                        lineno=lineno,
                        name=code.co_name,
                        line=line)
    return banner
