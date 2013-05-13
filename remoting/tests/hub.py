import unittest
import collections
from ..hub import Hub, Address, Sender, pair

__all__ = ('HubTest',)


class HubTest(unittest.TestCase):
    def test_addr(self):
        addr = Hub.local().addr()
        self.assertEqual(len(addr), 1)

        addr_111 = addr.route((111,))
        self.assertEqual(addr_111, Address((111,)))

        self.assertEqual(addr_111.unroute(), addr)

    def test_sender_receiver(self):
        res = ResultQueue()
        recv, send = pair()

        with self.assertRaises(ValueError):
            send.send('no-recv')  # no receiver

        # send
        recv(res)
        with self.assertRaises(ValueError):
            recv(lambda *a: res(*a))  # multiple handlers
        send.send('1')
        with self.assertRaises(ValueError):
            send.send('no-recv')  # no receiver
        self.assertEqual(res.pop(), ('1', recv.addr, None))
        self.assertFalse(res)

        # send with source
        recv(res)
        send.send('2', 'sender')
        self.assertEqual(res.pop(), ('2', recv.addr, 'sender'))

        # call
        recv(res)
        send('3')(res)
        self.assertEqual(len(Hub.local()), 1)  # handler will be cleaned up
        msg, dst, src = res.pop()
        self.assertEqual(msg, '3')
        self.assertEqual(dst, recv.addr)
        self.assertTrue(isinstance(src, Sender))
        self.assertFalse(res)

        with self.assertRaises(ValueError):
            send('4')(res)  # send on address without a receiver
            res.pop()[0].value

        src.send('5')
        self.assertEqual(res.pop()[0].value, '5')
        self.assertFalse(res)

        self.assertEqual(len(Hub.local()), 0)

    def test_faulty_handler(self):
        recv, send = pair()

        def faulty(msg, dst, src):
            if msg == '0':
                raise RuntimeError()
            return False
        recv(faulty)

        with self.assertRaises(RuntimeError):
            send.send('0')
        self.assertEqual(len(Hub.local()), 1)
        send.send('1')
        self.assertEqual(len(Hub.local()), 0)

    def test_reentrancy(self):
        res = ResultQueue()
        recv, send = pair()

        def handler(msg, dst, src):
            res(msg)
            if msg == 'first':
                send.send('second')
                return True
            else:
                return False
        recv(handler)

        send.send('first')
        self.assertEqual(res.pop(), ('first',))
        self.assertEqual(res.pop(), ('second',))


class ResultQueue(object):
    def __init__(self):
        self.queue = collections.deque()

    def __call__(self, *args):
        self.queue.append(args)
        return False

    def pop(self):
        return self.queue.popleft()

    def __len__(self):
        return len(self.queue)

    def __bool__(self):
        return bool(self.queue)
    __nonzero__ = __bool__
