import unittest
import operator
import itertools
from ..dispose import FuncDisp, CompDisp
from ..monad import async

__all__ = ('FuncDispTest', 'CompDispTest',)


class FuncDispTest(unittest.TestCase):
    def test(self):
        def disp():
            res[0] += 1
        res = [0]

        with FuncDisp(disp) as d0:
            self.assertFalse(d0)
            self.assertEqual(res[0], 0)
        self.assertTrue(d0)
        self.assertEqual(res[0], 1)
        d0.dispose()
        self.assertEqual(res[0], 1)

        d1 = FuncDisp(disp)
        self.assertEqual(res[0], 1)
        d1.dispose()
        self.assertEqual(res[0], 2)


class CompDispTest(unittest.TestCase):
    def test(self):
        ctx = [0, 0, 0, 0]
        d0, d1, d2, d3 = map(FuncDisp, (
            lambda: operator.setitem(ctx, 0, 1),
            lambda: operator.setitem(ctx, 1, 1),
            lambda: operator.setitem(ctx, 2, 1),
            lambda: operator.setitem(ctx, 3, 1)))

        d = CompDisp((d0,))
        self.assertFalse(d)
        self.assertEqual(ctx, [0, 0, 0, 0])
        d += d1
        with d:
            self.assertEqual(ctx, [0, 0, 0, 0])
        self.assertTrue(d)
        self.assertEqual(ctx, [1, 1, 0, 0])
        d += FuncDisp(lambda: d.add(d3))
        d.dispose()
        self.assertEqual(ctx, [1, 1, 0, 1])

    def test_order(self):
        ctx = [0, 0, 0, 0]
        order = itertools.count()
        d0, d1, d2, d3 = map(FuncDisp, (
            lambda: operator.setitem(ctx, 0, next(order)),
            lambda: operator.setitem(ctx, 1, next(order)),
            lambda: operator.setitem(ctx, 2, next(order)),
            lambda: operator.setitem(ctx, 3, next(order))))
        next(order)
        with CompDisp() as d:
            d.add(d0)
            d.add(d2)
            d.add(d1)
            d.add(d3)
            self.assertEqual(ctx, [0, 0, 0, 0])
        self.assertEqual(ctx, [4, 2, 3, 1])

    def test_async(self):
        with CompDisp() as d:
            future = d.__monad__().future()
            self.assertFalse(future.completed)
        self.assertTrue(future.completed)
        self.assertTrue(d.__monad__().future().completed)
