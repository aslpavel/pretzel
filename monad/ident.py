"""Identity monad implementation
"""
from .monad import Monad


class Identity(Monad):
    """Identity monad
    """
    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def bind(self, func):
        return Identity(func(self.value))

    def unit(self, val):
        return Identity(val)
