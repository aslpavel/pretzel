# -*- coding: utf-8 -*-
import os
import unittest
from .proxy import Remote
from ..hub import pair
from ..conn import ForkConnection
from ..conn.conn import ConnectionProxy
from ..proxy import Proxy, proxify
from ...core import schedule
from ...tests import async_test

__all__ = ('ConnectionTest',)


class ConnectionTest(unittest.TestCase):
    @async_test
    def test_fork(self):
        with (yield ForkConnection()) as conn:
            self.assertNotEqual(os.getpid(), (yield conn(os.getpid)()))
            self.assertEqual(conn.process.pid, (yield conn(os.getpid)()))

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
        with (yield ForkConnection()) as c0:
            c0_pid = yield c0(os.getpid)()
            self.assertTrue(isinstance(c0_pid, int))
            with (yield ~c0(ForkConnection)()) as c1:
                c1_pid = yield c1(os.getpid)()
                self.assertTrue(isinstance(c1_pid, int))
                self.assertTrue(isinstance(c1, ConnectionProxy))

        self.assertNotEqual(c0_pid, c1_pid)
        self.assertNotEqual(os.getpid(), c0_pid)
        self.assertNotEqual(os.getpid(), c1_pid)

        yield schedule()  # make sure we are not in handler
        self.assertFalse(c0.hub.handlers)

    @async_test
    def test_sender_roundtrip(self):
        r, s = pair()
        with (yield ForkConnection()) as conn:
            self.assertEqual(tuple((yield conn(s)).addr), tuple(s.addr))

# vim: nu ft=python columns=120 :
