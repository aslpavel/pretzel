"""Asynchronous application framework
"""
import sys
# Increase of recursion limit is desirable as in case of long sequence of
# instantly resolved monads do_block may exhaust it.
sys.setrecursionlimit(8192)

__all__ = []


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import tests, monad, core, stream, remoting, store

    suite = TestSuite()
    for test in (tests, monad, core, stream, remoting, store):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite


def load_bench(runner):
    """Load benchmarks protocol
    """
    from . import remoting

    for module in (remoting,):
        runner.add_module(module)
