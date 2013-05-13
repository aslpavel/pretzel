import unittest
from ..hub import Hub
from ..proxy import Proxy, proxify
from ...event import Event
from ...monad import async, do_return
from ...core import schedule
from ...tests import async_test

__all__ = ('ProxyTest',)


class ProxyTest(unittest.TestCase):
    @async_test
    def test(self):
        remote = Remote('val')
        with proxify(remote) as proxy:
            # simple
            self.assertEqual((yield proxy), remote)
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
            self.assertEqual((yield async_val).value, remote.value)

            with (yield proxify(proxy.value)) as value_proxy:
                self.assertTrue(isinstance(value_proxy, Proxy))

        yield schedule()  # handlers will be cleaned when coroutine is interrupted
        self.assertFalse(len(Hub.local()), 0)


class Remote (object):
    def __init__(self, value):
        self.items = {'item': 'item_value'}
        self.value = value
        self.event = Event()

    def __getitem__(self, name):
        return self.items[name]

    def __setitem__(self, name, value):
        self.items[name] = value

    def method(self, value=None):
        if value is None:
            return self.value
        else:
            value, self.value = self.value, value
            return value

    @async
    def method_async(self, value=None):
        yield self.event
        do_return(self.method(value))

    def method_error(self, error):
        raise error

    def __call__(self, value=None):
        self.event(value)
        return value

    def __monad__(self):
        self.event.__monad__().map_val(lambda r: r[0])
