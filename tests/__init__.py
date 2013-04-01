# -*- coding: utf-8 -*-


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import event

    suite = TestSuite()
    for test in (event,):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite

# vim: nu ft=python columns=120 :
