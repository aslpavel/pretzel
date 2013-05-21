"""SSL Socket Stream
"""
import socket
import errno
try:
    import ssl
except ImportError:
    ssl = None  # no SSL support

from .sock import Socket
from .buffered import BufferedStream
from ..monad import async, do_return
from ..core import POLL_READ, POLL_WRITE
from ..common import BrokenPipeError, BlockingErrorSet, PipeErrorSet

__all__ = ('SocketSSL', 'BufferedSocketSSL')


class SocketSSL(Socket):
    """SSL Socket Stream

    If socket has already been connected it must be wrapped with
    ssl.wrap_socket, otherwise it will be wrapped when AsyncSSLSocket.Connect
    is finished.
    """
    def __init__(self, sock, ssl_options=None, init=None, core=None):
        self.ssl_options = ssl_options or {}
        Socket.__init__(self, sock, init, core)

    @async
    def read(self, size):
        with self.reading:
            while True:
                try:
                    data = self.sock.recv(size)
                    if size and not data:
                        raise BrokenPipeError(errno.EPIPE, 'broken pipe')
                    do_return(data)
                except ssl.SSLError as error:
                    if error.args[0] != ssl.SSL_ERROR_WANT_READ:
                        raise
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
                except ssl.SSLError as error:
                    if error.args[0] != ssl.SSL_ERROR_WANT_WRITE:
                        raise
                except socket.error as error:
                    if error.errno not in BlockingErrorSet:
                        if error.errno in PipeErrorSet:
                            raise BrokenPipeError(error.errno, error.strerror)
                        raise
                yield self.core.poll(self.fd, POLL_WRITE)

    @async
    def connect(self, address):
        yield Socket.connect(self, address)
        with self.writing, self.reading:
            self.sock = ssl.wrap_socket(self.sock, do_handshake_on_connect=False,
                                        **self.ssl_options)
            # do handshake
            while True:
                event = None
                try:
                    self.sock.do_handshake()
                    do_return(self)
                except ssl.SSLError as error:
                    if error.args[0] == ssl.SSL_ERROR_WANT_READ:
                        event = POLL_READ
                    elif error.args[0] == ssl.SSL_ERROR_WANT_WRITE:
                        event = POLL_WRITE
                    else:
                        raise
                yield self.core.poll(self.fd, event)

    @async
    def accept(self):
        with self.reading:
            while True:
                try:
                    client, addr = self.sock.accept()
                    context = getattr(self.sock, 'context', None)
                    if context:  # python >= 3.2
                        client = context.wrap_socket(client, server_side=True)
                    else:
                        client = ssl.wrap_socket(client, server_side=True,
                                                 **self.ssl_options)
                    do_return((SocketSSL(client, self.bufsize, self.ssl_options,
                               self.core), addr))
                except socket.error as error:
                    if error.errno not in BlockingErrorSet:
                        raise
                yield self.core.poll(self.fd, POLL_READ)


class BufferedSocketSSL(BufferedStream):
    def __init__(self, sock, bufsize=None, ssl_options=None, init=None, core=None):
        BufferedStream.__init__(self, SocketSSL(sock, ssl_options, init, core), bufsize)

    def detach(self):
        return BufferedStream.detach(self).detach()

    @async
    def accept(self):
        with self.reading:
            sock, addr = yield self.base.accept()
            do_return((BufferedSocketSSL(sock.Socket, self.bufsize,
                       sock.ssl_options, True, sock.core), addr))
