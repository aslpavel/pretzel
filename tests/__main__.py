import os
import unittest
import argparse
from .. import __package__ as pretzel

def main():
    """Run unit tests on pretzel pacakge
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--coverage', dest='coverage',
                        action='store_true', help='run coverage')
    opts = parser.parse_args()

    if opts.coverage:
        import coverage
        cov = coverage.coverage()
        cov.start()
        try:
            unittest.main(module=pretzel)
        finally:
            cov.stop()
            cov.save()
            cov.report(show_missing=False)
    else:
        unittest.main(module=pretzel)

if __name__ == '__main__':
    main()
