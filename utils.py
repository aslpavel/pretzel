"""Utility functions and types
"""
from functools import wraps

__all__ = ('lazy', 'cached', 'called',)


def lazy(func, *args, **kwargs):
    """Lazy value
    """
    @wraps(func)
    def lazy_func():
        if not value:
            value.append(func(*args, **kwargs))
        return value[0]
    value = []
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


def called(func):
    """Called function
    """
    return wraps(func)(func())
