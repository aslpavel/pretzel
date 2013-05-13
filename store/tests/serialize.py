# -*- coding: utf-8 -*-
import io
import struct
import unittest
from ..serialize import Serializer

__all__ = ('SerializerTest',)


class SerializerTest(unittest.TestCase):
    """Serializer unit test
    """
    def test_struct(self):
        """Structure serializer
        """
        struct_save = []
        format = struct.Struct('>L')

        # empty
        stream = io.BytesIO()
        serial = Serializer(stream)
        serial.write_struct_list(struct_save, format)

        stream.seek(0)
        struct_load = serial.read_struct_list(format)
        self.assertEqual(struct_save, struct_load)

        # normal
        stream = io.BytesIO()
        serial = Serializer(stream)
        struct_save.extend(range(10))
        serial.write_struct_list(struct_save, format)

        stream.seek(0)
        struct_load = serial.read_struct_list(format)
        self.assertEqual(struct_save, struct_load)

        # tuple
        stream = io.BytesIO()
        serial = Serializer(stream)
        struct_save = [(i, i) for i in range(10)]
        format = struct.Struct('BB')
        serial.write_struct_list(struct_save, format, True)

        stream.seek(0)
        struct_load = serial.read_struct_list(format, True)
        self.assertEqual(struct_save, struct_load)

    def test_bytes(self):
        """Bytes serializer
        """
        bytes_save = []

        # empty
        stream = io.BytesIO()
        serial = Serializer(stream)
        serial.write_bytes_list(bytes_save)

        stream.seek(0)
        bytes_load = serial.read_bytes_list()
        self.assertEqual(bytes_save, bytes_load)

        # normal
        stream = io.BytesIO()
        serial = Serializer(stream)
        bytes_save.extend(str(i).encode() for i in range(10))
        serial.write_bytes_list(bytes_save)

        stream.seek(0)
        bytes_load = serial.read_bytes_list()
        self.assertEqual(bytes_save, bytes_load)
