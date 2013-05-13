from .bptree import BPTree
from .provider.store import StoreBPTreeProvider

__all__ = ('StoreMap',)


class StoreMap(BPTree):
    """B+Tree with store as back end
    """
    def __init__(self, store, header, order=None, key_type=None, value_type=None, compress=None):
        BPTree.__init__(self, StoreBPTreeProvider(store, header, order, key_type, value_type, compress))

    @property
    def header(self):
        return self.provider.header

    @property
    def store(self):
        return self.provider.store

    @property
    def size(self):
        """Size occupied on store
        """
        return self.provider.size_in_store()

    def flush(self, prune=None):
        """Flush dirty nodes to store
        """
        self.provider.flush(prune)

    def drop(self):
        """Completely delete mapping from the store
        """
        self.provider.drop()

    def dispose(self):
        """Flush dirty nodes to store
        """
        self.flush(prune=True)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return ('StoreMap(len:{}, size:{}, key_type:{}, val_type:{}, compress:{})'
                .format(len(self), self.size, self.provider.key_type,
                        self.provider.value_type, self.provider.compress))

    def __repr__(self):
        return str(self)
