# -*- coding: utf-8 -*-
import inspect
from functools import wraps
from .result import Result

__all__ = ('do', 'do_return', 'do_done',)


def do(Monad):
    """Do block

    Create Haskell style do blocks from generator function. One obvious limitation
    of this implementation it cannot be used with monad which call bound function
    multiple times inside bind implementation (List monad for example). And it
    also requires that embedded value be Result.
    """
    error = lambda: Monad.unit(Result.from_current_error())
    value = lambda val: Monad.unit(Result.from_value(val))

    def do(block):
        if not inspect.isgeneratorfunction(block):
            @wraps(block)
            def do_block(*args, **kw):
                try:
                    return value(block(*args, **kw))

                except _return as ret:
                    return value(ret.args[1]) if ret.args[0] == 0 else ret.args[1]
                except Exception:
                    return error()
        else:
            @wraps(block)
            def do_block(*args, **kw):
                def do_next(result):
                    val, err = result.pair if isinstance(result, Result) else (result, None)
                    try:
                        monad = (gen.send(val) if err is None else gen.throw(*err)).__monad__()
                        return Monad.bind(monad, do_next)

                    except _return as ret:
                        return value(ret.args[1]) if ret.args[0] == 0 else ret.args[1]
                    except StopIteration as ret:
                        return value(ret.args[0] if ret.args else None)
                    except Exception:
                        return error()

                gen = block(*args, **kw)
                return do_next(Result.from_value(None))
        return do_block
    return do


def do_return(value):
    """Return value from do block
    """
    raise _return(0, value)


def do_done(monad):
    """Return monad from do block
    """
    raise _return(1, monad)


class _return(BaseException):
    """Helper exception used to return from do block

    Use separate result class instead of StopIteration because otherwise it will
    be handled in standard exception closure.
    """

# vim: nu ft=python columns=120 :
