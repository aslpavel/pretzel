import unittest
from ..list import List

__all__ = ('MonadTest',)


class MonadTest(unittest.TestCase):
    def test_sequence(self):
        # sequence :: (Monad m) => [m a] -> m [a]
        self.assertEqual(List.sequence([List(1, 2), List(-1, -2)]),
                         List((1, -1), (1, -2), (2, -1), (2, -2)))

    def test_map(self):
        # map :: (Monad m) => (a -> m a) -> [a] -> m [a]
        self.assertEqual(List.map(lambda a: List(-a, a), [1, 2]),
                         List((-1, -2), (-1, 2), (1, -2), (1, 2)))

    def test_filter(self):
        # filter :: (Monad m) => (a -> m Bool) -> [a] -> m [a]
        self.assertEqual(List.filter(lambda a: List(a % 2 == 0), range(10)),
                         List((0, 2, 4, 6, 8),))

    def test_fold(self):
        # fold :: (Monad m) => (a -> b -> m a) -> a -> [b] -> m a
        self.assertEqual(List.fold(lambda a, b: List(a + b), 0, range(10)),
                         List(45))

    def test_lift_func(self):
        # lift_func :: (Monad m) => (a0 -> ... -> r) -> (m a0 -> ... -> m r)
        list_add = List.lift_func(lambda a, b: a + b)
        self.assertEqual(list_add(List(0, 1), List(0, 1)), List(0, 1, 1, 2))

    def test_ap(self):
        # ap :: (Monad a) => m (a -> b) -> (m a -> m b)
        self.assertEqual(List.ap(List(lambda a: a*2))(List(1, 2)), List(2, 4))
