"""Helper classes to compose disposable objects
"""
__all__ = ('Disposable', 'FuncDisp', 'CompDisp',)


class Disposable(object):
    """Base disposable
    """
    __slots__ = tuple()

    def __call__(self):
        self.dispose()

    def disposed(self):
        raise NotImplementedError()

    def __bool__(self):
        return self.disposed()

    def __nonzero__(self):
        return self.disposed()

    def dispose(self):
        raise NotImplementedError()

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False


class FuncDisp(Disposable):
    """Action based disposable object
    """
    __slots__ = ('action',)

    def __init__(self, action=None):
        self.action = action

    def disposed(self):
        return self.action is None

    def dispose(self):
        action, self.action = self.action, None
        if action is not None:
            return action()

    def __str__(self):
        return '<{}[disp:{}] at {}>'.format(type(self).__name__,
                                            self.disposed, id(self))
    __repr__ = __str__


class CompDisp(Disposable):
    """Composite multiple disposables

    Treat multiple disposable as one.
    """
    __slots__ = ('disps',)

    def __init__(self, disps=None):
        self.disps = []
        if disps:
            try:
                for disp in disps:
                    self.add(disp)
            except Exception:
                self.dispose()
                raise

    def add(self, disp):
        disp.__enter__()
        if self.disps is None:
            disp.__exit__(None, None, None)
        else:
            self.disps.append(disp)
        return disp

    def __iadd__(self, disp):
        self.add(disp)
        return self

    def remove(self, disp):
        try:
            if self.disps is None:
                return False
            self.disps.remove(disp)
            return True
        except ValueError:
            return False
        finally:
            disp.__exit__(None, None, None)

    def __isub__(self, disp):
        self.remove(disp)
        return self

    def __len__(self):
        return len(self.disps) if self.disps else 0

    def disposed(self):
        return self.disps is None

    def dispose(self):
        disps, self.disps = self.disps, None
        if disps is not None:
            for disp in reversed(disps):
                disp.__exit__(None, None, None)

    def __str__(self):
        return '<{}[disp:{} len:{}] at {}>'.format(type(self).__name__,
                                                   self.disposed, len(self), id(self))
    __repr__ = __str__

# vim: nu ft=python columns=120 :
