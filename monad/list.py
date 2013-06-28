"""List monad implementation
"""
from .monad import Monad

__all__ = ('List',)


class List(tuple, Monad):
    """List monad
    """
    __slots__ = tuple()

    def __new__(cls, *vals):
        return tuple.__new__(cls, vals)

    def __init__(cls, *vals):
        pass

    @classmethod
    def from_iter(cls, iter):
        return cls(*iter)

    @classmethod
    def unit(cls, val):
        return cls(val)

    def bind(self, func):
        return List.from_iter(tuple(fval
                              for mval in self
                              for fval in func(mval).__monad__()))

    @property
    def value(self):
        return tuple(self)

    @classmethod
    def zero(cls):
        return cls()

    def plus(self, monad):
        return List.from_iter(self + monad.__monad__())

    def __reduce__(self):
        return List, tuple(self)

    def __str__(self):
        return 'List({})'.format(', '.join(repr(val) for val in self))

    __repr__ = __str__
