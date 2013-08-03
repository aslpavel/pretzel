Pretzel
-------
[![Build Status][build_badge]][build_url]
[![Coverage Status][coverage_badge]][coverage_url]

Is an asynchronous application framework for python

Features
--------
* C# like async/await(async/yield) paradigm for asynchronous programming (monad base)
* Cool asynchronous I/O loop implementation
* Uniform asynchronous stream implementation for sockets and pipes
* Interact with subprocesses asynchronously
* Greenlet support (but not required)
* Remote code executing over ssh or in child process (with only requirements python and ssh)
* Python 2/3, PyPy (starting from 2.0) compatible
* Asynchronous python shell `python -mpretzel.apps.shell` (requires greenlet)

Installation
------------
As git submodule:
```
git submodule add git://github.com/aslpavel/pretzel.git <path_to_submodule>
```
Pip from git:
```
pip install git+git://github.com/aslpavel/pretzel-pkg.git
```
Pip from PyPI
```
pip install pretzel
```

Approach
--------
Usage of asynchronous functions is similar to C# async/await but instead of
`async` attribute it uses `@async` decorator and instead of `await` keyword,
`yield` is used. Internally unit of asynchrony is implemented as continuation
monad `Cont` with embedded `Result` monad (similar to Haskell's `Cont` and
`Either` monads) as its value. One important difference of `Cont` monad from C#
`Task` object, is that `Task` represents already running asynchronous operation,
but continuation monad is a sequence of computations, and this computations are
not started. `.future()` method on instance of `Cont` can be used to create
`Task` like object. To use this library you don't have to understand notion of
the monad. Simple asynchronous function would look like this.

```python
from pretzel.monad import async
from pretzel.core import sleep

@async
def print_after(delay, *args, **kwargs):
  """Calls print function after the lapse of `delay` sedonds.
  """
  yield sleep(delay)  # execution will be resumed in delay seconds
  print(*args, **kwargs)
```

To return something meaningful in python3 you can just use `return` keyword,
but in python2 you have to use `do_return` function (it will also work in
python3) as `return` with value cannot be used inside a generator function.
Result of such asynchronous function is again a continuation monad, if exception
is thrown during execution of its body, it is marshaled to receiver of the
result and can be processed correctly. For example.

```python
@async
def process_error():
  @async
  def throw_after(delay, error):
    yield sleep(delay)
    raise error

  try:
    yield throw_after(1, ValueError('test error'))
  except ValueError as error:
    # process error in a meaningfull way
  do_return('done')  # exectly equivalent to: return 'done'
```

Asynchronous values (continuation monads) can be composed with two helper
functions `async_all` and `async_any`.

```python
@async
def composition_example():
  yield async_all([sleep(1), sleep(2)])  # will be resumed in 2 seconds
  yield async_any([sleep(1), sleep(2)])  # will be resumed in 1 sedond

  result_all = yield async_all([func1(), func2()])  # = (result1, result2)
  reuslt_any = yield async_any([func1(), func2()])  # = result1 | result2
```

`Cont` monad can also be called with callback function as its argument, in this
case, on completion of asynchronous operation, callback will be called with
`Result` monad. If callback function is not specified default, then default
continuation callback will be used which only reports errors if any.

```python
>>> sleep(1)(print)
Result(val:1374307530.015137)
>>> sleep(None)()
[continuation] error in coroutine started from
  File "<console>", line 1, in <module>
`-------------------------------------------------------------------------------
Host   : fiend
Process: 13492
Error  : TypeError("unsupported operand type(s) for +: 'float' and 'NoneType'")

Traceback (most recent call last):
  File "./pretzel/monad/do.py", line 26, in do_block
    return value(block(*args, **kwargs))
  File "./pretzel/core/core.py", line 118, in sleep
    do_done(self.time_queue.on(time() + delay))
TypeError: unsupported operand type(s) for +: 'float' and 'NoneType'
```

Inside body of asynchronous function you can `yield` not only `Cont` monad
directly, but any object implementing `.__monad__()` method which returns `Cont`
monad. There are many such types in this library, for example `Event`

```python
@async
def func():
  print(1)
  yield event
  print(2)
  print((yield event))
event = Event()
func()()     # 1 is printed
event('e0')  # 2 is printed
event('e1')  # 'e1' is printed
```

Main loop
---------
`Core` class implements I/O loop, and it is used internally to implement
asynchronous streams, timers and more. Previously used `sleep` function will
work correctly only in presence of running I/O loop. Simplest way to
intialize and use `Core` object is to use `@app` decorator.

```python
"""Minimal pretzel application

Sleeps for one second, then prints 'done' and exits.
"""
from pretzel.app import app
from pretzel.core import sleep

@app
def main():
  yield sleep(1)
  print('done')

if __name__ == '__main__':
  main()
```

See [Core's init module](https://github.com/aslpavel/pretzel/blob/master/core/__init__.py)
for full list of available functions and their descriptions.

Remoting
--------
Main reason for creation of this framework was to execute code on a set of
machines via ssh connection. It is achieved by usage of `SSHConnection` class.
`SSHConnection` is a callable object which returns proxy object for its
argument. You can call proxy object, get its attributes or items `proxy[item]`,
result of such operations is again a proxy object with this embedded operations.
Proxy implements monad interface, and to get result of embedded chain of
operations you can yield it inside asynchronous function. In this example we
create proxy for `os.getpid` function, call it and then execute on remote
process by yielding it. There is no need for pretzel to be installed on remote
machine.

```python
import os
from pretzel.app import app
from pretzel.remoting import SSHConnection

@app
def main():
  """Connect to localhost via ssh and print remote process's pid

  Note:
    You have to be able to login to the remote host without
    entering any password (by means of ssh keys) otherwise
    connecition will fail.
  """
  with (yield SSHConnection('localhost')) as conn:
    print((yield conn(os.getpid)()))

if __name__ == '__main__':
  main()
```

Connection can marshal any pickle-able object, or `Sender` object plus any object
which is reducible to set of pickle-able and `Sender` objects. `Proxy` and
`Connection` itself are examples of such objects. You can also create proxy
object from any arbitrary object with `proxify` or `proxify_func`.

```python
import os
from pretzel.app import app
from pretzel.remoting import SSHConnection, proxify

class Remote(object):
  """Object which will be used remotely
  """
  def __init__(self):
    self.value = 0

  def next(self):
    self.value += 1
    return self.value

  def getpid(self):
    return os.getpid()

@app
def main():
  with (yield SSHConnection('localhost')) as conn:
    with (yield proxify(conn(Remote)())) as o:  # remote object proxy
      print(os.getpid(), (yield o.getpid()))    # prints two different pids
      print((yield o.next()))  # prints 1
      print((yield o.next()))  # prints 2

if __name__ == '__main__':
  main()
```

But `Cont` monad is not marshallable, that is why there is special operation on
proxy object `~` which is equivalent to `yield` inside asynchronous function.
Here is an example of remote execution of asynchronous function.

```python
from pretzel.app import app
from pretzel.process import process_call
from pretzel.remoting import SSHConnection

@app
def main():
  """Execute 'ls' on remote machine and show result of the execution
  """
  with (yield SSHConnection('localhost')) as conn:
    out, err, code = yield ~conn(process_call)('ls')
    print(out.decode())

if __name__ == '__main__':
  main()
```

There is also a way to work with multiple connections as if it one, by means of
`composite_ssh_conn`. It accepts list of hosts and returns composite connection,
which behaves as ordinary connection but returns set of results.

```python
import os
from pretzel.app import app
from pretzel.remoting import composite_ssh_conn

@app
def main():
  hosts = ['localhost', 'localhost']
  with (yield composite_ssh_conn(hosts)) as conns:
    result = yield conns(os.getpid)()
    print(result)  # List(25163, 25162) - iterable object of pids

if __name__ == '__main__':
  main()
```

Remoting submodule can be used as workaround for python's GIL, in a similar
fashion to `multiprocessing` module. You can use `ForkConnection` (or
`composite_fork_conn`) which behaves as `SSHConnection` but instead of
connecting via ssh, it just spawns new process.

```python
import time
from pretzel.app import app
from pretzel.remoting import composite_fork_conn

def computation_heavy_task():
  """Some computation intensive task
  """
  start_time = time.time()
  time.sleep(10)
  stop_time = time.time()
  return int(stop_time - start_time)

@app
def main():
  with (yield composite_fork_conn(10)) as conns:  # create 10 connections
    result = yield conns(computation_heavy_task)()
    print(result)  # prints List(10, 10, 10, 10, 10, 10, 10, 10, 10, 10)

if __name__ == '__main__':
  main()
```

Examples
--------
* [Simple echo server](https://gist.github.com/aslpavel/5635559)
* [Cat remote file over ssh](https://gist.github.com/aslpavel/5635610)

[build_badge]: https://api.travis-ci.org/aslpavel/pretzel.png "build status"
[build_url]: https://travis-ci.org/aslpavel/pretzel
[coverage_badge]: https://coveralls.io/repos/aslpavel/pretzel/badge.png?branch=master "coverage status"
[coverage_url]: https://coveralls.io/r/aslpavel/pretzel?branch=master
