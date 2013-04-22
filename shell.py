"""Pretzel asynchronous shell
"""
import sys
import code
import signal
import textwrap
import functools
from pretzel.event import Event
from pretzel.core import Core, schedule
from pretzel.stream import BufferedFile
from pretzel.monad import Cont
from pretzel.common import BrokenPipeError
from pretzel.app import app_run, async_green, bind_green

__all__ = ('shell',)


@async_green
def shell():
    """Create asynchronous interactive shell
    """
    def input_async(prompt=''):
        if prompt:
            sys.stdout.write(prompt)
            sys.stdout.flush()
        try:
            stdin.blocking(False)
            return bind_sigint(getline())
        except BrokenPipeError:
            raise EOFError()
    stdin = BufferedFile(0, closefd=False)
    getline = singleton(lambda: stdin.read_until_sub()
                        .map_val(lambda res: res.bind(
                                 lambda line: line.strip().decode())))

    # interrupt signal handling
    def bind_sigint(monad):
        value = bind_green(monad.__monad__() | sigint)
        if value is sigint_tag:
            raise KeyboardInterrupt()
        return value
    sigint = Event()
    sigint_tag = object()
    signal.signal(signal.SIGINT, lambda *_: schedule()(
                  lambda _: sigint(sigint_tag)))

    # shell
    shell = code.InteractiveConsole({
        'val': bind_sigint,
        'mon': lambda monad: monad.__monad__(),
        'core': Core.local(),
    })
    shell.raw_input = input_async
    for line in textwrap.dedent("""\
        from __future__ import print_function
        from pretzel.monad import *
        from pretzel.event import *
        from pretzel.core import *
        from pretzel.remoting import *
        from pretzel.process import *
        """).split('\n'):
            shell.runsource(line.rstrip())
    shell.interact(textwrap.dedent("""\
        Welcome to asynchronous pretzel shell!
            {}
            val  - get value associated with continuation monad
            mon  - get associated monad
            core - application core object
        """).format(''))


def singleton(action):
    """Singleton asynchronous action

    If there is current non finished action all new continuations will be hooked
    to this action result, otherwise new action will be started.
    """
    @functools.wraps(action)
    def singleton_action():
        def run(ret):
            done.on_once(lambda val: ret(val))
            if len(done) == 1:
                action().__monad__()(lambda val: done(val))
        return Cont(run)
    done = Event()
    return singleton_action


if __name__ == '__main__':
    app_run(shell())
