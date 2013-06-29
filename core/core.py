"""Core is an asynchronous execution loop
"""
import os
import sys
import errno
import signal
import itertools
import threading
from time import time
from heapq import heappush, heappop
if sys.version_info[0] > 2:
    from _thread import get_ident
else:  # pragma: no cover
    from thread import get_ident

from .poll import Poller, POLL_ERROR, POLL_READ, POLL_WRITE, POLL_DISCONNECT
from ..uniform import BrokenPipeError, ConnectionError, CanceledError, BlockingErrorSet
from ..monad import Result, async, async_block, do_done
from ..state_machine import StateMachine
from ..dispose import CompDisp

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
        self.tick = 0
        self.state = StateMachine(self.STATE_GRPAH, self.STATE_NAMES)

        self.files_queue = {}
        self.time_queue = TimeQueue()
        self.sched_queue = SchedQueue(self)
        self.proc_queue = ProcQueue(self)

        self.thread_ident = None
        self.poller = Poller.from_name(poller)
        self.waker = Waker(self)

        def dispose_core():
            if not self.state(self.STATE_DISP):
                return
            try:
                exc = CanceledError('core has been disposed')
                files_queue, self.files_queue = self.files_queue, {}
                for file in files_queue.values():
                    file.dispose(exc)
                self.time_queue.dispose(exc)
                self.sched_queue.dispose(exc)
                self.proc_queue.dispose(exc)
            finally:
                self.waker.dispose()
                self.poller.dispose()
        self.dispose = CompDisp()
        self.dispose.add_action(dispose_core)

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

    @async
    def sleep(self, delay):
        """Sleep

        Interrupt current coroutine for specified amount of time
        """
        if self.state.state == self.STATE_DISP:
            raise CanceledError('core is disposed')
        do_done(self.time_queue.on(time() + delay))

    @async
    def sleep_until(self, when):
        """Sleep until

        Interrupt current coroutine until specified time is reached
        """
        if self.state.state == self.STATE_DISP:
            raise CanceledError('core is disposed')
        do_done(self.time_queue.on(when))

    @async
    def poll(self, fd, mask):
        """Poll file descriptor

        Poll file descriptor for events specified by mask. If mask is None then
        specified descriptor is unregistered and all pending events are resolved
        with BrokenPipeError, otherwise future is resolved with bitmap of the
        events happened on file descriptor or error if any.
        """
        if mask is not None and self.state.state == self.STATE_DISP:
            raise CanceledError('core is disposed')
        file = self.files_queue.get(fd)
        if file is None:
            file = FileQueue(fd, self.poller)
            self.files_queue[fd] = file
        do_done(file.on(mask))

    @async
    def schedule(self):
        """Schedule continuation to be executed on this core

        Scheduled continuation will be executed on next iteration circle. This
        function can be called from different thread, but not from signal handler
        as heappush used by time_queue is not reentrant. Returns this core object.
        """
        if self.state.state == self.STATE_DISP:
            raise CanceledError('core is disposed')
        if self.thread_ident == get_ident():
            do_done(self.time_queue.on(0).then_val(self))
        else:
            do_done(self.sched_queue.on())

    @async
    def waitpid(self, pid):
        """Wait pid

        Schedule continuation to be executed when process with pid is terminated.
        """
        if self.state.state == self.STATE_DISP:
            raise CanceledError('core is disposed')
        do_done(self.proc_queue.on(pid))

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
        if self.state.state == self.STATE_DISP:
            raise RuntimeError('core is disposed')

        top_level = False
        wakeup_fd = None
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

            # Install signal wakeup file descriptor
            try:
                wakeup_fd = signal.set_wakeup_fd(self.waker.fileno())
            except ValueError:
                pass # non-main thread

            timer = self.time_queue
            files = self.files_queue
            sched = self.sched_queue
            proc = self.proc_queue
            poll = self.poller.poll

            events = tuple()
            while True:
                for fd, event in events:
                    files[fd](event)
                timer(time())
                sched()
                proc()

                # Yield control to check conditions before blocking (Core has been
                # stopped or desired future resolved). If there is no file
                # descriptors registered and timeout is negative poller will raise
                # StopIteration and break this loop.
                yield

                events = (poll(0) if not block else
                          poll(min(timer.timeout(time()), sched.timeout())))
                self.tick += 1
        finally:
            if wakeup_fd is not None:
                signal.set_wakeup_fd(wakeup_fd)
            if top_level:
                self.thread_ident = None

    def __iter__(self):
        return iter(self.iterator())

    @property
    def disposed(self):
        return self.state.state == self.STATE_DISP

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return '{}(state:{}, tick:{})'.format(type(self).__name__,
                                              self.state.state_name(), self.tick)

    def __repr__(self):
        return str(self)


class TimeQueue(object):
    """Time queue

    Schedule continuation to be executed when specified time is reached.
    """
    __slots__ = ('queue', 'uid',)

    def __init__(self):
        self.uid = itertools.count()  # used to distinguish simultaneous continuations
        self.queue = []

    def on(self, when):
        return async_block(lambda ret:
                           heappush(self.queue, (when, next(self.uid), ret)))

    def __call__(self, time_now):
        if not self.queue:
            return
        resolved = []
        while self.queue:
            time_when, _, ret = self.queue[0]
            if time_when > time_now:
                break
            resolved.append(heappop(self.queue))
        for time_when, _, ret in resolved:
            ret(time_when)

    def timeout(self, now):
        if self.queue:
            return min(CORE_TIMEOUT, max(0, self.queue[0][0] - now))
        else:
            return CORE_TIMEOUT

    def dispose(self, exc=None):
        error = Result.from_exception(exc or CanceledError('time queue has been disposed'))
        queue, self.queue = self.queue, []
        for when, _, ret in queue:
            ret(error)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __len__(self):
        return len(self.queue)

    def __str__(self):
        return 'TimeQueue(len:{})'.format(len(self))

    def __repr__(self):
        return str(self)


class FileQueue(object):
    """File queue

    Schedule continuation to be executed when specified file descriptor
    conditions are met.
    """
    __slots__ = ('fd', 'poller', 'mask', 'handlers',)

    def __init__(self, fd, poller):
        self.fd = fd
        self.poller = poller
        self.mask = 0
        self.handlers = []

    def on(self, mask):
        @async_block
        def cont(ret):
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
        return cont

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
        error = Result.from_exception(exc or CanceledError('file queue has been disposed'))
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
        return '{}(fd:{}, flags:{})'.format(type(self).__name__, self.fd, flags)

    def __repr__(self):
        return str(self)


class SchedQueue(object):
    """Scheduler queue

    Schedules continuation to be executed on specified core
    """
    def __init__(self, core):
        self.core = core
        self.rets = []
        self.rets_lock = threading.RLock()

    def on(self):
        @async_block
        def cont(ret):
            with self.rets_lock:
                self.rets.append(ret)
            self.core.wake()
        return cont

    def __call__(self):
        with self.rets_lock:
            rets, self.rets = self.rets, []
        for ret in rets:
            ret(self.core)

    def timeout(self):
        return 0 if self.rets else CORE_TIMEOUT

    def dispose(self, exc=None):
        error = Result.from_exception(exc or CanceledError('scheduler queue has been disposed'))
        with self.rets_lock:
            rets, self.rets = self.rets, []
        for ret in self.rets:
            ret(error)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __len__(self):
        return len(self.rets)

    def __str__(self):
        return 'SchedQueue(len:{})'.format(len(self))

    def __repr__(self):
        return str(self)


class ProcQueue(object):
    """Process queue

    Schedule continuation to be executed when process with specified pid
    has been terminated.
    """
    current = [None]
    current_lock = threading.RLock()

    def __init__(self, core):
        self.core = core
        self.pids = {}
        self.pending = False

    def init(self):
        if self.current[0] == self:
            return
        elif self.current[0] is None:
            with self.current_lock:
                if self.current[0] is None:
                    self.current[0] = self
                    signal.signal(signal.SIGCHLD,
                                  lambda *_: setattr(self, 'pending', True))
                    return
        raise ValueError('process queue can only be used by single core')

    def on(self, pid):
        @async_block
        def cont(ret):
            pid_done, status = os.waitpid(pid, os.WNOHANG)
            if pid_done == pid:
                ret(os.WEXITSTATUS(status))
            else:
                if self.pids.get(pid):
                    raise ValueError('pid {} has already being waited'.format(pid))
                self.pids[pid] = ret
        self.init()
        return cont

    def __call__(self):
        pending, self.pending = self.pending, False
        if not pending:
            return

        resolved = []
        for pid, ret in tuple(self.pids.items()):
            try:
                pid_done, status = os.waitpid(pid, os.WNOHANG)
                if pid_done == pid:
                    self.pids.pop(pid, None)
                    resolved.append((ret, os.WEXITSTATUS(status)))
            except OSError:
                self.pids.pop(pid, None)
                resolved.append((ret, Result.from_current_error()))
        for ret, status in resolved:
            ret(status)

    def dispose(self, exc=None):
        if self.current[0] == self:
            signal.signal(signal.SIGCHLD, signal.SIG_DFL)
            self.current[0] = None
        error = Result.from_exception(exc or CanceledError('process queue has been disposed'))
        pids, self.pids = self.pids, {}
        for ret in self.pids.values():
            ret(error)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __len__(self):
        return len(self.pids)

    def __str__(self):
        return 'ProcQueue(len:{})'.format(len(self))

    def __repr__(self):
        return str(self)


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
            except (CanceledError, BrokenPipeError):
                pass
            finally:
                self.dispose()
        consumer()()

    def fileno(self):
        return self.writer

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
