"""Shell connection

Connection with process over standard output and input, error stream
is untouched.
"""
import io
import os
import sys
import socket
import pickle
import textwrap

from .stream import StreamConnection
from ..importer import Importer
from ... import PRETZEL_BUFSIZE, PRETZEL_RECLIMIT
from ...monad import async
from ...process import Process, PIPE
from ...boot import BootImporter, boot_pack, __name__ as boot_name
from ...core import Core
from ...stream import BufferedFile

__all__ = ('ShellConnection',)


class ShellConnection(StreamConnection):
    """Shell connection

    Connection with process over standard output and input, error stream
    is untouched.
    """
    def __init__(self, command=None, escape=None, py_exec=None,
                 environ=None, bufsize=None, hub=None, core=None):
        StreamConnection.__init__(self, hub=hub, core=core)

        self.bufsize = bufsize
        self.py_exec = py_exec or sys.executable
        self.command = command or []
        self.command.extend((self.py_exec, '-c', '\'{}\''.format(shell_tramp)
                            if escape else shell_tramp))
        self.environ = environ
        self.process = None

    @async
    def do_connect(self, target):
        """Fork connect implementation

        Target is pickle-able and call-able which will be called upon successful
        connection with connection this as its only argument.
        """
        def preexec():  # pragma: no cover
            os.chdir('/')
            os.setsid()
        self.process = yield (self.dispose.add(Process(self.command, stdin=PIPE,
                                               stdout=PIPE, preexec=preexec,
                                               bufsize=self.bufsize, core=self.core)))

        # check remote python version
        version = yield self.process.stdout.read_bytes()
        if version.decode() != str(sys.version_info[0]):
            raise RuntimeError('remote python major version mismatch local:{} remote:{}'
                               .format(sys.version_info[0], version.decode()))

        # send environment data
        environ = {
            'PRETZEL_RECLIMIT': str(PRETZEL_RECLIMIT),
            'PRETZEL_BUFSIZE': str(PRETZEL_BUFSIZE),
        }
        if self.environ:
            environ.update(self.environ)
        self.process.stdin.write_bytes(pickle.dumps(environ))

        # send boot data
        boot_data = (BootImporter.from_modules().bootstrap(
                     shell_conn_init, self.bufsize).encode('utf-8'))
        self.process.stdin.write_bytes(boot_data)
        yield self.process.stdin.flush()

        yield StreamConnection.do_connect(self, (self.process.stdout,
                                                 self.process.stdin))
        yield self(os.chdir)('/')

        # install importer
        self.dispose.add((yield Importer.create_remote(self)))
        self.module_map['_boot'] = boot_name

        # update flags
        self.flags['pid'] = yield self(os.getpid)()
        self.flags['host'] = yield self(socket.gethostname)()


def shell_conn_init(bufsize):  # pragma: no cover
    """Shell connection initialization function
    """
    # Make sure standard output and input won't be used. As it is now used
    # for communication.
    in_fd = os.dup(0)
    with io.open(os.devnull, 'r') as stdin:
        os.dup2(stdin.fileno(), 0)
    out_fd = os.dup(1)
    os.dup2(sys.stderr.fileno(), 1)

    with Core.local() as core:
        # initialize connection
        conn = StreamConnection(core=core)
        conn.flags['pid'] = os.getpid()
        conn.flags['host'] = socket.gethostname()
        conn.dispose.add_action(lambda: core.schedule()(lambda _: core.dispose()))

        # connect
        in_stream = BufferedFile(in_fd, bufsize=bufsize, core=core)
        in_stream.close_on_exec(True)
        out_stream = BufferedFile(out_fd, bufsize=bufsize, core=core)
        out_stream.close_on_exec(True)
        conn.connect((in_stream, out_stream))()

        if not core.disposed:
            core()

shell_tramp = boot_pack(textwrap.dedent("""\
    import os, io, sys, struct, pickle
    size_struct = struct.Struct("{size_format}")
    # send version
    version = str(sys.version_info[0]).encode()
    os.write(1, size_struct.pack(len(version)))
    os.write(1, version)
    # receiver payload
    with io.open(0, "rb", buffering=0, closefd=False) as stream:
        def read_bytes():
            size_data = stream.read(size_struct.size)
            if len(size_data) < size_struct.size:
                sys.exit(0)
            size = size_struct.unpack(size_data)[0]
            data = io.BytesIO()
            while size > data.tell():
                chunk = stream.read(size - data.tell())
                if not chunk:
                    raise ValueError("payload is incomplete")
                data.write(chunk)
            return data.getvalue()
        env_data = read_bytes()
        boot_data = read_bytes()
    os.environ.update(pickle.loads(env_data))
    exec(boot_data.decode("utf-8"))
    """.format(size_format=BufferedFile.size_struct.format.decode())))
