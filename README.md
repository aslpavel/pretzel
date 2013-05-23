Pretzel
-------
![build status is unknown](build_status "Build status")
Is an asynchronous application framework for python

Features
--------
* C# like async/await(async/yield) paradigm for asynchronous programming (monad base)
* Cool asynchronous I/O loop implementation
* Uniform asynchronous stream implementation for sockets and pipes
* Interact with subprocesses asynchronously
* Greenlet support (but not required)
* Remote code executing over ssh (with only requirements python and ssh itself)
* Python 2/3, PyPy compatible
* Asynchronous python shell `python -mpretzel.apps.shell` (requires greenlet)

Examples
--------
* [Simple echo server](https://gist.github.com/aslpavel/5635559)
* [Cat remote file over ssh](https://gist.github.com/aslpavel/5635610)

[build_status]: https://api.travis-ci.org/aslpavel/pretzel.png
