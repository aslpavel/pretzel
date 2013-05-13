from .monad import Cont

__all__ = ('Event',)


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

    def __len__(self):
        return len(self.handlers)

    def __bool__(self):
        return bool(self.handlers)

    def __monad__(self):
        """Continuation for nearest event
        """
        return Cont(lambda ret: self.on_once(ret))

    def future(self):
        """Future for nearest event
        """
        return self.__monad__().future()

    def __str__(self):
        return 'Event(len:{})'.format(len(self))

    def __repr__(self):
        return str(self)
