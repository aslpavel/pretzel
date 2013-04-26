"""Connection
"""
import io
import sys

from pickle import Pickler, Unpickler
from ..hub import Hub, Sender, pair
from ..proxy import Proxy
from ..expr import LoadConstExpr, LoadArgExpr
from ...common import reraise
from ...event import Event
from ...core import Core
from ...monad import Result, async, do_return
from ...state_machine import StateMachine
from ...dispose import CompDisp

__all__ = ('Connection',)


class Connection(object):
    """Connection
    """
    STATE_INIT = 0
    STATE_CONNI = 1
    STATE_CONND = 2
    STATE_DISP = 3
    STATE_GRAPH = StateMachine.compile_graph({
        STATE_INIT:  (STATE_CONNI, STATE_DISP),
        STATE_CONNI: (STATE_CONND, STATE_DISP),
        STATE_CONND: (STATE_DISP,),
        STATE_DISP:  (STATE_DISP,)
    })
    STATE_NAMES = ('not-connected', 'connecting', 'connected', 'disposed',)

    def __init__(self, hub=None, core=None):
        self.hub = hub or Hub.local()
        self.core = core or Core.local()
        self.module_map = {}

        self.receiver, self.sender = pair(hub=self.hub)
        self.disp = CompDisp()
        self.state = StateMachine(self.STATE_GRAPH, self.STATE_NAMES)
        self.recv_ev = Event()

        ## marshaling
        PACK_ROUTE = 1
        PACK_UNROUTE = 2

        class pickler_type(Pickler):
            def persistent_id(this, target):
                if isinstance(target, Sender):
                    if target.hub is not self.hub:
                        raise ValueError('sender\'s hub must match hub used by connection')
                    if target.addr == self.sender.addr:
                        # This sender was previously received from this connection
                        # so it must not be routed again.
                        return PACK_UNROUTE, target.addr.unroute()
                    else:
                        # Sender must be routed
                        return PACK_ROUTE, target.addr

        self.pickler_type = pickler_type

        class unpickler_type(Unpickler):
            def persistent_load(this, state):
                pack, args = state
                if pack == PACK_ROUTE:
                    return Sender(self.hub, args.route(self.sender.addr))
                elif pack == PACK_UNROUTE:
                    return Sender(self.hub, args if args else self.sender.addr)
                else:
                    raise ValueError('Unknown pack type: {}'.format(pack))

            def find_class(this, modname, name):
                modname = self.module_map.get(modname, modname)
                module = sys.modules.get(modname, None)
                if module is None:
                    __import__(modname)
                    module = sys.modules[modname]
                if getattr(module, '__initializing__', False):
                    # Module is being imported. Interrupt unpickling.
                    raise InterruptError()
                return getattr(module, name)

        self.unpickler_type = unpickler_type

    def __call__(self, target):
        """Create proxy object from provided pickle-able constant.
        """
        return Proxy(self.sender, LoadConstExpr(target))

    @property
    def connected(self):
        return self.state.state == self.STATE_CONND

    @async
    def connect(self, target=None):
        self.state(self.STATE_CONNI)
        try:
            def send(msg, dst, src):
                stream = io.BytesIO()
                self.pickler_type(stream, -1).dump((msg, dst, src))
                self.do_send(stream.getvalue())
                return True
            self.receiver(send)
            yield self.do_connect(target)
            self.state(self.STATE_CONND)
        except Exception:
            error = sys.exc_info()
            self.dispose()
            reraise(*error)
        do_return(self)

    @async
    def do_connect(self, target):
        """Connect implementation
        """

    def do_disconnect(self):
        """Disconnect implementation
        """

    def do_send(self, msg):
        """Send packed message to other peer
        """
        raise NotImplementedError()

    @async
    def do_recv(self, msg):
        """Handle remote packed message
        """
        # Detachment from  current coroutine is vital here because if handler
        # tries to create nested core loop to resolve future synchronously
        # (i.g. importer proxy) it can block dispatching coroutine.
        yield self.core.schedule()
        self.recv_ev(msg)

        while True:
            src = None
            try:
                msg, dst, src = self.unpickler_type(io.BytesIO(msg)).load()
                dst = dst.unroute()  # strip remote connection address

                if dst:
                    # After striping remote connection address, destination
                    # is not empty so it needs to be routed.
                    self.hub.send(msg, dst, src)
                else:
                    if msg is None:
                        self.dispose()
                        return
                    if src is None:
                        yield msg(self)
                    else:
                        src.send((yield msg(self)))
                break
            except InterruptError:
                yield self.recv_ev  # wait for pending import
            except Exception:
                if not self.disposed:
                    err = Result.from_current_error()
                    if src is not None:
                        src.send(err)
                    else:
                        err.trace()  # nowhere to send, just show trace
                break

    def __monad__(self):
        return self.connect()

    def __reduce__(self):
        return ConnectionProxy, (self.sender, LoadArgExpr(0))

    @property
    def disposed(self):
        return self.state.state == self.STATE_DISP

    def dispose(self):
        if self.state(self.STATE_DISP):
            self.receiver.dispose()
            self.do_disconnect()
            self.disp.dispose()

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return ("<{} [state:{} addr:{}] at {}>".format(type(self).__name__,
                self.state.state_name(), self.sender.addr, id(self)))

    def __repr__(self):
        return str(self)


class ConnectionProxy(Proxy):
    def __call__(self, target):
        return Proxy(self._sender, LoadConstExpr(target))


class InterruptError (BaseException):
    """Interrupt helper exception type
    """
