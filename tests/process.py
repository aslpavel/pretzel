import os
import time
import errno
import json
import textwrap
import unittest
import tempfile
from . import async_test
from ..monad import Cont, async_all
from ..boot import boot_pack
from ..dispose import CompDisp
from ..process import (Process, ProcessPipe, ProcessError, PIPE, DEVNULL,
                       process_call, process_chain_call,)
from .. import PRETZEL_TEST_TIMEOUT

__all__ = ('ProcessTest',)


class ProcessTest(unittest.TestCase):
    stress_count = 128

    @async_test
    def test_pipe(self):
        check_fds = boot_pack(textwrap.dedent("""\
            import os
            import sys
            import errno
            import json
            result = []
            for fd in sys.argv[1:]:
                try:
                    os.fstat(int(fd))
                    result.append(True)
                except OSError as error:
                    if error.errno != errno.EBADF:
                        raise
                    result.append(False)
            sys.stdout.write(json.dumps(result))
            """))
        pipe = ProcessPipe(reader=True)
        result = yield process_call(('python', '-c', check_fds,
                                    str(pipe.parent_fd).encode(),
                                    str(pipe.child_fd).encode()),
                                    preexec=lambda: pipe(), check=False)
        # child's fds
        self.assertEqual(result[1:], (b'', 0))
        self.assertEqual(json.loads(result[0].decode()), [False, True])
        # parent's fds
        pipe()
        self.assertEqual(check_fd(pipe.parent_fd), True)
        self.assertEqual(check_fd(pipe.child_fd), False)

    @async_test
    def test_call(self):
        out, err, code = yield process_call(command, b'10', check=False)

        self.assertEqual(code, 117)
        self.assertEqual(out, b'02468')
        self.assertEqual(err, b'13579')

    @async_test
    def test_call_shell(self):
        shell_command = list(command)
        shell_command[-1] = '\'{}\''.format(command[-1])
        shell_command += ['| wc -c']
        out, err, code = yield process_call(shell_command, b'10', shell=True)
        self.assertEqual(code, 0)
        self.assertEqual(out, b'5\n')
        self.assertEqual(err, b'13579')

    @async_test
    def test_call_with_fd(self):
        with CompDisp() as dispose:
            # different file descriptors
            def preexec_diff():
                if(check_fd(stdin.fileno()) or
                   check_fd(stdout.fileno()) or
                   check_fd(stderr.fileno())):
                    raise ValueError('descriptor must be closed by pipe_cleanup')
            stdin = dispose.add(tempfile.TemporaryFile())
            stdout = dispose.add(tempfile.TemporaryFile())
            stderr = dispose.add(tempfile.TemporaryFile())
            stdin.write(b'10')
            stdin.seek(0)
            out, err, code = yield process_call(command, stdin=stdin, stdout=stdout,
                                                stderr=stderr, check=False,
                                                preexec=preexec_diff)
            self.assertEqual(code, 117)
            self.assertEqual(out, None)
            self.assertEqual(err, None)
            stdout.seek(0)
            self.assertEqual(stdout.read(), b'02468')
            stderr.seek(0)
            self.assertEqual(stderr.read(), b'13579')

            # duplicating file descriptors
            def preexec_same():
                if check_fd(stream.fileno()):
                    raise ValueError('descriptor must be closed by pipe_cleanup')
            stream = dispose.add(tempfile.TemporaryFile())
            stream.write(b'10')
            stream.seek(0)
            out, err, code = yield process_call(command, stdin=stream, stdout=stream,
                                                stderr=stream, check=False,
                                                preexec=preexec_same)
            self.assertEqual(code, 117)
            self.assertEqual(out, None)
            self.assertEqual(err, None)
            stream.seek(0)
            self.assertEqual(stream.read(), b'100123456789')

    @async_test
    def test_call_big(self):
        out_ref = b'01234567890' * (1 << 22)  # 40Mb
        out, err, code = yield process_call('cat', out_ref, check=False)
        self.assertEqual(code, 0)
        self.assertEqual(out_ref, out)

    @async_test
    def test_cleanup(self):
        with (yield Process('cat', stdin=PIPE, stdout=PIPE, stderr=PIPE,
                            check=False)) as proc:
            self.assertTrue(proc.stdin.close_on_exec())
            self.assertTrue(proc.stdout.close_on_exec())
            self.assertTrue(proc.stderr.close_on_exec())
        yield proc.status

    @async_test
    def test_bad_exec(self):
        with self.assertRaises(OSError):
            print((yield process_call('does_not_exists')))

    @async_test
    def test_stress_seq(self):
        result_ref = yield process_call('uname')
        self.assertEqual(result_ref[-1], 0)
        results = yield Cont.sequence((process_call('uname'),) * self.stress_count)
        for result in results:
            self.assertEqual(result.value, result_ref)

    @async_test
    def test_stress_sim(self):
        result_ref = yield process_call('uname')
        self.assertEqual(result_ref[-1], 0)
        results = yield async_all((process_call('uname'),) * self.stress_count)
        self.assertEqual(results, (result_ref,) * self.stress_count)

    @async_test
    def test_devnull(self):
        self.assertEqual((yield process_call('cat', stdin=DEVNULL)),
                         (b'', b'', 0))

    @async_test
    def test_check_option(self):
        out, err, code = yield process_call('false', check=False)
        self.assertNotEqual(code, 0)
        with self.assertRaises(ProcessError):
            yield process_call('false', check=True)

    @async_test
    def test_kill(self):
        with (yield Process(['sleep', '10'], kill=0.5)) as proc:
            pass
        self.assertFalse(proc.status.completed)
        start = time.time()
        self.assertEqual((yield proc.status), 0)
        stop = time.time()
        self.assertTrue(stop - start < max(PRETZEL_TEST_TIMEOUT - 1, 1))

    @async_test
    def test_chain(self):
        commands = [command, ['cat'], ['wc', '-c']]

        # data in memory data
        self.assertEqual((yield process_chain_call(commands, stdin=b'10', check=False)),
                         (b'5\n', b'13579', (117, 0, 0)))

        # data in files
        with CompDisp() as dispose:
            stdin = dispose.add(tempfile.TemporaryFile())
            stdout = dispose.add(tempfile.TemporaryFile())
            stderr = dispose.add(tempfile.TemporaryFile())
            stdin.write(b'10')
            stdin.seek(0)
            result = yield process_chain_call(commands, stdin=stdin, stdout=stdout,
                                              stderr=stderr, check=False)
            self.assertEqual(result, (None, None, (117, 0, 0)))
            stdout.seek(0)
            self.assertEqual(stdout.read(), b'5\n')
            stderr.seek(0)
            self.assertEqual(stderr.read(), b'13579')

        with self.assertRaises(ProcessError):
            yield process_chain_call(commands, stdin=b'10')


command = ['python', '-c', textwrap.dedent("""\
    import sys
    for value in range(int(input())):
        if value % 2 == 1:
            sys.stderr.write(str(value))
            sys.stderr.flush()
        else:
            sys.stdout.write(str(value))
            sys.stdout.flush()
    sys.exit (117)
    """)]


def check_fd(fd):
    """Check if descriptor is a valid one
    """
    try:
        os.fstat(fd)
        return True
    except OSError as error:
        if error.errno != errno.EBADF:
            raise
        return False
