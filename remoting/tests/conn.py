import os
import unittest
from .proxy import Remote
from ..hub import pair
from ..conn import ForkConnection, SSHConnection
from ..conn.conn import ConnectionProxy
from ..proxy import Proxy, proxify
from ...core import schedule
from ...monad import async_all
from ...boot import BootLoader
from ...tests import async_test

__all__ = ('ForkConnectionTest', 'SSHConnectionTest',)


class ForkConnectionTest(unittest.TestCase):
    conn_type = ForkConnection
    conn_args = tuple()

    @async_test
    def test_proxy(self):
        with (yield self.conn_type(*self.conn_args)) as conn:
            self.assertNotEqual(os.getpid(), (yield conn(os.getpid)()))

            with (yield proxify(conn(Remote)('val'))) as proxy:
                # call
                self.assertEqual((yield proxy('test')), 'test')

                # attribute
                self.assertEqual((yield proxy.value), 'val')
                with self.assertRaises(AttributeError):
                    yield proxy.bad_attr

                # item
                self.assertEqual((yield proxy['item']), 'item_value')
                with self.assertRaises(KeyError):
                    yield proxy['bad item']

                # method
                self.assertEqual((yield proxy.method()), (yield proxy.value))
                self.assertEqual((yield proxy.method('val_new')), 'val')
                self.assertEqual((yield proxy.method()), (yield proxy.value))
                with self.assertRaises(RuntimeError):
                    yield proxy.method_error(RuntimeError())

                # asynchronous method
                async_val = (~proxy.method_async()).__monad__().future()
                self.assertFalse(async_val.completed)
                yield proxy()
                self.assertEqual((yield async_val).value, (yield proxy.value))

                with (yield proxify(proxy.value)) as value_proxy:
                    self.assertTrue(isinstance(value_proxy, Proxy))

        # process exit status
        self.assertEqual((yield conn.process.status), 0)
        self.assertFalse(conn.hub.handlers)

    @async_test
    def test_nested(self):
        """Nested connection test
        """
        pids = set()
        with (yield self.conn_type(*self.conn_args)) as c0:
            pids.add((yield c0(os.getpid)()))
            with (yield ~c0(self.conn_type)(*self.conn_args)) as c1:
                pids.add((yield c1(os.getpid)()))
                self.assertTrue(isinstance(c1, ConnectionProxy))
                with (yield ~c1(self.conn_type)(*self.conn_args)) as c2:
                    pids.add((yield c2(os.getpid)()))
        self.assertEqual(len(pids), 3)

        yield schedule()  # make sure we are not in handler
        self.assertFalse(c0.hub.handlers)

    @async_test
    def test_sender_roundtrip(self):
        r, s = pair()
        with (yield self.conn_type(*self.conn_args)) as conn:
            self.assertEqual(tuple((yield conn(s)).addr), tuple(s.addr))

    @async_test
    def test_interrupt(self):
        """Test interrupt inside Connection.do_recv
        """
        from .conn_int import int_function
        with (yield self.conn_type(*self.conn_args)) as conn:
            # We need to send two requests (second will cause interrupt)
            res0, res1 = yield async_all((conn(int_function)(), conn(int_function)()))
            self.assertEqual(res0, int_function())
            self.assertEqual(res1, int_function())

    @async_test
    def test_importer(self):
        with (yield self.conn_type(*self.conn_args)) as conn:
            self.assertEqual((yield conn(clean_path)()), [])
            self.assertEqual((yield conn(__import__)('wsgiref').__loader__ >> type),
                             BootLoader)


class SSHConnectionTest(ForkConnectionTest):
    conn_type = SSHConnection
    conn_args = ('localhost',)


def clean_path():
    """Clean system path to force use of connection importer

    Called from remote connection.
    """
    import sys
    del sys.path[:]
    return sys.path
