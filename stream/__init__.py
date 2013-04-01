# -*- coding: utf-8 -*-

__all__ = []


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import tests

    suite = TestSuite()
    for test in (tests,):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite

# vim: nu ft=python columns=120 :
