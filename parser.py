"""Monadic parser combinator
"""
import struct    as S
import functools as F
from .monad import Monad, do, do_return

__all__ = ('Parser', 'ParserResult', 'ParserError', 'parser', 'string',
           'take', 'take_while', 'struct',)


class ParserError(Exception):
    """Parser error
    """

class ParserResult(tuple):
    """Parser result

    ParserResult a = Error String | Done a String | Partial (Parser a)
    """
    ERROR   = 0b001
    DONE    = 0b010
    PARTIAL = 0b100

    def __new__(cls, tupe, value):
        assert tupe in {0b001, 0b010, 0b100}, "Invalid parser result type: {}".format(tupe)
        return tuple.__new__(cls, (tupe, value))

    @classmethod
    def from_error(cls, error):
        return cls(cls.ERROR, error)

    @classmethod
    def from_done(cls, value, left):
        return cls(cls.DONE, (value, left))

    @classmethod
    def from_partial(cls, parser):
        return cls(cls.PARTIAL, parser)

    def __str__(self):
        t, v = self
        if t & self.ERROR:
            return "ParserError(\"{}\")".format(v)
        elif t & self.DONE:
            return "ParserDone({},\"{}\")".format(*v)
        elif t & self.PARTIAL:
            return "ParserPartial(...)"

    def __repr__(self):
        return str(self)


class Parser(Monad):
    """Monadic parser

    Parser a = Parser { run :: String -> ParserResult a }
    """
    __slots__ = ('run',)

    def __init__ (self, run):
        self.run = run

    def __call__(self, s):
        return self.run(s)

    def parse_only(self, data):
        """Parse input `data`, if `data` is incorrect or too short raise and error.
        """
        gen = iter([data, b''])
        return self.parse_with(lambda: next(gen))

    def parse_with(self, get):
        """Run parser and execute function `get` if more data is needed.

        Function `get` shoud return empty streen when input is deleeted.
        """
        parser = self
        while True:
            data = get()
            if not data:
                raise ParserError("Not enough input")
            tupe, value = parser.run(data)
            if tupe & ParserResult.DONE:
                return value
            elif tupe & ParserResult.PARTIAL:
                parser = value
            else: raise ParserError(value)

    # Monad
    @classmethod
    def unit(cls, v):
        return Parser(lambda s: ParserResult.from_done(v, s))

    def bind(self, fun):
        def run(s):
            r = self.run(s)
            t, v = r
            if t & ParserResult.DONE:
                v, l = v
                return fun(v).__monad__().run(l)
            elif t & ParserResult.PARTIAL:
                return ParserResult.from_partial(v.__monad__().bind(fun))
            else:
                return r
        return Parser(run)

    # Alternative | MonadPlus
    @staticmethod
    def zero():
        """Always failing parser.
        """
        return Parser(lambda _: ParserResult.from_error("Zero parser"))

    def __or__(self, other):
        """Tries this parser and if fails use other.
        """
        def run(s):
            r = self.run(s)
            t, v = r
            if t & ParserResult.DONE:
                return r
            elif t & ParserResult.PARTIAL:
                def run_other(c):
                    return other.__monad__().run(s + c)
                return ParserResult.from_partial(v | Parser(run_other))
            else:
                return other.__monad__().run(s)
        return Parser(run)

    def __and__(self, other):
        return self.bind(
            lambda l: other.bind(
                lambda r: self.unit((l, r))))

    def plus(self, other):
        """Tries this parser and if fails use other.
        """
        return self | other

    # Combinators
    def __lshift__(self, other):
        return (self & other).map_val(lambda p: p[0])

    def __rshift__(self, other):
        return (self & other).map_val(lambda p: p[1])

    def some(self):
        """Match at least once.
        """
        return self.bind(
            lambda x: (self.some() | self.unit(tuple())).bind(
                lambda xs: self.unit((x,) + xs)))

    def many(self):
        """Match zero or more.
        """
        return self.bind(
            lambda x: self.many().bind(
                lambda xs: self.unit((x,) + xs))) | self.unit(tuple())

    def repeat(self, count):
        """Repeat this parser `count` times.
        """
        return self.Sequence((self,) * count)


def parser(block):
    """Parser do block
    """
    def unwrap_result(r):
        t, v = r
        if t & ParserResult.DONE:
            v, s = v
            return (ParserResult.from_done(v.value, s) if v.error is None else
                    ParserResult.from_error(v.error))
        elif t & ParserResult.PARTIAL:
            return ParserResult.from_partial(Parser(lambda s: unwrap_result(v.run(s))))
        else:
            return r
    do_block = do(Parser)(block)
    return F.wraps(block)(
        lambda *a, **kw: Parser(
            lambda s: unwrap_result(do_block(*a, **kw).run(s))))


def string(target):
    """Match specified `target` string.
    """
    def run(s):
        if len(s) < len(target):
            if target.startswith(s):
                return ParserResult.from_partial(Parser(lambda c: run(s + c)))
            else:
                return ParserResult.from_error("Target mismatches input")
        elif s.startswith(target):
            return ParserResult.from_done(target, s[len(target):])
        else:
            return ParserResult.from_error("Target mismatches input")
    return Parser(run)


def take(count):
    """Parse `count` bytes
    """
    def run(s):
        if len(s) < count:
            return ParserResult.from_partial(Parser(lambda c: run(s + c)))
        return ParserResult.from_done(s[:count], s[count:])
    return Parser(run)


def take_while(pred):
    """Take while predicate is true
    """
    def run(s, chunks=tuple()):
        for i, c in enumerate(s):
            if not pred(c):
                return ParserResult.from_done(''.join(chunks) + s[:i], s[i:])
        return ParserResult.from_partial(Parser(lambda c: run(c, chunks + (s,))))
    return Parser(run)


def struct(st):
    """Unpack from `st` struct object or struct description.
    """
    st = S.Struct(st) if isinstance(st, (str, bytes)) else st
    def unpack(d):
        vs = st.unpack(d)
        return vs if len(vs) != 1 else vs[0]
    return take(st.size).map_val(unpack)
