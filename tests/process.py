import textwrap
import unittest
import tempfile
import time
from . import async_test
from ..monad import Cont, async_all
from ..dispose import CompDisp
from ..process import (Process, ProcessError, PIPE, DEVNULL,
                       process_call, process_chain_call,)
from .. import PRETZEL_TEST_TIMEOUT

__all__ = ('ProcessTest',)


class ProcessTest(unittest.TestCase):
    stress_count = 128

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
    def test_call_fd(self):
        with CompDisp() as dispose:
            stdin = dispose.add(tempfile.TemporaryFile())
            stdout = dispose.add(tempfile.TemporaryFile())
            stderr = dispose.add(tempfile.TemporaryFile())

            stdin.write(b'10')
            stdin.seek(0)
            out, err, code = yield process_call(command, stdin=stdin, stdout=stdout,
                                                stderr=stderr, check=False)

            self.assertEqual(code, 117)
            self.assertEqual(out, None)
            self.assertEqual(err, None)
            stdout.seek(0)
            self.assertEqual(stdout.read(), b'02468')
            stderr.seek(0)
            self.assertEqual(stderr.read(), b'13579')

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
        else:
            sys.stdout.write(str(value))
    sys.stderr.flush()
    sys.stdout.flush()
    sys.exit (117)
    """)]
