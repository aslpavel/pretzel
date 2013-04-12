from . import core, poll
from .core import *
from .poll import *

__all__ = (core.__all__ + poll.__all__ + ('sleep', 'sleep_until',
           'poll', 'schedule',))


def sleep(delay, core=None):
    """Sleep for "delay" seconds
    """
    return (core or Core.local()).sleep(delay)


def sleep_until(when, core=None):
    """Sleep until "when" time is reached
    """
    return (core or Core.local()).sleep_until(when)


def poll(fd, mask, core=None):
    """Poll file descriptor

    Poll file descriptor for events specified by mask. If mask is None then
    specified descriptor is unregistered and all pending events are resolved
    with BrokenPipeError, otherwise future is resolved with bitmap of the
    events happened on file descriptor or error if any.
    """
    return (core or Core.local()).poll(fd, mask)


def schedule(core=None):
    """Schedule continuation to be executed on specified core (local by default)

    Scheduled continuation will be executed on next iteration circle. This
    function can be called from different thread.
    """
    return (core or Core.local()).schedule()


def waitpid(pid, core=None):
    """Wait pid

    Schedule continuation to be executed when process with pid is terminated.
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
