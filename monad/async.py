"""Asynchronous utility functions

Function to work and create continuation monads with embedded value of
result monad type.
"""
from functools import wraps
from collections import deque
from .do import do
from .do_green import do_green
from .cont import Cont
from .result import Result, callsite_banner
from ..event import Event

__all__ = ('async', 'async_green', 'async_block', 'async_any', 'async_all',
           'async_limit', 'async_single',)


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
        def block_ret(val=None):
            try:
                if block_done[0]:  # pragma: no cover
                    raise RuntimeError('return handler has been called twice')
                block_done[0] = True
                ret(val if isinstance(val, Result) else Result.from_value(val))
            except Exception:  # pragma: no cover
                Result.from_current_error().trace(banner=banner)
        try:
            block_done = [False]
            block(block_ret)
        except Exception:
            if block_done[0]:
                Result.from_current_error().trace(banner=banner)
            else:
                block_ret(Result.from_current_error())
    banner = callsite_banner('[async_block] return function failed')
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
        # Context structure: [completed?]
        ctx = [False]

        def cont_ret(val):
            if not ctx[0]:
                ctx[0] = True
                ret(val)

        for cont in conts:
            cont.run(cont_ret)
    return any_cont


def async_all(conts):
    """All continuation

    Resolved with the list of results of all continuations.
    """
    conts = tuple(cont.__monad__() for cont in conts)
    if not conts:
        return Cont.unit(Result.unit(tuple()))

    @async_block
    def all_cont(ret):
        # Context structure: [val_0 .. val_N, count]
        ctx = [None] * (len(conts) + 1)
        ctx[-1] = len(conts)

        def cont_register(index, cont):
            def cont_ret(val):
                ctx[index] = (val if isinstance(val, Result) else Result.from_value(val))
                ctx[-1] -= 1
                if not ctx[-1]:
                    ret(Result.sequence(ctx[:-1]))
            cont.run(cont_ret)

        for index, cont in enumerate(conts):
            cont_register(index, cont)
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
        def func_limit(*args, **kwargs):
            @async_block
            def cont(ret):
                worker_queue.append((ret, args, kwargs))
                if worker_count[0] < limit:
                    worker()()
            return cont

        return func_limit
    return async_limit


def async_single(func, *args, **kwargs):
    """Singleton asynchronous action

    If there is current non finished continuation, all calls would return this
    continuation, otherwise new continuation will be started.
    """
    @wraps(func)
    def func_single():
        @async_block
        def cont(ret):
            done.on_once(ret)
            if len(done.handlers) == 1:
                func(*args, **kwargs).__monad__()(done)
        return cont
    done = Event()
    return func_single
