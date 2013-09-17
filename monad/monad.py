"""Base monad type with implementation of common monadic functions.
"""
from .proxy import Proxy
from functools import wraps, reduce

__all__ = ('Monad', 'monad',)


class Monad(object):
    """Base monad type
    """
    __slots__ = tuple()

    def __init__(self):
        raise NotImplementedError()

    def __monad__(self):
        return self

    @classmethod
    def unit(cls, val):
        """Create primitive monad from value

        unit :: (Monad m) => a -> m a
        """
        raise NotImplementedError()

    def bind(self, func):
        """Bind function

        bind :: (Monad m) => m a -> (a -> m b) -> m b
        """
        raise NotImplementedError()

    @property
    def value(self):
        """Get embedded monad value

        This monad independent version works only inside do_green block.
        """
        from .do_green import bind_green
        return bind_green(self)

    @property
    def proxy(self):
        """Put this monad inside proxy monad
        """
        return Proxy(self)

    def __irshift__(self, func):
        return self.bind(func)

    @classmethod
    def zero(cls):
        """Zero monad

        zero :: (Monad m) => () -> m a
        """
        raise NotImplementedError()

    def plus(self, monad):
        """Monad plus operation

        plus :: (Monad m) => m a -> m b -> m c
        Plus laws:
            (m0 + m1) + m2 == m0 + (m1 + m2)
            m + zero == m
        """
        raise NotImplementedError()

    def __add__(self, monad):
        return self.plus(monad)

    def then(self, monad):
        return self.bind(lambda _: monad)

    def __rshift__(self, monad):
        return self.then(monad)

    def then_val(self, val):
        return self.then(self.unit(val))

    def map_val(self, func):
        """Functors map operation

        map :: (Monad m) => m a -> (a -> b) -> m b
        """
        return self.bind(lambda val: self.unit(func(val)))

    def join(self):
        """Join nested monad

        The 'join' function is the conventional monad join operator. It is used
        to remove one level of monadic structure, projecting its bound argument
        into the outer level.

        join :: (Monad m) => m (m a) -> m a
        """
        return self.bind(lambda m: m.__monad__())

    @classmethod
    def Map(Monad, mapper, vals):
        """Map with monadic function (mapM)

        Map :: (Monad m) => (a -> m b) -> [a] -> m [b]
        """
        return Monad.Sequence(mapper(val) for val in vals)

    @classmethod
    def Filter(Monad, pred, vals):
        """Filter with monadic predicate (filterM)

        Filter :: (Monad m) => (a -> m Bool) -> [a] -> m [a]
        """
        def chain(mvals, val):
            return mvals.bind(lambda vals: pred(val).__monad__().bind(
                              lambda add: Monad.unit(vals + (val,) if add else vals)))
        return reduce(chain, vals, Monad.unit(tuple()))

    @classmethod
    def Fold(Monad, folder, acc, vals):
        """Fold with monadic function (foldM)

        Fold :: (Monad m) => (a -> b -> m a) -> a -> [b] -> m a
        """
        def fold(acc, vals):
            if not vals:
                return Monad.unit(acc)
            val, vals = vals[0], vals[1:]
            return folder(acc, val).__monad__().bind(lambda acc: fold(acc, vals))
        vals = tuple(vals)
        return fold(acc, vals)

    @classmethod
    def Sequence(Monad, monads):
        """Sequence monads

        Evaluate each action in the sequence from left to right, and collect the results.

        Sequence :: Monad m => [m a] -> m [a]
        """
        def chain(mvals, mval):
            return mvals.bind(lambda vals: mval.bind(lambda val: Monad.unit(vals + (val,))))
        return reduce(chain, (monad.__monad__() for monad in monads), Monad.unit(tuple()))

    def __and__(self, monad):
        """Compose two monads into one

        Equivalent to Monad.Sequence((self, monad)).
        (&) :: m a -> m b -> m (a, b)
        """
        return self.bind(lambda val: monad.__monad__().bind(
                         lambda mval: self.unit((val, mval))))

    @classmethod
    def Lift(Monad, monad):
        """Wrap monad's value inside primitive monad of this type
        """
        monad = monad.__monad__()
        return monad.bind(lambda val: monad.unit(Monad.unit(val)))

    @classmethod
    def LiftFunc(Monad, func):
        """Promote function to fully monadic one (arguments and result)

        LiftFunc :: Monad m => (a0 -> ... -> aN -> r) -> (m a0 -> ... -> m aN -> m r)
        """
        return wraps(func)(lambda *margs: Monad.Sequence(margs).bind(lambda args: Monad.unit(func(*args))))

    @classmethod
    def LiftFuncResult(Monad, func):
        """Promote function to monadic one (result only)

        LiftFuncResult :: Monad m => (a -> b) -> a -> m b
        """
        return wraps(func)(lambda *args, **kw: Monad.unit(func(*args, **kw)))

    @classmethod
    def Ap(Monad, mfunc):
        """Applicative <*> operator

        Ap :: Monad m => m (a -> b) -> m a -> m b
        """
        return lambda ma: mfunc.bind(lambda func: ma.bind(lambda a: Monad.unit(func(a))))


def monad(target):
    """Get associated monad
    """
    return target.__monad__()
