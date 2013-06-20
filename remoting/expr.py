"""Micro virtual machine, compiler and abstract syntax tree for it
"""
import types
from ..monad import Cont, Result
from ..uniform import StringIO

__all__ = ('Expr', 'LoadArgExpr', 'LoadConstExpr', 'CallExpr',
           'GetAttrExpr', 'SetAttrExpr', 'GetItemExpr', 'SetItemExpr',
           'ReturnExpr', 'RaiseExpr', 'BindExpr', 'CmpExpr', 'IfExpr', 'WhileExpr',
           'Code', 'CodeGen')

HAS_ARG = 128

OP_POP = 1
OP_DUP = 2
OP_RETURN = 3
OP_RAISE = 4
OP_BIND = 5
OP_GETITEM = 6
OP_SETITEM = 7
OP_NOP = 8

OP_LDARG = 129    # argument index
OP_LDCONST = 130  # constant index
OP_CALL = 131     # number of arguments
OP_GETATTR = 132  # name as constant index
OP_SETATTR = 133  # name as constant index
OP_JMP = 134      # jump offset
OP_JMP_IF = 135   # jump offset
OP_JMP_IFN = 136  # jump offset
OP_COMPARE = 137  # compare operation

MAP_OP_NAME = {
    OP_POP:     'OP_POP',
    OP_DUP:     'OP_DUP',
    OP_RETURN:  'OP_RETURN',
    OP_RAISE:   'OP_RAISE',
    OP_BIND:    'OP_BIND',
    OP_GETITEM: 'OP_GETITEM',
    OP_SETITEM: 'OP_SETITEM',
    OP_NOP:     'OP_NOP',
    OP_LDARG:   'OP_LDARG',
    OP_LDCONST: 'OP_LDCONST',
    OP_CALL:    'OP_CALL',
    OP_GETATTR: 'OP_GETATTR',
    OP_SETATTR: 'OP_SETATTR',
    OP_JMP:     'OP_JMP',
    OP_JMP_IF:  'OP_JMP_IF',
    OP_JMP_IFN: 'OP_JMP_IFN',
    OP_COMPARE: 'OP_COMPARE',
}
MAP_NAME_OP = dict((name, op) for op, name in MAP_OP_NAME.items())

CMP_LE = 0   # <
CMP_LQ = 1   # <=
CMP_EQ = 2   # ==
CMP_NE = 3   # !=
CMP_GT = 4   # >
CMP_GE = 5   # >=
CMP_IN = 6   # in
CMP_NIN = 7  # not in
CMP_IS = 8   # is
CMP_ISN = 9  # is not
MAP_CMP_NAME = {
    CMP_LE:  '<',
    CMP_LQ:  '<=',
    CMP_EQ:  '==',
    CMP_NE:  '!=',
    CMP_GT:  '>',
    CMP_GE:  '>=',
    CMP_IN:  'in',
    CMP_NIN: 'not in',
    CMP_IS:  'is',
    CMP_ISN: 'is not'
}
MAP_NAME_CMP = dict((name, cmp) for cmp, name in MAP_CMP_NAME.items())


class Expr (object):
    __slots__ = tuple()

    def compile(self, gen):
        raise NotImplementedError()

    def code(self):
        gen = CodeGen()
        self.compile(gen)
        return gen.code()

    def __str__(self):
        return 'Nop'

    def __repr__(self):
        return str(self)


class LoadArgExpr(Expr):
    __slots__ = ('index',)

    def __init__(self, index):
        self.index = index

    def compile(self, gen):
        gen.emit(OP_LDARG, self.index)

    def __str__(self):
        return 'arg:{}'.format(self.index)


class LoadConstExpr(Expr):
    __slots__ = ('const',)

    def __init__(self, const):
        self.const = const

    def compile(self, gen):
        gen.emit(OP_LDCONST, gen.const(self.const))

    def __str__(self):
        if isinstance(self.const, (types.FunctionType, types.BuiltinFunctionType)):
            return getattr(self.const, '__qualname__', self.const.__name__)
        else:
            return repr(self.const)


class CallExpr(Expr):
    __slots__ = ('fn', 'args', 'kwargs',)

    def __init__(self, fn, *args, **kwargs):
        assert len(args) < 0xf or len(kwargs) > 0xf, "max argument count exceeded"
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def compile(self, gen):
        gen.load(self.fn)
        if self.args:
            for arg in self.args:
                gen.load(arg)
        if self.kwargs:
            for kw, arg in self.kwargs.items():
                gen.emit(OP_LDCONST, gen.const(kw))
                gen.load(arg)
        gen.emit(OP_CALL, len(self.args) | len(self.kwargs) << 4)

    def __str__(self):
        return ('{}({}{}{})'.format(self.fn,
                ', '.join(repr(arg) for arg in self.args),
                ', ' if self.args and self.kwargs else '',
                ', '.join('{}={}'.format(kw, repr(arg))
                          for kw, arg in self.kwargs.items())))


class GetAttrExpr(Expr):
    __slots__ = ('target', 'name',)

    def __init__(self, target, name):
        self.target = target
        self.name = name

    def compile(self, gen):
        gen.load(self.target)
        gen.emit(OP_GETATTR, gen.const(self.name))

    def __str__(self):
        return '{}.{}'.format(self.target, self.name)


class SetAttrExpr (Expr):
    __slots__ = ('target', 'name', 'value',)

    def __init__(self, target, name, value):
        self.target = target
        self.name = name
        self.value = value

    def compile(self, gen):
        gen.load(self.value)
        gen.load(self.target)
        gen.emit(OP_SETATTR, gen.const(self.name))

    def __str__(self):
        return '{}.{} = {}'.format(self.target, self.name, self.value)


class GetItemExpr (Expr):
    __slots__ = ('target', 'item',)

    def __init__(self, target, item):
        self.target = target
        self.item = item

    def compile(self, gen):
        gen.load(self.target)
        gen.load(self.item)
        gen.emit(OP_GETITEM)

    def __str__(self):
        return '{}[{}]'.format(self.target, self.item)


class SetItemExpr(Expr):
    __slots__ = ('target', 'item', 'value',)

    def __init__(self, target, item, value):
        self.target = target
        self.item = item
        self.value = value

    def compile(self, gen):
        gen.load(self.value)
        gen.load(self.target)
        gen.load(self.item)
        gen.emit(OP_SETITEM)

    def __str__(self):
        return '{}[{}] = {}'.format(self.target, self.item, self.value)


class ReturnExpr(Expr):
    __slots__ = ('result',)

    def __init__(self, result):
        self.result = result

    def compile(self, gen):
        gen.load(self.result)
        gen.emit(OP_RETURN)

    def __str__(self):
        return 'return {}'.format(self.result)


class RaiseExpr(Expr):
    __slots__ = ('error',)

    def __init__(self, error):
        self.error = error

    def compile(self, gen):
        gen.load(self.error)
        gen.emit(OP_RAISE)

    def __str__(self):
        return 'raise {}'.format(self.error)


class BindExpr(Expr):
    __slots__ = ('target',)

    def __init__(self, target):
        self.target = target

    def compile(self, gen):
        gen.load(self.target)
        gen.emit(OP_BIND)

    def __str__(self):
        return '<-{}'.format(self.target)


class CmpExpr(Expr):
    __slots__ = ('op', 'first', 'second',)

    def __init__(self, op, first, second):
        self.op = op if isinstance(op, int) else MAP_NAME_CMP[op]
        self.first = first
        self.second = second

    def compile(self, gen):
        gen.load(self.first)
        gen.load(self.second)
        gen.emit(OP_COMPARE, self.op)

    def __str__(self):
        return '{}{}{}'.format(self.first, self.op, self.second)


class IfExpr(Expr):
    __slots__ = ('cond', 'true', 'false',)

    def __init__(self, cond, true, false=None):
        self.cond = cond
        self.true = true
        self.false = false

    def compile(self, gen):
        jmp_label = gen.label()
        end_label = gen.label()

        # condition
        gen.load(self.cond)
        gen.emit(OP_JMP_IF, jmp_label)
        # false
        gen.load(self.false)
        gen.emit(OP_JMP, end_label)
        # true
        gen.label_mark(jmp_label)
        gen.load(self.true)
        # end
        gen.label_mark(end_label)

    def __str__(self):
        return '{} if {} else {}'.format(self.true, self.cond, self.false)


class WhileExpr(Expr):
    __slots__ = ('cond', 'body',)

    def __init__(self, cond, body):
        self.cond = cond
        self.body = body

    def compile(self, gen):
        begin_label = gen.label()
        end_label = gen.label()

        # condition
        gen.label_mark(begin_label)
        gen.load(self.cond)
        gen.emit(OP_JMP_IFN, end_label)
        # body
        gen.load(self.body)
        gen.emit(OP_POP)
        gen.emit(OP_JMP, begin_label)
        # end
        gen.label_mark(end_label)

    def __str__(self):
        return 'while {}: {}'.format(self.cond, self.body)


class CodeLabel(int):
    __slots__ = tuple()

    def __str__(self):
        return 'l:{}'.format(int.__str__(self))


class CodeGen(object):
    __slots__ = ('ops', 'consts', 'labels',)

    def __init__(self):
        self.ops = []
        self.consts = []
        self.labels = []

    def emit(self, op, arg=None):
        self.ops.append(op)
        if op & HAS_ARG:
            assert arg is not None, "this opcode must not have argument"
            self.ops.append(arg)

    def const(self, const):
        try:
            return self.consts.index(const)
        except Exception:
            self.consts.append(const)
            return len(self.consts) - 1

    def load(self, target):
        if isinstance(target, Expr):
            target.compile(self)
        else:
            self.emit(OP_LDCONST, self.const(target))

    def label(self):
        self.labels.append(None)
        return CodeLabel(len(self.labels) - 1)

    def label_mark(self, label):
        if self.labels[label] is not None:
            raise ValueError('label has already been marked')
        self.labels[label] = len(self.ops)

    def code(self):
        if None in self.labels:
            raise ValueError('not all labels has been marked')
        for index in range(len(self.ops)):
            if isinstance(self.ops[index], CodeLabel):
                self.ops[index] = self.labels[self.ops[index]]
        return Code(bytearray(self.ops),
                    tuple(self.consts) if self.consts else None)


class Code(tuple):
    __slots__ = tuple()

    def __new__(cls, ops, consts):
        return tuple.__new__(cls, (ops, consts))

    def __reduce__(self):
        return Code, tuple(self)

    @property
    def ops(self):
        return self[0]

    @property
    def consts(self):
        return self[1]

    def __call__(self, *args, **opts):
        monad = opts.get('monad', Cont)
        return monad.unit(None).bind(lambda _: self.eval(args, 0, [], monad))

    def eval(self, args, pos, stack, monad):
        ops, consts = self
        a_empty = tuple()
        try:
            ops_size = len(ops)
            while pos < ops_size:
                if ops[pos] & HAS_ARG:
                    op, arg = ops[pos:pos + 2]
                    pos = pos + 2
                else:
                    op, arg = ops[pos], '<not available>'
                    pos = pos + 1

                if op == OP_LDARG:
                    stack.append(args[arg])

                elif op == OP_LDCONST:
                    stack.append(consts[arg])

                elif op == OP_POP:
                    stack.pop()

                elif op == OP_DUP:
                    stack.append(stack[-1])

                elif op == OP_CALL:
                    if arg:
                        a_count, kw_count = arg & 0xf, arg >> 4
                        kw = {}
                        if kw_count:
                            for _ in range(kw_count):
                                val, key = stack.pop(), stack.pop()
                                kw[key] = val
                        a = a_empty
                        if a_count:
                            a, stack = stack[-a_count:], stack[:-a_count]
                        stack.append(stack.pop()(*a, **kw))
                    else:
                        stack.append(stack.pop()())

                elif op == OP_RETURN:
                    break

                elif op == OP_RAISE:
                    raise stack.pop()

                elif op == OP_BIND:
                    def eval_cont(val):
                        stack.append(val)
                        return self.eval(args, pos, list(stack), monad)
                    return monad.bind(stack.pop().__monad__(), eval_cont)

                elif op == OP_GETATTR:
                    stack.append(getattr(stack.pop(), consts[arg]))

                elif op == OP_SETATTR:
                    setattr(stack.pop(), consts[arg], stack.pop())

                elif op == OP_GETITEM:
                    item, target = stack.pop(), stack.pop()
                    stack.append(target[item])

                elif op == OP_SETITEM:
                    item, target, value = stack.pop(), stack.pop(), stack.pop()
                    target[item] = value

                elif op == OP_JMP:
                    pos = arg

                elif op == OP_JMP_IF:
                    if stack.pop():
                        pos = arg

                elif op == OP_JMP_IFN:
                    if not stack.pop():
                        pos = arg

                elif op == OP_COMPARE:
                    second, first = stack.pop(), stack.pop()
                    if arg == CMP_LE:
                        cmp = first < second
                    elif arg == CMP_LQ:
                        cmp = first <= second
                    elif arg == CMP_EQ:
                        cmp = first == second
                    elif arg == CMP_NE:
                        cmp = first != second
                    elif arg == CMP_GT:
                        cmp = first > second
                    elif arg == CMP_GE:
                        cmp = first >= second
                    elif arg == CMP_IN:
                        cmp = first in second
                    elif arg == CMP_NIN:
                        cmp == first not in second
                    elif arg == CMP_IS:
                        cmp = first is second
                    elif arg == CMP_ISN:
                        cmp = first is not second
                    else:
                        raise ValueError('unknown compare operation: {}'.format(arg))
                    stack.append(cmp)

                elif op == OP_NOP:
                    continue

                else:
                    raise ValueError('unknown operation code: {}'.format(op))

            return monad.unit(Result.from_value(stack.pop() if stack else None))

        except Exception:
            return monad.unit(Result.from_current_error())

    def __str__(self):
        ops, consts = self
        stream = StringIO()
        stream.write('Code(size:{}, consts:{}, opcodes:\n'.format(len(ops),
                     len(consts) if consts else 0))

        pos = 0
        while pos < len(ops):
            if ops[pos] & HAS_ARG:
                op, arg = ops[pos:pos + 2]
                stream.write('  {:>02} {:<10} '.format(pos, MAP_OP_NAME[op]))
                if op in (OP_LDCONST, OP_GETATTR, OP_SETATTR):
                    stream.write(repr(consts[arg]))
                elif op == OP_COMPARE:
                    stream.write(MAP_CMP_NAME[arg])
                else:
                    stream.write(repr(arg))
                stream.write('\n')
                pos = pos + 2

            else:
                op, arg = ops[pos], '<not available>'
                stream.write('  {:>02} {}\n'.format(pos, MAP_OP_NAME[op]))
                pos = pos + 1

        stream.seek(stream.tell() - 1)
        stream.write(')')
        return stream.getvalue()

    def __repr__(self):
        return str(self)
