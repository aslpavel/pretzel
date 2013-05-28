"""Helper module (used by connection tests)

This module will cause interrupt inside Connection.do_recv if
int_function is called inside remote connection.
"""
try:
    import not_existing_module
except ImportError:
    pass

__all__ = ('remote_function',)


def int_function():
    return 'done'
