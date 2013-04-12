import textwrap
import unittest

from ..process import Process, PIPE, process_call
from ..monad import Cont
from . import async_test


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
        with Process(['cat'], stdin=PIPE, stdout=PIPE, stderr=PIPE) as proc:
            self.assertTrue(proc.stdin.close_on_exec())
            self.assertTrue(proc.stdout.close_on_exec())
            self.assertTrue(proc.stderr.close_on_exec())
        yield proc
        self.assertEqual(proc.stdin, None)
        self.assertEqual(proc.stdout, None)
        self.assertEqual(proc.stderr, None)

    @async_test
    def test_bad_exec(self):
        with self.assertRaises(OSError):
            print((yield process_call(['does_not_exists'])))

        '''
        # wait for full process termination (SIGCHLD)
        process_waiter = ProcessWaiter.Instance ()
        for _ in Core.Instance ():
            if not process_waiter.conts:
                break
        '''

    @async_test
    def test_stress(self):
        procs = yield Cont.sequence(process_call(['uname']) for _ in range(20))
        for proc in procs:
            proc.value
