"""Haskell style do blocks from greenlets
"""
from functools import wraps
from .result import Result
try:
    import greenlet
except ImportError:
    greenlet = None

__all__ = ('do_green', 'bind_green',)


if greenlet is None:
    def do_green(Monad):
        def do(block):
            @wraps(block)
            def do_block(*args, **kw):
                raise NotImplementedError('greenlet module was not found')
            return do_block
        return do

    def bind_green(monad):
        raise NotImplementedError('greenlet module was not found')

else:
    def do_green(Monad):
        """Greenlet based do block

        Create Haskell style do blocks from greenlet coroutine. One obvious
        limitation of this implementation it cannot be used with monad which call
        bound function multiple times inside bind implementation (e.g. List monad).
        """
        unit = Monad.unit

        def do(block):
            @wraps(block)
            def do_block(*args, **kw):
                def do_next(result):
                    coro.parent = greenlet.getcurrent()
                    val, err = (result.pair if isinstance(result, Result) else
                               (result, None))
                    try:
                        result = (coro.switch(val) if err is None else
                                  coro.throw(*err))
                        if coro.dead:
                            return unit(Result.from_value(result))
                        else:
                            return result.__monad__().bind(do_next)
                    except Exception:
                        return unit(Result.from_current_error())
                coro = _do_greenlet(lambda _: block(*args, **kw))
                return do_next(None)
            return do_block
        return do

    class _do_greenlet(greenlet.greenlet):
        """Do specific greenlet
        """

    def bind_green(monad):
        """Bind monad inside greenlet do block
        """
        curr = greenlet.getcurrent()
        if not isinstance(curr, _do_greenlet) or curr.parent is None:
            raise RuntimeError('bind outside of do_greenlet')
        return curr.parent.switch(monad)
