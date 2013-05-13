"""Store based B+Tree provider
"""
import io
import sys
import json
import zlib
import struct
import codecs
import binascii
import operator
import functools
from bisect import bisect
if sys.version_info[0] > 2:
    import pickle
else:
    import cPickle as pickle
from .provider import BPTreeProvider
from ..bptree import BPTreeNode, BPTreeLeaf
from ...alloc import StoreBlock
from ...serialize import Serializer

__all__ = ('StoreBPTreeProvider',)


class StoreBPTreeProvider(BPTreeProvider):
    """Store based B+Tree provider

    Keeps serialized(possible compressed) nodes inside store. Keys and values
    are serialized according to specified type. Possible values for type are
    'bytes', 'pickle:protocol', 'struct:struct_type', 'json'.
    """

    order_default = 128
    type_default = 'pickle:{}'.format(pickle.HIGHEST_PROTOCOL)
    compress_default = 9
    desc_struct = struct.Struct('>Q')
    crc32_struct = struct.Struct('>I')
    leaf_struct = struct.Struct('>QQ')

    def __init__(self, store, header, order=None, key_type=None,
                 value_type=None, compress=None):
        """Create provider

        Creates new provider or loads existing one identified by name. Compress
        argument specifies compression level default is 9(maximum compression).
        If key_type(value_type) is not specified they are set to 'pickle'
        """
        self.store = store
        self.header = header
        self.d2n = {}
        self.desc_next = -1
        self.dirty_set = set()

        header_data = header()
        if header_data:
            state_json = header_data[:-self.crc32_struct.size]
            crc32 = self.crc32_struct.unpack(header_data[-self.crc32_struct.size:])[0]
            if crc32 != binascii.crc32(state_json) & 0xffffffff:
                raise ValueError('Header checksum failed')
            state = json.loads(state_json.decode())
            self.size_st = state['size']
            self.depth_st = state['depth']
            self.order_st = state['order']
            self.key_type, self.read_keys, self.write_keys = self.type_parse(state['key_type'])
            self.value_type, self.read_vals, self.write_vals = self.type_parse(state['value_type'])
            self.compress = state.get('compress', 0)
            self.root_st = self.node_load(state['root'])

        else:
            self.size_st = 0
            self.depth_st = 1
            self.order_st = order or self.order_default
            self.key_type, self.read_keys, self.write_keys = self.type_parse(key_type or self.type_default)
            self.value_type, self.read_vals, self.write_vals = self.type_parse(value_type or self.type_default)
            self.compress = compress if compress is not None else self.compress_default
            self.root_st = self.create([], [], True)

    def flush(self, prune=None):
        """Flush provider and store
        """
        d2n_reloc = {}  # relocated nodes
        leaf_queue = {}

        ## flush leafs
        def leaf_enqueue(leaf):
            leaf_stream = io.BytesIO()

            # save leaf
            leaf_stream.seek(self.leaf_struct.size)
            if self.compress:
                with CompressorStream(leaf_stream, self.compress) as stream:
                    self.read_keys(stream, leaf.keys)
                    self.read_vals(stream, leaf.children)
            else:
                self.read_keys(leaf_stream, leaf.keys)
                self.read_vals(leaf_stream, leaf.children)

            # enqueue leaf
            leaf_queue[leaf] = leaf_stream

            # allocate space
            desc = self.store.reserve(leaf_stream.tell() + 1, None if leaf.desc < 0 else leaf.desc)
            if leaf.desc != desc:
                # queue parent for update
                if leaf is not self.root_st:
                    parent, key = self.root_st, leaf.keys[0]
                    while True:
                        parent_desc = parent.children[bisect(parent.keys, key)]
                        if parent_desc == leaf.desc:
                            break
                        parent = self.desc_to_node(parent_desc)
                    if parent not in self.dirty_set:
                        node_queue.add(parent)

                # queue next and previous for update
                for sibling_desc in(leaf.prev, leaf.next):
                    # descriptor is negative, node is dirty
                    if(sibling_desc > 0 and                # negative node is dirty for sure
                       sibling_desc not in d2n_reloc):     # relocated node is also dirty

                        sibling = self.d2n.get(sibling_desc)
                        if sibling:
                            # node has already been loaded
                            if(sibling not in self.dirty_set and
                               sibling not in leaf_queue):
                                    # queue it for update
                                    leaf_enqueue(sibling)
                        else:
                            # node hasn't been loaded
                            leaf_enqueue(self.node_load(sibling_desc))

                # update descriptor maps
                self.d2n.pop(leaf.desc)
                d2n_reloc[leaf.desc], leaf.desc = leaf, desc
                self.d2n[desc] = leaf

        # enqueue leafs and create dirty nodes queue
        node_queue = set()
        for node in self.dirty_set:
            if node.is_leaf:
                leaf_enqueue(node)
            else:
                node_queue.add(node)

        # all leafs has been allocated now
        for leaf, leaf_stream in leaf_queue.items():
            # update previous
            prev = d2n_reloc.get(leaf.prev)
            if prev is not None:
                leaf.prev = prev.desc
            # update next
            next = d2n_reloc.get(leaf.next)
            if next is not None:
                leaf.next = next.desc

            # leaf header(perv, next)
            leaf_stream.seek(0)
            leaf_stream.write(self.leaf_struct.pack(leaf.prev, leaf.next))

            # leaf tag
            leaf_stream.seek(0, io.SEEK_END)
            leaf_stream.write(b'\x01')

            # put leaf in store
            desc = self.store.save(leaf_stream.getvalue(), leaf.desc)
            assert leaf.desc == desc

        ## flush nodes
        def node_flush(node):
            # flush children
            for index in range(len(node.children)):
                child_desc = node.children[index]
                child = d2n_reloc.get(child_desc)
                if child is not None:
                    # child has already been flushed
                    node.children[index] = child.desc
                else:
                    child = self.d2n.get(child_desc)
                    if child in node_queue:
                        # flush child and update index
                        node.children[index] = node_flush(child)

            # node
            node_stream = io.BytesIO()
            if self.compress:
                with CompressorStream(node_stream, self.compress) as stream:
                    self.read_keys(stream, node.keys)
                    Serializer(stream).write_struct_list(node.children, self.desc_struct)
            else:
                self.read_keys(node_stream, node.keys)
                Serializer(node_stream).write_struct_list(node.children, self.desc_struct)

            # node tag
            node_stream.write(b'\x00')

            # put node in store
            desc = self.store.save(node_stream.getvalue(), None if node.desc < 0 else node.desc)

            # check if node has been relocated
            if node.desc != desc:
                # queue parent for update
                if node is not self.root_st:
                    parent, key = self.root_st, node.keys[0]
                    while True:
                        parent_desc = parent.children[bisect(parent.keys, key)]
                        if parent_desc == node.desc:
                            break
                        parent = self.d2n[parent_desc]
                    if parent not in self.dirty_set:
                        node_queue.add(parent)

                # update descriptor maps
                self.d2n.pop(node.desc)
                d2n_reloc[node.desc], node.desc = node, desc
                self.d2n[desc] = node

            # remove node from dirty set
            node_queue.discard(node)

            return desc

        while node_queue:
            node_flush(node_queue.pop())

        # clear dirty
        self.dirty_set.clear()
        if prune:
            self.d2n.clear()  # release all nodes except root_st
            self.d2n[self.root_st.desc] = self.root_st

        state = {
            'size': self.size_st,
            'depth': self.depth_st,
            'order': self.order_st,
            'key_type': self.key_type,
            'value_type': self.value_type,
            'compress': self.compress,
            'root': self.root_st.desc
        }
        state_json = json.dumps(state, sort_keys=True).encode()
        crc32 = binascii.crc32(state_json) & 0xffffffff

        header_data = state_json + self.crc32_struct.pack(crc32)
        if self.header() != header_data:
            self.header(header_data)

    def size(self, value=None):
        self.size_st = self.size_st if value is None else value
        return self.size_st

    def depth(self, value=None):
        self.depth_st = self.depth_st if value is None else value
        return self.depth_st

    def order(self):
        return self.order_st

    def root(self, value=None):
        self.root_st = self.root_st if value is None else value
        return self.root_st

    def size_in_store(self):
        """Size occupied on store
        """
        return (functools.reduce(operator.add, (StoreBlock.from_desc(node.desc).size
                for node in self if node.desc > 0), 0))

    def node_to_desc(self, node):
        return node.desc

    def desc_to_node(self, desc):
        if desc:
            return self.d2n.get(desc) or self.node_load(desc)

    def create(self, keys, children, is_leaf):
        desc, self.desc_next = self.desc_next, self.desc_next - 1
        node = (StoreBPTreeLeaf(desc, keys, children) if is_leaf else
                StoreBPTreeNode(desc, keys, children))
        self.d2n[desc] = node
        self.dirty_set.add(node)
        return node

    def dirty(self, node):
        self.dirty_set.add(node)

    def release(self, node):
        self.d2n.pop(node.desc)
        self.dirty_set.discard(node)
        if node.desc >= 0:
            self.store.delete(node.desc)

    def drop(self):
        """Completely delete provider from the store
        """
        self.flush()
        for node in tuple(self):
            self.store.delete(node.desc)
        self.header(b'')
        self.size_st = 0
        self.depth_st = 1
        self.root_st = self.create([], [], True)

    def node_load(self, desc):
        """Load node by its descriptor
        """
        node_data = self.store.load(desc)
        node_tag = node_data[-1:]

        if node_tag != b'\x01':
            node_stream = (io.BytesIO(node_data[:-1]) if not self.compress else
                           io.BytesIO(zlib.decompress(node_data[:-1])))
            node = StoreBPTreeNode(desc,
                                   self.write_keys(node_stream),
                                   Serializer(node_stream).read_struct_list(self.desc_struct))
        else:
            prev, next = self.leaf_struct.unpack(node_data[:self.leaf_struct.size])
            node_stream = (io.BytesIO(node_data[self.leaf_struct.size:-1]) if not self.compress else
                           io.BytesIO(zlib.decompress(node_data[self.leaf_struct.size:-1])))
            node = StoreBPTreeLeaf(desc,
                                   self.write_keys(node_stream),
                                   self.write_vals(node_stream))
            node.prev = prev
            node.next = next

        self.d2n[desc] = node
        return node

    def type_parse(self, type):
        """Parse type

        Returns(type, to_stream, from_steram) for specified type.
        """
        if type == 'bytes':
            return('bytes',
                   lambda stream, items: Serializer(stream).write_bytes_list(items),
                   lambda stream: Serializer(stream).read_bytes_list())

        elif type.startswith('pickle'):
            protocol = int(type.partition(':')[-1] or str(pickle.HIGHEST_PROTOCOL))
            return('pickle:{}'.format(protocol),
                   lambda stream, items: pickle.dump(items, stream, protocol),
                   lambda stream: pickle.load(stream))

        elif type.startswith('struct:'):
            format = type.partition(':')[-1].encode()
            it_struct = struct.Struct(format)
            it_comp = len(format.translate(None, b'<>=!@')) > 1
            return('struct:{}'.format(format.decode()),
                   lambda stream, items: Serializer(stream).write_struct_list(items, it_struct, it_comp),
                   lambda stream: Serializer(stream).read_struct_list(it_struct, it_comp))

        elif type == 'json':
            encode = codecs.getencoder('utf-8')
            decode = codecs.getdecoder('utf-8')
            header = struct.Struct('>Q')
            header_size = header.size

            def json_save(stream, items):
                data = encode(json.dumps(items))[0]
                stream.write(header.pack(len(data)))
                stream.write(data)

            def json_load(stream):
                data_size = header.unpack(stream.read(header_size))[0]
                return json.loads(decode(stream.read(data_size))[0])

            return('json', json_save, json_load)

        raise ValueError('Unknown serializer type: {}'.format(type))


class StoreBPTreeNode(BPTreeNode):
    """Store B+Tree Node
    """
    __slots__ = BPTreeNode.__slots__ + ('desc',)

    def __init__(self, desc, keys, children):
        self.desc = desc
        self.keys = keys
        self.children = children
        self.is_leaf = False


class StoreBPTreeLeaf(BPTreeLeaf):
    """Store B+Tree Leaf
    """
    __slots__ = BPTreeLeaf.__slots__ + ('desc',)

    def __init__(self, desc, keys, children):
        self.desc = desc
        self.keys = keys
        self.children = children
        self.prev = 0
        self.next = 0
        self.is_leaf = True


class CompressorStream(object):
    """Compression stream adapter
    """
    __slots__ = ('stream', 'compressor',)

    def __init__(self, stream, level):
        self.stream = stream
        self.compressor = zlib.compressobj(level)

    def write(self, data):
        return self.stream.write(self.compressor.compress(data))

    def __enter__(self):
        return self

    def __exit__(self, et, oe, tb):
        self.stream.write(self.compressor.flush())
        return False
