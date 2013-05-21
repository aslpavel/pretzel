from . import stream, file, sock, sock_ssl, wrapped, buffered

from .stream import *
from .file import *
from .sock import *
from .sock_ssl import *
from .wrapped import *
from .buffered import *

__all__ = (stream.__all__ + file.__all__ + sock.__all__ + sock_ssl.__all__ +
           wrapped.__all__ + buffered.__all__)


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import tests

    suite = TestSuite()
    for test in (tests,):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite
