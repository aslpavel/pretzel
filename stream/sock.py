"""Socket stream

Wraps python socket object and provides stream interface.
"""
import socket
import errno

from .file import File
from .buffered import BufferedStream
from ..monad import async, do_return
from ..core import POLL_READ, POLL_WRITE
from ..uniform import BrokenPipeError, BlockingErrorSet, PipeErrorSet

__all__ = ('Socket', 'BufferedSocket',)


class Socket(File):
    """Socket stream
    """
    def __init__(self, sock, init=None, core=None):
        self.sock = sock  # used by blocking method
        File.__init__(self, sock.fileno(), closefd=False, init=bool(init), core=core)

    @async
    def read(self, size):
        with self.reading:
            while True:
                try:
                    data = self.sock.recv(size)
                    if size and not data:
                        raise BrokenPipeError(errno.EPIPE, 'broken pipe')
                    do_return(data)
                except socket.error as error:
                    if error.errno not in BlockingErrorSet:
                        if error.errno in PipeErrorSet:
                            raise BrokenPipeError(error.errno, error.strerror)
                        raise
                yield self.core.poll(self.fd, POLL_READ)

    @async
    def write(self, data):
        with self.writing:
            while True:
                try:
                    do_return(self.sock.send(data))
                except socket.error as error:
                    if error.errno not in BlockingErrorSet:
                        if error.errno in PipeErrorSet:
                            raise BrokenPipeError(error.errno, error.strerror)
                        raise
                yield self.core.poll(self.fd, POLL_WRITE)

    @async
    def connect(self, address):
        with self.initing:
            try:
                self.sock.connect(address)
                do_return(self)
            except socket.error as error:
                if error.errno not in BlockingErrorSet:
                    raise
            yield self.core.poll(self.fd, POLL_WRITE)
            do_return(self)

    @async
    def accept(self):
        with self.reading:
            while True:
                try:
                    client, addr = self.sock.accept()
                    do_return((Socket(client, init=True, core=self.core), addr))
                except socket.error as error:
                    if error.errno not in BlockingErrorSet:
                        raise
                yield self.core.poll(self.fd, POLL_READ)

    def bind(self, address):
        with self.initing:
            return self.sock.bind(address)

    def listen(self, backlog):
        if self.disposed:
            raise ValueError('socket is disposed')
        return self.sock.listen(backlog)

    def shutdown(self, how):
        if self.disposed:
            raise ValueError('socket is disposed')
        return self.sock.shutdown(how)

    def dispose(self):
        if File.dispose(self):
            sock, self.sock = self.sock, None
            if sock:
                sock.close()
            return True
        return False

    @async
    def detach(self):
        sock, self.sock = self.sock, None
        if not self.dispose():
            raise ValueError('socket is disposed')
        self.blocking(True)
        return sock

    def blocking(self, enable=None):
        if enable is None:
            return self.sock.gettimeout() != 0.0
        self.sock.setblocking(enable)
        return enable


class BufferedSocket (BufferedStream):
    def __init__(self, sock, bufsize=None, init=None, core=None):
        BufferedStream.__init__(self, Socket(sock, init=init, core=core), bufsize)

    def detach(self):
        return BufferedStream.detach(self).detach()

    @async
    def accept(self):
        with self.reading:
            sock, addr = yield self.base.accept()
            do_return((BufferedSocket(sock.sock, self.bufsize, True, sock.core), addr))
