"""Asynchronous application framework
"""
import os
import sys
import select

__all__ = ('PRETZEL_RECLIMIT', 'PRETZEL_BUFSIZE', 'PRETZEL_TEST_TIMEOUT',
           'PRETZEL_POLLER',)

# Environment configurable pretzel variables
PRETZEL_RECLIMIT = int(os.environ.get('PRETZEL_RECLIMIT', '8192'))
PRETZEL_BUFSIZE = int(os.environ.get('PRETZEL_BUFSIZE', '65536'))
PRETZEL_TEST_TIMEOUT = int(os.environ.get('PRETZEL_TEST_TIMEOUT', '5'))
PRETZEL_POLLER = os.environ.get('PRETZEL_POLLER',
                                'epoll' if hasattr(select, 'epoll') else
                                'kqueue' if hasattr(select, 'kqueue') else
                                'select')


# Increase of recursion limit is desirable as in case of long sequence of
# instantly resolved monads do_block may exhaust it.
sys.setrecursionlimit(int(os.environ.get('PRETZEL_RECLIMIT', '8192')))


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
