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


class Curry(object):
    """Curried function
    """
    __slots__ = ('func', 'args', 'arity',)

    def __init__(self, func, args, arity):
        self.func = func
        self.arity = arity
        self.args = args

    def __call__(self, *args):
        if len(args) >= self.arity:
            return self.func(*(self.args + args))
        else:
            return Curry(self.func, self.args + args, self.arity - len(args))

    def __reduce__(self):
        return type(self), (self.func, self.args, self.arity,)

    def __str__(self):
        return ('{}(func:{}, args:{}, arity:{})' .format(type(self).__name__,
                getattr(self.func, '__name__', self.func), self.arity, self.args))

    def __repr__(self):
        return str(self)


def curry(arity):
    """Curried function decorator

    Returns decorator which creates carried function with specified arity.
    """
    def curried(func):
        return Curry(func, tuple(), arity)
    return curried
