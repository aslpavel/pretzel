from .monad import Monad

__all__ = ('List',)


class List(Monad):
    """List
    """
    __slots__ = ('items',)

    def __init__(self, items):
        self.items = tuple(items)

    def __iter__(self):
        return iter(self.items)

    @staticmethod
    def unit(val):
        return List((val,))

    def bind(self, func):
        return List(fval for mval in self for fval in func(mval).__monad__())

    @staticmethod
    def zero():
        return List(tuple())

    def plus(self, monad):
        return List(self.items + monad.__monad__().items)

    def __str__(self):
        return '<{}>'.format(', '.join(repr(item) for item in self.items))
    __repr__ = __str__
