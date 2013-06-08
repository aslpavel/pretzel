"""Base asynchronous stream type
"""
from collections import defaultdict
from .. import PRETZEL_BUFSIZE
from ..monad import async
from ..state_machine import StateMachine
from ..common import BrokenPipeError

__all__ = ('Stream',)


class Stream(object):
    """Base class for asynchronous streams
    """
    FLAG_READ = 0b00001
    FLAG_WRITE = 0b00010
    FLAG_IDLE = 0b00100

    STATE_NONE = 0b00000
    STATE_READ = FLAG_READ | FLAG_IDLE  # 0b00101
    STATE_WRITE = FLAG_WRITE | FLAG_IDLE  # 0b00110
    STATE_READ_WRITE = FLAG_READ | FLAG_WRITE | FLAG_IDLE  # 0b00111
    STATE_IDLE = FLAG_IDLE  # 0b00100
    STATE_INIT = 0b01000
    STATE_DISPOSED = 0b10000
    STATE_GRAPH = StateMachine.compile_graph({
        STATE_NONE: (STATE_INIT, STATE_DISPOSED),
        STATE_READ: (STATE_IDLE, STATE_READ_WRITE, STATE_DISPOSED),
        STATE_WRITE: (STATE_IDLE, STATE_READ_WRITE, STATE_DISPOSED),
        STATE_READ_WRITE: (STATE_READ, STATE_WRITE, STATE_DISPOSED),
        STATE_INIT: (STATE_NONE, STATE_IDLE, STATE_DISPOSED),
        STATE_IDLE: (STATE_READ, STATE_WRITE, STATE_DISPOSED),
        STATE_DISPOSED: (STATE_DISPOSED,),
    })
    STATE_NAMES = defaultdict(lambda: 'invalid')
    STATE_NAMES.update({
        STATE_NONE: 'not-inited',
        STATE_READ: 'read',
        STATE_WRITE: 'write',
        STATE_READ_WRITE: 'read-write',
        STATE_INIT: 'initing',
        STATE_IDLE: 'idle',
        STATE_DISPOSED: 'disposed'
    })

    def __init__(self):
        self.state = StateMachine(self.STATE_GRAPH, self.STATE_NAMES)
        self.reading = StateFlagScope(self.state, self.FLAG_READ)
        self.writing = StateFlagScope(self.state, self.FLAG_WRITE)
        self.initing = StateTransScope(self.state, self.STATE_INIT,
                                       self.STATE_IDLE, self.STATE_NONE)

    def fileno(self):
        raise NotImplementedError()

    @async
    def read(self, size):
        """Read data

        Size of returned data expected to be in range [1..size], otherwise
        BrokenPipeError must be raised. Reading scope must be entered for
        duration of reading.
        """
        with self.reading:
            raise NotImplementedError()

    @async
    def write(self, data):
        """Write data

        Returns length of written data. Writing scope must be entered for
        duration of writing.
        """
        with self.writing:
            raise NotImplementedError()

    @async
    def flush(self):
        """Flush write buffers

        Must hook continuation to the current flush if any or start new one.
        """

    @async
    def flush_and_dispose(self):
        """Flush data and dispose stream
        """
        yield self.flush()
        self.dispose()

    @async
    def copy_to(self, stream, bufsize=None):
        """Copy content of this stream to different stream

        Stream can be either asynchronous stream or python binary stream.
        """
        bufsize = bufsize or PRETZEL_BUFSIZE
        if isinstance(stream.write(b''), int):
            # destination stream is synchronous python stream
            try:
                while True:
                    stream.write((yield self.read(bufsize)))
            except BrokenPipeError:
                pass
            stream.flush()
        else:
            try:
                while True:
                    yield stream.write((yield self.read(bufsize)))
            except BrokenPipeError:
                pass
            yield stream.flush()

    @property
    def disposed(self):
        return self.state.state == self.STATE_DISPOSED

    def dispose(self):
        return self.state(self.STATE_DISPOSED)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return '{}(state:{})'.format(type(self).__name__, self.state.state_name())

    def __repr__(self):
        return str(self)


class StateFlagScope(object):
    __slots__ = ('state', 'flag')

    def __init__(self, state, flag):
        self.state = state
        self.flag = flag

    def __enter__(self):
        self.state(self.state.state | self.flag)
        return self

    def __exit__(self, et, eo, tb):
        self.state(self.state.state & ~self.flag)
        return False

    def __bool__(self):
        return bool(self.state.state & self.flag)
    __nonzero__ = __bool__

    def __str__(self):
        return str(bool(self))
    __repr__ = __str__


class StateTransScope(object):
    __slots__ = ('state', 'prog', 'succ', 'fail',)

    def __init__(self, state, prog, succ, fail):
        self.state = state
        self.prog = prog
        self.succ = succ
        self.fail = fail

    def __call__(self):
        self.state(self.prog)
        self.state(self.succ)

    def __enter__(self):
        self.state(self.prog)
        return self

    def __exit__(self, et, eo, tb):
        self.state(self.succ if et is None or not issubclass(et, Exception) else
                   self.fail)
        return False

    def __bool__(self):
        return bool(self.state.state == self.prog)
    __nonzero__ = __bool__

    def __str__(self):
        return str(bool(self))
    __repr__ = __str__
