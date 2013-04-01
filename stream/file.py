# -*- coding: utf-8 -*-
import os
import fcntl
__all__ = ('fd_close_on_exec', 'fd_blocking',)


def fd_close_on_exec(fd, enable=None):
    """Set or get file descriptor blocking
    """
    return fd_option(fd, fcntl.F_GETFD, fcntl.F_SETFD, fcntl.FD_CLOEXEC, enable)


def fd_blocking(fd, enable=None):
    """Set or get file descriptor close_on_exec
    """
    return not fd_option(fd, fcntl.F_GETFL, fcntl.F_SETFL, os.O_NONBLOCK,
                         None if enable is None else not enable)


def fd_option(fd, get_flag, set_flag, option_flag, enable=None):
    """Set or get file descriptor option
    """
    options = fcntl.fcntl(fd, get_flag)
    if enable is None:
        return bool(options & option_flag)
    elif enable:
        options |= option_flag
    else:
        options &= ~option_flag
    fcntl.fcntl(fd, set_flag, options)
    return enable

# vim: nu ft=python columns=120 :
