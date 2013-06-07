import os
import unittest
from ..conn.composite import composite_fork_conn
from ...tests import async_test

__all__ = ('CompositeConnectionTest',)


class CompositeConnectionTest(unittest.TestCase):
    @async_test
    def test_flat(self):
        with (yield composite_fork_conn(3, mesh='flat')) as conns:
            pid = os.getpid()
            for ppid in (yield conns(os.getppid)()):
                self.assertEqual(pid, ppid)

    @async_test
    def test_mesh(self):
        with (yield composite_fork_conn(3, mesh='tree:2')) as conns:
            pids = dict(zip((yield conns(os.getpid)()),
                            (yield conns(os.getppid)())))
        direct = list(pid for pid, ppid in pids.items() if ppid == os.getpid())
        indirect = list(pid for pid, ppid in pids.items() if ppid in direct)
        self.assertEqual(len(direct), 2)
        self.assertEqual(len(indirect), 1)
