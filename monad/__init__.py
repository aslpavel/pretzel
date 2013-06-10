"""Different kinds of monads and do block notation
"""
from . import monad, ident, result, list, cont, proxy
from . import async as _async
from . import do as _do
from . import do_green as _do_green
from .monad import *
from .do import *
from .do_green import *
from .ident import *
from .result import *
from .list import *
from .cont import *
from .async import *
from .proxy import *

__all__ = (monad.__all__ + _do.__all__ + _do_green.__all__ + ident.__all__ +
           result.__all__ + list.__all__ + cont.__all__ + _async.__all__ +
           proxy.__all__)


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import tests

    suite = TestSuite()
    for test in (tests,):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite
