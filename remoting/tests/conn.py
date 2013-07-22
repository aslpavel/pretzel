import os
import textwrap
import unittest
import functools
import importlib
from .proxy import Remote
from ..hub import pair
from ..conn import ForkConnection, SSHConnection
from ..conn.conn import ConnectionProxy
from ..proxy import Proxy, proxify
from ...core import schedule
from ...monad import Result, monad, async_all
from ...boot import BootLoader, boot_pack
from ...process import process_call
from ...tests import async_test
from ...utils import identity
from ... import PRETZEL_POLLER, __name__ as pretzel

__all__ = ('ForkConnectionTest', 'SSHConnectionTest',)


class ForkConnectionTest(unittest.TestCase):
    conn_env = {'PRETZEL_POLLER': PRETZEL_POLLER}
    conn_type = functools.partial(ForkConnection, environ=conn_env)

    @async_test
    def test_misc(self):
        environ = self.conn_env.copy()
        environ['MYENV'] = 'MYVAL'
        with (yield self.conn_type(environ=environ)) as conn:
            # make sure process id differ
            self.assertNotEqual((yield conn(os.getpid)()), os.getpid())

            # make sure poller is the same
            self.assertEqual((yield conn(importlib.import_module)
                             (pretzel).PRETZEL_POLLER), PRETZEL_POLLER)

            # current working directory
            self.assertEqual((yield conn(os.getcwd)()), '/')

            # bad message
            with self.assertRaises(TypeError):
                yield conn.sender('bad_message')

            # result marshaling
            self.assertEqual((yield conn(Result.from_value('test_value'))),
                             'test_value')
            with self.assertRaises(RuntimeError):
                yield conn(Result.from_exception(RuntimeError()))

            # environment
            remote_environ = conn(importlib.import_module)('os').environ
            self.assertEqual((yield remote_environ.get('MYENV')), 'MYVAL')
            self.assertEqual(os.environ.get('MYENV'), None)

            # big data
            data_ref = b'0123456789' * (1 << 22)  # 40Mb
            data = yield conn(identity)(data_ref)
            self.assertEqual(data_ref, data)

    @async_test
    def test_proxy(self):
        with (yield self.conn_type()) as conn:
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
                async_val = monad(~proxy.method_async()).future()
                self.assertFalse(async_val.completed)
                yield proxy()
                self.assertEqual((yield async_val), (yield proxy.value))

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
        with (yield self.conn_type()) as c0:
            pids.add((yield c0(os.getpid)()))
            with (yield ~c0(self.conn_type)()) as c1:
                pids.add((yield c1(os.getpid)()))
                self.assertTrue(isinstance(c1, ConnectionProxy))
                with (yield ~c1(self.conn_type)()) as c2:
                    pids.add((yield c2(os.getpid)()))
        self.assertEqual(len(pids), 3)

        yield schedule()  # make sure we are not in handler
        self.assertFalse(c0.hub.handlers)

    @async_test
    def test_sender_roundtrip(self):
        r, s = pair()
        with (yield self.conn_type()) as conn:
            self.assertEqual(tuple((yield conn(s)).addr), tuple(s.addr))

    @async_test
    def test_interrupt(self):
        """Test interrupt inside Connection.do_recv
        """
        from .conn_int import int_function
        with (yield self.conn_type()) as conn:
            # We need to send two requests (second will cause interrupt)
            res0, res1 = yield async_all((conn(int_function)(), conn(int_function)()))
            self.assertEqual(res0, int_function())
            self.assertEqual(res1, int_function())

    @async_test
    def test_importer(self):
        with (yield self.conn_type()) as conn:
            self.assertEqual((yield conn(clean_path)()), [])
            self.assertEqual((yield conn(__import__)('wsgiref').__loader__ >> type),
                             BootLoader)


class SSHConnectionTest(ForkConnectionTest):
    conn_type = functools.partial(SSHConnection, host='localhost',
                                  environ=ForkConnectionTest.conn_env)

    @async_test
    def test_stdout(self):
        """Test that stdout if forwarded to stdin
        """
        test_stdout_source = textwrap.dedent("""\
            from __future__ import print_function
            from {pretzel}.app import app
            from {pretzel}.remoting import SSHConnection
            @app
            def main():
                with (yield SSHConnection('localhost')) as conn:
                    yield conn(print)('done', end='')
            main()
            """.format(pretzel=pretzel))
        result = yield process_call(['python', '-c', boot_pack(test_stdout_source)])
        self.assertEqual(result, (b'', b'done', 0))


def clean_path():  # pragma: no cover
    """Clean system path to force use of connection importer

    Called from remote connection.
    """
    import sys
    del sys.path[:]
    return sys.path
