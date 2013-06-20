import math
import unittest
import itertools
from heapq import heappush, heappop
from ..do import do_return
from ..async import async, async_block, async_all, async_any, async_limit
from ..result import Result
from ...event import Event

__all__ = ('ContTest',)


class ContTest(unittest.TestCase):
    """Continuation monad unit tests
    """
    def test_normal(self):
        rets, rets_ref = [], []
        e0, e1 = Event(), Event()

        @async
        def test_async(result):
            rets.append((yield e0))
            rets.append('0-1')
            rets.append((yield e1))
            rets.append('1-2')
            rets.append((yield e0))
            rets.append('2-R')
            do_return(result)

        test_async('done')(lambda val: rets.append(val))
        self.assertEqual(rets, rets_ref)

        e1(1)
        self.assertFalse(rets, rets_ref)
        e0(2)
        rets_ref.extend([2, '0-1'])
        self.assertEqual(rets, rets_ref)
        e1(Result.from_value(3))
        rets_ref.extend([3, '1-2'])
        self.assertEqual(rets, rets_ref)
        e0(4)
        rets_ref.extend([4, '2-R', Result.from_value('done')])
        self.assertEqual(rets, rets_ref)

    def test_error(self):
        rets, rets_ref = [], []
        ev = Event()
        error = ValueError('test')

        @async
        def test_async():
            try:
                rets.append((yield ev))
            except Exception as error:
                rets.append(error)
            rets.append((yield ev))
            rets.append((yield ev))

        test_async()(lambda val: rets.extend(('done', val,)))
        self.assertEqual(rets, rets_ref)

        ev(Result.from_exception(error))
        rets_ref.append(error)
        self.assertEqual(rets, rets_ref)

        ev('value')
        rets_ref.append('value')
        self.assertEqual(rets, rets_ref)

        ev(Result.from_exception(error))
        rets_ref.extend(('done', Result.from_exception(error),))
        self.assertEqual(rets, rets_ref)

    def test_block(self):
        rets, rets_ref = [], []
        hs = []
        exc = ValueError('test')

        def test_async(exc=None):
            @async_block
            def cont(ret):
                if exc is None:
                    hs.append(ret)
                else:
                    raise exc
            return cont

        test_async(exc)(lambda val: rets.append(val))
        rets_ref.append(Result.from_exception(exc))
        self.assertEqual(rets, rets_ref)

        test_async()(lambda val: rets.append(val))
        hs[-1]('done')
        rets_ref.append(Result.from_value('done'))
        self.assertEqual(rets, rets_ref)

        test_async()(lambda val: rets.append(val))
        hs[-1](Result.from_value('done value'))
        rets_ref.append(Result.from_value('done value'))
        self.assertEqual(rets, rets_ref)

    def test_all(self):
        rets = []
        e0, e1 = Event(), Event()

        async_all((e0, e1))(lambda val: rets.append(val))
        self.assertEqual(len(e0.handlers), 1)
        self.assertEqual(len(e1.handlers), 1)

        e1('two')
        e0('one')
        self.assertFalse(e0.handlers)
        self.assertFalse(e1.handlers)
        self.assertEqual(rets.pop().value, ('one', 'two'))

        async_all(tuple())(lambda val: rets.append(val))
        self.assertEqual(rets.pop().value, tuple())

    def test_any(self):
        rets = []
        e0, e1 = Event(), Event()

        async_any((e0, e1))(lambda val: rets.append(val))
        self.assertEqual(len(e0.handlers), 1)
        self.assertEqual(len(e1.handlers), 1)

        e0('done')
        self.assertFalse(e0.handlers)
        self.assertTrue(e1.handlers)
        self.assertEqual(rets.pop().value, 'done')

        e1('done_next')
        self.assertFalse(e1.handlers)

        with self.assertRaises(ValueError):
            async_any(tuple())

    def test_limit(self):
        timer = Timer()
        timer_limit_10 = async_limit(10)(lambda val: timer(val))

        count = 1024
        res = async_all(timer_limit_10(1) for i in range(count)).future()
        for i in range(count):
            if res.completed:
                res.value
                break
            timer.tick()
        self.assertEqual(timer.time, math.ceil(count / 10.))


class Timer(object):
    def __init__(self):
        self.time = 0
        self.uid = itertools.count()
        self.queue = []

    def __call__(self, time):
        @async_block
        def cont(ret):
            heappush(self.queue, (self.time + time, next(self.uid), ret))
        return cont

    def tick(self):
        self.time += 1
        while self.queue:
            time, _, ret = self.queue[0]
            if time > self.time:
                return
            else:
                heappop(self.queue)
                ret(self.time)
