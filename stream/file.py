"""File stream

File stream is stream created from file descriptor.
"""
import os
import errno
import fcntl
from .stream import Stream
from .buffered import BufferedStream
from ..core import Core, POLL_READ, POLL_WRITE
from ..monad import async, do_return
from ..uniform import BrokenPipeError, BlockingErrorSet, PipeErrorSet

__all__ = ('File', 'BufferedFile', 'fd_close_on_exec', 'fd_blocking',)


class File(Stream):
    """File stream

    File stream is stream created from file descriptor.
    """
    def __init__(self, fd, closefd=None, init=None, core=None):
        Stream.__init__(self)

        self.fd = fd if isinstance(fd, int) else fd.fileno()
        self.closefd = closefd is None or closefd
        self.core = core or Core.local()
        self.blocking(False)
        if init is None or init:
            self.initing()

    def fileno(self):
        return self.fd

    @async
    def read(self, size):
        with self.reading:
            while True:
                try:
                    data = os.read(self.fd, size)
                    if size and not data:
                        raise BrokenPipeError(errno.EPIPE, 'broken pipe')
                    do_return(data)
                except OSError as error:
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
                    do_return(os.write(self.fd, data))
                except OSError as error:
                    if error.errno not in BlockingErrorSet:
                        if error.errno in PipeErrorSet:
                            raise BrokenPipeError(error.errno, error.strerror)
                        raise
                yield self.core.poll(self.fd, POLL_WRITE)

    def dispose(self):
        if Stream.dispose(self):
            fd, self.fd = self.fd, -1
            self.core.poll(fd, None)()  # resolve with BrokenPipeError
            if self.closefd:
                os.close(fd)
            return True
        return False

    def detach(self):
        if self.disposed:
            raise ValueError('file is disposed')
        try:
            self.closefd = False
            self.blocking(True)
            return self.fd
        finally:
            self.dispose()

    def blocking(self, enable=None):
        return fd_blocking(self.fd, enable)

    def close_on_exec(self, enable=None):
        return fd_close_on_exec(self.fd, enable)

    def __str__(self):
        flags = []
        if self.fd > 0:
            self.blocking() and flags.append('blocking')
            self.close_on_exec() and flags.append('close_on_exec')
        return ('{}(fd:{}, flags:{}, state:{})'.format(type(self).__name__,
                self.fd, ','.join(flags), self.state.state_name()))

    def __repr__(self):
        return str(self)


class BufferedFile(BufferedStream):
    def __init__(self, fd, bufsize=None, closefd=None, core=None):
        BufferedStream.__init__(self, File(fd, closefd, True, core), bufsize)

    def detach(self):
        return BufferedStream.detach(self).detach()


def fd_close_on_exec(fd, enable=None):
    """Set or get file descriptors close_on_exec flag
    """
    return fd_option(fd, fcntl.F_GETFD, fcntl.F_SETFD, fcntl.FD_CLOEXEC, enable)


def fd_blocking(fd, enable=None):
    """Set or get file descriptors blocking flag
    """
    return not fd_option(fd, fcntl.F_GETFL, fcntl.F_SETFL, os.O_NONBLOCK,
                         None if enable is None else not enable)


def fd_option(fd, get_flag, set_flag, option_flag, enable=None):
    """Set or get file descriptor option
    """
    options = fcntl.fcntl(fd, get_flag)
    if enable is None:
        return bool(options & option_flag)
    elif enable:
        options |= option_flag
    else:
        options &= ~option_flag
    fcntl.fcntl(fd, set_flag, options)
    return enable
