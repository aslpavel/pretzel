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
Usage of asynchronous functions is similar to C# async/await but instead of `async` attribute it uses `@async`
decorator and instead of `await` keyword, `yield` is used. Internaly unit of asynchrocity is implemented
as continuation monad `Cont` with embeded `Result` monad (similar to Haskell's `Cont` and `Either` monads)
as its value. But to use this library you don't have to understand notion of the monad.
Simple asynchronous function would look like this.
```python
from pretzel.monad import async
from pretzel.core imoprt sleep

@async
def print_after(delay, *args, **kwargs):
  """Calls print function after the lapse of `delay` sedonds.
  """
  yield sleep(delay)  # execution will be resumed in delay seconds
  print(*args, **kwargs)
```
To return something meaningfull in python3 you can just use `return` keyword, but in python2 you have to
use `do_return` function (it will also work in python3) as `return` with value cannot be used inside a generator
function. Result of such asynchronous function is again a continuation monad, if exception is thrown during
execution of its body, it is marshaled to receiver of the result and can be processed correctly.
For example.
```python
@async
def process_error():
   @async
   def trhow_after(delay, error):
      yield sleep(delay)
      raise error
      
   try:
      yield throw_after(1, ValueError('test error'))
   except ValueError as error:
      # process error in a meaningfull way
   ...
```
Asynchronous values (continuation monads) can be composed with two helper functions
`async_all` and `async_any`.
```python
@async
def composition_example():
  yield async_all([sleep(1), sleep(2)])  # will be resumed in 2 seconds
  yield async_any([sleep(1), sleep(2)])  # will be resumed in 1 sedond

  result_all = yield async_all([func1(), func2()])  # = (result1, result2)
  reuslt_any = yield async_any([func1(), func2()])  # = result1 | result2 
```

Main loop
---------
`Core` class implemnts I/O loop, and it used internally to implement asynchronous streams, timers and more.
Previously used `sleep` function will work correctly only in presence of running I/O loop.


Examples
--------
* [Simple echo server](https://gist.github.com/aslpavel/5635559)
* [Cat remote file over ssh](https://gist.github.com/aslpavel/5635610)

[build_badge]: https://api.travis-ci.org/aslpavel/pretzel.png "build status"
[build_url]: https://travis-ci.org/aslpavel/pretzel
[coverage_badge]: https://coveralls.io/repos/aslpavel/pretzel/badge.png?branch=master "coverage status"
[coverage_url]: https://coveralls.io/r/aslpavel/pretzel?branch=master
