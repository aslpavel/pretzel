import random
import unittest
from ..alloc import StoreBlock, StoreAllocator

__all__ = ('StoreAllocatorTest',)


class StoreAllocatorTest(unittest.TestCase):
    """Store allocator unit tests
    """
    def test_stress(self):
        """Stress test for store allocator
        """
        alloc = StoreAllocator()
        size = 0
        blocks = []

        def reload():
            alloc.blocks = [StoreBlock.from_desc(block.to_desc()) for block in alloc.blocks]

        # fill
        for _ in range(1 << 16):
            order = random.randint(1, 10)
            size += 1 << order
            blocks.append(alloc.alloc_by_order(order))
        self.assertEqual(len(set(block.offset for block in blocks)), len(blocks))
        self.assertEqual(alloc.size, size)
        reload()

        # remove half
        for block in blocks[1 << 15:]:
            size -= block.size
            alloc.free(block)
        blocks = blocks[:1 << 15]
        self.assertEqual(len(set(block.offset for block in blocks)), len(blocks))
        self.assertEqual(alloc.size, size)
        reload()

        # add more
        for _ in range(1 << 15):
            order = random.randint(1, 10)
            size += 1 << order
            blocks.append(alloc.alloc_by_order(order))
        self.assertEqual(len(set(block.offset for block in blocks)), len(blocks))
        self.assertEqual(alloc.size, size)
        reload()

        # remove some
        for block in blocks[1 << 14:]:
            size -= block.size
            alloc.free(block)
        blocks = blocks[:1 << 14]
        self.assertEqual(len(set(block.offset for block in blocks)), len(blocks))
        self.assertEqual(alloc.size, size)
        reload()

        # remove all
        for block in blocks:
            size -= block.size
            alloc.free(block)
        self.assertEqual(size, 0)
        self.assertEqual(alloc.size, 0)
        reload()
