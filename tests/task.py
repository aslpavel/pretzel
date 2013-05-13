import time
import unittest
from . import async_test
from ..monad import async_all
from ..task import ThreadPool, task

__all__ = ('TaskTest',)


class TaskTest(unittest.TestCase):
    @async_test
    def test(self):
        """This test may fail if system is really busy
        """
        sleep_time = .3
        sleep_action = lambda: time.sleep(sleep_time)
        try:
            with ThreadPool.main() as pool:
                # thread count test
                start = time.time()
                yield async_all((task(sleep_action),) * (pool.size + 1))
                stop = time.time()
                self.assertEqual(int((stop - start) / sleep_time), 2)

                # error test
                def error():
                    raise RuntimeError()
                with self.assertRaises(RuntimeError):
                    yield task(error)

                # disposed task
                pool.size = 1
                task(sleep_action)(lambda _: None)
                disp_task = task(lambda: time.sleep(100)).future()

            with self.assertRaises(ValueError):
                yield disp_task

        finally:
            ThreadPool.main(None)
