import io
import unittest
from ..store import StreamStore

__all__ = ('StoreStreamTest',)


class StoreStreamTest(unittest.TestCase):
    def testCheck(self):
        store = StreamStore(io.BytesIO())
        stream = store.create_stream(b'test', bufsize=8)

        # read outside of data
        self.assertEqual(stream.seek(10), 10)
        self.assertEqual(stream.read(), b'')
        self.assertEqual(stream.size, 0)

        # write outside of data(zero filling)
        self.assertEqual(stream.write(b'X'), 1)
        self.assertEqual(stream.seek(0), 0)
        self.assertEqual(stream.size, 11)
        self.assertEqual(stream.read(), b'\x00' * 10 + b'X')
        self.assertEqual(stream.tell(), 11)

        # data update
        stream.seek(1)
        self.assertEqual(stream.write(b'ABC'), 3)
        self.assertEqual(stream.read(1), b'\x00')
        stream.seek(0)
        self.assertEqual(stream.read(5), b'\x00ABC\x00')
        stream.flush()

        # reload stream
        stream = store.create_stream(b'test')
        self.assertEqual(stream.read(), b'\x00ABC' + b'\x00' * 6 + b'X')

    def test_mult(self):
        store = StreamStore(io.BytesIO())
        with store.create_stream('a') as a, store.create_stream('b') as b:
            a.write(b'stream a')
            b.write(b'stream b')
        with store.create_stream('a') as a, store.create_stream('b') as b:
            self.assertEqual(a.read(), b'stream a')
            self.assertEqual(b.read(), b'stream b')
