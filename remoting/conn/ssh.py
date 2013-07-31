"""SSH Connection

Connection with remote machine over ssh protocol.
"""
from .shell import ShellConnection

__all__ = ('SSHConnection',)


class SSHConnection(ShellConnection):
    """SSH Connection
    """
    def __init__(self, host, port=None, ssh_identity=None, ssh_exec=None,
                 py_exec=None, environ=None, bufsize=None, hub=None, core=None):
        self.host = host
        self.port = port
        self.ssh_identity = ssh_identity
        self.ssh_exec = ssh_exec or 'ssh'

        # ssh command
        command = [
            self.ssh_exec,          # command
            '-A',                   # forward ssh agent
            '-C',                   # enable compression
            '-T',                   # disable pseudo-tty allocation
            '-o', 'BatchMode=yes',  # never ask password
            self.host,              # host
        ]
        command.extend(('-i', self.ssh_identity) if self.ssh_identity else [])
        command.extend(('-p', self.port) if self.port else [])

        ShellConnection.__init__(self, command=command, escape=True,
                                 py_exec=py_exec, environ=environ,
                                 bufsize=bufsize, hub=hub, core=core)

    def connect(self):
        return ShellConnection.connect(self, self.host)
