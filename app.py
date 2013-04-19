"""Asynchronous application trampoline decorator
"""
import functools
from .core import Core
from .monad import (async, async_green, async_any, async_all, async_block,
                    do_return, bind_green,)

__all__ = ('app', 'app_green', 'async', 'async_green', 'async_any', 'async_all',
           'async_block', 'do_return', 'bind_green',)


def app(main):
    """Application decorator

    Create main coroutine and initialize asynchronous context.
    """
    return app_with_opts(main, async)


def app_green(main):
    """Application decorator

    Create main coroutine and initialize asynchronous context.
    """
    return app_with_opts(main, async_green)


def app_with_opts(main, async, poller=None):
    """Application decorator

    Create main coroutine and initialize asynchronous context.
    """
    @functools.wraps(main)
    def app_main(*a, **kw):
        with Core.local(Core(poller)) as core:
            app_future = async(main)(*a, **kw).future()
            app_future(lambda _: core.dispose())
            if not core.disposed:
                core()
        assert app_future.completed
        return app_future.result.value
    return app_main
