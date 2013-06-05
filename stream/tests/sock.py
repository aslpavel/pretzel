import io
import socket
import unittest
import itertools
from ..sock import Socket
from ...monad import async
from ...common import BrokenPipeError
from ...core import schedule
from ...tests import async_test

__all__ = ('SockTest',)


class SockTest(unittest.TestCase):
    PORT = 54321
    BLOCK = b'X' * 1024

    @async_test
    def test(self):
        received = io.BytesIO()

        @async
        def server_coro():
            with Socket(socket.socket()) as sock:
                sock.bind(('localhost', self.PORT))
                sock.listen(10)
                client, addr = yield sock.accept()
                with client:
                    try:
                        while True:
                            received.write((yield client.read(1024)))
                    except BrokenPipeError:
                        pass
        server = server_coro().future()
        server.__monad__()()  # error trace if any
        if server.completed:
            yield server

        with Socket(socket.socket()) as sock:
            yield sock.connect(('localhost', self.PORT))

            # fill socket buffer
            size = 0
            for _ in itertools.count():
                write = sock.write(self.BLOCK).future()
                if not write.completed:
                    size += yield write
                    break
                else:
                    size += write.value

            # drain socket
            while received.tell() < size:
                yield schedule()
            self.assertEqual(received.getvalue(), b'X' * size)
            received.seek(0)
            received.truncate(0)

            # send some data
            yield sock.write(b'one')
            yield schedule()

            yield sock.write(b', two')
            yield schedule()

            yield sock.write(b', three')
            yield schedule()

        yield server
        self.assertEqual(received.getvalue(), b'one, two, three')
