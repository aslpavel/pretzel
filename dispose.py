"""Helper classes to compose disposable objects
"""
from .monad import async_block

__all__ = ('Disposable', 'FuncDisp', 'CompDisp',)


class Disposable(object):
    """Base disposable
    """
    __slots__ = tuple()

    def __call__(self):
        return self.dispose()

    @property
    def disposed(self):
        raise NotImplementedError()

    def __bool__(self):
        return self.disposed

    def __nonzero__(self):
        return self.disposed

    def dispose(self):
        raise NotImplementedError()

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return '{}(disposed:{})'.format(type(self).__name__, self.disposed)

    def __repr__(self):
        return str(self)


class FuncDisp(Disposable):
    """Action based disposable object
    """
    __slots__ = ('action',)

    def __init__(self, action=None):
        self.action = action

    @property
    def disposed(self):
        return self.action is None

    def dispose(self):
        action, self.action = self.action, None
        if action is None:
            return False
        else:
            action()
            return True


class CompDisp(Disposable):
    """Composite disposable

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

    def add_action(self, action):
        return self.add(FuncDisp(action))

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

    @property
    def disposed(self):
        return self.disps is None

    def dispose(self):
        disps, self.disps = self.disps, None
        if disps is None:
            return False
        else:
            for disp in reversed(disps):
                disp.__exit__(None, None, None)
            return True

    def __monad__(self):
        """Wait for composite disposable object to be disposed
        """
        return async_block(lambda ret: self.add_action(lambda: ret(None)))
