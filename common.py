"""Common function and types
"""
import io
import sys
import errno

__all__ = ('reraise', 'execute', 'StringIO', 'ConnectionError',
           'BrokenPipeError', 'CanceledError', 'BlockingErrorSet',
           'PipeErrorSet', 'PY2', 'PY3',)


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

if sys.version_info[0] > 2:
    import builtins
    execute = getattr(builtins, "exec")
    del builtins

    def reraise(tp, value, tb=None):
        """Re-raise exception
        """
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value

    StringIO = io.StringIO
    PY2 = False
    PY3 = True

else:
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

    exec("""def reraise(tp, value, tb=None):
        raise tp, value, tb""")

    StringIO = io.BytesIO
    PY2 = True
    PY3 = False

BlockingErrorSet = {errno.EAGAIN, errno.EALREADY, errno.EWOULDBLOCK,
                    errno.EINPROGRESS, errno.EINTR}
PipeErrorSet = {errno.EPIPE,  errno.ESHUTDOWN}
