"""Manipulate system processes asynchronously
"""
import io
import os
import sys
import pickle
import signal
import atexit
from .event import Event
from .dispose import CompDisp
from .monad import Result, Cont, async, async_all, do_return
from .core import Core
from .stream import Pipe
from .common import BrokenPipeError
from .state_machine import StateMachine

__all__ = ('Process', 'PIPE', 'DEVNULL', 'STDIN', 'STDOUT', 'STDERR', 'process_call')

PIPE = -1
DEVNULL = -2
DEVNULL_FD = None
STDIN = sys.__stdin__.fileno() if sys.__stdin__ else DEVNULL
STDOUT = sys.__stdout__.fileno() if sys.__stdout__ else DEVNULL
STDERR = sys.__stderr__.fileno() if sys.__stderr__ else DEVNULL


class Process(object):
    """Asynchronous child process
    """
    STATE_INIT = 0
    STATE_FORK = 1
    STATE_RUN = 2
    STATE_DISP = 3
    STATE_GRAPH = StateMachine.compile_graph({
        STATE_INIT: (STATE_DISP, STATE_FORK,),
        STATE_FORK: (STATE_DISP, STATE_RUN,),
        STATE_RUN:  (STATE_DISP,),
        STATE_DISP: (STATE_DISP,),
    })
    STATE_NAMES = ('not-run', 'forking', 'running', 'disposed',)
    KILL_DELAY = 10

    def __init__(self, command, stdin=None, stdout=None, stderr=None,
                 preexec=None, shell=None, environ=None, check=None,
                 bufsize=None, kill_delay=None, core=None):

        self.core = core or Core.local()
        self.disp = CompDisp()
        self.state = StateMachine(self.STATE_GRAPH, self.STATE_NAMES)

        class options(object):
            def __getattr__(self, name):
                return opts[name]
        opts = {
            'stdin': stdin,
            'stdout': stdout,
            'stderr': stderr,
            'environ': environ,
            'command': ['/bin/sh', '-c', ' '.join(command)] if shell else command,
            'kill_delay': kill_delay or self.KILL_DELAY,
            'check': check is None or check,
            'buffer': bufsize,
            'preexec': preexec,
            'status': Event(),
        }

        self.pid = None
        self.opts = options()
        self.status = self.opts.status.future()

    @async
    def __call__(self):
        self.state(self.STATE_FORK)
        core = self.core
        try:
            def pipe(file, fd_fallback, readable):
                """Create pipe from file
                """
                if file is None:
                    if fd_fallback < 0:  # DEVNULL
                        fd = devnull_get()
                    else:
                        fd = fd_fallback
                elif file == PIPE:
                    fd = None
                elif file == DEVNULL:
                    fd = devnull_get()
                else:
                    fd = file if isinstance(file, int) else file.fileno()
                return Pipe(None if fd is None else
                           ((None, fd) if readable else (fd, None)), self.opts.buffer, core)

            self.stdout_pipe = self.disp.add(pipe(self.opts.stdout, STDOUT, True))
            self.stderr_pipe = self.disp.add(pipe(self.opts.stderr, STDERR, True))
            self.stdin_pipe = self.disp.add(pipe(self.opts.stdin, STDIN, False))
            status_pipe = self.disp.add(Pipe(core=core))

            self.pid = os.fork()
            if self.pid:
                # dispose remote streams
                self.stdin_pipe.reader.dispose()
                self.stdout_pipe.writer.dispose()
                self.stderr_pipe.writer.dispose()
                status_pipe.writer.dispose()
                # close on exec
                for stream in (self.stdin_pipe.writer, self.stdout_pipe.reader,
                               self.stderr_pipe.reader, status_pipe.reader):
                    if stream is not None:
                        stream.close_on_exec(True)
            else:
                try:
                    status_fd = status_pipe.detach_writer(close_on_exec=True)
                    self.stdin_pipe.detach_reader(0)
                    self.stdout_pipe.detach_writer(1)
                    self.stderr_pipe.detach_writer(2)
                    if self.opts.preexec is not None:
                        self.opts.preexec()
                    os.execvpe(self.opts.command[0], self.opts.command,
                               self.opts.environ or os.environ)
                except Exception:
                    with io.open(status_fd, 'wb') as error_stream:
                        pickle.dump(Result.from_current_error(), error_stream)
                finally:
                    getattr(os, '_exit', lambda _: os.kill(os.getpid(), signal.SIGKILL))(255)

            status = self.core.waitpid(self.pid).future()  # no zombies
            try:
                error_data = yield status_pipe.reader.read_until_eof()
                if error_data:
                    pickle.loads(error_data).value  # will raise captured error
            except BrokenPipeError:
                pass
            self.state(self.STATE_RUN)
            status(self.dispose)
            do_return(self)

        except Exception:
            self.dispose(Result.from_current_error())
            raise

    @property
    def stdin(self):
        if self.state.state != self.STATE_RUN:
            raise ValueError('process is not running')
        return self.stdin_pipe.writer

    @property
    def stdout(self):
        if self.state.state != self.STATE_RUN:
            raise ValueError('process is not running')
        return self.stdout_pipe.reader

    @property
    def stderr(self):
        if self.state.state != self.STATE_RUN:
            raise ValueError('process is not running')
        return self.stderr_pipe.reader

    def __monad__(self):
        return self()

    def dispose(self, status=None):
        self.state(self.STATE_DISP)
        self.disp.dispose()
        if status is None:
            # schedule kill signal
            if self.pid and not self.status.completed:
                (self.core.sleep(self.opts.kill_delay)(lambda _:
                 not self.status.completed and os.kill(self.pid, signal.SIGTERM)))
        else:
            self.opts.status(status)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        """String representation of the process
        """
        return ('Process(state:{}, pid:{}, cmd:{})'.format(self.state.state_name(),
                self.pid, self.opts.command))

    def __repr__(self):
        return str(self)


def process_call(command, input=None, stdin=None, stdout=None, stderr=None,
                 preexec=None, shell=None, environ=None, check=None,
                 bufsize=None, kill_delay=None, core=None):
    """Asynchronously run command

    Asynchronously returns standard output, standard error and return code tuple.
    """
    if input is not None and stdin is not None:
        raise ValueError('input and stdin arguments cannot be used together')
    stdin = PIPE if stdin is None else stdin
    stdout = PIPE if stdout is None else stdout
    stderr = PIPE if stderr is None else stderr

    @async
    def process():
        with Process(command=command, stdin=stdin, stdout=stdout, stderr=stderr,
                     preexec=preexec, shell=shell, environ=environ, check=check,
                     bufsize=bufsize, kill_delay=kill_delay, core=core) as proc:
            yield proc
            if input:
                proc.stdin.write_schedule(input)
                proc.stdin.flush_and_dispose()()
            elif proc.stdin:
                proc.stdin.dispose()
            out = proc.stdout.read_until_eof() if proc.stdout else Cont.unit(None)
            err = proc.stderr.read_until_eof() if proc.stderr else Cont.unit(None)
            do_return((yield async_all((out, err, proc.status))))
    return process()


def devnull_get():
    """Get devnull file descriptor
    """
    global DEVNULL_FD
    if DEVNULL_FD is None:
        DEVNULL_FD = os.open(os.devnull, os.O_RDWR)
    return DEVNULL_FD


@atexit.register
def devnull_close():
    """Close devnull file descriptor
    """
    if DEVNULL_FD is not None:
        os.close(DEVNULL_FD)
