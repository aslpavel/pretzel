"""Different kinds of monads and do block notation
"""
from . import monad, result, cont, list, ident
from . import do as _do
from . import do_green as _do_green
from .monad import *
from .result import *
from .do import *
from .do_green import *
from .cont import *
from .list import *
from .ident import *

__all__ = (monad.__all__ + result.__all__ + _do.__all__ + _do_green.__all__ +
           cont.__all__ + list.__all__ + ident.__all__)


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import tests

    suite = TestSuite()
    for test in (tests,):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite
