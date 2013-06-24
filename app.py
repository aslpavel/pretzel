"""Asynchronous application trampoline decorator
"""
from functools import wraps
from .core import Core
from .monad import async, async_green

__all__ = ('app', 'app_green', 'app_run',)


def app(main):
    """Application decorator

    Create application from generator function.
    """
    return wraps(main)(lambda *a, **kw: app_run(async(main)(*a, **kw)))


def app_green(main):
    """Application decorator

    Create application from greenlet main function.
    """
    return wraps(main)(lambda *a, **kw: app_run(async_green(main)(*a, **kw)))


def app_run(cont):
    """Application trampoline

    Run continuation as application.
    """
    with Core.local(Core()) as core:
        app_future = cont.__monad__().future()
        app_future(lambda _: core.dispose())
        if not core.disposed:
            core()
    assert app_future.completed
    return app_future.value
