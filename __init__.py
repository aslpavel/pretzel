import sys
sys.setrecursionlimit(1 << 16)

__all__ = []


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import tests, monad, core, stream, remoting

    suite = TestSuite()
    for test in (tests, monad, core, stream, remoting):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite


def load_bench(runner):
    """Load benchmarks protocol
    """
    from . import remoting

    for module in (remoting,):
        runner.add_module(module)
