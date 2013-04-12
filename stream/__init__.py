from . import stream, file, sock, wrapped, buffered, pipe

from .stream import *
from .file import *
from .sock import *
from .wrapped import *
from .buffered import *
from .pipe import *

__all__ = (stream.__all__ + file.__all__ + sock.__all__ + wrapped.__all__ +
           buffered.__all__ + pipe.__all__)


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import tests

    suite = TestSuite()
    for test in (tests,):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite
