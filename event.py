from .monad import Cont
from collections import deque

__all__ = ('Event', 'EventQueue',)


class Event(object):
    """Event object
    """
    __slots__ = ('handlers',)

    def __init__(self):
        self.handlers = []

    def __call__(self, event):
        """Fire event
        """
        handlers, self.handlers = self.handlers, []
        for handler in handlers:
            if handler(event):
                self.handlers.append(handler)

    def on(self, handler):
        """On handler

        Returns specified handler. If handler returned value is False it will
        be automatically unsubscripted.
        """
        self.handlers.append(handler)
        return handler

    def on_once(self, handler):
        """Execute handler only once
        """
        def once_handler(event):
            handler(event)
            return False
        self.on(once_handler)

    def __iadd__(self, handler):
        self.on(handler)
        return self

    def off(self, handler):
        """Off handler

        Preferred way to do un-subscription is to return False from handler.
        Returns True in case of successful un-subscription.
        """
        try:
            self.handlers.remove(handler)
            return True
        except ValueError:
            return False

    def __isub__(self, handler):
        self.off(handler)
        return self

    def __monad__(self):
        """Continuation for nearest event
        """
        return Cont(lambda ret: self.on_once(ret))

    def future(self):
        """Future for nearest event
        """
        return self.__monad__().future()

    def __str__(self):
        return '{}(handlers:{})'.format(type(self).__name__, len(self.handlers))

    def __repr__(self):
        return str(self)

    def __reduce__(self):
        return ReducedEvent, (self.reduce().sender,)

    def reduce(self, hub=None):
        """Create reduced event

        Fire-able and send-able over remote connection but not subscribe-able.
        """
        from .remoting import pair

        def fire_event(msg, dst, src):
            op, event = msg
            if op == EVENT_FIRE:
                self(event)
                return True
            elif op == EVENT_DISPOSE:
                return False
            else:
                raise ValueError('unknown reduced event operation')
        recv, send = pair(hub=hub)
        recv(fire_event)
        return ReducedEvent(send)

    def dispose(self):
        """Does nothing

        Compatibility with reduced event interface.
        """

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False


class EventQueue(Event):
    """Event queue

    Event object which queues event to be handled later if no handler is set.
    """
    __slots__ = Event.__slots__ + ('queue',)

    def __init__(self):
        Event.__init__(self)
        self.queue = deque()

    def __call__(self, event):
        if self.handlers:
            Event.__call__(self, event)
        else:
            self.queue.append(event)

    def on(self, handler):
        Event.on(self, handler)
        while self.handlers:
            if not self.queue:
                return
            Event.__call__(self, self.queue.popleft())

    def __len__(self):
        return len(self.queue)

    def __bool__(self):
        return bool(self.queue)

    def __str__(self):
        return '{}(len:{}, handlers:{})'.format(type(self).__name__,
                                                len(self.queue), len(self.handlers))


class ReducedEvent(object):
    """Reduced event

    Can be called and send over remote connection but cannot be subscribed to.
    """
    __slots__ = ('sender',)

    def __init__(self, sender):
        self.sender = sender

    def __call__(self, event):
        if self.sender is not None:
            if self.sender.try_send((EVENT_FIRE, event)):
                return
            self.dispose()
        raise ValueError('reduced event is disposed')

    def dispose(self):
        sender, self.sender = self.sender, None
        if sender:
            sender.try_send((EVENT_DISPOSE, None))

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return 'ReducedEvent(addr:{})'.format(self.sender.addr
                                              if self.sender else None)

    def __repr__(self):
        return str(self)

EVENT_FIRE = 0
EVENT_DISPOSE = 1
