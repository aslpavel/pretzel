"""Utility functions and types
"""
from functools import wraps

__all__ = ('lazy', 'cached', 'identity', 'call', 'curry',)


def lazy(func, *args, **kwargs):
    """Lazy value
    """
    @wraps(func)
    def lazy_func():
        if not val:
            val.append(func(*args, **kwargs))
        return val[0]
    val = []
    return lazy_func


def cached(func):
    """Cached function
    """
    @wraps(func)
    def cached_func(*args):
        val = cache.get(args, cache_tag)
        if val is cache_tag:
            val = func(*args)
            cache[args] = val
        return val
    cache = {}
    cache_tag = object()
    cached_func.cache = cache
    return cached_func


def identity(val):
    """Identity function
    """
    return val


def call(func, *args, **kwargs):
    """Call function
    """
    return func(*args, **kwargs)


def curry(arity):
    """Curried function decorator

    Returns decorator which creates carried function with specified arity.
    """
    def curry(func, func_arity, func_args):
        def curried(*args):
            if len(args) >= func_arity:
                return func(*(func_args + args))
            else:
                return curry(func, func_arity - len(args), func_args + args)
        return curried

    def curried(func):
        return wraps(func)(curry(func, arity, tuple()))
    return curried
