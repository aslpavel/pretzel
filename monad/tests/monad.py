import unittest
from ..list import List

__all__ = ('MonadTest',)


class MonadTest(unittest.TestCase):
    def test_sequence(self):
        # Sequence :: (Monad m) => [m a] -> m [a]
        self.assertEqual(List.Sequence([List(1, 2), List(-1, -2)]),
                         List((1, -1), (1, -2), (2, -1), (2, -2)))

    def test_map(self):
        # Map :: (Monad m) => (a -> m a) -> [a] -> m [a]
        self.assertEqual(List.Map(lambda a: List(-a, a), [1, 2]),
                         List((-1, -2), (-1, 2), (1, -2), (1, 2)))

    def test_filter(self):
        # Filter :: (Monad m) => (a -> m Bool) -> [a] -> m [a]
        self.assertEqual(List.Filter(lambda a: List(a % 2 == 0), range(10)),
                         List((0, 2, 4, 6, 8),))

    def test_fold(self):
        # Fold :: (Monad m) => (a -> b -> m a) -> a -> [b] -> m a
        self.assertEqual(List.Fold(lambda a, b: List(a + b), 0, range(10)),
                         List(45))

    def test_lift_func(self):
        # LiftFunc :: (Monad m) => (a0 -> ... -> r) -> (m a0 -> ... -> m r)
        list_add = List.LiftFunc(lambda a, b: a + b)
        self.assertEqual(list_add(List(0, 1), List(0, 1)), List(0, 1, 1, 2))

    def test_ap(self):
        # Ap :: (Monad a) => m (a -> b) -> (m a -> m b)
        self.assertEqual(List.Ap(List(lambda a: a * 2))(List(1, 2)), List(2, 4))
