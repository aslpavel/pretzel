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
from .stream import BufferedFile, fd_close_on_exec
from .common import BrokenPipeError
from .state_machine import StateMachine

__all__ = ('Process', 'ProcessError', 'ProcessPipe', 'PIPE', 'DEVNULL',
           'process_call',)


def devnull_fd():
    """Get devnull file descriptor
    """
    global DEVNULL_FD
    if DEVNULL_FD is None:
        DEVNULL_FD = os.open(os.devnull, os.O_RDWR)
    return DEVNULL_FD


@atexit.register
def devnull_fd_dispose():
    """Close devnull file descriptor
    """
    global DEVNULL_FD
    fd, DEVNULL_FD = DEVNULL_FD, None
    if fd is not None:
        os.close(fd)


PIPE = -1
DEVNULL = -2
DEVNULL_FD = None
STDIN_FD = sys.__stdin__.fileno() if sys.__stdin__ else devnull_fd()
STDOUT_FD = sys.__stdout__.fileno() if sys.__stdout__ else devnull_fd()
STDERR_FD = sys.__stderr__.fileno() if sys.__stderr__ else devnull_fd()


class ProcessError(Exception):
    """Process specific error
    """


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

        opts = {
            'stdin': stdin,
            'stdout': stdout,
            'stderr': stderr,
            'environ': environ,
            'command': ['/bin/sh', '-c', ' '.join(command)] if shell else command,
            'kill_delay': kill_delay or self.KILL_DELAY,
            'check': check is None or check,
            'bufsize': bufsize,
            'preexec': preexec,
            'status': Event(),
        }

        class options(object):
            def __getattr__(self, name):
                return opts[name]
        self.opts = options()

        self.pid = None
        self.stdin = None
        self.stdout = None
        self.stderr = None
        self.status = self.opts.status.future()

    @async
    def __call__(self):
        self.state(self.STATE_FORK)
        core = self.core
        try:
            def pipe(file, default, reader):
                """Create pair of getters for stream and associated descriptor
                """
                def fake_pipe(child_fd):
                    def detach(fd=None):
                        if pid == os.getpid():
                            assert fd is None, 'fd option must not be used in parent process'
                            return None
                        else:
                            if fd is None or fd == child_fd:
                                return child_fd
                            else:
                                os.dup2(child_fd, fd)
                                os.close(child_fd)
                                return fd
                    return detach
                pid = os.getpid()

                # from default descriptor
                if file is None:
                    return fake_pipe(default)
                # from pipe
                elif file == PIPE:
                    return self.disp.add(ProcessPipe(reader, bufsize=self.opts.bufsize, core=core))
                # from /dev/null
                elif file == DEVNULL:
                    return fake_pipe(devnull_fd())
                # from custom descriptor
                else:
                    return fake_pipe(file if isinstance(file, int) else file.fileno())

            stdin = pipe(self.opts.stdin, STDIN_FD, False)
            stdout = pipe(self.opts.stdout, STDOUT_FD, True)
            stderr = pipe(self.opts.stderr, STDERR_FD, True)
            status_pipe = self.disp.add(ProcessPipe(True, bufsize=self.opts.bufsize, core=core))

            self.pid = os.fork()
            # parent
            if self.pid:
                self.stdin = stdin()
                self.stdout = stdout()
                self.stderr = stderr()

                status = self.core.waitpid(self.pid).future()  # no zombies
                status(self.dispose)
                try:
                    error_data = yield self.disp.add(status_pipe()).read_until_eof()
                    if error_data:
                        pickle.loads(error_data).value  # will raise captured error
                except BrokenPipeError:
                    pass

            # child
            else:
                try:
                    status_fd = status_pipe()
                    fd_close_on_exec(status_fd, True)
                    stdin(0)
                    stdout(1)
                    stderr(2)
                    if self.opts.preexec is not None:
                        self.opts.preexec()
                    os.execvpe(self.opts.command[0], self.opts.command,
                               self.opts.environ or os.environ)
                except Exception:
                    with io.open(status_fd, 'wb') as error_stream:
                        pickle.dump(Result.from_current_error(), error_stream)
                finally:
                    getattr(os, '_exit', lambda _: os.kill(os.getpid(), signal.SIGKILL))(255)

            self.state(self.STATE_RUN)
            do_return(self)
        except Exception:
            self.dispose(Result.from_current_error())
            raise

    def __monad__(self):
        return self()

    def dispose(self, status=None):
        self.state(self.STATE_DISP)
        self.disp.dispose()
        for stream in (self.stdin, self.stdout, self.stderr):
            if stream is not None:
                stream.dispose()
        if status is None:
            # schedule kill signal
            if self.pid and not self.status.completed:
                (self.core.sleep(self.opts.kill_delay)(lambda _:
                 not self.status.completed and os.kill(self.pid, signal.SIGTERM)))
        else:
            def check_status(status):
                if self.opts.check and status != 0:
                    raise ProcessError('non-zero exit status: {}'.format(status))
                return status
            self.opts.status(status.bind(check_status))

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


class ProcessPipe(object):
    """Pipe to communicate with forked process
    """
    def __init__(self, reader, bufsize=None, core=None):
        self.core = core
        self.bufsize = bufsize
        self.parent_pid = os.getpid()
        self.parent_fd, self.child_fd = os.pipe() if reader else reversed(os.pipe())
        fd_close_on_exec(self.parent_fd, True)

    def __call__(self, fd=None):
        """Detach appropriate object

        Detaches stream in parent process, and descriptor in child process.
        """
        parent_pid, self.parent_pid = self.parent_pid, None
        if parent_pid is None:
            raise RuntimeError('pipe has already been detached')
        if parent_pid == os.getpid():
            assert fd is None, 'fd option must not be used in parent process'
            os.close(self.child_fd)
            stream = BufferedFile(self.parent_fd, bufsize=self.bufsize, core=self.core)
            return stream
        else:
            os.close(self.parent_fd)
            if fd is None or fd == self.child_fd:
                return self.child_fd
            else:
                os.dup2(self.child_fd, fd)
                os.close(self.child_fd)
                return fd

    def dispose(self):
        parent_pid, self.parent_pid = self.parent_pid, None
        if parent_pid is not None:
            os.close(self.parent_fd)
            os.close(self.child_fd)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return ('ProcessPipe(pid:{}, parent_fd:{}, child_fd:{})'.format
               (self.parent_pid, self.parent_fd, self.child_fd))

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
