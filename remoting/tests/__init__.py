
__all__ = []


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import hub, expr, proxy, conn

    suite = TestSuite()
    for test in (hub, expr, proxy, conn):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite
