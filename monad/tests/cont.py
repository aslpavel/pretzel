import unittest
from ..do import do_return
from ..cont import async, async_block, async_all, async_any
from ..result import Result
from ...event import Event

__all__ = ('ContTest',)


class ContTest(unittest.TestCase):
    """Continuation monad unit tests
    """
    def test_normal(self):
        rets, rets_ref = [], []
        e0, e1 = Event(), Event()

        @async
        def test_async(result):
            rets.append((yield e0))
            rets.append('0-1')
            rets.append((yield e1))
            rets.append('1-2')
            rets.append((yield e0))
            rets.append('2-R')
            do_return(result)

        test_async('done')(lambda val: rets.append(val))
        self.assertEqual(rets, rets_ref)

        e1(1)
        self.assertFalse(rets, rets_ref)
        e0(2)
        rets_ref.extend([2, '0-1'])
        self.assertEqual(rets, rets_ref)
        e1(Result.from_value(3))
        rets_ref.extend([3, '1-2'])
        self.assertEqual(rets, rets_ref)
        e0(4)
        rets_ref.extend([4, '2-R', Result.from_value('done')])
        self.assertEqual(rets, rets_ref)

    def test_error(self):
        rets, rets_ref = [], []
        ev = Event()
        error = ValueError('test')

        @async
        def test_async():
            try:
                rets.append((yield ev))
            except Exception as error:
                rets.append(error)
            rets.append((yield ev))
            rets.append((yield ev))

        test_async()(lambda val: rets.extend(('done', val,)))
        self.assertEqual(rets, rets_ref)

        ev(Result.from_exception(error))
        rets_ref.append(error)
        self.assertEqual(rets, rets_ref)

        ev('value')
        rets_ref.append('value')
        self.assertEqual(rets, rets_ref)

        ev(Result.from_exception(error))
        rets_ref.extend(('done', Result.from_exception(error),))
        self.assertEqual(rets, rets_ref)

    def test_block(self):
        rets, rets_ref = [], []
        hs = []
        exc = ValueError('test')

        def test_async(exc=None):
            @async_block
            def cont(ret):
                if exc is None:
                    hs.append(ret)
                else:
                    raise exc
            return cont

        test_async(exc)(lambda val: rets.append(val))
        rets_ref.append(Result.from_exception(exc))
        self.assertEqual(rets, rets_ref)

        test_async()(lambda val: rets.append(val))
        hs[-1]('done')
        rets_ref.append(Result.from_value('done'))
        self.assertEqual(rets, rets_ref)

        test_async()(lambda val: rets.append(val))
        hs[-1](Result.from_value('done value'))
        rets_ref.append(Result.from_value('done value'))
        self.assertEqual(rets, rets_ref)

    def test_all(self):
        rets = []
        e0, e1 = Event(), Event()

        async_all((e0, e1))(lambda val: rets.append(val))
        self.assertEqual(len(e0), 1)
        self.assertEqual(len(e1), 1)

        e1('two')
        e0('one')
        self.assertFalse(e0)
        self.assertFalse(e1)
        self.assertEqual(rets.pop().value, ('one', 'two'))

    def test_any(self):
        rets = []
        e0, e1 = Event(), Event()

        async_any((e0, e1))(lambda val: rets.append(val))
        self.assertEqual(len(e0), 1)
        self.assertEqual(len(e1), 1)

        e0('done')
        self.assertFalse(e0)
        self.assertTrue(e1)
        self.assertEqual(rets.pop().value, 'done')

        e1('done_next')
        self.assertFalse(e1)
