# -*- coding: utf-8 -*-
from .do import do
from .monad import Monad
from .result import Result
from functools import wraps

__all__ = ('Cont', 'callcc', 'async', 'async_block')


class Cont(Monad):
    """Continuation monad

    Haskell style continuation monad ContT {run :: (a -> r) -> r}.
    """
    __slots__ = ('run',)

    def __init__(self, run):
        self.run = run

    def __call__(self, ret=lambda val: val):
        return self.run(ret)

    def __monad__(self):
        return self

    @staticmethod
    def unit(val):
        return Cont(lambda ret: ret(val))

    def bind(self, func):
        return Cont(lambda ret: self.run(lambda val: func(val).__monad__().run(ret)))


def callcc(func):
    """Call with current continuation

    callcc :: ((a -> Cont r b) -> Cont r a) -> Cont r a
    """
    return Cont(lambda ret: func(lambda val: Cont(lambda _: ret(val))).__monad__.run(ret))


def async(block):
    """Better "do" block for continuation monad

    It is also possible to run returned continuation multiple times, which
    is not possible with "do" block.
    """
    do_block = do(Cont)(block)
    return wraps(block)(lambda *a, **kw: Cont(lambda ret: do_block(*a, **kw).run(ret)))


def async_block(block):
    """Create continuation from block

    Behaves similar to callcc but returned continuation is not resolved when
    block is left. And if block raises and error returned continuation will be
    resolved with result monad containing this error.
    """
    def async_block(ret):
        try:
            block(lambda val=None: ret(val if isinstance(val, Result) else
                                       Result.from_value(val)))
        except Exception:
            ret(Result.from_current_error())
    return Cont(async_block)

# vim: nu ft=python columns=120 :
