"""Monadic parser combinator
"""
import struct    as S
import functools as F
from .utils import call
from .monad import Monad, do, do_return

__all__ = ('Parser', 'ParserResult', 'ParserError', 'parser',
           'at_end', 'end_of_input', 'string', 'take', 'take_while', 'struct',)


class ParserError(Exception):
    """Parser error
    """

class ParserResult(tuple):
    """Parser result

    ParserResult a = Error String | Done a String Bool | Partial (Parser a)
    """
    ERROR   = 0b001
    DONE    = 0b010
    PARTIAL = 0b100

    def __new__(cls, tupe, value):
        assert tupe in {0b001, 0b010, 0b100}, "Invalid parser result type: {}".format(tupe)
        return tuple.__new__(cls, (tupe, value))

    @classmethod
    def from_error(cls, error):
        assert isinstance(error, str), "Error must be a string"
        return cls(cls.ERROR, error)

    @classmethod
    def from_done(cls, value, chunk, last):
        return cls(cls.DONE, (value, chunk, last))

    @classmethod
    def from_partial(cls, parser):
        return cls(cls.PARTIAL, parser)

    def __str__(self):
        tupe, value = self
        if tupe & self.ERROR:
            return "ParserError(\"{}\")".format(value)
        elif tupe & self.DONE:
            value, chunk, last = value
            return "ParserDone({},{}{})".format(value, repr(chunk), "$" if last else "")
        elif tupe & self.PARTIAL:
            return "ParserPartial(...)"

    def __repr__(self):
        return str(self)


class Parser(Monad):
    """Monadic parser

    Parser a = Parser { run :: String -> Bool -> ParserResult a }
    """
    __slots__ = ('run',)

    def __init__ (self, run, *args):
        self.run = F.partial(run, *args)

    def __call__(self, chunk, last):
        return self.run(chunk, last)

    def parse_only(self, *chunks):
        """Parse input `chunks`, if `chunks` is incorrect or too short raise and error.
        """
        return self.parse_only_iter(chunks)

    def parse_only_iter(self, chunks):
        """Run parser with provided `chunks`
        """
        parser, chunk = self, b''
        for chunk in chunks:
            tupe, value = parser(chunk, False)
            if tupe & ParserResult.DONE:
                return value[:-1]
            elif tupe & ParserResult.ERROR:
                raise ParserError(value)
            parser = value
        tupe, value = parser(b'' if isinstance(chunk, bytes) else '', True)
        if tupe & ParserResult.DONE:
            return value[:-1]
        elif tupe & ParserResult.ERROR:
            raise ParserError(value)
        raise ParserError("Partial parser after consuming last chunk")

    # Monad
    @classmethod
    def unit(cls, value):
        return Parser(ParserResult.from_done, value)

    def bind(self, fun):
        def run(chunk, last):
            result = self(chunk, last)
            tupe, value = result
            if tupe & ParserResult.DONE:
                value, chunk, last = value
                return fun(value).__monad__()(chunk, last)
            elif tupe & ParserResult.PARTIAL:
                if last:
                    return ParserResult.error("Partial result with last chunk")
                return ParserResult.from_partial(value.__monad__().bind(fun))
            else:
                return result
        return Parser(run)

    # Alternative | MonadPlus
    @staticmethod
    def zero():
        """Always failing parser.
        """
        return Parser(lambda chunk, last: ParserResult.from_error("Zero parser"))

    def __or__(self, other):
        """Tries this parser and if fails use other.
        """
        def run(parser, chunks, chunk, last):
            result = parser(chunk, last)
            tupe, value = result
            if tupe & ParserResult.DONE:
                return result
            elif tupe & ParserResult.PARTIAL and not last:
                return ParserResult.from_partial(Parser(run, value, (chunk, chunks)))
            else:
                return other.__monad__()(_chunks_merge((chunk, chunks)), last)
        return Parser(run, self, tuple())

    def __and__(self, other):
        return self.bind(
            lambda left: other.bind(
                lambda right: self.unit((left, right))))

    def plus(self, other):
        """Tries this parser and if fails use other.
        """
        return self | other

    # Combinators
    def __lshift__(self, other):
        return (self & other).map_val(lambda pair: pair[0])

    def __rshift__(self, other):
        return (self & other).map_val(lambda pair: pair[1])

    @property
    def some(self):
        """Match at least once.
        """
        return self.bind(
            lambda val: (self.some | self.unit(tuple())).bind(
                lambda vals: self.unit((val,) + vals)))

    @property
    def many(self):
        """Match zero or more.
        """
        return self.bind(
            lambda val: self.many.bind(
                lambda vals: self.unit((val,) + vals))) | self.unit(tuple())

    def repeat(self, count):
        """Repeat this parser `count` times.
        """
        return self.Sequence((self,) * count)


def parser(block):
    """Parser do block
    """
    def unwrap_result(result):
        tupe, value = result
        if tupe & ParserResult.DONE:
            value, chunk, last = value
            return (ParserResult.from_done(value.value, chunk, last) if value.error is None else
                    ParserResult.from_error(value.error))
        elif tupe & ParserResult.PARTIAL:
            return ParserResult.from_partial(Parser(lambda chunk, last: unwrap_result(value(chunk, last))))
        else:
            return result
    do_block = do(Parser)(block)
    return F.wraps(block)(
        lambda *args, **kwargs: Parser(
            lambda chunk, last: unwrap_result(do_block(*args, **kwargs)(chunk, last))))


"""Return indication of weither end of input has been reached
"""
@call
def at_end():
    def run(chunk, last):
        if chunk:
            return ParserResult.from_done(False, chunk, last)
        elif last:
            return ParserResult.from_done(True, chunk, last)
        else:
            return ParserResult.from_partial(Parser(run))
    return Parser(run)


"""Matches only if all input has been consumed
"""
end_of_input = at_end.bind(lambda end: Parser(lambda chunk, last: ParserResult.from_error("Not end of input"))
                           if not end else Parser.unit(None))


def string(target):
    """Match specified `target` string.
    """
    def run(suffix, chunk, last):
        if len(chunk) < len(suffix):
            if suffix.startswith(chunk):
                if last:
                    return ParserResult.from_error("Not enough input")
                else:
                    return ParserResult.from_partial(Parser(run, suffix[len(chunk):]))
            else:
                return ParserResult.from_error("Target mismatches input")
        elif chunk.startswith(suffix):
            return ParserResult.from_done(target, chunk[len(suffix):], last)
        else:
            return ParserResult.from_error("Target mismatches input")
    return Parser(run, target)


def take(count):
    """Parse `count` bytes
    """
    def run(length, chunks, chunk, last):
        if length > len(chunk):
            if last:
                return ParserResult.from_error("Not enough input")
            else:
                return ParserResult.from_partial(Parser(run, length - len(chunk), (chunk, chunks)))
        else:
            return ParserResult.from_done(_chunks_merge((chunk[:length], chunks)),
                                          chunk[length:], last)
    return Parser(run, count, tuple())


def take_while(pred):
    """Take while predicate is true
    """
    def run(chunks, chunk, last):
        for i, c in enumerate(chunk):
            if not pred(c):
                return ParserResult.from_done(_chunks_merge((chunk[:i], chunks)), chunk[i:], last)
        if last:
            return ParserResult.from_error("Not enough input")
        else:
            return ParserResult.from_partial(Parser(run, (chunk, chunks)))
    return Parser(run, tuple())


def struct(pattern):
    """Unpack from `pattern` struct object or struct description.
    """
    struct = S.Struct(pattern) if isinstance(pattern, (str, bytes)) else pattern
    def unpack(data):
        vals = struct.unpack(data)
        return vals if len(vals) != 1 else vals[0]
    return take(struct.size).map_val(unpack)


def _chunks_merge(chunks):
    """Merge reversed linked list of chunks `cs` to single chunk.

    ("three", ("two-", ("one-", ()))) -> "one-two-three"
    """
    chunks_ = []
    while chunks:
        chunk, chunks = chunks
        chunks_.append(chunk)
    return chunks_[0][:0].join(reversed(chunks_)) if chunks_ else b""
