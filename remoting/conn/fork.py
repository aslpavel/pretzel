"""Fork connection

Connection with forked and exec-ed process via two pipes.
"""
import os
import sys
from .stream import StreamConnection
from ..importer import Importer
from ...process import Process, ProcessPipe, PIPE
from ...monad import async
from ...stream import BufferedFile
from ...core import Core
from ...boot import BootImporter, __name__ as boot_name

__all__ = ('ForkConnection',)


class ForkConnection(StreamConnection):
    """Fork connection

    Connection with forked and exec-ed process via two pipes.
    """
    def __init__(self, command=None, environ=None, bufsize=None, hub=None, core=None):
        StreamConnection.__init__(self, hub=hub, core=core)
        self.bufsize = bufsize
        self.command = [sys.executable, '-'] if command is None else command
        self.environ = environ
        self.process = None

    @async
    def do_connect(self, target):
        """Fork connect implementation

        Target is pickle-able and call-able which will be called upon successful
        connection with connection this as its only argument.
        """
        # pipes
        reader = self.dispose.add(ProcessPipe(True, bufsize=self.bufsize, core=self.core))
        writer = self.dispose.add(ProcessPipe(False, bufsize=self.bufsize, core=self.core))

        # process
        def preexec():  # pragma: no cover
            reader()
            writer()
            os.chdir('/')
            os.setsid()

        self.process = self.dispose.add(Process(self.command,
                                        stdin=PIPE, preexec=preexec, kill_delay=-1,
                                        bufsize=self.bufsize, core=self.core))
        yield self.process  # exec-ed

        # send payload
        payload = (BootImporter.from_modules().bootstrap
                  (fork_conn_init, writer.child_fd, reader.child_fd,
                   self.bufsize, self.environ).encode())
        self.process.stdin.write_schedule(payload)
        yield self.process.stdin.flush_and_dispose()

        reader_stream = self.dispose.add(reader())
        writer_stream = self.dispose.add(writer())
        yield StreamConnection.do_connect(self, (reader_stream, writer_stream))

        # install importer
        self.dispose.add((yield Importer.create_remote(self)))
        self.module_map['_boot'] = boot_name

        # update name
        self.flags['pid'] = self.process.pid
        self.flags['type'] = 'fork'


def fork_conn_init(reader_fd, writer_fd, bufsize, environ):  # pragma: no cover
    """Fork connection initialization function
    """
    if environ:
        os.environ.update(environ)

    with Core.local() as core:
        # initialize connection
        conn = StreamConnection(core=core)
        conn.flags['pid'] = os.getpid()
        conn.flags['type'] = 'fork'
        conn.dispose.add_action(lambda: core.schedule()(lambda _: core.dispose()))

        # connect
        reader = BufferedFile(reader_fd, bufsize=bufsize, core=core)
        reader.close_on_exec(True)
        writer = BufferedFile(writer_fd, bufsize=bufsize, core=core)
        writer.close_on_exec(True)
        conn.connect((reader, writer))()

        # execute core
        if not core.disposed:
            core()
