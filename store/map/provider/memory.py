"""In memory B+Tree provider

Mainly for testing purposes.
"""
from .provider import BPTreeProvider
from ..bptree import BPTreeNode, BPTreeLeaf

__all__ = ('MemoryBPTreeProvider',)


class MemoryBPTreeProvider(BPTreeProvider):
    """In memory B+Tree Provider
    """
    def __init__(self, order):
        self.root_st = self.create([], [], True)
        self.size_st = 0
        self.depth_st = 1
        self.order_st = order

    def size(self, value=None):
        if value is not None:
            self.size_st = value
        return self.size_st

    def depth(self, value=None):
        if value is not None:
            self.depth_st = value
        return self.depth_st

    def order(self):
        return self.order_st

    def root(self, value=None):
        if value is not None:
            self.root_st = value
        return self.root_st

    def node_to_desc(self, node):
        return node

    def desc_to_node(self, desc):
        return desc

    def create(self, keys, children, is_leaf):
        return (BPTreeLeaf(keys, children) if is_leaf else
                BPTreeNode(keys, children))

    def dirty(self, node):
        pass

    def release(self, node):
        pass
