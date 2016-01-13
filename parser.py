"""Monadic parser combinator
"""
import struct    as S
import functools as F
from .utils import call
from .uniform import PY2
from .monad import Monad, do, do_return

__all__ = ('Parser', 'ParserResult', 'ParserError',
           'parser',
           'at_end', 'end_of_input',
           'match',
           'string',
           'take', 'take_while', 'take_rest',
           'struct',
           'Varint', 'Bytes'
)

#-------------------------------------------------------------------------------
# Parser
#-------------------------------------------------------------------------------
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
        return cls(cls.ERROR, str(error))

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

    def __parser__(self):
        """Parsable interface

        Anything with this method will be treated as parser.
        """
        return self

    def __call__(self, chunk, last):
        """Execute parser

        () :: Parser a -> String -> Bool -> ParserResult a
        """
        return self.run(chunk, last)

    def parse_only(self, *chunks):
        """Parse input `chunks`, if `chunks` is incorrect or too short raise and error.

        parse_only :: Parser a -> String -> (a, String) | Exception
        """
        return self.parse_only_iter(chunks)

    def parse_only_iter(self, chunks):
        """Run parser with provided `chunks`

        parse_only_iter :: Parser a -> [String] -> (a, String) | Exception
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
        """Unit parser

        unit :: a -> Parser a
        """
        return Parser(ParserResult.from_done, value)

    def bind(self, fun):
        """Bind parser with parser producing function

        bind :: Parser a -> (a -> Parser b) -> Parser b
        """
        def run(chunk, last):
            result = self(chunk, last)
            tupe, value = result
            if tupe & ParserResult.DONE:
                value, chunk, last = value
                return fun(value).__parser__()(chunk, last)
            elif tupe & ParserResult.PARTIAL:
                if last:
                    return ParserResult.error("Partial result with last chunk")
                return ParserResult.from_partial(value.__parser__().bind(fun))
            else:
                return result
        return Parser(run)

    # Alternative | MonadPlus
    @staticmethod
    def zero():
        """Always failing parser.

        zero :: Parser a
        """
        return Parser(lambda chunk, last: ParserResult.from_error("Zero parser"))

    def __or__(self, other):
        """Tries this parser and if fails use other.

        (|) :: Parser a -> Parser a -> Parser a
        """
        def run(parser, chunks, chunk, last):
            result = parser(chunk, last)
            tupe, value = result
            if tupe & ParserResult.DONE:
                return result
            elif tupe & ParserResult.PARTIAL and not last:
                return ParserResult.from_partial(Parser(run, value, (chunk, chunks)))
            else:
                return other.__parser__()(_chunks_merge((chunk, chunks)), last)
        return Parser(run, self, tuple())

    def __and__(self, other):
        """Collect result of two parser in a tuple

        (&) :: Parser a -> Parser b -> Parser (a, b)
        """
        return self.bind(
            lambda left: other.__parser__().bind(
                lambda right: self.unit((left, right))))

    def plus(self, other):
        """Tries this parser and if fails use other.

        plus :: Parser a -> Parser a -> Parser a
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

        some :: Parser a -> Parser [a]
        """
        return self.bind(
            lambda val: (self.some | self.unit(tuple())).bind(
                lambda vals: self.unit((val,) + vals)))

    @property
    def many(self):
        """Match zero or more.

        match :: Parser a -> Parser [a]
        """
        return self.bind(
            lambda val: self.many.bind(
                lambda vals: self.unit((val,) + vals))) | self.unit(tuple())

    def repeat(self, count):
        """Repeat this parser `count` times.
        """
        return self.Sequence((self,) * count)


#-------------------------------------------------------------------------------
# Parser block decorator
#-------------------------------------------------------------------------------
def parser(block):
    """Parser block decorator

    Construct parser from generator block.
    """
    def unwrap(result):
        tupe, value = result
        if tupe & ParserResult.DONE:
            value, chunk, last = value
            return (ParserResult.from_done(value.value, chunk, last) if value.error is None else
                    ParserResult.from_error(value.error))
        elif tupe & ParserResult.PARTIAL:
            return ParserResult.from_partial(Parser(lambda chunk, last: unwrap(value(chunk, last))))
        else:
            return result
    do_block = do(Parser)(block)
    return F.wraps(block)(
        lambda *args, **kwargs: Parser(
            lambda chunk, last: unwrap(do_block(*args, **kwargs)(chunk, last))))


#-------------------------------------------------------------------------------
# Parsers
#-------------------------------------------------------------------------------
@call
def at_end():
    """Return indication of weither end of input has been reached

    at_end :: Parser Bool
    """
    def run(chunk, last):
        if chunk:
            return ParserResult.from_done(False, chunk, last)
        elif last:
            return ParserResult.from_done(True, chunk, last)
        else:
            return ParserResult.from_partial(Parser(run))
    return Parser(run)


@call
def end_of_input():
    """Matches only if all input has been consumed

    end_on_input :: Parser None
    """
    return at_end.bind(lambda end:
        Parser(lambda chunk, last: ParserResult.from_error("Not end of input"))
                              if not end else Parser.unit(None))


def match(parser):
    """Returns result of a parse and the portion of input that was consumed

    match :: Parser a -> Parser (String, a)
    """
    def run(parser, chunks, chunk, last):
        chunks = (chunk, chunks)
        result = parser.__parser__()(chunk, last)
        tupe, value = result
        if tupe & ParserResult.DONE:
            value, chunk, last = value
            match = _chunks_merge(chunks)[:-len(chunk)] if chunk else _chunks_merge(chunks)
            return ParserResult.from_done((match, value), chunk, last)
        elif tupe & ParserResult.PARTIAL:
            return ParserResult.from_partial(Parser(run, value, chunks))
        else:
            return result
    return Parser(run, parser, tuple())


def string(target):
    """Match specified `target` string.

    string :: String -> Parser String
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

    take :: Int -> Parser String
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

    take_white :: (Char -> Bool) -> Parser String
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


@call
def take_rest():
    """Take rest of the input

    take_rest :: Parser String
    """
    def run(chunks, chunk, last):
        if last:
            return ParserResult.from_done(_chunks_merge((chunk, chunks)), chunk[:0], last)
        else:
            return ParserResult.from_partial(Parser(run, (chunk, chunks)))
    return Parser(run, tuple())


def struct(pattern):
    """Unpack from `pattern` struct object or struct description.

    struct :: (String | Struct a) -> Parser a
    """
    struct = S.Struct(pattern) if isinstance(pattern, (str, bytes)) else pattern
    def unpack(data):
        vals = struct.unpack(data)
        return vals if len(vals) != 1 else vals[0]
    return take(struct.size).map_val(unpack)


#-------------------------------------------------------------------------------
# Parsable types
#-------------------------------------------------------------------------------
class Varint(int):
    """Varint value

    Compactly packable integer value. Most significant bit indicates whether there is
    more octets to be parsed apart from current, lower 7 bits hold two's complement
    representation of value, least significant group first, first bit in this series
    indicates weither value is negative.
    """
    __slots__ = tuple()

    def __new__(cls, value):
        return int.__new__(cls, value)

    def __bytes__(self):
        """Bytes representation for Varint
        """
        value  = (abs(self) << 1) | (1 if self < 0 else 0)
        octets = bytearray()
        while True:
            octet, value = value & 0x7f, value >> 7
            if value > 0:
                octets.append(octet | 0x80)
            else:
                octets.append(octet)
                break
        return bytes(octets)

    @classmethod
    def __parser__(cls):
        """Varint value parser
        """
        byte = cls.__byte
        def from_octets(octets):
            octets = octets[0] + octets[1]
            value  = sum((byte(o) & 0x7f) << i * 7 for i, o in enumerate(octets))
            if value & 0x1:
                return cls(-(value >> 1))
            else:
                return cls(value >> 1)
        return ((take_while(lambda octet: byte(octet) & 0x80) & take(1))
                .map_val(from_octets))

    @classmethod
    def __monad__(cls):
        return cls.__parser__()

    if PY2:
        __byte = staticmethod(lambda b: ord(b))
    else:
        __byte = staticmethod(lambda b: b)

    def __str__(self):
        return '{}({})'.format(type(self).__name__, int.__str__(self))

    def __repr__(self):
        return str(self)


class Bytes(bytes):
    """Parsable bytes

    Bytes prefixed with variant indicating size of bytes
    """
    def __bytes__(self):
        return Varint(len(self)).__bytes__() + self

    @classmethod
    def __parser__(cls):
        return Varint.__parser__().bind(take).map_val(cls)

    @classmethod
    def __monad__(cls):
        return cls.__parser__()

    def __str__(self):
        return '{}({})'.format(type(self).__name__, bytes.__str__(self))

    def __repr__(self):
        return str(self)


#-------------------------------------------------------------------------------
# Helpers
#-------------------------------------------------------------------------------
def _chunks_merge(chunks):
    """Merge reversed linked list of chunks `cs` to single chunk.

    ("three", ("two-", ("one-", ()))) -> "one-two-three"
    """
    chunks_ = []
    while chunks:
        chunk, chunks = chunks
        chunks_.append(chunk)
    return chunks_[0][:0].join(reversed(chunks_)) if chunks_ else b""
