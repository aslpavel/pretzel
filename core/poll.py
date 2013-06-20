import errno
import select
from .. import PRETZEL_POLLER

__all__ = ('Poller', 'POLL_READ', 'POLL_WRITE', 'POLL_URGENT', 'POLL_DISCONNECT', 'POLL_ERROR',)

EPOLLIN = 0x001
EPOLLPRI = 0x002
EPOLLOUT = 0x004
EPOLLRDNORM = 0x040
EPOLLRDBAND = 0x080
EPOLLWRNORM = 0x100
EPOLLWRBAND = 0x200
EPOLLMSG = 0x400
EPOLLERR = 0x008
EPOLLHUP = 0x010
EPOLLRDHUP = 0x2000
EPOLLONESHOT = 1 << 30
EPOLLET = 1 << 31

POLL_READ = EPOLLIN
POLL_WRITE = EPOLLOUT
POLL_URGENT = EPOLLPRI
POLL_ERROR = EPOLLERR | EPOLLHUP
POLL_DISCONNECT = EPOLLHUP


class Poller (object):
    @classmethod
    def from_name(cls, name=None):
        name = name or PRETZEL_POLLER

        if name == 'epoll' and hasattr(select, 'epoll'):
            return EPollPoller()
        elif name == 'kqueue' and hasattr(select, 'kqueue'):
            return KQueuePoller()
        elif name == 'select':
            return SelectPoller()

        raise NotImplementedError('poller method is not support: {}'.format(name))

    def register(self, fd, mask):
        raise NotImplementedError()

    def modify(self, fd, mask):
        raise NotImplementedError()

    def unregister(self, fd):
        raise NotImplementedError()

    def poll(self, timeout):
        raise NotImplementedError()

    def dispose(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return '{}()'.format(type(self).__name__)

    def __repr__(self):
        return str(self)


class EPollPoller (Poller):
    """Poller base on epoll
    """
    def __init__(self):
        self.fds = {}
        self.epoll = select.epoll()

        from ..stream.file import fd_close_on_exec
        fd_close_on_exec(self.epoll.fileno(), True)

    def register(self, fd, mask):
        self.epoll.register(fd, mask)
        self.fds.setdefault(fd, True)

    def modify(self, fd, mask):
        self.epoll.modify(fd, mask)

    def unregister(self, fd):
        if self.fds.pop(fd, None):
            self.epoll.unregister(fd)

    def poll(self, timeout):
        if not self.fds and timeout < 0:
            raise StopIteration()  # would have blocked indefinitely

        try:
            return self.epoll.poll(timeout)
        except (IOError, OSError) as error:
            if error.errno == errno.EINTR:
                return tuple()
            raise

    def dispose(self):
        self.epoll.close()

    def __str__(self):
        return '{}(fds:{}, fd:{})'.format(type(self).__name__, len(self.fds),
                                          self.epoll.fileno())


class SelectPoller(Poller):
    """Poller base on select
    """
    SUPPORTED_MASK = POLL_READ | POLL_WRITE

    def __init__(self):
        self.read = set()
        self.write = set()
        self.error = set()

    def register(self, fd, mask):
        if mask | self.SUPPORTED_MASK != self.SUPPORTED_MASK:
            raise ValueError('unsupported event mask: {}'.format(mask))

        self.error.add(fd)
        if mask & POLL_READ:
            self.read.add(fd)
        if mask & POLL_WRITE:
            self.write.add(fd)

    def modify(self, fd, mask):
        self.unregister(fd)
        self.register(fd, mask)

    def unregister(self, fd):
        self.read.discard(fd)
        self.write.discard(fd)
        self.error.discard(fd)

    def poll(self, timeout):
        if not self.error and timeout < 0:
            raise StopIteration()  # would have blocked indefinitely

        try:
            read, write, error = select.select(self.read, self.write, self.error,
                                               timeout if timeout >= 0 else None)
        except (OSError, IOError) as error:
            if error.errno == errno.EINTR:
                return tuple()
            raise
        except select.error as error:
            if error.args[0] == errno.EINTR:
                return tuple()
            raise

        events = {}
        for fd in read:
            events[fd] = events.get(fd, 0) | POLL_READ
        for fd in write:
            events[fd] = events.get(fd, 0) | POLL_WRITE
        for fd in error:
            events[fd] = events.get(fd, 0) | POLL_ERROR

        return events.items()

    def __str__(self):
        return '{}(read:{}, write:{})'.format(type(self).__name__,
                                              len(self.read), len(self.write))


class KQueuePoller(SelectPoller):
    pass
