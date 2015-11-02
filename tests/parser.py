import unittest
import struct as S
from ..monad import do_return
from ..uniform import PY2
from ..parser import *
if PY2:
    bytes = lambda v: v.__bytes__()

__all__ = ('ParserTest',)


class ParserTest(unittest.TestCase):
    """Parser unittest
    """
    def success(self, parser, result, left, *chunks):
        self.assertEqual(parser.__parser__().parse_only_iter(chunks), (result, left))

    def failure(self, parser, *chunks):
        with self.assertRaises(ParserError):
            parser.__parser__().parse_only_iter(chunks)

    def test_string(self):
        p = string("abc")
        for data in ("abb", "ab"):
            self.failure(p, data)
        self.success(p, "abc", "" , "abc")
        self.success(p, "abc", "d", "abcd")
        self.success(p, "abc", "d", "a", "b", "cd", "e")

    def test_monad(self):
        # bind
        p = string("begin") & string(",") & string("end")
        r = (("begin", ","), "end")
        for data in ("begin|end", "begin,en"):
            self.failure(p, data)
        self.success(p, r, ",tail", "begin,end,tail")
        self.success(p, r, "|"    , "beg", "in,", "end|")
        # unit
        self.success(Parser.unit(10), 10, "abc", "abc")

    def test_alternative(self):
        # or
        p = string("abc") | string("abde")
        self.success(p, "abc" , "|", "abc|")
        self.success(p, "abde", "|", "abde|")
        self.success(p, "abc" , "|", "a", "b", "c|")
        self.success(p, "abde", "|", "a", "b", "d", "e|")
        self.failure(p, "abb")
        # empty
        for p in (string("abc") | Parser.zero(), Parser.zero() | string("abc")):
            for d in ("ab", "abb"):
                self.failure(p, d)
                self.success(p, "abc", "d", "abcd")
                self.success(p, "abc", "d", "a", "bcd")

    def test_some(self):
        p = string("ab").some
        self.success(p, ("ab", "ab"), "a", "ababa")
        self.success(p, ("ab",)     , "" , "ab")
        for d in ("a", "ac"):
            self.failure(p, d)

    def test_many(self):
        p = string("ab").many
        self.success(p, ("ab", "ab"), "c" , "ababc")
        self.success(p, ("ab",)     , ""  , "ab")
        self.success(p, tuple()     , "ac", "ac")

    def test_shifts(self):
        p = string("ab") >> string("cd")
        self.success(p, "cd", "e", "abcde")
        self.failure(p, "abe")
        p = string("ab") << string("cd")
        self.success(p, "ab", "e", "abcde")
        self.failure(p, "abe")

    def test_parser(self):
        @parser
        def header():
            name  = yield take_while(lambda c: c != ":")
            yield take(1)
            value = yield take_while(lambda c: c != "\n")
            do_return((name, value.strip()))
        self.success(header(), ("Type", "32"), "\n", "Type: 32\n")
        self.success(header(), ("Type", "32"), "\n", "Typ", "e:", "3", "2\n")
        self.failure(header(), "Typa: 32")
        self.failure(header(), "Type: 32")

    def test_take(self):
        p = take(3)
        self.success(p, "abc", "" , "abc")
        self.success(p, "abc", "d", "abcd")
        self.success(p, "abc", "d", "ab", "cd")
        self.failure(p, "ab")

    def test_take_while(self):
        p = take_while(lambda c: c != 'a')
        self.success(p, "--" , "a++", "--a++")
        self.success(p, "---", "a++", "-", "--", "a++")

    def test_take_rest(self):
        self.success(take_rest, "abcd", "",  "a", "bcd")
        self.success(take_rest, "", "", "")

    def test_struct(self):
        for p in (struct("I"), struct(S.Struct("I"))):
            self.success(p, 42, b'' , S.pack("I", 42))
            self.success(p, 42, b'|', S.pack("I", 42) + b'|')
            self.failure(p, b'   ')

    def test_parens(self):
        @parser
        def parens():
            yield string("(")
            yield parens().many
            yield string(")")
        p = match(parens()).map_val(lambda pair: pair[0])
        self.success(p, "()"    , ""  , "()")
        self.success(p, "()"    , ")" , "())")
        self.success(p, "(()())", ""  , "(()", "())")
        self.success(p, "()"    , "()", "()()")
        self.failure(p, ")")
        self.failure(p, "(()")

    def test_end(self):
        p = string("a")
        self.success(p >> at_end      , True , "" , "a")
        self.success(p >> at_end      , False, "b", "ab")
        self.success(p << end_of_input, "a"  , "" , "a")
        self.failure(p << end_of_input, "ab")

    def test_match(self):
        self.success(match(take(5))     , ("abcde",) * 2        , "fg", "ab", "cd", "efg")
        self.success(match(take(2).many), ("abcd", ("ab", "cd")), "e" , "a", "bcd", "e")
        self.success(match(take(3))     , ("abc",) * 2          , ""  , "abc")

    def test_variant(self):
        self.success(Variant, Variant(777) , b'' , bytes(Variant(777)))
        self.success(Variant, Variant(-777), b'' , bytes(Variant(-777)))
        self.success(Variant, Variant(42)  , b'|', bytes(Variant(42)) + b'|')
        self.failure(Variant, b'')

    def test_bytes(self):
        self.success(Bytes, Bytes(b'one'), b'' , bytes(Bytes(b'one')))
        self.success(Bytes, Bytes(b'one'), b'|', bytes(Bytes(b'one')) + b'|')
        self.failure(Bytes, b'')

