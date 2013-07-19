import unittest
from ..utils import lazy, cached, curry

__all__ = ('UtilsTest',)


class UtilsTest(unittest.TestCase):
    def test_lazy(self):
        @lazy
        def lazy_val():
            calls[0] += 1
            return 'value'
        calls = [0]
        self.assertEqual(calls, [0])

        self.assertEqual(lazy_val(), 'value')
        self.assertEqual(calls, [1])

        self.assertEqual(lazy_val(), 'value')
        self.assertEqual(calls, [1])

    def test_cached(self):
        @cached
        def func(arg):
            args.append(arg)
            return arg
        args = []

        self.assertEqual(func(1), 1)
        self.assertEqual(args, [1])

        self.assertEqual(func(1), 1)
        self.assertEqual(args, [1])

        self.assertEqual(func(2), 2)
        self.assertEqual(args, [1, 2])

        self.assertEqual(func(1), 1)
        self.assertEqual(args, [1, 2])

    def test_curry(self):
        @curry(2)
        def add(a, b):
            return a + b

        self.assertEqual(add(1)(2), 3)
        self.assertEqual(add(1, 2), 3)
