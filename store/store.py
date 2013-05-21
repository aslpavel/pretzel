"""Store data inside some flat store (file, memory)

Data can be named and unnamed. Named data addressed by its name.
Unnamed data addressed by its descriptor which can change if data changed.
Descriptor is an unsigned 64-bit integer.
"""
import io
import os
import struct
from .alloc import StoreBlock, StoreAllocator
from .serialize import Serializer
from ..dispose import CompDisp

__all__ = ('Store', 'StreamStore', 'FileStore',)


class Store(object):
    """Store data inside some flat store (file, memory)

    Data can be named and unnamed. Named data addressed by its name.
    Unnamed data addressed by its descriptor which can change if data changed.
    Descriptor is an unsigned 64-bit integer.
    """

    header_struct = struct.Struct('>QQ')
    desc_struct = struct.Struct('>Q')

    def __init__(self, offset=None):
        self.disps = CompDisp()
        offset = offset or 0
        self.offset = offset + self.header_struct.size

        header = self.load_by_offset(offset, self.header_struct.size)
        self.alloc_desc, self.names_desc = ((0, 0) if not header else
                                            self.header_struct.unpack(header))

        # allocator
        if self.alloc_desc:
            self.alloc = StoreAllocator.from_stream(io.BytesIO(self.load(self.alloc_desc)))
        else:
            self.alloc = StoreAllocator()

        # names
        if self.names_desc:
            serialzer = Serializer(io.BytesIO(self.load(self.names_desc)))
            self.names = dict(zip(
                serialzer.read_bytes_list(),                    # names
                serialzer.read_struct_list(self.desc_struct)))  # descriptors
        else:
            self.names = {}

    def load(self, desc):
        """Load data by descriptor
        """
        if not desc:
            return b''
        block = StoreBlock.from_desc(desc)
        return self.load_by_offset(self.offset + block.offset, block.used)

    def load_by_name(self, name):
        """Load data by name
        """
        return self.load(self.names.get(name, 0))

    def load_by_offset(self, offset, size):
        """Load data by offset and size
        """
        raise NotImplementedError()

    def __getitem__(self, name):
        """Load data by name
        """
        return self.load_by_name(name)

    def save(self, data, desc=None):
        """Save data by descriptor

        Try to save data inside space pointed by descriptor and
        if its not enough allocate new space. Returns descriptor of saved data
        """
        if not data:
            return 0

        block = self.reserve_block(len(data), desc)
        self.save_by_offset(self.offset + block.offset, data)
        return block.to_desc()

    def save_by_name(self, name, data):
        """Save data by name
        """
        if not data:
            self.delete_by_name(name)
        else:
            self.names[name] = self.save(data, self.names.get(name))
        return data

    def save_by_offset(self, offset, data):
        """Save data by offset
        """
        raise NotImplementedError()

    def __setitem__(self, name, data):
        """Save data by name
        """
        self.save_by_name(name, data)

    def delete(self, desc):
        """Delete data by descriptor

        Free space occupied by data pointed by descriptor
        """
        if not desc:
            return
        self.alloc.free(StoreBlock.from_desc(desc))

    def delete_by_name(self, name):
        """Delete data by name
        """
        desc = self.names.pop(name, None)
        if desc:
            self.delete(desc)

    def __delitem__(self, name):
        """Delete data by name
        """
        self.delete_by_name(name)

    def reserve(self, size, desc=None):
        """Reserve space without actually writing anything in it

        Returns store's block descriptor.
        """
        return self.reserve_block(size, desc).to_desc()

    def reserve_block(self, size, desc=None):
        """Reserve space without actually writing anything in it

        Return store block.
        """
        if desc:
            block = StoreBlock.from_desc(desc)
            if block.size >= size:
                block.used = size
                return block
            self.alloc.free(block)
        block = self.alloc.alloc(size)
        block.used = size
        return block

    def flush(self):
        """Flush current state
        """
        # names
        if self.names:
            sr = Serializer(io.BytesIO())
            sr.write_bytes_list(tuple(self.names.keys()))
            sr.write_struct_list(tuple(self.names.values()), self.desc_struct)
            self.names_desc = self.save(sr.stream.getvalue(), self.names_desc)
        else:
            self.delete(self.names_desc)
            self.names_desc = 0

        # Check if nothing is allocated of the only thing allocated is
        # allocator itself.
        if self.alloc.size - (StoreBlock.from_desc(self.alloc_desc).size if self.alloc_desc else 0):
            while True:
                alloc_state = self.alloc.to_stream(io.BytesIO()).getvalue()
                self.alloc_desc, alloc_desc = self.save(alloc_state, self.alloc_desc), self.alloc_desc
                if self.alloc_desc == alloc_desc:
                    break
        else:
            alloc_desc, self.alloc_desc = self.alloc_desc, 0
            self.delete(alloc_desc)
            assert not self.alloc.size, 'Allocator is broken'

        # header
        self.save_by_offset(
            self.offset - self.header_struct.size,
            self.header_struct.pack(self.alloc_desc, self.names_desc))

    @property
    def size(self):
        """Total space used excluding internal storage data
        """
        size = 0
        if self.alloc_desc:
            size += StoreBlock.from_desc(self.alloc_desc).size
        if self.names_desc:
            size += StoreBlock.from_desc(self.names_desc).size
        for desc in self.names.values():
            size += StoreBlock.from_desc(desc).size
        return self.alloc.size - size

    def create_cell(self, name):
        """Cell object

        Cell is a callable object. When called with argument sets argument as new
        stored value and returns stored value. Otherwise just returns stored value.
        """
        def cell(value=None):
            """Get/Set value

            If value is not set returns stored value, otherwise sets value as
            stored value.
            """
            return(self.load_by_name(name) if value is None else
                   self.save_by_name(name, value))
        name = name if isinstance(name, bytes) else name.encode()
        return cell

    def create_map(self, name, order=None, key_type=None, value_type=None, compress=None):
        """Create name mapping (B+Tree)
        """
        from .map import StoreMap
        cell = self.create_cell('__map:{}'.format(name))
        mapping = StoreMap(self, cell, order, key_type, value_type, compress)
        self.disps.add(mapping)
        return mapping

    def create_stream(self, name, bufsize=None, compress=None):
        """Create stream object with store back-end.
        """
        from .stream import StoreStream
        cell = self.create_cell('__stream:{}'.format(name))
        stream = StoreStream(self, cell, bufsize, compress)
        self.disps.add(stream)
        return stream

    def dispose(self):
        """Flush and Close
        """
        self.disps()
        self.flush()

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False

    def __str__(self):
        return '{}(size:{}, names:{})'.format(type(self).__name__,
                                              self.size, len(self.names))

    def __repr__(self):
        return str(self)


class StreamStore(Store):
    """Stream based store
    """
    def __init__(self, stream, offset=None):
        self.stream = stream
        Store.__init__(self, offset)

    def save_by_offset(self, offset, data):
        self.stream.seek(offset)
        return self.stream.write(data)

    def load_by_offset(self, offset, size):
        self.stream.seek(offset)
        return self.stream.read(size)

    def flush(self):
        Store.flush(self)
        self.stream.flush()


class FileStore(StreamStore):
    """File based store
    """
    def __init__(self, path, mode=None, offset=None):
        mode = mode or 'r'
        self.mode = mode
        if mode == 'r':
            filemode = 'rb'
        elif mode == 'w':
            filemode = 'r+b'
        elif mode == 'c':
            if not os.path.lexists(path):
                filemode = 'w+b'
            else:
                filemode = 'r+b'
        elif mode == 'n':
            filemode = 'w+b'
        else:
            raise ValueError('Unknown mode: {}'.format(mode))
        StreamStore.__init__(self, io.open(path, filemode, buffering=0), offset)

    def flush(self):
        if self.mode != 'r':
            StreamStore.flush(self)

    def dispose(self):
        StreamStore.dispose(self)
        self.stream.close()

    def __str__(self):
        return ('FileStream(size:{}, names:{}, mode:{}, path:{})'.format
               (self.size, len(self.names), self.mode, self.stream.name))
