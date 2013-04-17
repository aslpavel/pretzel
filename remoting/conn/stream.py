"""Stream connection
"""
from .conn import Connection
from ...monad import async
from ...common import CanceledError, BrokenPipeError

__all__ = ('StreamConnection',)


class StreamConnection (Connection):
    """Stream based connected
    """
    def __init__(self, hub=None, core=None):
        Connection.__init__(self, hub, core)
        self.in_stream = None
        self.out_stream = None

    @async
    def do_connect(self, target):
        """Connect implementation

        Target is tuple of input and output streams.
        """
        @async
        def recv_coro():
            try:
                if self.in_stream.disposed:
                    return
                # Begin read next message before dispatching current one, as
                # connection may be closed during dispatching and input stream
                # became disposed.
                msg_next = self.in_stream.read_bytes().future()
                while True:
                    msg, msg_next = (yield msg_next), self.in_stream.read_bytes().future()
                    self.do_recv(msg)(lambda val: (not self.disposed) and val.trace())
            except (CanceledError, BrokenPipeError):
                pass
            finally:
                self.dispose()

        self.in_stream, self.out_stream = target
        recv_coro()()

    def do_disconnect(self):
        if self.in_stream is not None:
            self.in_stream.dispose()
        if self.out_stream is not None:
            self.out_stream.dispose()

    def do_send(self, msg):
        self.out_stream.write_bytes(msg)
        self.out_stream.flush()()
        return True

# vim: nu ft=python columns=120 :
