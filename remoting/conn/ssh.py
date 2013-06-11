"""SSH Connection

Connection with remote machine over ssh protocol.
"""
from .shell import ShellConnection

__all__ = ('SSHConnection',)


class SSHConnection(ShellConnection):
    """SSH Connection
    """
    def __init__(self, host, port=None, identity_file=None, ssh_exec=None,
                 py_exec=None, environ=None, bufsize=None, hub=None, core=None):
        self.host = host
        self.port = port
        self.identity_file = identity_file
        self.ssh_exec = ssh_exec or 'ssh'

        # ssh command
        command = [
            self.ssh_exec,          # command
            '-T',                   # disable pseudo-tty allocation
            '-o', 'BatchMode=yes',  # never ask password
            self.host,              # host
        ]
        command.extend(('-i', self.identity_file) if self.identity_file else [])
        command.extend(('-p', self.port) if self.port else [])

        ShellConnection.__init__(self, command=command, escape=True,
                                 py_exec=py_exec, environ=environ,
                                 bufsize=bufsize, hub=hub, core=core)
