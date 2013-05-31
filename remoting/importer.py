"""Remote importer
"""
import os
import sys
import socket
import inspect
import pkgutil
from .hub import pair
from .expr import SetItemExpr, GetAttrExpr, LoadArgExpr
from ..core import Core
from ..monad import Result, async, do_return
from ..boot import BootLoader

__all__ = ('Importer',)


class Importer(object):
    def __init__(self, sender, location=None):
        self.sender = sender
        self.location = location or (socket.gethostname(), os.getpid())
        self.loaders = {}

    @classmethod
    def create(cls, hub=None):
        """Create importer proxy object
        """
        def importer_handler(name, dst, src):
            try:
                if name is None:
                    return False  # dispose importer
                module = sys.modules.get(name, False)
                if module is None:
                    src.send(None)  # Module is cached as not found (python 2)
                    return True
                loader = pkgutil.get_loader(name)
                if loader is None or not hasattr(loader, 'get_source'):
                    src.send(None)
                    return True
                source = loader.get_source(name)
                if source is None:
                    src.send(None)
                    return True
                ispkg = loader.is_package(name)
                if module and hasattr(module, '__package__'):
                    pkg = module.__package__
                else:
                    pkg = name if ispkg else name.rpartition('.')[0]
                try:
                    filename = (inspect.getfile(loader.get_code(name)) if not module else
                                inspect.getfile(module))
                except TypeError:
                    filename = '<unknown>'
                src.send(BootLoader(name, source, filename, ispkg, pkg))
            except Exception:
                src.send(Result.from_current_error())
            return True

        recv, send = pair(hub=hub)
        recv(importer_handler)
        return Importer(send)

    @classmethod
    @async
    def create_remote(cls, conn, index=None):
        """Create and install importer on specified connection
        """
        importer = Importer.create(conn.hub)
        try:
            yield conn(importer)(index)

            # determine full name of __main__ module
            module = sys.modules.get('__main__', None)
            while module is not None:
                try:
                    file = inspect.getsourcefile(module)
                    if not file:
                        break
                except TypeError:
                    # __main__ is a built-in module. Do not need to map anything
                    break
                name = os.path.basename(file).partition('.')[0]
                package = getattr(module, '__package__', None)
                if package:
                    name = '{}.{}'.format(package, name)
                else:
                    try:
                        source = inspect.getsource(module)
                    except Exception:
                        # __main__ source file is <stdin> or something like this
                        break
                    loader = BootLoader(name, source, file, False, None)
                    yield conn(loader)().__package__

                # remote_conn.module_map['__main__'] = main
                yield conn.sender(SetItemExpr(GetAttrExpr(LoadArgExpr(0),
                                  'module_map'), '__main__', name).code())
                conn.module_map[name] = '__main__'
                break
            do_return(importer)

        except Exception:
            importer.dispose()
            raise

    def __call__(self, index=None):
        """Install importer
        """
        if self in sys.meta_path:
            return
        if index is None:
            sys.meta_path.append(self)
        else:
            sys.meta_path.insert(index, self)

    def find_module(self, name, path=None):
        if self.sender is None:
            return None
        loader = self.loaders.get(name, False)
        if loader is False:
            # Function find_module must be synchronous, so we must execute core
            # until request is fulfilled.
            loader = self.sender(name).future()
            for _ in Core.local():
                if loader.completed:
                    loader = loader.value
                    break
            self.loaders[name] = loader
        if loader is None:
            return None
        return loader

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False
        return self.sender == other.sender

    def __hash__(self):
        return hash(self.sender)

    def __reduce__(self):
        return Importer, (self.sender, self.location)

    def dispose(self):
        if self in sys.meta_path:
            sys.meta_path.remove(self)
        sender, self.sender = self.sender, None
        if sender is not None:
            try:
                sender.send(None)
            except ValueError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return ('{}(addr:{}, host:{}, pid:{})'.format(type(self).__name__,
                self.sender.addr if self.sender else None,
                *self.location))

    def __repr__(self):
        return str(self)
