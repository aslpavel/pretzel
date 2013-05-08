"""Proxy monad
"""

__all__ = ('Proxy',)


class Proxy(object):
    """Proxy monad

    All operation on this proxy object are executed inside context of the monad
    and on bound monad value.
    """
    __slots__ = ('__monad',)

    def __init__(self, monad):
        self.__monad = monad.__monad__()

    def __monad__(self):
        return self.__monad

    def __map(self, func):
        monad = self.__monad
        return type(self)(monad.bind(lambda val: monad.unit(func(val))))

    def __call__(self, *a, **kw):
        return self.__map(lambda val: val(*a, **kw))

    ## attributes
    def __getattr__(self, name):
        return self.__map(lambda val: getattr(val, name))

    def __delattr__(self, name):
        return self.__map(lambda val: val.__delattr__(name))

    ## items
    def __getitem__(self, item):
        return self.__map(lambda val: val[item])

    def __delitem__(self, item):
        return self.__map(lambda val: val.__delitem__(item))

    def __contains__(self, item):
        return self.__map(lambda val: val.__contains__(item))

    ## compare
    def __lt__(self, other):
        return self.__map(lambda val: val.__lt__(other))

    def __le__(self, other):
        return self.__map(lambda val: val.__le__(other))

    def __eq__(self, other):
        return self.__map(lambda val: val.__eq__(other))

    def __ne__(self, other):
        return self.__map(lambda val: val.__ne__(other))

    def __gt__(self, other):
        return self.__map(lambda val: val.__gt__(other))

    def __ge__(self, other):
        return self.__map(lambda val: val.__ge__(other))

    ## arithmetic
    def __add__(self, other):
        return self.__map(lambda val: val.__add__(other))

    def __sub__(self, other):
        return self.__map(lambda val: val.__sub__(other))

    def __mul__(self, other):
        return self.__map(lambda val: val.__mul__(other))

    def __truediv__(self, other):
        return self.__map(lambda val: val.__truediv__(other))

    def __floordiv__(self, other):
        return self.__map(lambda val: val.__floordiv__(other))

    def __mod__(self, other):
        return self.__map(lambda val: val.__mod__(other))

    def __divmod__(self, other):
        return self.__map(lambda val: val.__divmod__(other))

    def __pow__(self, other):
        return self.__map(lambda val: val.__pow__(other))

    def __lshift__(self, other):
        return self.__map(lambda val: val.__lshift__(other))

    def __rshift__(self, other):
        return self.__map(lambda val: val.__rshift__(other))

    def __and__(self, other):
        return self.__map(lambda val: val.__and__(other))

    def __xor__(self, other):
        return self.__map(lambda val: val.__xor__(other))

    def __or__(self, other):
        return self.__map(lambda val: val.__or__(other))

    def __neg__(self):
        return self.__map(lambda val: val.__neg__())

    def __pos__(self):
        return self.__map(lambda val: val.__pos__())

    def __abs__(self):
        return self.__map(lambda val: val.__abs__())

    def __invert__(self):
        return self.__map(lambda val: val.__invert__())

    ## scope
    def __enter__(self):
        return self.__map(lambda val: val.__enter__())

    def __exit__(self, et, eo, tb):
        self.__map(lambda val: val.__exit__(et, eo, tb))
        return False

    ## representation
    def __str__(self):
        return str(self.__monad)

    def __repr__(self):
        return repr(self.__monad)
