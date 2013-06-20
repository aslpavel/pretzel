import io
import re
import struct
import unittest
import collections

from ..stream import Stream
from ..buffered import Buffer, BufferedStream
from ...monad import Result, async, do_return
from ...event import Event
from ...uniform import BrokenPipeError

__all__ = ('BufferTest', 'BufferedStreamTest',)


class BufferTest (unittest.TestCase):
    def test(self):
        buff = Buffer()

        buff.enqueue(b'01234')
        buff.enqueue(b'56789')
        buff.enqueue(b'01234')

        self.assertEqual(len(buff), 15)

        # single chunk
        self.assertEqual(buff.slice(3), b'012')
        self.assertEqual(tuple(buff.chunks), (b'01234', b'56789', b'01234',))

        # cross chunk
        self.assertEqual(buff.slice(6), b'012345')
        self.assertEqual(tuple(buff.chunks), (b'0123456789', b'01234',))

        # discard chunk
        buff.dequeue(3)
        self.assertEqual(len(buff), 12)
        self.assertEqual(buff.offset, 3)
        self.assertEqual(tuple(buff.chunks), (b'0123456789', b'01234',))

        # with offset
        self.assertEqual(buff.slice(3), b'345')
        self.assertEqual(tuple(buff.chunks), (b'0123456789', b'01234',))

        # discard cross chunk
        buff.dequeue(8)
        self.assertEqual(len(buff), 4)
        self.assertEqual(buff.offset, 1)
        self.assertEqual(tuple(buff.chunks), (b'01234',))

        buff.enqueue(b'56789')
        buff.enqueue(b'01234')

        # cross chunks with offset
        self.assertEqual(buff.slice(5), b'12345')
        self.assertEqual(tuple(buff.chunks), (b'0123456789', b'01234',))

        # peek all
        self.assertEqual(buff.slice(128), b'12345678901234')
        self.assertEqual(tuple(buff.chunks), (b'012345678901234',))

        buff.enqueue(b'56789')

        # discard all
        buff.dequeue(128)
        self.assertEqual(len(buff), 0)
        self.assertEqual(tuple(buff.chunks), tuple())

        for _ in range(3):
            buff.enqueue(b'0123456789')

        # discard with chunk cut
        buff.dequeue(6)
        self.assertEqual(len(buff), 24)
        self.assertEqual(buff.offset, 0)
        self.assertEqual(tuple(buff.chunks), (b'6789', b'0123456789', b'0123456789'))

        # discard edge
        buff.dequeue(14)
        self.assertEqual(len(buff), 10)
        self.assertEqual(buff.offset, 0)
        self.assertEqual(tuple(buff.chunks), (b'0123456789',))

        # discard less then half
        buff.dequeue(4)
        self.assertEqual(len(buff), 6)
        self.assertEqual(buff.offset, 4)
        self.assertEqual(tuple(buff.chunks), (b'0123456789',))

        # discard big
        buff.dequeue(128)
        self.assertEqual(len(buff), 0)
        self.assertEqual(buff.offset, 0)
        self.assertEqual(tuple(buff.chunks), tuple())


class BufferedStreamTest (unittest.TestCase):
    def test_read(self):
        res = ResultQueue()
        stream = BufferedStream(DummyStream(), 8)

        stream.read(6)(res)
        stream.read_complete(b'012')
        self.assertEqual(res.pop(), b'012')

        stream.read(3)(res)
        stream.read_complete(b'012345')
        self.assertEqual(res.pop(), b'012')
        stream.read(6)(res)
        self.assertEqual(res.pop(), b'345')

        stream.read(3)(res)
        stream.read_complete(b'0123456789')
        self.assertEqual(res.pop(), b'012')
        stream.read(6)(res)
        self.assertEqual(res.pop(), b'34567')
        self.assertFalse(res)

    def test_read_until_size(self):
        res = ResultQueue()
        stream = BufferedStream(DummyStream(), 8)

        stream.read_until_size(10)(res)
        self.assertFalse(res)
        stream.read_complete(b'0123456789')
        self.assertFalse(res)
        stream.read_complete(b'0123456789')
        self.assertEqual(res.pop(), b'0123456701')

        stream.read_until_size(4)(res)
        self.assertEqual(res.pop(), b'2345')
        self.assertFalse(res)

    def test_read_until_eof(self):
        res = ResultQueue()
        stream = BufferedStream(DummyStream(), 1024)

        stream.read_until_eof()(res)
        stream.read_complete(b'01234')
        stream.read_complete(b'56789')
        self.assertFalse(res)
        stream.read_complete(Result.from_exception(BrokenPipeError()))
        self.assertEqual(res.pop(), b'0123456789')
        self.assertFalse(res)

    def test_read_until_sub(self):
        res = ResultQueue()
        stream = BufferedStream(DummyStream(), 8)

        stream.read_until_sub(b';')(res)
        stream.read_complete(b'01234')
        self.assertFalse(res)
        stream.read_complete(b'56789;01')
        self.assertEqual(res.pop(), b'0123456789;')

        stream.read_until_sub(b';')(res)
        self.assertFalse(res)
        stream.read_complete(b'234;')
        self.assertEqual(res.pop(), b'01234;')
        self.assertFalse(res)

    def test_read_until_regex(self):
        res = ResultQueue()
        stream = BufferedStream(DummyStream(), 1024)
        regex = re.compile(br'([^=]+)=([^&]+)&')

        stream.read_until_regex(regex)(res)
        stream.read_complete(b'key_0=')
        self.assertFalse(res)
        stream.read_complete(b'value_0&key_1')
        self.assertEqual(res.pop()[0], b'key_0=value_0&')

        stream.read_until_regex(regex)(res)
        self.assertFalse(res)
        stream.read_complete(b'=value_1&tail')
        self.assertEqual(res.pop()[0], b'key_1=value_1&')

        stream.read(4)(res)
        self.assertEqual(res.pop(), b'tail')
        self.assertFalse(res)

    def test_write(self):
        res = ResultQueue()
        stream = BufferedStream(DummyStream(), 8)

        stream.write(b'0123456')(res)
        stream.write_complete(10)
        self.assertEqual(res.pop(), 7)
        self.assertEqual(stream.written, b'')

        stream.write(b'7')(res)  # flusher started
        self.assertEqual(res.pop(), 1)
        stream.write(b'89')(res)
        self.assertEqual(res.pop(), 2)
        stream.write_complete(10)
        self.assertEqual(stream.written, b'01234567')

        stream.write_complete(2)
        self.assertEqual(stream.written, b'0123456789')
        self.assertFalse(res)

        stream.written_stream.truncate(0)
        stream.written_stream.seek(0)
        stream.write(b'X' * 17)(res)  # blocked
        self.assertFalse(res)
        stream.write_complete(8)
        self.assertFalse(res)
        stream.write_complete(8)
        self.assertFalse(res)
        stream.write_complete(1)
        self.assertEqual(stream.written, b'X' * 17)
        self.assertEqual(res.pop(), 17)
        self.assertFalse(res)

    def test_bytes(self):
        res = ResultQueue()
        stream = BufferedStream(DummyStream(), 1024)
        bytes = b'some bytes string'

        stream.write_bytes(bytes)
        stream.flush()(res)
        self.assertFalse(res)
        stream.write_complete(1024)
        self.assertEqual(res.pop(), None)

        stream.read_bytes()(res)
        stream.read_complete(stream.written)
        self.assertEqual(res.pop(), bytes)
        self.assertFalse(res)

    def test_struct_list(self):
        res = ResultQueue()
        stream = BufferedStream(DummyStream(), 1024)

        struct_type = struct.Struct('>H')
        struct_list = [23, 16, 10, 32, 45, 18]

        stream.write_struct_list(struct_list, struct_type)
        stream.flush()()
        stream.write_complete(1024)

        stream.read_struct_list(struct_type)(res)
        stream.read_complete(stream.written)
        self.assertEqual(res.pop(), struct_list)
        self.assertFalse(res)

    def test_struct_list_complex(self):
        res = ResultQueue()
        stream = BufferedStream(DummyStream(), 1024)

        struct_type = struct.Struct('>HH')
        struct_list = [(23, 0), (16, 1), (10, 2), (32, 3), (45, 4), (18, 5)]

        stream.write_struct_list(struct_list, struct_type, True)
        stream.flush()()
        stream.write_complete(1024)

        stream.read_struct_list(struct_type, True)(res)
        stream.read_complete(stream.written)
        self.assertEqual(res.pop(), struct_list)
        self.assertFalse(res)

    def test_bytes_list(self):
        res = ResultQueue()
        stream = BufferedStream(DummyStream(), 1024)
        bytes_list = [b'one', b'two', b'three', b'four', b'five']

        stream.write_bytes_list(bytes_list)
        stream.flush()()
        stream.write_complete(1024)

        stream.read_bytes_list()(res)
        stream.read_complete(stream.written)
        self.assertEqual(res.pop(), bytes_list)
        self.assertFalse(res)


class DummyStream(Stream):
    def __init__(self):
        Stream.__init__(self)
        self.initing()
        self.written_stream = io.BytesIO()
        self.read_complete = Event()
        self.write_complete = Event()

    @async
    def read(self, size):
        with self.reading:
            do_return((yield self.read_complete)[:size])

    @async
    def write(self, data):
        with self.writing:
            size = yield self.write_complete
            self.written_stream.write(data[:size])
            do_return(min(size, len(data)))

    @property
    def written(self):
        return self.written_stream.getvalue()


class ResultQueue(object):
    def __init__(self):
        self.queue = collections.deque()

    def __call__(self, val):
        self.queue.append(val)

    def pop(self):
        return self.queue.popleft().value

    def __len__(self):
        return len(self.queue)

    def __bool__(self):
        return bool(self.queue)
    __nonzero__ = __bool__
