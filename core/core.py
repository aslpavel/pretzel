"""Core is an Asynchronous I/O and Timer execution loop
"""
import os
import sys
import errno
import itertools
import threading
from time import time
from heapq import heappush, heappop
if sys.version_info[0] > 2:
    from _thread import get_ident
else:
    from thread import get_ident

from .poll import Poller, POLL_ERROR, POLL_READ, POLL_WRITE, POLL_DISCONNECT
from ..common import BrokenPipeError, ConnectionError, CanceledError, BlockingErrorSet
from ..monad import Result, async, async_block
from ..state_machine import StateMachine

__all__ = ('Core',)

"""
Core's maximum timeout for sleeping inside poll. It easier to manipulate positive
timeout then doing branching with negative values. And waking up once in a while
won't hurt.
"""
CORE_TIMEOUT = 3600.0


class Core(object):
    """Core object

    Asynchronous I/O and Timer execution loop. Executes until all requested
    asynchronous operation are completed or when object itself is disposed.
    All interaction with the Core must be done from that Core's thread,
    exception are schedule() and wake().
    """

    STATE_IDLE = 0
    STATE_EXEC = 1
    STATE_DISP = 2
    STATE_NAMES = ('idle', 'executing', 'disposed',)
    STATE_GRPAH = StateMachine.compile_graph({
        STATE_IDLE: (STATE_IDLE, STATE_EXEC, STATE_DISP),
        STATE_EXEC: (STATE_IDLE, STATE_DISP),
        STATE_DISP: (STATE_DISP,),
    })

    inst_lock = threading.RLock()
    inst_local = threading.local()
    inst_main = None

    def __init__(self, poller=None):
        self.state = StateMachine(self.STATE_GRPAH, self.STATE_NAMES)
        self.thread_ident = None

        self.poller = Poller.from_name(poller)
        self.files = {}
        self.timer = Timer()
        self.sched = Scheduler(self)
        self.waker = Waker(self)

    @classmethod
    def main(cls, inst=None):
        """Main core instance
        """
        with cls.inst_lock:
            if inst is None:
                if cls.inst_main is None:
                    cls.inst_main = Core()
                inst = cls.inst_main
            else:
                cls.inst_main = inst
        return inst

    @classmethod
    def local(cls, inst=None):
        """Thread local instance
        """
        if inst is None:
            inst = getattr(cls.inst_local, 'inst', None)
            if inst is None:
                return cls.local(cls.main())
        else:
            cls.inst_local.inst = inst
        return inst

    def sleep(self, delay):
        """Sleep

        Interrupt current coroutine for specified amount of time
        """
        return self.timer.on(time() + delay)

    def sleep_until(self, when):
        """Sleep until

        Interrupt current coroutine until specified time is reached
        """
        return self.timer.on(when)

    def poll(self, fd, mask):
        """Poll file descriptor

        Poll file descriptor for events specified by mask. If mask is None then
        specified descriptor is unregistered and all pending events are resolved
        with BrokenPipeError, otherwise future is resolved with bitmap of the
        events happened on file descriptor or error if any.
        """
        file = self.files.get(fd)
        if file is None:
            file = File(fd, self.poller)
            self.files[fd] = file
        return file.on(mask)

    def schedule(self):
        """Schedule continuation to be executed on this core

        Scheduled continuation will be executed on next iteration circle. This
        function can be called from different thread.
        """
        if self.thread_ident == get_ident():
            return self.timer.on(0)
        else:
            return self.sched.on()

    def wake(self):
        if self.thread_ident != get_ident():
            self.waker()

    def __call__(self, dispose=False):
        return self.start()

    def start(self, dispose=False):
        """Start core execution
        """
        self.state(self.STATE_EXEC)
        try:
            for _ in self.iterator():
                if self.state.state != self.STATE_EXEC:
                    break
        finally:
            if self.state.state != self.STATE_DISP:
                if dispose:
                    self.dispose()
                else:
                    self.state(self.STATE_IDLE)

    def stop(self):
        """Stop core execution
        """
        return self.state(self.STATE_IDLE)

    def iterator(self, block=True):
        """Core's iterator

        Starts new iteration loop. Returns generator object which yield at the
        beginning of each iteration.
        """

        top_level = False
        try:
            # Thread identity is used by wake() to make sure call to waker is
            # really needed. And it also used to make sure core is iterating only
            # on one thread.
            with self.inst_lock:
                if self.thread_ident is None:
                    self.thread_ident = get_ident()
                    top_level = True
                elif self.thread_ident != get_ident():
                    raise ValueError('core has already being run on a different thread')

            timer = self.timer
            files = self.files
            sched = self.sched
            poll = self.poller.poll

            events = tuple()
            while True:
                for fd, event in events:
                    files[fd](event)
                timer(time())
                sched()

                # Yield control to check conditions before blocking (Core has been
                # stopped or desired future resolved). If there is no file
                # descriptors registered and timeout is negative poller will raise
                # StopIteration and break this loop.
                yield

                events = (poll(0) if not block else
                          poll(min(timer.timeout(time()), sched.timeout())))
        finally:
            if top_level:
                self.thread_ident = None

    def __iter__(self):
        return iter(self.iterator())

    def dispose(self, exc=None):
        if not self.state(self.STATE_DISP):
            return

        exc = exc or CanceledError('core has been disposed')
        files, self.files = self.files, {}
        for file in files.values():
            file.dispose(exc)
        self.timer.dispose(exc)
        self.sched.dispose(exc)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose(eo)
        return False

    def __str__(self):
        return '<{} [state:{}] at {}>'.format(type(self).__name__,
                                              self.state.state_name(), id(self))

    def __repr__(self):
        return str(self)


class Timer(object):
    """Timer dispatch object
    """
    __slots__ = ('queue', 'uid',)

    def __init__(self):
        self.uid = itertools.count()
        self.queue = []

    def on(self, when):
        return async_block(lambda ret: heappush(self.queue, (when, next(self.uid), ret)))

    def __call__(self, now):
        if not self.queue:
            return

        queue = []
        while self.queue:
            when, _, ret = self.queue[0]
            if when > now:
                break
            queue.append(heappop(self.queue))
        for when, _, ret in queue:
            ret(when)

    def timeout(self, now):
        if self.queue:
            return min(CORE_TIMEOUT, max(0, self.queue[0][0] - now))
        else:
            return CORE_TIMEOUT

    def dispose(self, exc=None):
        error = Result.from_exception(exc or CanceledError('timer has been disposed'))
        queue, self.queue = self.queue, []
        for when, _, ret in queue:
            ret(error)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False


class File(object):
    """File dispatch object
    """
    __slots__ = ('fd', 'poller', 'mask', 'handlers',)

    def __init__(self, fd, poller):
        self.fd = fd
        self.poller = poller
        self.mask = 0
        self.handlers = []

    def on(self, mask):
        @async_block
        def register(ret):
            if mask is None:
                self.dispose(BrokenPipeError(errno.EPIPE, 'detached from core'))
                ret(None)
            elif not mask:
                raise ValueError('empty mask')
            elif self.mask & mask:
                raise ValueError('intersecting mask')
            else:
                if self.mask:
                    self.poller.modify(self.fd, self.mask | mask)
                else:
                    self.poller.register(self.fd, mask)
                self.mask |= mask
                self.handlers.append((mask, ret))
        return register

    def off(self, mask):
        if not (mask & self.mask):
            return []

        disable, enable = [], []
        for msk, ret in self.handlers:
            if msk & mask:
                self.mask &= ~msk
                disable.append(ret)
            else:
                enable.append((msk, ret))
        if self.mask:
            self.poller.modify(self.fd, self.mask)
        else:
            self.poller.unregister(self.fd)

        self.handlers = enable
        return disable

    def __call__(self, mask):
        if mask & ~POLL_ERROR:
            for ret in self.off(mask):
                ret(mask)
        else:
            exc = (BrokenPipeError(errno.EPIPE, 'broken pipe') if mask & POLL_DISCONNECT else
                   ConnectionError())
            self.dispose(exc)

    def dispose(self, exc=None):
        error = Result.from_exception(exc or CanceledError('file has been disposed'))
        for ret in self.off(self.mask):
            ret(error)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        flags = ','.join(name for flag, name in ((POLL_READ, 'read'),
                        (POLL_WRITE, 'write'), (POLL_ERROR, 'error')) if self.mask & flag)
        return '<{} [fd:{} flags:{}] at {}>'.format(type(self).__name__, self.fd, flags, id(self))

    def __repr__(self):
        return str(self)


class Scheduler(object):
    """Scheduler object

    Schedules continuation to be executed on specified core
    """
    def __init__(self, core):
        self.rets = []
        self.rets_lock = threading.RLock()

    def on(self):
        @async_block
        def schedule(ret):
            with self.rets_lock:
                self.rets.append(ret)
            self.core.wake()
        return schedule

    def __call__(self):
        with self.rets_lock:
            rets, self.rets = self.rets, []
        for ret in self.rets:
            ret(self.core)

    def timeout(self):
        return 0 if self.rets else CORE_TIMEOUT

    def dispose(self, exc=None):
        error = Result.from_exception(exc or CanceledError('scheduler has been disposed'))
        with self.rets_lock:
            rets, self.rets = self.rets, []
        for ret in self.rets:
            ret(error)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False


class Waker(object):
    """Core waker
    """
    def __init__(self, core):
        self.core = core
        self.reader, self.writer = os.pipe()

        from ..stream.file import fd_blocking, fd_close_on_exec
        fd_blocking(self.reader, False)
        fd_blocking(self.writer, False)
        fd_close_on_exec(self.reader, True)
        fd_close_on_exec(self.writer, True)

        @async
        def consumer():
            """Consumer coroutine"""
            try:
                while True:
                    try:
                        data = os.read(self.reader, 65536)
                        if not data:
                            break
                    except OSError as error:
                        if error.errno not in BlockingErrorSet:
                            break
                    yield self.core.poll(self.reader, POLL_READ)
            finally:
                self.dispose()
        consumer()()

    def __call__(self):
        try:
            os.write(self.writer, b'\x00')
        except OSError as error:
            if error.errno not in BlockingErrorSet:
                raise

    def dispose(self):
        reader, self.reader = self.reader, -1
        if reader >= 0:
            os.close(reader)
            self.core.poll(reader, None)
        writer, self.writer = self.writer, -1
        if writer >= 0:
            os.close(writer)
            self.core.poll(writer, None)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

# vim: nu ft=python columns=120 :
