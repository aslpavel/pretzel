"""Create pickle-able object closure from function
"""
import types
import marshal
import importlib
from ..common import PY3
__all__ = ('Closure',)


class Closure(object):
    """Pickle-able object which behaves as function
    """
    __slots__ = ('func',)

    def __init__(self, func):
        assert isinstance(func, types.FunctionType)
        self.func = func

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def __reduce__(self):
        closure = _closure_get(self.func)
        return (_closure_resotre,
               (marshal.dumps(self.func.__code__),
                self.func.__name__,
                self.func.__module__,
                self.func.__kwdefaults__ if PY3 else self.func.func_defaults,
                None if closure is None else
                tuple(cell.cell_contents for cell in closure)))

    def __str__(self):
        return 'Closure({})'.format(self.func.__name__)

    def __repr__(self):
        return str(self)


def _closure_resotre(code, name, module, argdefs, closure):
    return Closure(types.FunctionType(
                   marshal.loads(code),
                   importlib.import_module(module).__dict__,
                   name,
                   argdefs,
                   None if closure is None else
                   tuple(_closure_get(lambda: val)[0] for val in closure)))


if hasattr(_closure_resotre, '__closure__'):
    def _closure_get(func):
        return func.__closure__
else:
    def _closure_get(func):
        return func.func_closure
