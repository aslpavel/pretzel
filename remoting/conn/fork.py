"""Fork connection

Connection with forked and exec-ed process via two pipes.
"""
import os
import sys

from .stream import StreamConnection
from ..importer import Importer
from ...process import Process, PIPE
from ...monad import async
from ...stream import BufferedFile, Pipe
from ...core import Core
from ...boot import BootImporter

__all__ = ('ForkConnection',)


class ForkConnection(StreamConnection):
    """Fork connection

    Connection with forked and exec-ed process via two pipes.
    """
    def __init__(self, command=None, buffer_size=None, hub=None, core=None):
        StreamConnection.__init__(self, hub, core)
        self.buffer_size = buffer_size
        self.command = [sys.executable, '-'] if command is None else command
        self.process = None

    @async
    def do_connect(self, target):
        """Fork connect implementation

        Target is pickle-able and call-able which will be called upon successful
        connection with connection this as its only argument.
        """
        # pipes
        in_pipe = self.disp.add(Pipe(buffer_size=self.buffer_size, core=self.core))
        out_pipe = self.disp.add(Pipe(buffer_size=self.buffer_size, core=self.core))

        # process
        def preexec():
            in_pipe.detach_reader()
            out_pipe.detach_writer()
            os.chdir('/')
            os.setsid()

        self.process = self.disp.add(Process(self.command,
                                     stdin=PIPE, preexec=preexec, kill_delay=-1,
                                     buffer_size=self.buffer_size, core=self.core))
        yield self.process

        # close remote side of pipes
        in_fd = in_pipe.reader.fileno()
        in_pipe.reader.dispose()
        out_fd = out_pipe.writer.fileno()
        out_pipe.writer.dispose()

        # send payload
        payload = (BootImporter.from_modules().bootstrap
                  (fork_conn_init, in_fd, out_fd, self.buffer_size).encode())
        self.process.stdin.write_schedule(payload)
        yield self.process.stdin.flush_and_dispose()

        out_pipe.reader.close_on_exec(True)
        in_pipe.writer.close_on_exec(True)
        yield StreamConnection.do_connect(self, (out_pipe.reader, in_pipe.writer))

        # install importer
        self.disp.add((yield Importer.create_remote(self)))


def fork_conn_init(in_fd, out_fd, buffer_size):
    """Fork connection initialization function
    """
    with Core.local() as core:
        # initialize connection
        conn = StreamConnection(core=core)
        conn.disp.add(core)

        # connect
        in_stream = BufferedFile(in_fd, buffer_size=buffer_size, core=core)
        in_stream.close_on_exec(True)
        out_stream = BufferedFile(out_fd, buffer_size=buffer_size, core=core)
        out_stream.close_on_exec(True)
        conn.connect((in_stream, out_stream))()

        # execute core
        if not core.disposed:
            core()

# vim: nu ft=python columns=120 :
