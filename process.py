# -*- coding: utf-8 -*-
import io
import os
import sys
import pickle
import signal
from .dispose import FuncDisp, CompDisp
from .monad import Cont, async, do_return
from .core import Core
from .stream import Pipe
from .common import BrokenPipeError

__all__ = ('Process', 'PIPE', 'DEVNULL', 'STDIN', 'STDOUT', 'STDERR', 'process_call')

PIPE = -1
DEVNULL = -2
STDIN = sys.stdin.fileno()
STDOUT = sys.stdout.fileno()
STDERR = sys.stderr.fileno()


class Process(object):
    """Asynchronous child process
    """
    default_kill_delay = 10

    def __init__(self, command, stdin=None, stdout=None, stderr=None,
                 preexec=None, shell=None, environ=None, check=None,
                 buffer_size=None, kill_delay=None, core=None):

        self.core = core or Core.local()
        self.disp = CompDisp()

        self.command = ['/bin/sh', '-c', ' '.join(command)] if shell else command
        self.environ = environ
        self.kill_delay = kill_delay or self.default_kill_delay
        self.check = check is None or check

        self.pid = None
        self.status = None

        ## PIPES
        def pipe(file, file_default, readable):
            if file is None:
                fd = file_default
            elif file == PIPE:
                fd = None
            elif file == DEVNULL:
                if not hasattr(self, 'null_fd'):
                    self.null_fd = os.open(os.devnull, os.O_RDWR)
                    self.disp += FuncDisp(lambda: os.close(self.null_fd))
                fd = self.null_fd
            else:
                fd = file if isinstance(file, int) else file.fileno()
            return Pipe(None if fd is None else
                       ((None, fd) if readable else (fd, None)), buffer_size, core)
        self.stdout_pipe = self.disp.add(pipe(stdout, STDOUT, True))
        self.stderr_pipe = self.disp.add(pipe(stderr, STDERR, True))
        self.stdin_pipe = self.disp.add(pipe(stdin, STDIN, False))

        ## STATUS
        @async
        def status():
            status = self.core.waitpid(self.pid).future()
            try:
                # restore error from error stream if any
                error_dump = yield status_pipe.reader.read_until_eof()
                if error_dump:
                    raise pickle.loads(error_dump)
            except BrokenPipeError:
                pass
            do_return((yield status))
        status_pipe = self.disp.add(Pipe(core=core))

        ## FORK
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
            # start status coroutine
            self.status = status().future()
        else:
            try:
                status_fd = status_pipe.detach_writer()
                self.stdin_pipe.detach_reader(0)
                self.stdout_pipe.detach_writer(1)
                self.stderr_pipe.detach_writer(2)
                if preexec is not None:
                    preexec()
                os.execvpe(self.command[0], self.command, self.environ or os.environ)
            except Exception as error:
                with io.open(status_fd, 'wb') as error_stream:
                    pickle.dump(error, error_stream)
            finally:
                getattr(os, '_exit', lambda _: os.kill(os.getpid(), signal.SIGKILL))(255)

    @property
    def stdin(self):
        return self.stdin_pipe.writer

    @property
    def stdout(self):
        return self.stdout_pipe.reader

    @property
    def stderr(self):
        return self.stderr_pipe.reader

    def __monad__(self):
        return self.status.__monad__()

    def dispose(self):
        @async
        def kill_child():
            try:
                if self.kill_delay > 0:
                    yield self.core.sleep(self.kill_delay)
            finally:
                if not self.status.completed and self.kill_delay >= 0:
                    os.kill(self.pid, signal.SIGTERM)
        self.disp.dispose()
        if not self.status.completed:
            kill_child()()

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        """String representation of the process
        """
        if self.status.completed:
            value, error = self.status.result.pair
            status = value if error is None else repr(error)
        else:
            status = 'running'
        return '<Process[pid:{} status:{}] at {}'.format(self.pid, status, id(self))
    __repr__ = __str__


def process_call(command, input=None, stdin=None, stdout=None, stderr=None,
                 preexec=None, shell=None, environ=None, check=None, buffer_size=None,
                 kill_delay=None, core=None):
    """Asynchronously run command

    Asynchronously returns standard output, standard error and return code tuple.
    """
    if input is not None and stdin is not None:
        raise ValueError('input and stdin options cannot be used together')
    stdin = PIPE if stdin is None else stdin
    stdout = PIPE if stdout is None else stdout
    stderr = PIPE if stderr is None else stderr

    @async
    def process():
        with Process(command=command, stdin=stdin, stdout=stdout, stderr=stderr,
                     preexec=preexec, shell=shell, environ=environ, check=check,
                     buffer_size=buffer_size, kill_delay=kill_delay, core=core) as proc:
            if input:
                proc.stdin.write_schedule(input)
                proc.stdin.close()()
            else:
                proc.stdin.dispose()
            out = proc.stdout.read_until_eof() if proc.stdout else Cont.unit(None)
            err = proc.stderr.read_until_eof() if proc.stderr else Cont.unit(None)
            out, err, status = yield Cont.sequence((out, err, proc.status))
            do_return((out.value, err.value, status.value))
    return process()

# vim: nu ft=python columns=120 :
