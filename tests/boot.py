import io
import sys
import unittest
from ..boot import BootLoader

__all__ = ('BootTest',)


class BootTest(unittest.TestCase):
    def test_loader(self):
        # simple module
        name = '_boot_test'
        loader = BootLoader(name, 'VALUE="value"', '<stdin>', False)

        self.assertFalse(loader.is_package(name))
        self.assertEqual(loader.get_source(name), 'VALUE="value"')
        self.assertTrue(isinstance(loader.get_code(name),
                                   type((lambda: None).__code__)))

        name_bad = name + '_bad'
        for action in (lambda: loader.load_module(name_bad),
                       lambda: loader.is_package(name_bad),
                       lambda: loader.get_source(name_bad),
                       lambda: loader.get_code(name_bad)):
            with self.assertRaises(ImportError):
                action()

        mod = loader()
        self.assertTrue(mod is loader())
        try:
            self.assertTrue(name in sys.modules)
            self.assertEqual(mod.VALUE, 'value')
            self.assertEqual(mod.__file__, '<stdin>')
            self.assertEqual(mod.__name__, name)
            self.assertEqual(mod.__package__, '')
            self.assertFalse(hasattr(mod, '__path__'))
        finally:
            sys.modules.pop(mod.__name__)

        # restore
        loader_stream = loader.to_stream(io.BytesIO())
        loader_stream.seek(0)
        loader_restored = BootLoader.from_stream(loader_stream)
        self.assertFalse(loader_restored.is_package(name))
        self.assertEqual(loader_restored.get_source(name),
                         loader.get_source(name))

        # bad module
        bad_loader = BootLoader('_boot_bad_test', 'raise RuntimeError()',
                                '<stdin>', False)
        with self.assertRaises(RuntimeError):
            bad_loader()
        self.assertTrue('_boot_bad_test' not in sys.modules)
