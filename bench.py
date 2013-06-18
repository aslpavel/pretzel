"""Benchmark class
"""
from __future__ import print_function
import sys
import time
from operator import add
from functools import reduce
from .monad import async, do_return
from .app import app

__all__ = ('Benchmark', 'TextBenchmarkRunner',)


class Benchmark(object):
    default_error = 0.01
    default_time = time.time
    min_count = 5
    max_time = 15

    def __init__(self, name=None, factor=None):
        self.name = name or type(self).__name__
        self.factor = factor or 1

    @async
    def init(self):
        """Initialize benchmark
        """

    @async
    def body(self):
        raise NotImplementedError()

    def __call__(self, error=None, time=None):
        """Execute benchmark
        """
        error = error or self.default_error
        time = time or self.default_time

        def result(result=None):
            if result is not None:
                results.append(float(result))
            if len(results) < self.min_count:
                return None, None
            res_mean = reduce(add, results, 0) / len(results)
            res_error = (reduce(add, ((result - res_mean) ** 2
                         for result in results), 0) / (len(results) - 1))
            return res_mean, res_error
        results = []

        @app
        def run():
            try:
                yield self.init()
                begin_time = time()
                while True:
                    start_time = time()
                    yield self.body()
                    stop_time = time()
                    res_mean, res_error = result(stop_time - start_time)
                    if res_mean is None:
                        continue
                    if (res_error / res_mean <= error or
                       (stop_time - begin_time) >= self.max_time):
                        do_return((res_mean, res_error))
            finally:
                self.dispose()

        res_mean, res_error = run()
        return (self.name, res_mean / self.factor,
                res_error / res_mean, len(results) * self.factor)

    def dispose(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False


class TextBenchmarkRunner (object):
    def __init__(self, file=None):
        self.benchs = []
        self.file = file or sys.stdout

    def add(self, bench):
        """Add benchmark
        """
        self.benchs.append(bench)

    def add_module(self, module):
        """Add benchmark from module
        """
        getattr(module, 'load_bench')(self)

    def __call__(self, error_thresh=None, timer=None):
        # run benchmarks
        lines = [('Name', 'Time', 'Count', 'Count/Time', 'Deviation',)]
        time_total = 0
        for bench in self.benchs:
            name, time, error, count = bench(error_thresh, timer)
            lines.append((name,                           # name
                         '{:.3f}s'.format(time * count),  # time
                         '{:.0f}'.format(count),          # count
                         '{:.0f}'.format(1 / time),       # count/time
                         '{:.3f}%'.format(error * 100)))  # error
            time_total += time * count
            self.file.write('.')
            self.file.flush()
        self.file.write('\n{}\n'.format('-' * 70))
        self.file.write('Ran {} benchmarks in {:.3f}s\n\n'
                        .format(len(lines), time_total))

        # calculate columns width
        widths = [0] * len(lines[0])
        for line in lines:
            for index in range(len(widths)):
                widths[index] = max(widths[index], len(line[index]))

        for index in range(len(widths)):
            widths[index] += 2

        format = '  {}\n'.format(''.join('{{:<{}}}'
                                 .format(width) for width in widths))
        lines.insert(1, tuple('-' * (width - 1) for width in widths))
        for line in lines:
            self.file.write(format.format(*line))
        self.file.write('\n')
        self.file.flush()


def main():
    from importlib import import_module
    bench_runner = TextBenchmarkRunner()
    bench_runner.add_module(import_module(__package__))
    bench_runner()

if __name__ == '__main__':
    main()
