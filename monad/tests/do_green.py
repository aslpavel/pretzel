import unittest
try:
    import greenlet
except ImportError:
    greenlet = None
from ..do_green import bind_green
from ..async import async_green
from ..result import Result
from ...event import Event

__all__ = ('DoGreenTest',)


class DoGreenTest(unittest.TestCase):
    @unittest.skipIf(greenlet is None, 'greenlet module is not installed')
    def test(self):
        event = Event()
        get = lambda: bind_green(event)
        ret = lambda val: rets.append(val)
        rets = []

        @async_green
        def green():
            return get()

        green()(ret)
        self.assertEqual(rets, [])

        event('value')
        self.assertEqual(rets.pop().value, 'value')

        green()(ret)
        event(Result.from_exception(ValueError('test')))
        with self.assertRaises(ValueError):
            rets.pop().value

        with self.assertRaises(RuntimeError):
            bind_green(event)  # bind outside of greenlet
