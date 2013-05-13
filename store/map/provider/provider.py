__all__ = ('BPTreeProvider',)


class BPTreeProvider(object):
    """BPTree Provider Interface
    """
    def size(self, value=None):
        """Count of key-value pairs inside B+Tree
        """
        raise NotImplementedError()

    def depth(self, value=None):
        """Depth of B+Tree
        """
        raise NotImplementedError()

    def root(self, value=None):
        """Root node of B+Tree
        """
        raise NotImplementedError()

    def order(self):
        """Order of B+Tree Node
        """
        raise NotImplementedError()

    def node_to_desc(self, node):
        """Get nodes descriptor
        """
        raise NotImplementedError()

    def desc_to_node(self, desc):
        """Get node by its descriptor
        """
        raise NotImplementedError()

    def create(self, keys, children, is_leaf):
        """Create new node
        """
        raise NotImplementedError()

    def dirty(self, node):
        """Mark node as dirty
        """
        raise NotImplementedError()

    def release(self, node):
        """Release node
        """
        raise NotImplementedError()

    def flush(self):
        """Flush provider
        """

    def dispose(self):
        """Dispose provider
        """
        self.flush()

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __iter__(self):
        """Iterate over all nodes
        """
        stack = [self.root()]
        while stack:
            node = stack.pop()
            yield node
            if not node.is_leaf:
                for desc in node.children:
                    stack.append(self.desc_to_node(desc))

    def __str__(self):
        return ('{}(size:{}, order:{}, depth:{}, root:{})'.format(type(self).__name__,
                self.size(), self.order(), self.depth(), self.root()))

    def __repr__(self):
        return str(self)
