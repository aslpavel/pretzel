import functools
from .core import Core
from .monad import do_return, async, async_any, async_all, async_block

__all__ = ('app', 'do_return', 'async', 'async_any', 'async_all', 'async_block',)


def app(main):
    """Application decorator

    Create asynchronous application with provide main function.
    """
    @functools.wraps(main)
    def app_main(*a, **kw):
        with Core.local() as core:
            app_future = async(main)(*a, **kw).future()
            app_future(lambda _: core.dispose())
            if not core.disposed:
                core()
        assert app_future.completed
        app_future.result.value  # raises error if test function has failed
    return app_main
