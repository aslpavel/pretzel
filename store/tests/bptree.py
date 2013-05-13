import io
import random
import unittest
from ..map.bptree import BPTree
from ..map.provider.memory import MemoryBPTreeProvider
from ..map.provider.store import StoreBPTreeProvider
from ..store import StreamStore

__all__ = ('BPTreeTest',)


class BPTreeTest(unittest.TestCase):
    """B+Tree unit tests
    """
    def test_consist(self):
        """B+Tree consistency tests
        """
        provider = self.provider()
        tree, std = BPTree(provider), {}

        # compare tree and map mappings
        def validate(tree):
            self.assertEqual(len(tree), len(list(tree)))
            self.assertEqual(len(tree), len(std))
            for k, v in tree.items():
                self.assertEqual(std.get(k), v)
            for k, v in std.items():
                self.assertEqual(tree.get(k), v)

        # item count
        count = 1 << 10

        # reload
        provider = self.provider(provider)
        tree = BPTree(provider)
        validate(tree)

        # Insertion(10 .. 1024)
        for i in range(10, count):
            tree[i], std[i] = str(i), str(i)
        validate(tree)

        # reload
        provider = self.provider(provider)
        tree = BPTree(provider)
        validate(tree)

        # Insert(0 .. 10)
        for i in range(0, 10):
            tree[i], std[i] = str(i), str(i)
        validate(tree)

        # reload
        provider = self.provider(provider)
        tree = BPTree(provider)
        validate(tree)

        # Range
        self.assertEqual(list(tree[100:201]), [(key, str(key)) for key in range(100, 202)])
        self.assertEqual(list(tree[:100]), [(key, str(key)) for key in range(0, 101)])
        self.assertEqual(list(tree[101:102.5]), [(101, '101'), (102, '102')])
        self.assertEqual(list(tree[1022:]), [(1022, '1022'), (1023, '1023')])
        self.assertEqual(list(tree[100:10]), [])

        # Deletion
        keys = list(range(count))
        half = len(keys) >> 1
        random.shuffle(keys)
        for i in keys[:half]:
            self.assertEqual(tree.pop(i), std.pop(i))
        validate(tree)

        # reload
        provider = self.provider(provider)
        tree = BPTree(provider)
        validate(tree)

        for i in keys[half:]:
            self.assertEqual(tree.pop(i), std.pop(i))
        self.assertEqual(len(tree), 0)
        validate(tree)

        # reload
        provider = self.provider(provider)
        tree = BPTree(provider)
        validate(tree)

        return provider

    def provider(self, provider=None):
        """Memory B+Tree provider
        """
        if provider is None:
            return MemoryBPTreeProvider(order=7)
        return provider


class StoreBPTreeTest(BPTreeTest):
    """B+Tree with store provider unit tests
    """
    def provider(self, provider=None):
        """Store B+Tree provider
        """
        if provider is None:
            store = StreamStore(io.BytesIO())
        else:
            provider.flush()
            provider.store.flush()
            store = StreamStore(provider.store.stream)
        return StoreBPTreeProvider(store, store.create_cell('::test'), order=7)

    def test_consist(self):
        provider = BPTreeTest.test_consist(self)
        provider.drop()
        self.assertEqual(provider.store.size, 0)
