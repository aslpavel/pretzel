import functools
from .. import PRETZEL_TEST_TIMEOUT
from ..core import Core, sleep
from ..uniform import CanceledError
from ..monad import Result, async
from ..remoting.hub import Hub

__all__ = ('async_test',)


def async_test(test):
    """Run asynchronous test in context of newly create core object
    """
    def timeout():
        return (sleep(PRETZEL_TEST_TIMEOUT).map_val(lambda _:
                Result.from_exception(CanceledError('test timeout'))))

    @functools.wraps(test)
    def test_async(*args):
        core_prev = Core.local()
        try:
            with Core.local(Core()) as core:
                test_future = (async(test)(*args) | timeout()).future()
                test_future(lambda _: core.dispose())
                if not core.disposed:
                    core()
        finally:
            Core.local(core_prev)
            Hub.local(Hub())
        assert test_future.completed
        test_future.value
    return test_async


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import event, dispose, process, task, boot, utils

    suite = TestSuite()
    for test in (event, dispose, process, task, boot, utils):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite
