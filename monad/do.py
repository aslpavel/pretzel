"""Create Haskell style do blocks from generator function
"""
import inspect
from functools import wraps
from .result import Result

__all__ = ('do', 'do_return', 'do_done',)


def do(Monad):
    """Do block

    Create Haskell style do blocks from generator function. One obvious
    limitation of this implementation it cannot be used with monad which call
    bound function multiple times inside bind implementation (e.g. List monad).
    """
    unit = Monad.unit
    error = lambda: unit(Result.from_current_error())
    value = lambda val: unit(Result.from_value(val))

    def do(block):
        if not inspect.isgeneratorfunction(block):
            @wraps(block)
            def do_block(*args, **kwargs):
                try:
                    return value(block(*args, **kwargs))
                except _return as ret:
                    return value(ret.args[1]) if ret.args[0] == 0 else ret.args[1]
                except Exception:
                    return error()
        else:
            @wraps(block)
            def do_block(*args, **kwargs):
                def do_next(do_world, result):
                    if do_world != gen_world[0]:
                        raise ValueError("Same generator based continuation called twice")
                    val, err = (result.pair if isinstance(result, Result) else
                               (result, None))
                    try:
                        gen_world[0] += 1
                        monad = (gen.send(val) if err is None else
                                 gen.throw(*err)).__monad__()
                        return monad.bind(lambda r: do_next(do_world + 1, r))
                    except _return as ret:
                        gen.close()
                        return value(ret.args[1]) if ret.args[0] == 0 else ret.args[1]
                    except StopIteration as ret:
                        gen.close()
                        return value(ret.args[0] if ret.args else None)
                    except Exception:
                        return error()

                try:
                    gen = block(*args, **kwargs)
                    gen_world = [0]
                    return do_next(0, Result.from_value(None))
                except Exception:
                    return error()
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
