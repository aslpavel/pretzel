"""Remoting benchmarks
"""
import itertools
from .conn import ForkConnection
from .proxy import proxify
from ..monad import async, async_all
from ..bench import Benchmark


class FuncBench(Benchmark):
    """Benchmark function call
    """
    def __init__(self):
        Benchmark.__init__(self, 'remoting.func', 1)
        self.conn = None

    @async
    def init(self):
        self.conn = yield ForkConnection()
        self.func = self.conn(remote)()
        if ((yield self.func), (yield self.func)) != (1, 2):
            raise ValueError('initialization test failed')

    def body(self):
        return self.func

    def dispose(self):
        conn, self.conn = self.conn, None
        if conn:
            conn.dispose()


class FuncAsyncBench(FuncBench):
    """Benchmark asynchronous function call
    """
    def __init__(self):
        Benchmark.__init__(self, 'remoting.func_async', 512)
        self.conn = None

    def body(self):
        return async_all((self.func,) * self.factor)


class MethodBench (Benchmark):
    """Benchmark proxy method call
    """
    def __init__(self):
        Benchmark.__init__(self, 'remoting.method', 1)
        self.conn = None

    @async
    def init(self):
        self.conn = yield ForkConnection()
        self.proxy = yield proxify(self.conn(Remote)())
        self.method = self.proxy.method()
        if ((yield self.method), (yield self.method)) != (1, 2):
            raise ValueError('initialization test failed')

    def body(self):
        return self.method

    def dispose(self):
        proxy, self.proxy = self.proxy, None
        if proxy:
            proxy.dispose()
        conn, self.conn = self.conn, None
        if conn:
            conn.dispose()


class MethodAsyncBench(MethodBench):
    """Benchmark asynchronous proxy method call
    """
    def __init__(self):
        Benchmark.__init__(self, 'remoting.method_async', 1024)
        self.conn = None

    def body(self):
        return async_all((self.method,) * self.factor)


def remote():
    return next(fn_count)
fn_count = itertools.count(1)


class Remote(object):
    def __init__(self):
        self.count = itertools.count(1)

    def method(self):
        return next(self.count)


def load_bench(runner):
    """Load benchmarks
    """
    for bench in ((FuncBench(), FuncAsyncBench(),
                   MethodBench(), MethodAsyncBench(),)):
        runner.add(bench)
