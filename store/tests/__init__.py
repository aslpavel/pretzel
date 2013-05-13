
__all__ = []


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import alloc, serialize, store, bptree, stream

    suite = TestSuite()
    for test in (alloc, serialize, store, bptree, stream):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite
