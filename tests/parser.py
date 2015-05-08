import unittest
import struct as S
from ..monad import do_return
from ..parser import *

__all__ = ('ParserTest',)


class ParserTest(unittest.TestCase):
    """Parser unittest
    """
    def test_string(self):
        p = string("abc")
        for data in ("abb", "ab"):
            with self.assertRaises(ParserError):
                p.parse_only(data)
        self.assertEqual(p.parse_only("abc"), ("abc", ""))
        self.assertEqual(p.parse_only("abcd"), ("abc", "d"))
        self.assertEqual(parse_from(p, "a","b","cd","e"), ("abc", "d"))

    def test_monad(self):
        # bind
        p = string("begin") & string(",") & string("end")
        r = (("begin", ","), "end")
        for data in ("begin|end", "begin,en"):
            with self.assertRaises(ParserError):
                p.parse_only(data)
        self.assertEqual(p.parse_only("begin,end,tail"), (r, ",tail"))
        self.assertEqual(parse_from(p, "beg", "in,", "end|"), (r, "|"))
        # unit
        self.assertEqual(Parser.unit(10).parse_only("abc"), (10, "abc"))

    def test_alternative(self):
        # or
        p = string("abc") | string("abde")
        self.assertEqual(p.parse_only("abc|"), ("abc","|"))
        self.assertEqual(p.parse_only("abde|"), ("abde","|"))
        self.assertEqual(parse_from(p, "a", "b", "c|"), ("abc", "|"))
        self.assertEqual(parse_from(p, "a", "b", "d", "e|"), ("abde", "|"))
        with self.assertRaises(ParserError):
            p.parse_only("abb")
        # empty
        for p in (string("abc") | Parser.zero(), Parser.zero() | string("abc")):
            for d in ("ab", "abb"):
                with self.assertRaises(ParserError):
                    p.parse_only(d)
                self.assertEqual(p.parse_only("abcd"), ("abc", "d"))
                self.assertEqual(parse_from(p, "a", "bcd"), ("abc", "d"))

    def test_some(self):
        p = string("ab").some
        self.assertEqual(p.parse_only("ababa"), (("ab","ab"), "a"))
        for d in ("a", "ac"):
            with self.assertRaises(ParserError):
                p.parse_only(d)

    def test_many(self):
        p = string("ab").many
        self.assertEqual(p.parse_only("ababc"), (("ab","ab"), "c"))
        self.assertEqual(p.parse_only("ac"), (tuple(), "ac"))

    def test_shifts(self):
        p = string("ab") >> string("cd")
        self.assertEqual(p.parse_only("abcde"), ("cd", "e"))
        with self.assertRaises(ParserError):
            p.parse_only("abe")
        p = string("ab") << string("cd")
        self.assertEqual(p.parse_only("abcde"), ("ab", "e"))
        with self.assertRaises(ParserError):
            p.parse_only("abe")

    def test_parser(self):
        @parser
        def header():
            name  = yield take_while(lambda c: c != ":")
            yield take(1)
            value = yield take_while(lambda c: c != "\n")
            do_return((name, value.strip()))
        self.assertEqual(header().parse_only("Type: 32\n"), (("Type", "32"), "\n"))
        self.assertEqual(parse_from(header(), "Type:", "3", "2\n"), (("Type", "32"), "\n"))

    def test_take(self):
        p = take(3)
        self.assertEqual(p.parse_only("abc"), ("abc", ""))
        self.assertEqual(p.parse_only("abcd"), ("abc", "d"))
        self.assertEqual(parse_from(p, "ab", "cd"), ("abc", "d"))
        with self.assertRaises(ParserError):
            p.parse_only("ab")

    def test_take_while(self):
        p = take_while(lambda c: c != 'a')
        self.assertEqual(p.parse_only("--a++"), ("--", "a++"))
        self.assertEqual(parse_from(p, "-", "--", "a++"), ("---", "a++"))

    def test_struct(self):
        for p in (struct("I"), struct(S.Struct("I"))):
            self.assertEqual(p.parse_only(S.pack("I", 42)), (42, b""))
            self.assertEqual(p.parse_only(S.pack("I", 42) + b"|"), (42, b"|"))
            with self.assertRaises(ParserError):
                self.assertEqual(p.parse_only(b'   '))

    def test_parens(self):
        @parser
        def parens():
            yield string("(")
            yield parens().many
            yield string(")")
        p = (parens() >> Parser.unit(True) | Parser.unit(False))
        self.assertEqual(p.parse_only(")"), (False, ")"))
        self.assertEqual(p.parse_only("()"), (True, ""))
        self.assertEqual(p.parse_only("())"), (True, ")"))
        self.assertEqual(p.parse_only("(()())"), (True, ""))
        self.assertEqual(p.parse_only("(()"), (False, "(()"))

    def test_end(self):
        p = string("a")
        self.assertEqual((p >> at_end).parse_only("a"), (True, ""))
        self.assertEqual((p >> at_end).parse_only("ab"), (False, "b"))
        self.assertEqual((p << end_of_input).parse_only("a"), ("a", ""))
        with self.assertRaises(ParserError):
            (p << end_of_input).parse_only("ab")

    def test_match(self):
        self.assertEqual(match(take(5)).parse_only("ab", "cd", "efg"), (("abcde",) * 2, "fg"))
        self.assertEqual(match(take(2).many).parse_only("a", "bcd", "e"), (("abcd", ("ab", "cd")), "e"))
        self.assertEqual(match(take(3)).parse_only("abc"), (("abc",) * 2, ""))


def parse_from(parser, *chunks):
    """Use iterator 'it' as source of chunks
    """
    return parser.parse_only_iter(chunks)

