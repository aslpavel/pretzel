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
        return (_restore_closure,
               (marshal.dumps(self.func.__code__),
                self.func.__name__,
                self.func.__module__,
                self.func.__kwdefaults__ if PY3 else self.func.func_defaults,
                None if self.func.__closure__ is None else
                tuple(cell.cell_contents for cell in self.func.__closure__)))

    def __str__(self):
        return 'Closure({})'.format(self.func.__name__)

    def __repr__(self):
        return str(self)


def _restore_closure(code, name, module, argdefs, closure):
    return Closure(types.FunctionType(
                   marshal.loads(code),
                   importlib.import_module(module).__dict__,
                   name,
                   argdefs,
                   None if closure is None else
                   tuple((lambda: val).__closure__[0] for val in closure)))
