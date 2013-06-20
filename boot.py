"""Bootstrap module

Bootstrap package hierarchy from single string.
"""
import os
import io
import re
import sys
import imp
import zlib
import json
import struct
import pickle
import inspect
import binascii
import textwrap
import importlib

__all__ = ('BootImporter', 'BootLoader', 'boot_source', 'boot_boot',
           'boot_binary',)


class BootImporter(object):
    """Bootstrap importer
    """
    __tag__ = '1f43bbd9-36e0-4084-84e5-b7fb14fdb1bd'

    def __init__(self, loaders=None):
        self.loaders = loaders or {}

    @classmethod
    def from_stream(cls, stream):
        loaders = {}
        for _ in range(struct.unpack('>L', stream.read(struct.calcsize('>L')))[0]):
            loader = BootLoader.from_stream(stream)
            loaders[loader.name] = loader
        return cls(loaders)

    def to_stream(self, stream):
        stream.write(struct.pack('>L', len(self.loaders)))
        for loader in self.loaders.values():
            loader.to_stream(stream)
        return stream

    @classmethod
    def from_bytes(cls, bytes):
        return cls.from_stream(io.BytesIO(bytes))

    def to_bytes(self):
        stream = io.BytesIO()
        self.to_stream(stream)
        return stream.getvalue()

    @classmethod
    def from_modules(cls, modules=None):
        instance = cls()
        if modules:
            for module in modules:
                instance.add_module(module)
        else:
            instance.add_module(__package__ or __name__.partition('.')[0])
        return instance

    def add_module(self, module):
        """Add module or package

        Only capable to add modules witch reside on disk as plain python files
        or in tomb.
        """
        if isinstance(module, str):
            # convert module name to module
            module = sys.modules.get(module, None) or importlib.import_module(module)

        # find top level package
        modname = (getattr(module, '__package__', '') or module.__name__).partition('.')[0]
        if modname != module.__name__:
            module = importlib.import_module(modname)

        if modname in self.loaders:
            return  # skip already imported packages

        loader = getattr(module, '__loader__', None)
        for importer in sys.meta_path:
            if modname in getattr(importer, 'loaders', {}):
                # package was loaded with BootImporter
                for name, loader in importer.loaders.items():
                    if name.startswith(modname):
                        self.loaders[name] = loader
                return

        # find package file
        filename = inspect.getsourcefile(module)
        if not filename:
            raise ValueError('module does not have sources: {}'.format(modname))

        # Use file name to determine if it is a package instead of loader.is_package
        # because is_package incorrectly handles __main__ module.
        if os.path.basename(filename).lower() == '__init__.py':
            root = os.path.dirname(filename)
            for path, dirs, files in os.walk(root):
                for file in files:
                    if not file.lower().endswith('.py'):
                        continue
                    filename = os.path.join(path, file)
                    source = self.read_source(filename)
                    name = (modname if os.path.samefile(path, root) else
                            '.'.join((modname, os.path.relpath(path, root).replace('/', '.'))))
                    if file.lower() == '__init__.py':
                        self.add_source(name, source, filename, True)
                    else:
                        self.add_source('.'.join((name, file[:-3])), source, filename, False)
        else:
            self.add_source(modname, self.read_source(filename), filename, False)

    def add_source(self, name, source, filename, ispkg=False, pkg=None):
        """Add source file as specified module
        """
        self.loaders[name] = BootLoader(name, source, filename, ispkg)

    def find_module(self, name, path=None):
        return self.loaders.get(name, None)

    def bootstrap(self, init=None, *init_a, **init_kw):
        """Create bootstrap source for this importer

        Initialization function ``init`` and its arguments ``init_a``,
        ``init_kw`` must be pickle-able objects and its required modules must be
        added to the importer.
        """
        if init and inspect.getmodule(init).__name__ not in self.loaders:
            raise ValueError('initialization function must reside in added modules')

        source = StringIO()
        source.write(textwrap.dedent("""\
            {}
            _boot.BootImporter.from_bytes({}).install()
            """).format(boot_boot('_boot'), boot_binary(self.to_bytes())))
        if init is not None:
            source.write(textwrap.dedent("""
                import pickle
                init, init_a, init_kw = pickle.loads({})
                if init is not None:
                    init(*init_a, **init_kw)
                """).format(boot_binary(pickle.dumps((init, init_a, init_kw)))))
        return source.getvalue()

    def install(self):
        """Install importer into system path
        """
        if self not in sys.meta_path:
            sys.meta_path.insert(0, self)

    def dispose(self):
        if self in sys.meta_path:
            self.meta_path.remove(self)

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    @staticmethod
    def read_source(filename):
        """Read source from file name
        """
        encoding = 'utf-8'
        encoding_pattern = re.compile(b'coding[:=]\s*([-\w.]+)')  # PEP: 0263

        source = io.BytesIO()
        with io.open(filename, 'rb') as stream:
            for line in stream:
                if line.startswith(b'#'):
                    match = encoding_pattern.search(line)
                    if match:
                        encoding = match.group(1).decode()
                        source.write(b'\n')
                        continue
                source.write(line)
        if PY2:
            return source.getvalue()
        else:
            return source.getvalue().decode(encoding)


class BootLoader(object):
    __slots__ = ('name', 'source', 'filename', 'ispkg', 'pkg',)

    def __init__(self, name, source, filename, ispkg, pkg=None):
        self.name = name
        self.source = source
        self.filename = filename
        self.ispkg = ispkg
        self.pkg = pkg or name if ispkg else name.rpartition('.')[0]

    @classmethod
    def from_stream(cls, stream):
        data = json.loads(zlib.decompress(stream.read(struct.unpack('>L',
                          stream.read(struct.calcsize('>L')))[0])).decode('utf-8'))
        if PY2:
            # Convert unicode string to bytes, avoids problems with traceback
            # creation and error reporting.
            return cls(data['name'].encode('utf-8'),
                       data['source'].encode('utf-8'),
                       data['filename'].encode('utf-8'),
                       data['ispkg'],
                       data['pkg'].encode('utf-8'))
        else:
            return cls(data['name'], data['source'], data['filename'],
                       data['ispkg'], data['pkg'])

    def to_stream(self, stream):
        data = zlib.compress(json.dumps({
            'name': self.name,
            'source': self.source,
            'filename': self.filename,
            'ispkg': self.ispkg,
            'pkg': self.pkg,
        }).encode('utf-8'), 9)
        stream.write(struct.pack('>L', len(data)))
        stream.write(data)
        return stream

    def __call__(self):
        return self.load_module(self.name)

    def load_module(self, name):
        module = sys.modules.get(name)
        if module is not None:
            return module
        if name != self.name:
            raise ImportError('loader cannot handle {}'.format(name))

        module = imp.new_module(self.name)
        module.__package__ = self.pkg
        module.__file__ = self.filename
        module.__loader__ = self
        if self.ispkg:
            module.__path__ = []

        module.__initializing__ = True
        sys.modules[name] = module
        try:
            execute(compile(self.source, module.__file__, 'exec'), module.__dict__)
            return module
        except Exception:
            sys.modules.pop(name, None)
            raise
        finally:
            module.__initializing__ = False

    def is_package(self, name):
        if name != self.name:
            raise ImportError('loader cannot handle {}'.format(name))
        return self.ispkg

    def get_source(self, name):
        if name != self.name:
            raise ImportError('loader cannot handle {}'.format(name))
        return self.source

    def get_code(self, name):
        if name != self.name:
            raise ImportError('loader cannot handle {}'.format(name))
        return compile(self.source, self.filename, 'exec')

    def __str__(self):
        return '{}(name:{}, package:{})'.format(type(self).__name__,
                                                self.name, self.pkg)

    def __repr__(self):
        return str(self)


def boot_source(name, source, filename):
    """Bootstrap python source

    Returns python source, witch when executed allows to import specified
    ``source`` as module with specified ``name``.
    """
    source_payload = textwrap.dedent("""\
        import sys
        import imp
        import zlib
        import binascii
        {sep}
        def load():
            module = imp.new_module("{name}")
            module.__file__ = "{filename}"
            module.__package__ = "{name}"
            sys.modules["{name}"] = module
            try:
                code = compile({source}, module.__file__, "exec")
                if sys.version_info[0] > 2:
                    exec(code, module.__dict__)
                else:
                    exec("exec code in module.__dict__")
                return module
            except Exception:
                sys.modules.pop("{name}")
                raise
        try:
            {name} = load()
        finally:
            del load
        """)
    return source_payload.format(name=name, filename=filename, sep='\n',
                                 source=boot_binary(source.encode('utf-8')))


def boot_boot(name):
    """Bootstrap this module

    Returns python source, witch when executed allows to import this module
    by specified "name".
    """
    module = sys.modules[__name__]
    return boot_source(name, inspect.getsource(module),
                       inspect.getsourcefile(module))


def boot_binary(data):
    """Binary data trampoline

    Returns source code which unpack into provided binary ``data``.
    """
    return ('zlib.decompress(binascii.a2b_base64(b"\\\n{}"))'.format(
            '\\\n'.join(textwrap.wrap(binascii.b2a_base64(zlib.compress(data, 9))
            .strip().decode('utf-8'), 78))))


#  python version compatibility
if sys.version_info[0] > 2:
    import builtins
    execute = getattr(builtins, "exec")
    del builtins

    def reraise(tp, value, tb=None):
        """Re-raise exception
        """
        if value.__traceback__ is not tb:
            raise value.with_traceback(tb)
        raise value

    StringIO = io.StringIO
    PY2 = False

else:
    def execute(code, globs=None, locs=None):
        """Execute code in a name space.
        """
        if globs is None:
            frame = sys._getframe(1)
            globs = frame.f_globals
            if locs is None:
                locs = frame.f_locals
            del frame
        elif locs is None:
            locs = globs
        exec("""exec code in globs, locs""")

    exec("""def reraise(tp, value, tb=None):
        raise tp, value, tb""")

    StringIO = io.BytesIO
    PY2 = True


def main():  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--main', dest='main', default='',
                        help='file used as __main__ module')
    parser.add_argument('modules', nargs=argparse.REMAINDER, help='modules')
    opts = parser.parse_args()

    sys.stdout.write('#! /usr/bin/env python\n' if opts.main else '')
    sys.stdout.write(BootImporter.from_modules(opts.modules or None).bootstrap())
    sys.stdout.write('\n')

    if opts.main:
        sys.stdout.write(BootImporter.read_source(opts.main))

if __name__ == '__main__':
    main()
