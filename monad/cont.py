"""Continuation monad implementation
"""
import types
from .monad import Monad
from .result import Result, callsite_banner

__all__ = ('Cont', 'Future', 'callcc',)


class Cont(Monad):
    """Continuation monad

    Haskell style continuation monad ContT {run :: (a -> r) -> r}.
    """
    __slots__ = ('run',)

    def __init__(self, run):
        self.run = run

    def __call__(self, ret=None):
        if ret is None:
            banner = callsite_banner('Error in coroutine started from:')
            return self.run(lambda val: isinstance(val, Result) and val.trace(banner=banner))
        else:
            return self.run(ret)

    def __or__(self, other):
        def run(ret):
            def done_ret(val):
                if not done[0]:
                    done[0] = True
                    ret(val)
            done = [False]
            self.run(done_ret)
            other.__monad__().run(done_ret)
        return Cont(run)

    def __monad__(self):
        return self

    @staticmethod
    def unit(val):
        return Cont(lambda ret: ret(val))

    def bind(self, func):
        return Cont(lambda ret: self.run(
                    lambda val: func(val).__monad__().run(ret)))

    def future(self):
        return Future(self)

    def __str__(self):
        return ('Cont(run:{})'.format(
                getattr(self.run, '__qualname__', self.run.__name__)
                if isinstance(self.run, types.FunctionType) else self.run))

    def __repr__(self):
        return str(self)


def callcc(func):
    """Call with current continuation

    callcc :: ((a -> Cont r b) -> Cont r a) -> Cont r a
    """
    return Cont(lambda ret: func(lambda val: Cont(
                                 lambda _: ret(val))).__monad__().run(ret))


class Future(object):
    """Future object containing future result of computation
    """
    __slots__ = ('res', 'rets',)

    def __init__(self, cont):
        self.res = None
        self.rets = []

        def ret(res):
            self.res = res
            rets, self.rets = self.rets, None
            assert rets is not None, 'continuation has been called twice'
            for ret in rets:
                ret(res)
        cont.__monad__()(ret)

    @property
    def value(self):
        if self.rets is None:
            return self.res.value if isinstance(self.res, Result) else self.res
        else:
            return Cont(self).value

    def __call__(self, ret):
        return ret(self.res) if self.rets is None else self.rets.append(ret)

    def __monad__(self):
        return Cont(self)

    def __or__(self, cont):
        return self.__monad__() | cont

    def __and__(self, cont):
        return self.__monad__() & cont

    @property
    def completed(self):
        return self.rets is None

    def __bool__(self):
        return self.rets is None

    __nonzero__ = __bool__

    def __str__(self):
        return ('Future(done:{}, value:{})'.format(self.completed, self.res))

    def __repr__(self):
        return str(self)
