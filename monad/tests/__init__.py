
__all__ = []


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import monad, do_async, do_green

    suite = TestSuite()
    for test in (monad, do_async, do_green):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite
