"""Asynchronous application trampoline decorator
"""
import functools
from .core import Core
from .monad import do_return, async, async_any, async_all, async_block

__all__ = ('app', 'do_return', 'async', 'async_any', 'async_all', 'async_block',)


def app(main):
    """Application decorator

    Create main coroutine and initialize asynchronous context.
    """
    @functools.wraps(main)
    def app_main(*a, **kw):
        with Core.local(Core()) as core:
            app_future = async(main)(*a, **kw).future()
            app_future(lambda _: core.dispose())
            if not core.disposed:
                core()
        assert app_future.completed
        return app_future.result.value
    return app_main
