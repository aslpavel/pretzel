"""Stream connection
"""
from .conn import Connection
from ...monad import async
from ...common import CanceledError, BrokenPipeError

__all__ = ('StreamConnection',)


class StreamConnection(Connection):
    """Stream based connected
    """
    def __init__(self, hub=None, core=None):
        Connection.__init__(self, hub=hub, core=core)
        self.reader = None
        self.writer = None

    @async
    def do_connect(self, target):
        """Connect implementation

        Target is tuple of input and output streams.
        """
        @async
        def recv_coro():
            try:
                if self.reader.disposed:
                    return
                # Begin read next message before dispatching current one, as
                # connection may be closed during dispatching and input stream
                # became disposed.
                msg_next = self.reader.read_bytes().future()
                while True:
                    msg, msg_next = (yield msg_next), self.reader.read_bytes().future()
                    self.do_recv(msg)()
            except (CanceledError, BrokenPipeError):
                pass
            finally:
                self.dispose()

        self.reader, self.writer = target
        recv_coro()()

    def do_disconnect(self):
        if self.reader is not None:
            self.reader.dispose()
        if self.writer is not None:
            self.writer.dispose()

    def do_send(self, msg):
        self.writer.write_bytes(msg)
        self.writer.flush()()
        return True
