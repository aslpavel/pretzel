"""Expression monad

Expression is a Reader monad with embedded monad which type depends on
environment provided during execution of expression. This module also provides
expression derived serializable convenience types.
"""
from ..monad import Monad, do, do_return

__all__ = ('Expr', 'ExprEnv', 'Env', 'Const', 'Arg', 'Call', 'GetAttr',
           'GetItem', 'If', 'Bind',)


class Expr(Monad):
    """Expression base type

    Expression is a Reader monad with embedded monad which type depends on
    environment provided during execution of expression.
    """
    __slots__ = ('run',)

    def __init__(self, run):
        self.run = run

    def __call__(self, env):
        return self.run(env)

    def bind(self, func):
        def run_bind(env):
            @do(env.type)
            def run():
                val = yield self(env)
                res = yield func(val).__monad__()(env)
                do_return(res)
            return run()
        return Expr(run_bind)

    @classmethod
    def unit(cls, val):
        def run_unit(env):
            return env.type.unit(val)
        return Expr(run_unit)

    def __reduce__(self):
        return Expr, (self.run,)

    def repr(self):
        # pragma: no cover
        return '...'

    def __str__(self):
        return 'Expr({})'.format(self.repr())

    def __repr__(self):
        return str(self)


class ExprEnv(object):
    """Environment object used by expression

    Contains monad type and arguments list.
    """
    __slots__ = ('type', 'args',)

    def __init__(self, type, **args):
        self.type = type
        self.args = args

    def __str__(self):
        return 'ExprEnv(type:{}, args:{})'.format(self.type, self.args)

    def __repr__(self):
        return str(self)


class Const(Expr):
    """Constant expression
    """
    __slots__ = ('const',)

    def __init__(self, const):
        self.const = const

    def __call__(self, env):
        return Expr.unit(self.const)(env)

    def __reduce__(self):
        return Const, (self.const,)

    def repr(self):
        # pragma: no cover
        return getattr(self.const, '__name__', repr(self.const))


class Arg(Expr):
    """Get argument by its name from environment
    """
    __slots__ = ('name',)

    def __init__(self, name):
        self.name = name

    def __call__(self, env):
        @do(env.type)
        def run():
            do_return(env.args[self.name])
        return run()

    def __reduce__(self):
        return Arg, (self.name,)

    def repr(self):
        # pragma: no cover
        return self.name


class Env(Expr):
    """Get environment
    """
    __slots__ = tuple()

    def __init__(self):
        pass

    def __call__(self, env):
        return Expr.unit(env)(env)

    def __reduce__(self):
        return Env, tuple()

    def repr(self):
        # pragma: no cover
        return 'Env()'


class Call(Expr):
    """Call function
    """
    __slots__ = ('func', 'args', 'kwargs',)

    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def __call__(self, env):
        @do(env.type)
        def run():
            func = yield self.func(env)
            args = []
            for arg in self.args:
                args.append((yield arg(env)))
            kwargs = {}
            for key, val in self.kwargs.items():
                kwargs[key] = yield val(env)
            do_return(func(*args, **kwargs))
        return run()

    def __reduce__(self):
        return _call_load, (self.func, self.args, self.kwargs,)

    def repr(self):
        # pragma: no cover
        args = ', '.join(arg.repr() for arg in self.args)
        kwargs = ', '.join('{}={}'.format(key, val.repr())
                           for key, val in self.kwargs.items())
        return '{}({}{}{})'.format(self.func.repr(), args,
                                   ', ' if args and kwargs else '', kwargs)


def _call_load(func, args, kwargs):
    """Call expression loader
    """
    return Call(func, *args, **kwargs)


class GetAttr(Expr):
    """Get attribute by its name
    """
    __slots__ = ('target', 'name',)

    def __init__(self, target, name):
        self.target = target
        self.name = name

    def __call__(self, env):
        @do(env.type)
        def run():
            target = yield self.target(env)
            do_return(getattr(target, self.name))
        return run()

    def __reduce__(self):
        return GetAttr, (self.target, self.name,)

    def repr(self):
        # pragma: no cover
        return '{}.{}'.format(self.target.repr(), self.name)


class GetItem(Expr):
    """Get item
    """
    __slots__ = ('target', 'item',)

    def __init__(self, target, item):
        self.target = target
        self.item = item

    def __call__(self, env):
        @do(env.type)
        def run():
            target = yield self.target(env)
            item = yield self.item(env)
            do_return(target[item])
        return run()

    def __reduce__(self):
        return GetItem, (self.target, self.item,)

    def repr(self):
        # pragma: no cover
        return '{}[{}]'.format(self.target.repr(), self.item.repr())


class If(Expr):
    """Ternary operation
    """
    __slots__ = ('cond', 'true', 'false',)

    def __init__(self, cond, true, false):
        self.cond = cond
        self.true = true
        self.false = false

    def __call__(self, env):
        @do(env.type)
        def run():
            if (yield self.cond(env)):
                result = yield self.true(env)
            else:
                result = yield self.false(env)
            do_return(result)
        return run()

    def __reduce__(self):
        return If, (self.cond, self.true, self.false,)

    def repr(self):
        # pragma: no cover
        return '{} if {} else {}'.format(self.true.repr(), self.cond.repr(),
                                         self.false.repr())


class Bind(Expr):
    """Get associated monadic value
    """
    __slots__ = ('target',)

    def __init__(self, target):
        self.target = target

    def __call__(self, env):
        @do(env.type)
        def run():
            res = yield (yield self.target(env))
            do_return(res)
        return run()

    def __reduce__(self):
        return Bind, (self.target,)

    def repr(self):
        # pragma: no cover
        return '<-{}'.format(self.target.repr())
