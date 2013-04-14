"""Result monad (Haskell's Either monad)
"""
import sys
import pdb
import traceback
from .monad import Monad
from ..common import reraise

__all__ = ('Result',)


class Result(Monad):
    """Result monad (Haskell's Either monad)
    """
    __slots__ = ('pair',)

    def __init__(self, pair):
        self.pair = pair

    @classmethod
    def from_value(cls, result):
        """From value factory
        """
        return cls.unit(result)

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

    def __str__(self):
        val = ('val:{}'.format(self.pair[0]) if self.pair[1] is None else
               'err:{}'.format(repr(self.pair[1][1])))
        return '<{}[{}]>'.format(type(self).__name__, val)
    __repr__ = __str__
