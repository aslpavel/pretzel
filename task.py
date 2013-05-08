"""Thread pool
"""
import os
import threading
import multiprocessing
from collections import deque
from .core import Core
from .monad import Result, async_block

__all__ = ('ThreadPool', 'task',)


class ThreadPool(object):
    """Thread pool
    """
    inst_lock = threading.RLock()
    inst_main = None

    def __init__(self, size=None):
        self.disposed = False

        self.threads = set()
        self.thread_count = size or _cpu_count()
        self.thread_idle = 0
        self.thread_queue = deque()
        self.thread_lock = threading.RLock()
        self.thread_cond = threading.Condition(self.thread_lock)

    @classmethod
    def main(cls, inst=None):
        """Access or create main thread pool object
        """
        with cls.inst_lock:
            if inst is None:
                if cls.inst_main is None:
                    cls.inst_main = cls()
                inst = cls.inst_main
            else:
                cls.inst_main = inst
        return inst

    @property
    def size(self):
        """Size of thread pool (number of threads)
        """
        return self.thread_count

    @size.setter
    def size(self, count):
        """Change size of thread pool (number of threads)
        """
        if count < 0:
            raise ValueError('thread pool size must be positive')
        with self.thread_lock:
            self.thread_count = count
            exit_count = len(self.threads) - count
            if exit_count > 0:
                for _ in range(exit_count):
                    self.thread_queue.appendleft(_action_exit)
                self.thread_cond.notify(exit_count)

    def __len__(self):
        return self.size

    def __call__(self, act, *act_a, **act_kw):
        """Schedule action to be executed on main thread pool

        Returns continuation which will be resolved with action result on
        local core object.
        """
        if self.disposed:
            raise ValueError('thread pool is disposed')

        @async_block
        def thread_cont(ret):
            def action(error=None):
                if error is not None:
                    res = Result.from_exception(error)
                else:
                    try:
                        res = act(*act_a, **act_kw)
                    except Exception:
                        res = Result.from_current_error()
                core.schedule()(lambda _: ret(res))
            core = Core.local()  # capture caller's core object

            with self.thread_lock:
                self.thread_queue.append(action)
                if not self.thread_idle and len(self.threads) < self.thread_count:
                    thread = threading.Thread(target=self.thread_main)
                    thread.daemon = True
                    self.threads.add(thread)
                    thread.start()
                else:
                    self.thread_cond.notify()

        return thread_cont

    def thread_main(self):
        """Worker main function
        """
        with self.thread_lock:
            if threading.current_thread() not in self.threads:
                raise ValueError('this function must be run in thread pool')
        Core.local(_bad_object(RuntimeError('can not access core inside '
                                            'thread pool\'s worker thread')))
        try:
            while True:
                with self.thread_lock:
                    while not self.thread_queue:
                        self.thread_idle += 1
                        self.thread_cond.wait()
                        self.thread_idle -= 1
                    action = self.thread_queue.popleft()
                action()
        except _thread_exit:
            pass
        finally:
            with self.thread_lock:
                self.threads.discard(threading.current_thread())

    def dispose(self):
        with self.thread_lock:
            if self.disposed:
                return
            elif threading.current_thread() in self.threads:
                raise ValueError('thread pool cannot be disposed from its own thread')
            self.disposed = True
            actions, self.thread_queue = self.thread_queue, deque((_action_exit,) * self.thread_count)
            self.thread_cond.notify(self.thread_count)
        for action in actions:
            action(ValueError('thread pool has been disposed'))

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return ('ThreadPool(size:{}, threads:{}, idle:{}, tasks:{})'.format(
                self.size, len(self.threads), self.thread_idle,
                len(self.thread_queue) + len(self.threads) - self.thread_idle))

    def __repr__(self):
        return str(self)


def task(action, *action_a, **action_kw):
    """Schedule action to be executed on main thread pool

    Returns continuation which will be resolved with action result on
    local core object.
    """
    return ThreadPool.main()(action, *action_a, **action_kw)


class _thread_exit(Exception):
    """Helper thread exit exception
    """


def _action_exit(error=None):
    if error is None:
        raise _thread_exit()


class _bad_object(object):
    """Bad object

    Raises and error on attempt of attribute access or call.
    """
    def __init__(self, error):
        object.__setattr__(self, '_error', error)

    def __getattr__(self, name):
        raise self._error

    def __setattr__(self, name, value):
        raise self._error

    def __call__(self, *a, **kw):
        raise self._error


def _cpu_count():
    """Returns the number of processors on this machine."""
    try:
        return multiprocessing.cpu_count()
    except NotImplementedError:
        pass
    try:
        return os.sysconf("SC_NPROCESSORS_CONF")
    except ValueError:
        pass
    return 1
