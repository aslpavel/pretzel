"""Utility functions and types to deal with python version differences.
"""
import io
import sys
import errno

__all__ = ('PY2', 'execute', 'reraise', 'StringIO', 'zip', 'map', 'filter',
           'ConnectionError', 'BrokenPipeError', 'CanceledError',
           'BlockingErrorSet', 'PipeErrorSet',)

PY2 = sys.version_info[0] == 2


#------------------------------------------------------------------------------#
# Exec                                                                         #
#------------------------------------------------------------------------------#
if PY2:
    def execute(code, globs=None, locs=None):
        """Execute code in a name space.
        """
        if globs is None:
            frame = sys._getframe(1)
            globs = frame.f_globals
            if locs is None:
                locs = frame.f_locals
            del frame
        elif locs is None:
            locs = globs
        exec("""exec code in globs, locs""")
else:
    import builtins
    execute = getattr(builtins, "exec")
    del builtins


#------------------------------------------------------------------------------#
# Raise                                                                        #
#------------------------------------------------------------------------------#
if PY2:
    exec("""def reraise(tp, value, tb=None):
        raise tp, value, tb""")
else:
    def reraise(tp, value, tb=None):
        """Re-raise exception
        """
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value


#------------------------------------------------------------------------------#
# IO String                                                                    #
#------------------------------------------------------------------------------#
if PY2:
    StringIO = io.BytesIO
else:
    StringIO = io.StringIO


#------------------------------------------------------------------------------#
# Iterators                                                                    #
#------------------------------------------------------------------------------#
if PY2:
    from itertools import (izip as zip,
                           imap as map,
                           ifilter as filter)
else:
    import builtins
    zip = getattr(builtins, "zip")
    map = getattr(builtins, "map")
    filter = getattr(builtins, "filter")


#------------------------------------------------------------------------------#
# Error types                                                                  #
#------------------------------------------------------------------------------#
class CanceledError(Exception):
    """Operation has been canceled
    """

if sys.version_info[:2] > (3, 2):
    from builtins import ConnectionError, BrokenPipeError
else:
    class ConnectionError(OSError, IOError):
        """Connection associated error
        """

    class BrokenPipeError(ConnectionError):
        """Broken pipe error
        """


#------------------------------------------------------------------------------#
# Error numbers sets                                                           #
#------------------------------------------------------------------------------#
BlockingErrorSet = set((errno.EAGAIN, errno.EALREADY, errno.EWOULDBLOCK,
                        errno.EINPROGRESS, errno.EINTR))
PipeErrorSet = set((errno.EPIPE, errno.ESHUTDOWN))
