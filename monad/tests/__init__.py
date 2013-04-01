# -*- coding: utf-8 -*-

__all__ = []


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import do, cont

    suite = TestSuite()
    for test in (do, cont,):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite

# vim: nu ft=python columns=120 :
