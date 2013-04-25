"""Shell connection

Connection with process over standard output and input, error stream
is untouched.
"""
import io
import os
import sys
import zlib
import struct
import binascii
import textwrap

from .stream import StreamConnection
from ..importer import Importer
from ...monad import async
from ...process import Process, PIPE
from ...boot import BootImporter
from ...core import Core
from ...stream import BufferedFile, fd_close_on_exec

__all__ = ('ShellConnection',)


class ShellConnection(StreamConnection):
    """Shell connection

    Connection with process over standard output and input, error stream
    is untouched.
    """
    def __init__(self, command=None, escape=None, py_exec=None,
                 buffer_size=None, hub=None, core=None):
        StreamConnection.__init__(self, hub, core)

        self.buffer_size = buffer_size
        self.py_exec = py_exec or sys.executable
        self.command = command or []
        self.command.extend((self.py_exec, '-c', '\'{}\''.format(shell_tramp)
                            if escape else shell_tramp))
        self.process = None

    @async
    def do_connect(self, target):
        """Fork connect implementation

        Target is pickle-able and call-able which will be called upon successful
        connection with connection this as its only argument.
        """
        def preexec():
            os.chdir('/')
            os.setsid()

        self.process = (self.disp.add(Process(self.command, stdin=PIPE,
                        stdout=PIPE, preexec=preexec, kill_delay=-1,
                        buffer_size=self.buffer_size, core=self.core)))

        # send payload
        payload = (BootImporter.from_modules().bootstrap(
                   shell_conn_init, self.buffer_size).encode('utf-8'))
        self.process.stdin.write_schedule(struct.pack('>I', len(payload)))
        self.process.stdin.write_schedule(payload)
        yield self.process.stdin.flush()

        yield StreamConnection.do_connect(self, (self.process.stdout,
                                                 self.process.stdin))

        # install importer
        self.disp.add((yield Importer.create_remote(self)))


def shell_conn_init(buffer_size):
    """Shell connection initialization function
    """
    # Make sure standard output and input won't be used. As it is now used
    # for communication.
    sys.stdin = io.open(os.devnull, 'r')
    fd_close_on_exec(sys.stdin.fileno())
    sys.stdout = io.open(os.devnull, 'w')
    fd_close_on_exec(sys.stdout.fileno())

    with Core.local() as core:
        # initialize connection
        conn = StreamConnection(core=core)
        conn.disp.add(core)

        # connect
        in_stream = BufferedFile(0, buffer_size=buffer_size, core=core)
        in_stream.close_on_exec(True)
        out_stream = BufferedFile(1, buffer_size=buffer_size, core=core)
        out_stream.close_on_exec(True)
        conn.connect((in_stream, out_stream))()

        if not core.disposed:
            core()


def boot_tramp(data):
    return ('import zlib,binascii;'
            'exec(zlib.decompress(binascii.a2b_base64(b"{}")))'.format(
            binascii.b2a_base64(zlib.compress(data)).strip().decode('utf-8')))

shell_tramp = boot_tramp(textwrap.dedent("""\
    import io, struct
    with io.open(0, "rb", buffering=0, closefd=False) as stream:
        size = struct.unpack(">I", stream.read(struct.calcsize(">I")))[0]
        data = io.BytesIO()
        while size > data.tell():
            chunk = stream.read(size - data.tell())
            if not chunk:
                raise ValueError("payload is incomplete")
            data.write(chunk)
    exec(data.getvalue().decode("utf-8"))
    """).encode('utf-8'))
