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

    Treat multiple disposables as one.
    """
    __slots__ = ('disposables',)

    def __init__(self, disposables=None):
        self.disposables = []
        if disposables:
            try:
                for disposable in disposables:
                    self.add(disposable)
            except Exception:
                self.dispose()
                raise

    def add(self, disposable):
        disposable.__enter__()
        if self.disposables is None:
            disposable.__exit__(None, None, None)
        else:
            self.disposables.append(disposable)
        return disposable

    def add_action(self, action):
        return self.add(FuncDisp(action))

    def __iadd__(self, disposable):
        self.add(disposable)
        return self

    def remove(self, disposable):
        try:
            if self.disposables is None:
                return False
            self.disposables.remove(disposable)
            return True
        except ValueError:
            return False
        finally:
            disposable.__exit__(None, None, None)

    def __isub__(self, disposable):
        self.remove(disposable)
        return self

    def __len__(self):
        return len(self.disposables) if self.disposables else 0

    @property
    def disposed(self):
        return self.disposables is None

    def dispose(self):
        disposables, self.disposables = self.disposables, None
        if disposables is None:
            return False
        else:
            for disposable in reversed(disposables):
                disposable.__exit__(None, None, None)
            return True

    def __monad__(self):
        """Wait for composite disposable object to be disposed
        """
        return async_block(lambda ret: self.add_action(lambda: ret(None)))
