# -*- coding: utf-8 -*-
import sys
import errno

__all__ = ('ConnectionError', 'BrokenPipeError',)

if sys.version_info[:2] > (3, 2):
    from builtins import ConnectionError, BrokenPipeError
else:
    class ConnectionError(OSError, IOError):
        """Connection associated error
        """

    class BrokenPipeError(ConnectionError):
        """Broken pipe error
        """

BlockingErrorSet = {errno.EAGAIN, errno.EALREADY, errno.EWOULDBLOCK, errno.EINPROGRESS}
PipeErrorSet = {errno.EPIPE,  errno.ESHUTDOWN}

# vim: nu ft=python columns=120 :
