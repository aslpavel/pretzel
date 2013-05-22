import unittest
from collections import deque
from ..event import Event, EventQueue
from ..monad import Cont

__all__ = ('EvetTest', 'EventQueueTest',)


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

    def test_reduce(self):
        items = []
        get = lambda: event.__monad__()(lambda val: items.append(val))
        event = Event()

        with event.reduce() as revent:
            get()
            self.assertEqual(items, [])

            revent(0)
            self.assertEqual(items, [0])

            revent(1)
            self.assertEqual(items, [0])

        with self.assertRaises(ValueError):
            revent(2)


class EventQueueTest(unittest.TestCase):
    def test(self):
        items = []
        get = lambda: queue.__monad__()(lambda val: items.append(val))
        queue = EventQueue()

        get()
        self.assertEqual(items, [])
        self.assertEqual(len(queue), 0)

        queue(0)
        self.assertEqual(items, [0])
        self.assertEqual(len(queue), 0)

        queue(1)
        queue(2)
        self.assertEqual(items, [0])
        self.assertEqual(len(queue), 2)

        get()
        self.assertEqual(items, [0, 1])
        self.assertEqual(len(queue), 1)

        get()
        self.assertEqual(items, [0, 1, 2])
        self.assertEqual(len(queue), 0)
