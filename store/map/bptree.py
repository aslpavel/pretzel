"""B+Tree implementation
"""
import sys
from bisect import bisect, bisect_left
from operator import itemgetter
from collections import MutableMapping
if sys.version_info[0] < 3:
    from itertools import imap as map

__all__ = ('BPTree', 'BPTreeNode', 'BPTreeLeaf',)


class Nothing(object):
    def __str__(self):
        return 'Nothing'

    def __repr__(self):
        return str(self)

nothing = Nothing()


class BPTree(MutableMapping):
    """B+Tree
    """
    def __init__(self, provider):
        self.provider = provider

    def __get(self, key, value=nothing):
        """Get value associated with key

        Returns value associated with key if any, otherwise value argument if
        it is set, else raises KeyValue exception.
        """

        desc_to_node = self.provider.desc_to_node

        # find leaf
        node = self.provider.root()
        for _ in range(self.provider.depth() - 1):
            node = desc_to_node(node.children[bisect(node.keys, key)])

        # find key
        index = bisect_left(node.keys, key)
        if index >= len(node.keys) or key != node.keys[index]:
            if value is self.nothing:
                raise KeyError(key)
            return value

        return node.children[index]

    def __get_range(self, low_key=None, high_key=None):
        """Get range of key-value pairs

        Returns iterator of key-value pairs for keys in[low_key .. high_key]
        """
        # validate range
        if low_key is not None and high_key is not None and low_key >= high_key:
            return

        # find first leaf
        desc_to_node = self.provider.desc_to_node
        node = self.provider.root()
        if low_key is not None:
            for depth in range(self.provider.depth() - 1):
                node = desc_to_node(node.children[bisect(node.keys, low_key)])
            index = bisect_left(node.keys, low_key)
            if index >= len(node.keys):
                next = desc_to_node(node.next)
                if next is None:
                    return
                node, index = next, 0
        else:
            for depth in range(self.provider.depth() - 1):
                node = desc_to_node(node.children[0])
            index = 0

        # iterate over whole leafs
        while not high_key or node.keys[-1] < high_key:
            for index in range(index, len(node.keys)):
                yield node.keys[index], node.children[index]
            node = desc_to_node(node.next)
            if node is None:
                return
            index = 0

        # iterate over last leaf
        for index in range(index, len(node.keys)):
            key, value = node.keys[index], node.children[index]
            if key > high_key:
                return
            yield key, value

    def __set(self, key, value):
        """Associate key with value

        If key has already been, replace it with new value.
        """

        order = self.provider.order()
        dirty = self.provider.dirty
        desc_to_node = self.provider.desc_to_node
        node_to_desc = self.provider.node_to_desc

        # find path
        node, path = self.provider.root(), []
        for depth in range(self.provider.depth() - 1):
            index = bisect(node.keys, key)
            path.append((index, index + 1, node))
            node = desc_to_node(node.children[index])

        # check if value is updated
        index = bisect_left(node.keys, key)
        if index < len(node.keys) and key == node.keys[index]:
            node.children[index] = value
            dirty(node)
            return
        path.append((index, index, node))

        # size += 1
        self.provider.size(self.provider.size() + 1)

        # update tree
        sibling = None
        while path:
            key_index, child_index, node = path.pop()

            # add new key
            node.keys.insert(key_index, key)
            node.children.insert(child_index, value)
            dirty(node)

            if len(node.keys) < order:
                return

            # node is full so we need to split it
            center = len(node.children) >> 1
            keys, node.keys = node.keys[center:], node.keys[:center]
            children, node.children = node.children[center:], node.children[:center]

            if node.is_leaf:
                # create right sibling
                sibling = self.provider.create(keys, children, True)

                # keep leafs linked
                sibling_desc, node_next_desc = node_to_desc(sibling), node.next
                node.next, sibling.prev = sibling_desc, node_to_desc(node)
                node_next = desc_to_node(node_next_desc)
                if node_next:
                    node_next.prev, sibling.next = sibling_desc, node_next_desc
                    dirty(node_next)

                # update key
                key, value = sibling.keys[0], sibling_desc

            else:
                # create right sibling
                sibling = self.provider.create(keys, children, False)

                # update key
                key, value = node.keys.pop(), node_to_desc(sibling)

            dirty(sibling)

        # create new root
        self.provider.depth(self.provider.depth() + 1)  # depth += 1
        self.provider.root(self.provider.create(
                           [key],
                           [node_to_desc(self.provider.root()), node_to_desc(sibling)],
                           False))

    def __pop(self, key, value=nothing):
        """Pop value associated with key

        Remove value associated with key if any. Returns this value or value
        argument if it is set, else raises KeyValue exception.
        """

        half_order = self.provider.order() >> 1
        dirty = self.provider.dirty
        desc_to_node = self.provider.desc_to_node

        # find path
        node, path = self.provider.root(), []
        for depth in range(self.provider.depth() - 1):
            index = bisect(node.keys, key)
            parent, node = node, desc_to_node(node.children[index])
            path.append((node, index, parent))

        # check if key exists
        index = bisect_left(node.keys, key)
        if index >= len(node.keys) or key != node.keys[index]:
            if value is self.nothing:
                raise KeyError(key)
            return value
        value = node.children[index]
        key_index, child_index = index, index

        # size -= 1
        self.provider.size(self.provider.size() - 1)

        # update tree
        while path:
            node, node_index, parent = path.pop()

            # remove scheduled(key | child)
            del node.keys[key_index]
            del node.children[child_index]

            if len(node.keys) >= half_order:
                dirty(node)
                return value

            ## redistribute
            left, right = None, None
            if node_index > 0:
                # has left sibling
                left = desc_to_node(parent.children[node_index - 1])
                if len(left.keys) > half_order:  # borrow from left sibling
                    # copy correct key to node
                    node.keys.insert(0, left.keys[-1] if node.is_leaf
                                     else parent.keys[node_index - 1])
                    # move left key to parent
                    parent.keys[node_index - 1] = left.keys.pop()
                    # move left child to node
                    node.children.insert(0, left.children.pop())

                    dirty(node), dirty(left), dirty(parent)
                    return value

            if node_index < len(parent.keys):
                # has right sibling
                right = desc_to_node(parent.children[node_index + 1])
                if len(right.keys) > half_order:  # borrow from right sibling
                    if node.is_leaf:
                        # move right key to node
                        node.keys.append(right.keys.pop(0))
                        # copy next right key to parent
                        parent.keys[node_index] = right.keys[0]
                    else:
                        # copy correct key to node
                        node.keys.append(parent.keys[node_index])
                        # move right key to parent
                        parent.keys[node_index] = right.keys.pop(0)
                    # move right child to node
                    node.children.append(right.children.pop(0))

                    dirty(node), dirty(right), dirty(parent)
                    return value

            ## merge
            src, dst, child_index = ((node, left, node_index) if left
                                     else(right, node, node_index + 1))

            if node.is_leaf:
                # keep leafs linked
                dst.next = src.next
                src_next = desc_to_node(src.next)
                if src_next is not None:
                    src_next.prev = src.prev
                    dirty(src_next)
            else:
                # copy parents key
                dst.keys.append(parent.keys[child_index - 1])

            # copy node's(keys | children)
            dst.keys.extend(src.keys)
            dst.children.extend(src.children)

            # mark nodes
            self.provider.release(src)
            dirty(dst)

            # update key index
            key_index = child_index - 1

        ## update root
        root = self.provider.root()
        del root.keys[key_index]
        del root.children[child_index]

        if not root.keys:
            depth = self.provider.depth()
            if depth > 1:
                # root is not leaf because depth > 1
                self.provider.root(desc_to_node(*root.children))
                self.provider.release(root)
                self.provider.depth(depth - 1)  # depth -= 1
        else:
            dirty(root)

        return value

    def __len__(self):
        return self.provider.size()

    def __getitem__(self, key):
        if isinstance(key, slice):
            return self.__get_range(low_key=key.start, high_key=key.stop)
        return self.__get(key)

    def __setitem__(self, key, value):
        return self.__set(key, value)

    def __delitem__(self, key):
        return self.__pop(key)

    def __iter__(self):
        return map(itemgetter(0), self.__get_range())

    def __contains__(self, key):
        return self.__get(key, None) is not None

    def get(self, key, default=None):
        return self.__get(key, default)

    def pop(self, key, default=None):
        return self.__pop(key, default)

    def items(self):
        return self.__get_range()

    def values(self):
        return map(itemgetter(1), self.__get_range())


class BPTreeNode(object):
    """B+Tree Node
    """
    __slots__ = ('keys', 'children', 'is_leaf')

    def __init__(self, keys, children):
        self.keys = keys
        self.children = children
        self.is_leaf = False

    def __str__(self):
        return 'Node(keys:{}, children:{})'.format(self.keys, self.children)

    def __repr__(self):
        return str(self)


class BPTreeLeaf(BPTreeNode):
    """B+Tree Node
    """
    __slots__ = ('keys', 'children', 'prev', 'next', 'is_leaf')

    def __init__(self, keys, children):
        self.keys = keys
        self.children = children
        self.prev = None
        self.next = None
        self.is_leaf = True

    def __str__(self):
        return ('Leaf(prev:{}, next:{}, keys:{}, children:{})'
                .format(self.prev, self.next, self.keys, self.children))
