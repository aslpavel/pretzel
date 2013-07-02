import unittest
from ..utils import lazy

__all__ = ('LazyTest',)


class LazyTest(unittest.TestCase):
    def test(self):
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
