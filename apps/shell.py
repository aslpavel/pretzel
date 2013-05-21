"""Asynchronous pretzel shell

Requires greenlet module to be installed.
"""
import os
import sys
import code
import signal
import socket
import textwrap
import functools
from collections import deque
from ..monad import Result, async, async_any, async_green, bind_green
from ..core import Core, schedule
from ..event import Event
from ..stream import BufferedFile
from ..common import BrokenPipeError, CanceledError
from ..remoting import ForkConnection, SSHConnection, pair
from ..state_machine import StateMachine
from .. import __package__ as pretzel_pkg

__all__ = ('Shell', 'ShellStream', 'prompt',)


class ShellBase(object):
    OP_EXEC = 0
    OP_PUSH = 1
    OP_INT = 2
    OP_EOT = 3

    def __init__(self, sender):
        self.sender = sender

    def __call__(self, locals=None, banner=None):
        """Execute shell
        """
        return self.sender((self.OP_EXEC, (locals, banner)))

    def push(self, line):
        """Push line to shell
        """
        return self.sender.send((self.OP_PUSH, line))

    def interrupt(self):
        """Interrupt shell
        """
        return self.sender.send((self.OP_INT, None))

    def end_of_transmission(self):
        """End-of-transmission
        """
        return self.sender.try_send((self.OP_EOT, None))

    def __reduce__(self):
        return ShellBase, (self.sender,)

    def __repr__(self):
        return 'Shell(addr:{})'.format(self.sender.addr)


class Shell(ShellBase):
    BANNER = textwrap.dedent("""\
        Welcome to asynchronous pretzel shell!
            {}
            bind   - bind value associated with continuation monad
            bound  - create bound version of asynchronous function
            monad  - get associated monad
            attach - attach shell to specified connection
            fork   - create fork connection
            ssh    - create ssh connection
            core   - application's core object

        -> host:{{host}} pid:{{pid}}""").format('')

    INIT_SOURCE = textwrap.dedent("""\
        from __future__ import print_function
        from {pkg}.core import *
        from {pkg}.monad import *
        from {pkg}.event import *
        from {pkg}.stream import *
        from {pkg}.process import *
        from {pkg}.task import *
        from {pkg}.remoting import *
        """.format(pkg=pretzel_pkg))

    STATE_INIT = 0
    STATE_EXEC = 1
    STATE_DISP = 2
    STATE_GRAPH = StateMachine.compile_graph({
        STATE_INIT: (STATE_EXEC, STATE_DISP),
        STATE_EXEC: (STATE_DISP,),
        STATE_DISP: (STATE_DISP,),
    })
    STATE_NAMES = ('initial', 'executing', 'disposed',)

    def __init__(self, output):
        self.output = output
        self.state = StateMachine(self.STATE_GRAPH, self.STATE_NAMES)

        self.push_ev = Event()
        self.push_buf = deque()
        self.int_ev = Event()
        self.int_tag = object()
        self.shell_rdr = None

        def process(msg, dst, src):
            if self.shell_rdr is None:
                if msg is None:
                    self.int_ev(self.int_tag)
                    return False
                else:
                    op, args = msg
                    if op == self.OP_INT:
                        self.push_buf.appendleft(msg)
                        self.int_ev(self.int_tag)
                    elif op == self.OP_EXEC:
                        self.execute(*args)(lambda res: src.send(res))
                    else:
                        self.push_buf.append(msg)
                    self.push_ev(None)
                    return True
            else:
                self.shell_rdr.sender.send(msg, src)
                return True
        recv, send = pair()
        recv(process)

        ShellBase.__init__(self, send)

    @async_green
    def execute(self, locals, banner):
        """Execute shell
        """
        def raw_input(prompt=''):
            """Write a prompt and read a line
            """
            if prompt:
                self.output.write(prompt)
            while True:
                if self.push_buf:
                    op, args = self.push_buf.popleft()
                    if op == self.OP_PUSH:
                        return args
                    elif op == self.OP_INT:
                        raise KeyboardInterrupt()
                    elif op == self.OP_EOT:
                        raise EOFError()
                    raise RuntimeError('unknown prompt operation: {}'.format(op))
                bind_green(self.push_ev)

        def bind(target):
            """Get associated monadic value
            """
            value = bind_green(monad(target) | self.int_ev)
            if value is self.int_tag:
                if self.push_buf:  # dequeue excessive OP_INT
                    self.push_buf.popleft()
                raise KeyboardInterrupt()
            return value

        def bound(func):
            """Create version of asynchronous function
            """
            @functools.wraps(func)
            def func_bound(*args, **kwargs):
                return bind(func(*args, **kwargs))
            return func_bound

        def monad(target):
            """Get associated monad
            """
            monad_getter = getattr(target, '__monad__', None)
            if monad_getter is None:
                raise ValueError('target is not a monad')
            return monad_getter()

        @async
        def attach(conn, **locals):
            """Create shell on specified connection
            """
            yield self.redirect((yield conn(Shell)(self.output)), locals)

        try:
            self.state(self.STATE_EXEC)
            stderr_prev, sys.stderr = sys.stderr, self.output
            stdout_prev, sys.stdout = sys.stdout, self.output

            locals = locals or {}
            locals.update({
                'bind': bind,
                'bound': bound,
                'monad': monad,
                'fork': bound(ForkConnection),
                'ssh': bound(SSHConnection),
                'attach': bound(attach),
                'core': Core.local(),
            })
            console = code.InteractiveConsole(locals)
            for line in self.INIT_SOURCE.split('\n'):
                console.runsource(line.rstrip())
            console.raw_input = raw_input
            console.interact((self.BANNER if banner is None else banner).format(
                             host=socket.gethostname(), pid=os.getpid()))
        finally:
            sys.stderr = stderr_prev
            sys.stdout = stdout_prev
            self.state(self.STATE_DISP)
            self.sender.try_send(None)

    @async
    def redirect(self, shell, locals=None):
        """Redirect input events to a different shell object
        """
        if self.shell_rdr is not None:
            raise ValueError('has already been redirected')
        try:
            self.shell_rdr = shell
            yield shell(locals, banner='-> host:{host} pid:{pid}')
        finally:
            self.shell_rdr = None
            self.output.write('-> host:{} pid:{}\n'.format(socket.gethostname(), os.getpid()))


class ShellStream(object):
    """Send-able stream like object
    """
    def __init__(self, stream):
        def write(data):
            stream.write(data)
            stream.flush()
            return True
        self.output = Event()
        self.output.on(write)

    def write(self, data):
        self.output(data)
        return len(data)

    def flush(self):
        pass

    def isatty(self):
        return False

    def fileno(self):
        raise NotImplementedError()

    def close(self):
        self.output.dispose()


@async
def prompt(shell, stdin=None):
    """Prompt shell
    """
    @async
    def prompt_coro():
        stream = None
        cancel = cancel_ev.future()
        try:
            stream = BufferedFile(stdin or sys.__stdin__, closefd=False)
            sigint = signal.signal(signal.SIGINT, lambda sig, stack:
                                   schedule()(lambda _: shell.interrupt()))
            while True:
                try:
                    line = yield async_any((stream.read_until_sub(b'\n'), cancel))
                    shell.push(line.rstrip().decode('utf-8'))
                except BrokenPipeError:
                    shell.end_of_transmission()
                except CanceledError:
                    break
        finally:
            signal.signal(signal.SIGINT, sigint)
            if stream is not None:
                stream.blocking(True)
                stream.dispose()
    try:
        cancel_ev = Event()
        yield async_any((shell(), prompt_coro()))
    finally:
        cancel_ev(Result.from_exception(CanceledError()))


if __name__ == '__main__':
    from ..app import app_run
    shell = Shell(ShellStream(sys.stdout))
    app_run(prompt(shell))
