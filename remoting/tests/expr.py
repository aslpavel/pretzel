import pickle
import operator
import unittest

from ..expr import *
from ...event import Event
from ...monad import Result, Identity, Cont, do, do_return

__all__ = ('ExprTest',)


class ExprTest(unittest.TestCase):
    def test_arg(self):
        self.assertEqual(run(Arg('first'), first=1), 1)
        with self.assertRaises(KeyError):
            run(Arg('undefined'))

    def test_const(self):
        self.assertEqual(run(Const('constant')), 'constant')

    def test_env(self):
        env_one_expr = GetItem(GetAttr(Env(), 'args'), Const('one'))
        self.assertEqual(run(env_one_expr, one='ONE'), 'ONE')

    def test_call(self):
        fn = lambda *a, **kw: (a, kw)
        self.assertEqual(run(Call(Const(fn), Const('arg'))), fn('arg'))
        self.assertEqual(run(Call(Const(fn), Const(0), one=Const(1))), fn(0, one=1))
        self.assertEqual(run(Call(Const(fn), two=Const(2))), fn(two=2))

    def test_attr(self):
        class A(object):
            pass
        a = A()

        with self.assertRaises(AttributeError):
            run(GetAttr(Const(a), 'key'))

        run(Call(Const(setattr), Const(a), Const('value'), Const('value')))
        self.assertEqual(a.value, 'value')
        self.assertEqual(run(GetAttr(Const(a), 'value')), 'value')

    def test_item(self):
        d = {}

        with self.assertRaises(KeyError):
            run(GetItem(Const(d), Const('key')))

        run(Call(Const(operator.setitem), Const(d), Const('key'), Const('value')))
        self.assertEqual({'key': 'value'}, d)
        self.assertEqual(run(GetItem(Const(d), Const('key'))), 'value')

    def test_bind(self):
        ev = Event()
        len_expr = reload(Call(Const(len), Bind(Arg('ev'))))
        ev_future = len_expr(ExprEnv(Cont, ev=ev)).future()

        self.assertFalse(ev_future.completed)
        ev('result')
        self.assertEqual(ev_future.value, len('result'))

    def test_if(self):
        max_expr = If(Call(Const(operator.gt), Arg('a'), Arg('b')),
                      Arg('a'), Arg('b'))

        max_expr = reload(max_expr)
        self.assertEqual(run(max_expr, a=3, b=2), 3)
        self.assertEqual(run(max_expr, a=2, b=3), 3)

    def test_do(self):
        @do(Expr)
        def run():
            val = yield Bind(Arg('ev'))
            do_return('Yes, {}!'.format(val))

        ev = Event()
        ev_future = run()(ExprEnv(Cont, ev=ev)).future()
        self.assertFalse(ev_future.completed)
        ev('Done')
        self.assertEqual(ev_future.value, 'Yes, Done!')


def run(expr, **args):
    """Run expression with Identity monad
    """
    result = expr(ExprEnv(Identity, **args)).value
    return result.value if isinstance(result, Result) else result


def reload(val):
    """Reload value with pickle
    """
    return pickle.loads(pickle.dumps(val, -1))
