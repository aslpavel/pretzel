
__all__ = []


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import buffered

    suite = TestSuite()
    for test in (buffered,):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite
