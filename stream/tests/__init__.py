
__all__ = []


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import buffered, file, sock

    suite = TestSuite()
    for test in (buffered, file, sock):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite
