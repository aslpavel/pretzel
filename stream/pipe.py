import os
from .file import BufferedFile

__all__ = ('Pipe',)


class Pipe (object):
    """Asynchronous pipe wrapper
    """
    def __init__(self, fds=None, buffer_size=None, core=None):
        if fds is None:
            reader_fd, writer_fd = os.pipe()
            self.reader = BufferedFile(reader_fd, buffer_size, True, core)
            self.writer = BufferedFile(writer_fd, buffer_size, True, core)
        else:
            self.reader = None
            if fds[0] is not None:
                self.reader = BufferedFile(fds[0], buffer_size, False, core)
            self.writer = None
            if fds[1] is not None:
                self.writer = BufferedFile(fds[1], buffer_size, False, core)

    def detach_reader(self, fd=None, blocking=None, close_on_exec=None):
        """Detach read and close write descriptors
        """
        return self._detach(self.reader, fd, blocking, close_on_exec)

    def detach_writer(self, fd=None, blocking=None, close_on_exec=None):
        """Detach write and close read descriptors
        """
        return self._detach(self.writer, fd, blocking, close_on_exec)

    def _detach(self, stream, fd=None, blocking=None, close_on_exec=None):
        if stream is None:
            raise ValueError('pipe is disposed')

        stream.blocking(blocking is None or blocking)
        stream.close_on_exec(close_on_exec)
        stream_fd = stream.detach()
        self.dispose()

        if fd is None or fd == stream_fd:
            return stream_fd
        else:
            os.dup2(stream_fd, fd)
            os.close(stream_fd)
            return fd

    def dispose(self):
        reader, self.reader = self.reader, None
        if reader is not None:
            reader.dispose()
        writer, self.writer = self.writer, None
        if writer is not None:
            writer.dispose()

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return 'Pipe(reader:{}, writer:{})'.format(self.reader, self.writer)

    def __rerp__(self):
        return str(self)
