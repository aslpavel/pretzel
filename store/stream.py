# -*- coding: utf-8 -*-
import zlib
import json
from .. import PRETZEL_BUFSIZE

__all__ = ('StoreStream',)


class StoreStream(object):
    """Stream object with Store back-end.
    """
    default_compress = 9

    def __init__(self, store, header, bufsize=None, compress=None):
        self.store = store
        self.header = header

        header = self.header()
        if not header:
            self.bufsize = bufsize or PRETZEL_BUFSIZE
            self.chunks = []
            self.size = 0
            self.compress = self.default_compress if compress is None else compress
        else:
            header = json.loads(header.decode())
            self.bufsize = header['bufsize']
            self.chunks = header['chunks']
            self.size = header['size']
            self.compress = header['compress']

        self.seek_pos = None
        self.chunk_index = None
        self.chunk_dirty = False
        self.chunk_zero = b'\x00' * self.bufsize
        self.chunk_switch(0)

    def chunk_switch(self, index=None):
        """Switch current chunk
        """
        if self.chunk_index == index:
            return

        if self.chunk_dirty:
            self.chunk_dirty = False
            chunk_desc = self.store.save(
                self.chunk.bytes() if not self.compress else
                zlib.compress(self.chunk.bytes(), self.compress))
            if self.chunk_index < len(self.chunks):
                self.chunks[self.chunk_index] = chunk_desc
            else:
                self.chunks.append(chunk_desc)

        self.chunk_index = self.chunk_index + 1 if index is None else index
        if self.chunk_index < len(self.chunks):
            self.chunk_desc = self.chunks[self.chunk_index]
            self.chunk = Chunk(
                self.bufsize,
                self.chunk_zero if self.chunk_desc is None else
                self.store.load(self.chunk_desc) if not self.compress else
                zlib.decompress(self.store.load(self.chunk_desc)))
        else:
            self.chunks.extend((None,) * (self.chunk_index - len(self.chunks)))
            self.chunk_desc = None
            self.chunk = Chunk(self.bufsize)

    def write(self, data):
        """Write data to stream
        """
        if self.seek_pos is not None:
            self.seek_do()

        data_size = len(data)
        data_offset = 0
        while True:
            data_offset += self.chunk.write(data[data_offset:])
            self.chunk_dirty = True
            if data_offset == data_size:
                break
            self.chunk_switch()

        self.size = max(self.size, self.chunk_index * self.bufsize + self.chunk.tell())
        return len(data)

    def read(self, size=None):
        """Read data from stream
        """
        if self.seek_pos is not None:
            if self.seek_pos < self.size:
                self.seek_do()
            else:
                return b''

        size = self.size if size is None else size
        data = []
        data_size = 0

        while True:
            chunk = self.chunk.read(size - data_size)
            data.append(chunk)
            data_size += len(chunk)
            if data_size == size:
                break
            if len(self.chunks) <= self.chunk_index + 1:
                break
            else:
                self.chunk_switch()

        return b''.join(data)

    def seek(self, pos, whence=0):
        """Seek stream
        """
        if whence == 0:    # SEEK_SET
            self.seek_pos = pos
        elif whence == 1:  # SEEK_CUR
            self.seek_pos = self.chunk_index * self.bufsize + self.chunk.tell() + pos
        elif whence == 2:  # SEEK_END
            self.seek_pos = self.size + pos
        else:
            raise ValueError('Invalid whence argument: {}'.format(whence))
        return self.seek_pos

    def seek_do(self):
        """Actually seek
        """
        seek_pos, self.seek_pos = self.seek_pos, None
        if seek_pos is None:
            return
        index, offset = divmod(seek_pos, self.bufsize)
        self.chunk_switch(index)
        self.chunk.seek(offset)

    def tell(self):
        """Tell current position inside stream
        """
        if self.seek_pos is None:
            return self.chunk_index * self.bufsize + self.chunk.tell()
        else:
            return self.seek_pos

    def truncate(self, pos=None):
        """Truncate stream
        """
        if pos is not None:
            self.seek(pos)
        self.seek_do()

        chunks, self.chunks = self.chunks[self.chunk_index + 1:], self.chunks[:self.chunk_index + 1]
        for chunk in chunks:
            self.store.Delete(chunk)
        self.chunk.truncate()
        self.chunk_dirty = True

    def flush(self):
        """Flush stream
        """
        if self.chunk_dirty:
            self.chunk_dirty = False
            chunk_desc = self.store.save(
                self.chunk.bytes() if not self.compress else
                zlib.compress(self.chunk.bytes(), self.compress))
            if self.chunk_index < len(self.chunks):
                self.chunks[self.chunk_index] = chunk_desc
            else:
                self.chunks.append(chunk_desc)

        header = json.dumps({
            'bufsize': self.bufsize,
            'chunks': self.chunks,
            'size': self.size,
            'compress': self.compress,
        }).encode()
        if self.header() != header:
            self.header(header)

    def close(self):
        return self.Flush()

    def dispose(self):
        self.flush()

    def __enter__(self):
        return self

    def __exit__(self, et, eo, tb):
        self.dispose()
        return False


class Chunk(object):
    """Chunk

    Stream like object but with fixed capacity.
    """
    __slots__ = ('buf', 'cap', 'pos', 'size')

    def __init__(self, cap, data=None):
        self.buf = bytearray(cap)
        self.cap = cap
        self.pos = 0
        if data:
            self.size = len(data)
            self.buf[:self.size] = data
        else:
            self.size = 0

    def write(self, data):
        data_size = min(self.cap - self.pos, len(data))
        self.buf[self.pos:self.pos + data_size] = data[:data_size]
        self.pos += data_size
        self.size = max(self.size, self.pos)
        return data_size

    def read(self, size=None):
        data = (self.buf[self.pos:self.size] if size is None else
                self.buf[self.pos:min(self.pos + size, self.size)])
        self.pos += len(data)
        return bytes(data)

    def seek(self, pos, whence=0):
        if whence == 0:    # SEEK_SET
            self.pos = pos
        elif whence == 1:  # SEEK_CUR
            self.pos += pos
        elif whence == 2:  # SEEK_END
            self.pos = self.size + pos
        return self.pos

    def tell(self):
        return self.pos

    def truncate(self, pos=None):
        self.size = self.pos if pos is None else pos
        return self.size

    def bytes(self):
        return bytes(self.buf[:self.size])

    def __str__(self):
        return 'Chunk(data:{}, pos:{}, cap:{})'.format(self.bytes(), self.pos, self.cap)

    def __repr__(self):
        return str(self)
