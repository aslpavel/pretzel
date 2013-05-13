import unittest
from collections import deque
from ..event import Event
from ..monad import Cont

__all__ = ('EvetTest',)


class EventTest(unittest.TestCase):
    def test(self):
        def handler(tag, ret):
            def handler(val):
                queue.append((tag, val))
                return ret
            return handler
        queue = deque()

        event = Event()
        event(0)

        h1 = event.on(handler('1', False))
        h2 = event.on(handler('2', True))

        event(1)
        self.assertEqual(queue.popleft(), ('1', 1))
        self.assertEqual(queue.popleft(), ('2', 1))
        self.assertFalse(queue)

        event(2)
        self.assertEqual(queue.popleft(), ('2', 2))
        self.assertFalse(queue)
        self.assertEqual(event.off(h1), False)
        self.assertEqual(event.off(h2), True)

    def test_monad(self):
        ret = lambda tag: lambda val: queue.append((tag, val))
        queue = deque()

        event = Event()
        event(0)

        monad = event.__monad__()
        self.assertTrue(isinstance(monad, Cont))
        monad(ret('1'))
        monad(ret('2'))

        event(1)
        self.assertEqual(queue.popleft(), ('1', 1))
        self.assertEqual(queue.popleft(), ('2', 1))
        self.assertFalse(queue)

        event(2)
        self.assertFalse(queue)
        self.assertFalse(event.handlers)

    def test_handler(self):
        rets = []
        event = Event()

        def h0(val):
            event('done')
            event.on(h1)

        def h1(val):
            rets.append(val)

        event.on(h0)
        event(0)
        self.assertEqual(rets, [])

        event(1)
        self.assertEqual(rets, [1])
