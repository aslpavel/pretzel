"""Message hub
"""
import threading
import itertools
from ..monad import Cont, async_block

__all__ = ('Hub', 'Sender', 'Receiver', 'pair',)


class Hub(object):
    """Message hub
    """
    inst_lock = threading.RLock()
    inst_local = threading.local()
    inst_main = None

    def __init__(self):
        self.handlers = {}
        addr_iter = itertools.count(1)
        self.addr = lambda: Address((next(addr_iter),))

    @classmethod
    def main(cls, inst=None):
        """Main core instance
        """
        with cls.inst_lock:
            if inst is None:
                if cls.inst_main is None:
                    cls.inst_main = Hub()
                inst = cls.inst_main
            else:
                cls.inst_main = inst
        return inst

    @classmethod
    def local(cls, inst=None):
        """Thread local instance
        """
        if inst is None:
            inst = getattr(cls.inst_local, 'inst', None)
            if inst is None:
                return cls.local(cls.main())
        else:
            cls.inst_local.inst = inst
        return inst

    def send(self, msg, dst, src):
        if not self.try_send(msg, dst, src):
            raise ValueError('no receiver for address: {}'.format(dst))

    def try_send(self, msg, dst, src):
        handler = self.handlers.get(dst, None)
        if handler is None:
            return False
        else:
            if not handler(msg, dst, src):
                self.handlers.pop(dst)
            return True

    def recv(self, dst, handler):
        if self.handlers.setdefault(dst, handler) != handler:
            raise ValueError('multiple receive handlers for address: {}'.format(dst))
        return handler

    def recv_once(self, dst, handler):
        def once_handler(msg, dst, src):
            handler(msg, dst, src)
            return False
        return self.recv(dst, once_handler)

    def unrecv(self, dst):
        return self.handlers.pop(dst, None) is not None

    def __len__(self):
        return len(self.handlers)

    def __str__(self):
        return 'Hub(len:{})'.format(len(self))

    def __repr__(self):
        return str(self)


class Address(tuple):
    """Hub address
    """
    __slots__ = tuple()

    def route(self, addr):
        return Address(self + addr)

    def unroute(self):
        if not self:
            raise ValueError('empty address cannot be unrouted')
        return Address(self[:-1])

    def __eq__(self, addr):
        return self[-1] == addr[-1]

    def __hash__(self):
        return hash(self[-1])

    def __str__(self):
        return '.'.join(str(p) for p in reversed(self))

    def __repr__(self):
        return str(self)


class Sender(object):
    """Hub sender
    """
    __slots__ = ('hub', 'addr',)

    def __init__(self, hub, addr):
        self.hub = hub
        self.addr = addr

    def send(self, msg, src=None):
        return self.hub.send(msg, self.addr, src)

    def try_send(self, msg, src=None):
        return self.hub.try_send(msg, self.addr, src)

    def __call__(self, msg):
        @async_block
        def sender_cont(ret):
            addr = self.hub.addr()
            self.hub.recv_once(addr, lambda msg, dst, src: ret(msg))
            try:
                self.hub.send(msg, self.addr, Sender(self.hub, addr))
            except Exception:
                self.hub.unrecv(addr)
                raise
        return sender_cont

    def __eq__(self, other):
        return (isinstance(other, type(self)) and
                (self.hub, self.addr) == (other.hub, other.addr))

    def __hash__(self):
        return hash(self.addr)

    def __str__(self):
        return 'Sender(addr:{})'.format(self.addr)

    def __repr__(self):
        return str(self)


class Receiver(object):
    """Hub receiver
    """
    __slots__ = ('hub', 'addr',)

    def __init__(self, hub, addr):
        if len(addr) > 1:
            raise ValueError('non local address {}'.format(addr))
        self.hub = hub
        self.addr = addr

    def future(self):
        return self.__monad__().future()

    def __call__(self, handler):
        return self.hub.recv(self.addr, handler)

    def __monad__(self):
        return Cont(lambda ret: self.hub.recv_once(self.addr,
                    lambda msg, dst, src: ret(msg, src)))

    def dispose(self):
        self.hub.unrecv(self.addr)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return ('Receiver(addr:{}, handler:{})'.format(self.addr,
                getattr(self.hub.handlers.get(self.addr), '__name__', None)))

    def __repr__(self):
        return str(self)


def pair(addr=None, hub=None):
    """Create receiver-sender pair
    """
    hub = hub or Hub.local()
    addr = addr or hub.addr()
    return Receiver(hub, addr), Sender(hub, addr)
