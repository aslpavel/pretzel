"""Utility functions and types
"""
from functools import wraps

__all__ = ('lazy',)


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
