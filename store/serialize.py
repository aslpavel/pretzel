"""Synchronous version of BufferedStream's serializer
"""
import struct

__slots__ = ('Serializer',)


class Serializer(object):
    """Stream serializer

    It is synchronous version of BufferedStream's serializer.
    """
    size_struct = struct.Struct('>I')

    def __init__(self, stream):
        self.stream = stream

    def read_bytes(self):
        """Read bytes object
        """
        return (self.stream.read(self.size_struct.unpack
               (self.stream.read(self.size_struct.size))[0]))

    def write_bytes(self, bytes):
        """Write bytes object to buffer
        """
        self.stream.write(self.size_struct.pack(len(bytes)))
        self.stream.write(bytes)

    def read_struct_list(self, struct, complex=None):
        """Read list of structures
        """
        struct_data = self.read_bytes()
        if complex:
            return [struct.unpack(struct_data[offset:offset + struct.size])
                    for offset in range(0, len(struct_data), struct.size)]
        else:
            return [struct.unpack(struct_data[offset:offset + struct.size])[0]
                    for offset in range(0, len(struct_data), struct.size)]

    def write_struct_list(self, struct_list, struct, complex=None):
        """Write list of structures to buffer
        """
        self.stream.write(self.size_struct.pack(len(struct_list) * struct.size))
        if complex:
            for struct_target in struct_list:
                self.stream.write(struct.pack(*struct_target))
        else:
            for struct_target in struct_list:
                self.stream.write(struct.pack(struct_target))

    def read_bytes_list(self):
        """Read array of bytes
        """
        return [self.stream.read(size)
                for size in self.read_struct_list(self.size_struct)]

    def write_bytes_list(self, bytes_list):
        """Write bytes array object to buffer
        """
        self.write_struct_list([len(bytes) for bytes in bytes_list], self.size_struct)
        for bytes in bytes_list:
            self.stream.write(bytes)
