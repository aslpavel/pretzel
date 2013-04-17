"""Send-able lazy proxy object
"""
from .hub import Pipe
from .expr import (LoadArgExpr, LoadConstExpr, CallExpr, GetAttrExpr,
                   GetItemExpr, BindExpr)

__all__ = ('Proxy', 'proxify')


class Proxy(object):
    """Send-able lazy proxy object
    """
    __slots__ = ('_sender', '_expr', '_code',)

    def __init__(self, sender, expr):
        self._sender = sender
        self._expr = expr
        self._code = None

    def __call__(self, *args):
        return Proxy(self._sender, CallExpr(self._expr, *args))

    def __getattr__(self, name):
        return Proxy(self._sender, GetAttrExpr(self._expr, name))

    def __getitem__(self, item):
        return Proxy(self._sender, GetItemExpr(self._expr, item))

    def __invert__(self):
        return Proxy(self._sender, BindExpr(self._expr))

    def __rshift__(self, func):
        return Proxy(self._sender, CallExpr(LoadConstExpr(func), self._expr))

    def __monad__(self):
        if self._code is None:
            self._code = self._expr.code()
        return self._sender(self._code)

    def __reduce__(self):
        return type(self), (self._sender, self._expr)

    def __str__(self):
        return ('<{}[addr:{} expr:{}]>'.format(type(self).__name__,
                self._sender.addr if self._sender else None, self._expr))

    def __repr__(self):
        return str(self)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        sender, self._sender = self._sender, None
        if sender is not None:
            sender.send(None)
        return False


def proxify(target, dispose=None, hub=None):
    """Create send-able proxy object from target object
    """
    if isinstance(target, Proxy):
        return target >> proxify

    def proxy_handler(code, dst, src):
        if code is None:
            if dispose is None or dispose:
                getattr(target, '__exit__', lambda *_: None)(None, None, None)
            return False  # unsubscribe proxy handler
        code(target)(lambda val: val.trace() if src is None else src.send(val))
        return True

    recv, send = Pipe(hub=hub)
    recv(proxy_handler)
    return Proxy(send, LoadArgExpr(0))
