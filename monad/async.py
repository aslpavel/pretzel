"""Asynchronous utility functions

Function to work and create continuation monads with embedded value of
result monad type.
"""
from functools import wraps
from collections import deque
from .do import do
from .do_green import do_green
from .cont import Cont
from .result import Result

__all__ = ('async', 'async_green', 'async_block', 'async_any', 'async_all',
           'async_limit',)


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
        def async_ret(val=None):
            try:
                ret(val if isinstance(val, Result) else Result.from_value(val))
            except Exception:
                banner = lambda: 'Return function passed to async_block failed'
                Result.from_current_error().trace(banner=banner)
        try:
            block(async_ret)
        except Exception:
            async_ret(Result.from_current_error())
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


def async_limit(limit):
    """Limit number of simultaneously executing coroutines

    Returns decorator, which limit number of unresolved continuations to
    specified limit value.
    """
    def async_limit(func):
        worker_count = [0]
        worker_queue = deque()

        @async
        def worker():
            try:
                worker_count[0] += 1
                while worker_queue:
                    ret, args, kwargs = worker_queue.popleft()
                    try:
                        ret((yield func(*args, **kwargs)))
                    except Exception:
                        ret(Result.from_current_error())
            finally:
                worker_count[0] -= 1

        @wraps(func)
        def async_limit(*args, **kwargs):
            @async_block
            def cont(ret):
                worker_queue.append((ret, args, kwargs))
                if worker_count[0] < limit:
                    worker()()
            return cont

        return async_limit
    return async_limit
