from . import core, poll
from .core import *
from .poll import *

__all__ = (core.__all__ + poll.__all__ + ('sleep', 'sleep_until',
           'poll', 'schedule',))


def sleep(delay, core=None):
    """Sleep for delay seconds

    Returns time when it supposed to be executed.
    """
    return (core or Core.local()).sleep(delay)


def sleep_until(when, core=None):
    """Sleep until specified unix time is reached

    Returns time when it supposed to be executed.
    """
    return (core or Core.local()).sleep_until(when)


def poll(fd, mask, core=None):
    """Poll file descriptor for events

    Poll file descriptor for events specified by mask. If mask is None then
    specified descriptor is unregistered and all pending events are resolved
    with BrokenPipeError, otherwise returns bitmap of the events happened on
    file descriptor or error if any.
    """
    return (core or Core.local()).poll(fd, mask)


def schedule(core=None):
    """Schedule execution to next iteration circle

    This function can be called from different thread, but not from signal
    handler as heappush used by time_queue is not reentrant. Returns associated
    core object.
    """
    return (core or Core.local()).schedule()


def waitpid(pid, core=None):
    """Wait for process with specified pid to be terminated

    Returns process's termination status.
    """
    return (core or Core.local()).waitpid(pid)


def load_tests(loader, tests, pattern):
    """Load test protocol
    """
    from unittest import TestSuite
    from . import tests

    suite = TestSuite()
    for test in (tests,):
        suite.addTests(loader.loadTestsFromModule(test))

    return suite
