"""Continuation monad implementation
"""
from .do import do
from .do_green import do_green
from .monad import Monad
from .result import Result
from functools import wraps

__all__ = ('Cont', 'Future', 'callcc', 'async', 'async_green', 'async_block',
           'async_any', 'async_all',)


class Cont(Monad):
    """Continuation monad

    Haskell style continuation monad ContT {run :: (a -> r) -> r}.
    """
    __slots__ = ('run',)

    def __init__(self, run):
        self.run = run

    def __call__(self, ret=lambda val: isinstance(val, Result) and val.trace()):
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
        return 'Cont({})'.format(self.run)

    __repr__ = __str__


def callcc(func):
    """Call with current continuation

    callcc :: ((a -> Cont r b) -> Cont r a) -> Cont r a
    """
    return Cont(lambda ret: func(lambda val: Cont(
                                 lambda _: ret(val))).__monad__().run(ret))


def async(block):
    """Better "do" block for continuation monad

    It is also possible to run returned continuation multiple times, which
    is not possible with "do" block.
    """
    do_block = do(Cont)(block)
    return wraps(block)(lambda *a, **kw: Cont(
                        lambda ret: do_block(*a, **kw).run(ret)))


def async_green(block):
    """Better "do_green" block for continuation monad

    It is also possible to run returned continuation multiple times, which
    is not possible with "do_green" block.
    """
    do_block = do_green(Cont)(block)
    return wraps(block)(lambda *a, **kw: Cont(
                        lambda ret: do_block(*a, **kw).run(ret)))


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


def async_any(conts):
    """Any continuation

    Resolved with the result of first continuation to be resolved.
    """
    conts = tuple(cont.__monad__() for cont in conts)
    if not conts:
        raise ValueError('continuation set is empty')

    @async_block
    def any_cont(ret):
        def any_ret(val):
            if not done[0]:
                done[0] = True
                ret(val)
        done = [False]
        for cont in conts:
            cont(any_ret)
    return any_cont


def async_all(conts):
    """All continuation

    Resolved with the list of results of all continuations.
    """
    conts = tuple(cont.__monad__() for cont in conts)
    if not conts:
        raise ValueError('continuation set is empty')

    @async_block
    def all_cont(ret):
        def all_ret(index, cont):
            def all_ret(val):
                if isinstance(val, Result):
                    res[index] = val
                else:
                    res[index] = Result.from_value(val)
                count[0] -= 1
                if not count[0]:
                    ret(Result.sequence(res))
            cont(all_ret)
        res = [None] * len(conts)
        count = [len(conts)]
        for index, cont in enumerate(conts):
            all_ret(index, cont)
    return all_cont


class Future(object):
    """Future object containing future result of computation
    """
    __slots__ = ('result', 'handlers',)

    def __init__(self, cont):
        self.result = None
        self.handlers = []

        def ret(res):
            self.result = res
            handlers, self.handlers = self.handlers, None
            for ret in handlers:
                ret(res)
        cont.__monad__()(ret)

    def __call__(self, ret):
        return (ret(self.result) if self.handlers is None else
                self.handlers.append(ret))

    def __monad__(self):
        return Cont(self)

    def __or__(self, cont):
        return self.__monad__() | cont

    def __and__(self, cont):
        return self.__monad__() & cont

    @property
    def completed(self):
        return self.handlers is None

    def __bool__(self):
        return self.handlers is None
    __nonzero__ = __bool__

    def __str__(self):
        return ('{}(done:{}, value:{})'.format(type(self).__name__,
                self.completed, self.result))

    def __repr__(self):
        return str(self)
