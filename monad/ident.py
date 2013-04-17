"""Identity monad implementation
"""
from .monad import Monad

__all__ = ('Identity',)


class Identity(Monad):
    """Identity monad
    """
    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def bind(self, func):
        return Identity(func(self.value))

    @classmethod
    def unit(cls, val):
        return cls(val)
