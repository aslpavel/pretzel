import io
import sys
import unittest
from ..boot import BootLoader

__all__ = ('BootTest',)


class BootTest(unittest.TestCase):
    def test_loader(self):
        # simple module
        name = '_boot_test'
        loader = BootLoader(name, 'VALUE="value"',
                            '_boot_test_path', False)
        loader_stream = loader.to_stream(io.BytesIO())
        loader_stream.seek(0)
        loader_restored = BootLoader.from_stream(loader_stream)
        self.assertFalse(loader.is_package(name))
        self.assertFalse(loader_restored.is_package(name))
        self.assertEqual(loader.get_source(name), 'VALUE="value"')
        self.assertEqual(loader_restored.get_source(name),
                         loader.get_source(name))
        self.assertTrue(isinstance(loader.get_code(name),
                                   type((lambda: None).__code__)))

        mod = loader()
        try:
            self.assertTrue(name in sys.modules)
            self.assertEqual(mod.VALUE, 'value')
            self.assertEqual(mod.__file__, '_boot_test_path')
            self.assertEqual(mod.__name__, name)
            self.assertEqual(mod.__package__, '')
            self.assertFalse(hasattr(mod, '__path__'))
        finally:
            sys.modules.pop(mod.__name__)

        # bad module
        bad_loader = BootLoader('_boot_bad_test', 'raise RuntimeError()',
                                '_boot_bad_test_path', False)
        with self.assertRaises(RuntimeError):
            bad_loader()
        self.assertTrue('_boot_bad_test' not in sys.modules)
