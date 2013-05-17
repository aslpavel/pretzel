"""Wrapped stream
"""
from .stream import Stream
from ..monad import async, do_return

__all__ = ('WrappedStream',)


class WrappedStream(Stream):
    """Wrapped stream

    Stream wrapped around base stream.
    """
    def __init__(self, base):
        Stream.__init__(self)
        self.initing()
        self.base = base

    def __getattr__(self, name):
        if self.disposed:
            raise ValueError('stream is disposed')
        return getattr(self.base, name)

    def fileno(self):
        if self.disposed:
            raise ValueError('stream is disposed')
        return self.base.fileno()

    @async
    def read(self, size):
        with self.reading:
            do_return((yield self.base.read(size)))

    @async
    def write(self, data):
        with self.writing:
            do_return((yield self.base.write(data)))

    def flush(self):
        if self.disposed:
            raise ValueError('stream is disposed')
        return self.base.flush()

    def dispose(self):
        if Stream.dispose(self):
            if self.base is not None:
                self.base.dispose()
            return True
        return False

    def detach(self):
        base, self.base = self.base, None
        if not self.dispose():
            raise ValueError('stream is disposed')
        return base

    def __str__(self):
        return ('{}({})'.format(type(self).__name__, self.base))
