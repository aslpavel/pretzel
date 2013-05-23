Pretzel
-------
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

```python
"""Simple echo server
"""
from __future__ import print_function
import sys
import socket
from pretzel.app import app, async
from pretzel.common import BrokenPipeError
from pretzel.stream import BufferedSocket

@async
def client_coro(sock, addr):
    """Client coroutine
    """
    try:
        print('[+clinet] fd:{} addr:{}'.format(sock.fileno(), addr))
        while True:
            data = yield sock.read(1024)  # receive data (throws an error if data is b'')
            sock.write_schedule(data)     # schedule data to be written
            yield sock.flush()            # flush buffered data
    except BrokenPipeError:
        pass
    finally:
        print('[-client] fd:{} addr:{}'.format(sock.fileno(), addr))
        sock.dispose()  # close client socket (with context may be used)


@async
def server_coro(host, port):
    """Server coroutine
    """
    with BufferedSocket(socket.socket()) as sock:  # create async socket
        sock.bind(('127.0.0.1', port))             # just bind
        sock.listen(10)                            # just listen
        print('[server] {}:{}'.format(host, port))
        while True:
            client, addr = yield sock.accept()  # asynchronously accept connection
            client_coro(client, addr)()         # start client coroutine (background)


@app
def main():
    if len(sys.argv) < 2:
        sys.stderr.write('usage: {} <port>\n'.format(sys.argv[0]))
        sys.exit(1)
    yield server_coro('localhost', int(sys.argv[1]))  # wait for server coroutine


if __name__ == '__main__':
    main()
```

```python
"""Cat remote file
"""
from __future__ import print_function
import os
import sys
from pretzel.app import app, async
from pretzel.remoting import SSHConnection

SIZE_LIMIT = 1 << 20  # 1Mb


@app
def main():
    """Read remote file
    """
    if len(sys.argv) < 3:
        sys.stderr.write('usage: {} <host> <path>\n'.format(sys.argv[0]))
        sys.exit(1)

    host = sys.argv[1]
    path = sys.argv[2]
    with (yield SSHConnection(host)) as ssh:  # create and connect
        # ssh(target) returns targets proxy object. When proxy object is awaited
        # request is send to remote side and executed. All exception are
        # marshaled.

        # check file access
        if not (yield ssh(os.access)(path, os.R_OK)):
            sys.stderr.write('[error] no such file: {}\n'.format(path))
            sys.exit(1)

        # check file size
        size = yield ssh(os.path.getsize)(path)
        if size > SIZE_LIMIT:
            sys.stderr.write('[error] file is too big: {}\n'.format(size))
            sys.exit(1)

        # read file
        print((yield ssh(open)(path).read()))


if __name__ == '__main__':
    main()
```
