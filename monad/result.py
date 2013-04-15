"""Result monad (Haskell's Either monad)
"""
import os
import sys
import pdb
import socket
import traceback
from .monad import Monad
from ..common import reraise, string_type, PY2

__all__ = ('Result', 'result_excepthook',)


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

    def trace(self, debug=False, file=None):
        """Show traceback

        Show traceback if any and optionally interrupt for debugging.
        """
        if self.pair[1] is None:
            return self
        traceback.print_exception(*self.pair[1])
        if debug:
            pdb.post_mortem(self.pair[1][2])

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
        value, error = self.pair
        if error is None:
            return _from_value, (value,)
        else:
            tb = (tb_fmt.format(name=error[0].__name__, message=str(error[1]),
                                tb=''.join(traceback.format_exception(*error))))
            tb += getattr(error[1], '_saved_traceback', '')
            exc = error[1]
            exc._saved_traceback = tb
            return _from_exc, (exc,)

    def __str__(self):
        val = ('val:{}'.format(self.pair[0]) if self.pair[1] is None else
               'err:{}'.format(repr(self.pair[1][1])))
        return '<{}[{}]>'.format(type(self).__name__, val)
    __repr__ = __str__

tb_fmt = """
`-------------------------------------------------------------------------------
Location : {host}/{pid}
Error    : {{name}}: {{message}}

{{tb}}""".format(host=socket.gethostname(), pid=os.getpid())


def result_excepthook(et, eo, tb, file=None):
    """Result specific exception hook

    Correctly shows embedded traceback if any.
    """
    stream = file or string_type()

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


def _from_value(val):
    return Result.from_value(val)


def _from_exc(exc):
    return Result.from_exception(exc)
