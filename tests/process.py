import textwrap
import unittest

from ..process import Process, ProcessError, PIPE, DEVNULL, process_call
from ..monad import Cont
from . import async_test

__all__ = ('ProcessTest',)


class ProcessTest(unittest.TestCase):
    @async_test
    def test_call(self):
        command = ['python', '-c', textwrap.dedent("""
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

        out, err, code = yield process_call(command, input=b'10', check=False)
        self.assertEqual(code, 117)
        self.assertEqual(out, b'02468')
        self.assertEqual(err, b'13579')

    @async_test
    def test_cleanup(self):
        with (yield Process(['cat'], stdin=PIPE, stdout=PIPE, stderr=PIPE, check=False)) as proc:
            self.assertTrue(proc.stdin.close_on_exec())
            self.assertTrue(proc.stdout.close_on_exec())
            self.assertTrue(proc.stderr.close_on_exec())
        yield proc.status

    @async_test
    def test_bad_exec(self):
        with self.assertRaises(OSError):
            print((yield process_call(['does_not_exists'])))

    @async_test
    def test_stress(self):
        reference = yield process_call(['uname'])
        procs = yield Cont.sequence(process_call(['uname']) for _ in range(30))
        for proc in procs:
            self.assertEqual(proc.value, reference)

    @async_test
    def test_devnull(self):
        self.assertEqual((yield process_call(['cat'], stdin=DEVNULL)),
                         (b'', b'', 0))

    @async_test
    def test_check(self):
        out, err, code = yield process_call(['false'], check=False)
        self.assertNotEqual(code, 0)
        with self.assertRaises(ProcessError):
            yield process_call(['false'], check=True)
