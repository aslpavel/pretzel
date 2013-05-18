"""Remoting module

Work with remote objects transparently.
"""
from . import hub, proxy, conn
from .hub import *
from .proxy import *
from .closure import *
from .conn import*

__all__ = hub.__all__ + proxy.__all__ + closure.__all__ + conn.__all__


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import tests

    suite = TestSuite()
    for test in (tests,):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite


def load_bench(runner):
    """Load benchmarks protocol
    """
    from . import bench
    bench.load_bench(runner)
