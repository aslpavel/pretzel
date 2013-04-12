from . import monad, result, cont, list
from . import do as _do
from .monad import *
from .result import *
from .do import *
from .cont import *
from .list import *

__all__ = (monad.__all__ + result.__all__ + _do.__all__ + cont.__all__ +
           list.__all__)


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import tests

    suite = TestSuite()
    for test in (tests,):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite
