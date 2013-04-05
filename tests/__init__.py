# -*- coding: utf-8 -*-
import functools
from ..core import Core
from ..monad import async

__all__ = ('async_test',)


def async_test(test):
    """Run asynchronous test in context of newly create core object
    """
    @functools.wraps(test)
    def test_async(*args):
        core_prev = Core.local()
        try:
            with Core.local(Core()) as core:
                test_future = async(test)(*args).future()
                test_future(lambda _: core.dispose())
                if not core.disposed:
                    core()
        finally:
            Core.local(core_prev)
        assert test_future.completed
        test_future.result.value  # raises error if test function has failed
    return test_async


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import event, dispose, process

    suite = TestSuite()
    for test in (event, dispose, process,):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite

# vim: nu ft=python columns=120 :
