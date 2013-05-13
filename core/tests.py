import os
import time
import unittest
from . import waitpid
from .core import FileQueue, TimeQueue, CORE_TIMEOUT
from .poll import POLL_READ, POLL_WRITE, POLL_URGENT, POLL_DISCONNECT, EPOLLERR
from ..common import BrokenPipeError, ConnectionError
from ..tests import async_test

__all__ = ('FileTest', 'TimeQueueTest', 'ProcQueueTest',)


class FileTest(unittest.TestCase):
    def test_dummy(self):
        polls, rets = [], []
        ret = lambda tag: lambda res: rets.append((tag, res))
        file = FileQueue('fd', self.DummyPoller(lambda *a: polls.append(a)))

        file.on(POLL_READ | POLL_WRITE)(ret('rw'))
        file.on(POLL_READ)(ret('r'))
        self.assertEqual(polls, [('reg', 'fd', POLL_READ | POLL_WRITE)])
        self.assertEqual(rets[0][0], 'r')
        with self.assertRaises(ValueError):  # intersecting mask
            rets[0][1].value
        del rets[:]

        file.on(POLL_URGENT)(ret('u'))
        self.assertEqual(len(polls), 2)
        self.assertEqual(polls[-1], ('mod', 'fd', POLL_READ | POLL_WRITE | POLL_URGENT))

        file(POLL_READ)
        self.assertEqual(rets[0][0], 'rw')
        self.assertEqual(rets[0][1].value, POLL_READ)
        self.assertEqual(len(polls), 3)
        self.assertEqual(polls[-1], ('mod', 'fd', POLL_URGENT))

        file(POLL_READ)
        self.assertEqual(len(rets), 1)

        file(POLL_URGENT)
        self.assertEqual(len(rets), 2)
        self.assertEqual(rets[-1][0], 'u')
        self.assertEqual(len(polls), 4)
        self.assertEqual(polls[-1], ('unreg', 'fd'))

        file.on(POLL_WRITE)(ret('w'))
        self.assertEqual(len(polls), 5)
        self.assertEqual(polls[-1], ('reg', 'fd', POLL_WRITE))

        file(POLL_DISCONNECT)
        self.assertEqual(len(polls), 6)
        self.assertEqual(polls[-1], ('unreg', 'fd'))
        self.assertEqual(len(rets), 3)
        self.assertEqual(rets[-1][0], 'w')
        with self.assertRaises(BrokenPipeError):
            rets[-1][1].value

        file.on(POLL_READ)(ret('r'))
        file.on(POLL_WRITE)(ret('w'))
        self.assertEqual(len(polls), 8)
        self.assertEqual(polls[-2:], [('reg', 'fd', POLL_READ),
                                      ('mod', 'fd', POLL_READ | POLL_WRITE)])

        file(EPOLLERR)
        self.assertEqual(len(polls), 9)
        self.assertEqual(polls[-1], ('unreg', 'fd'))
        self.assertEqual(len(rets), 5)
        self.assertEqual(rets[-2][0], 'r')
        with self.assertRaises(ConnectionError):
            rets[-2][1].value
        self.assertEqual(rets[-1][0], 'w')
        with self.assertRaises(ConnectionError):
            rets[-1][1].value

    class DummyPoller(object):
        def __init__(self, hook):
            self.hook = hook

        def register(self, fd, mask):
            self.hook('reg', fd, mask)

        def modify(self, fd, mask):
            self.hook('mod', fd, mask)

        def unregister(self, fd):
            self.hook('unreg', fd)


class TimeQueueTest(unittest.TestCase):
    def test(self):
        def res():
            ret = tuple(rets)
            del rets[:]
            return ret
        ret = lambda tag: lambda res: rets.append((tag, res.value))
        rets = []

        timer = TimeQueue()
        timer.on(1)(ret('1'))
        timer.on(2)(ret('2'))

        timer(.5)
        self.assertEqual(len(res()), 0)
        self.assertEqual(timer.timeout(.5), .5)

        timer(1.5)
        self.assertEqual(res(), (('1', 1),))

        timer(2)
        self.assertEqual(res(), (('2', 2),))
        self.assertEqual(timer.timeout(2), CORE_TIMEOUT)

        timer.on(1)(ret('1:0'))
        timer.on(1)(ret('1:1'))
        timer.on(2)(ret('2'))
        self.assertEqual(timer.timeout(3), 0)

        timer(3)
        self.assertEqual(res(), (('1:0', 1), ('1:1', 1), ('2', 2)))


class ProcQueueTest(unittest.TestCase):
    @async_test
    def test(self):
        pid = os.fork()
        if pid:
            self.assertEqual((yield waitpid(pid)), pid & 0xff)
        else:
            time.sleep(.3)
            os.execvp('/bin/sh', ['/bin/sh', '-c', 'exit {}'.format(os.getpid() & 0xff)])
