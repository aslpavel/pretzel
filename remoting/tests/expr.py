import unittest

from ..expr import *
from ...event import Event
from ...monad import Identity

__all__ = ('ExprTest',)


class ExprTest(unittest.TestCase):
    def test_load_arg(self):
        self.assertEqual(run_expr(LoadArgExpr(0), 'one', 'two'), 'one')
        self.assertEqual(run_expr(LoadArgExpr(1), 'one', 'two'), 'two')

    def test_load_const(self):
        self.assertEqual(run_expr(LoadConstExpr('constant')), 'constant')

    def test_call(self):
        fn = lambda *a, **kw: (a, kw)
        self.assertEqual(run_expr(CallExpr(fn, 'arg')), fn('arg'))
        self.assertEqual(run_expr(CallExpr(fn, 0, 1, 2, one=1, two=2)),
                         fn(0, 1, 2, one=1, two=2))
        self.assertEqual(run_expr(CallExpr(fn, one=1, two=2)), fn(one=1, two=2))

    def test_attr(self):
        class A(object):
            pass
        a = A()

        get_attr = GetAttrExpr(LoadConstExpr(a), 'key').code()
        set_attr = SetAttrExpr(LoadConstExpr(a), 'key', LoadArgExpr(0)).code()

        with self.assertRaises(AttributeError):
            run(get_attr)
        self.assertEqual(run(set_attr, 'value'), None)
        self.assertEqual(a.key, 'value')
        self.assertEqual(run(get_attr), 'value')

    def test_item(self):
        d = {}
        get_item = GetItemExpr(LoadConstExpr(d), LoadArgExpr(0)).code()
        set_item = SetItemExpr(LoadConstExpr(d), LoadArgExpr(0), LoadArgExpr(1)).code()

        with self.assertRaises(KeyError):
            run(get_item, 'key')
        self.assertEqual(run(set_item, 'key', 'value'), None)
        self.assertEqual({'key': 'value'}, d)
        self.assertEqual(run(get_item, 'key'), 'value')

    def test_raise(self):
        with self.assertRaises(RuntimeError):
            run_expr(RaiseExpr(LoadArgExpr(0)), RuntimeError('test'))

    def test_bind(self):
        ev = Event()
        ev_future = CallExpr(len, BindExpr(LoadArgExpr(0))).code()(ev).future()

        self.assertFalse(ev_future.completed)
        ev('result')
        self.assertEqual(ev_future.value, len('result'))

    def test_if(self):
        max_code = IfExpr(CmpExpr('>', LoadArgExpr(0), LoadArgExpr(1)),
                          LoadArgExpr(0),
                          LoadArgExpr(1)).code()

        self.assertEqual(run(max_code, 3, 2), 3)
        self.assertEqual(run(max_code, 2, 3), 3)

    def test_while(self):
        while_code = WhileExpr(CmpExpr('>', CallExpr(LoadArgExpr(0)), LoadConstExpr(0)),
                               CallExpr(LoadArgExpr(1))).code()
        ctx = [10, 0]

        def cond():
            ctx[0] -= 2
            return ctx[0]

        def body():
            ctx[1] += 1

        run(while_code, cond, body)
        self.assertEqual(ctx, [0, 4])


def run(code, *args):
    return code(*args, monad=Identity).value.value


def run_expr(expr, *args):
    return run(expr.code(), *args)
