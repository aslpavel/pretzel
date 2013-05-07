"""Connection mesh

Create ssh connection tree and work with same way as with single
ssh connection.

Example:
    conns = yield MeshConnection(['localhost'] * 9, 2)
    pids = list((yield conns(os.getpid)())))
    print(pids)  # [3269, 3277, 3285, 3270, 3278, 3290, 3271, 3276, 3282]
"""
import math
import random
from .ssh import SSHConnection
from ...monad import List, Proxy, async, async_all, do_return

__all__ = ('MeshConnection',)


@async
def MeshConnection(hosts, factor, **conn_opts):
    """Create ssh connection tree from list of hosts.
    """
    @async
    def connect(host, conn):
        if host is None:
            do_return(None)  # to level connection
        if conn is None:
            conn = yield SSHConnection(host, **conn_opts)
            conn = yield conn(conn)  # convert to proxy object (guarantees semantic)
        else:
            conn = yield ~conn(SSHConnection)(host, **conn_opts)
        do_return(conn)
    tree = Tree.from_list(hosts, factor)
    conns = yield tree(connect, None)
    do_return(ContList(conns[1:]))  # strip None from beginning


class ContList(Proxy):
    """List of continuation monads

    Behaves as proxy on list monad but when used as monad assumes that
    it contains list of continuation which will be executed simultaneously when
    executed.
    """
    __slots__ = Proxy.__slots__

    def __init__(self, items):
        Proxy.__init__(self, List(*items))

    def __monad__(self):
        return (async_all(Proxy.__monad__(self)).map_val
                         (lambda res: res.map_val(ContList)))

    def __iter__(self):
        """Iterate over containing items.
        """
        return iter(Proxy.__monad__(self))


class Tree(object):
    """Helper three structure
    """
    __slots__ = ('value', 'children',)

    def __init__(self, value, children):
        self.value = value
        self.children = children

    @classmethod
    def from_list(cls, items, factor, root=None):
        """Build tree

        Creates tree of items with factor children.
        """
        def build(vals):
            val, vals = vals[0], vals[1:]
            bucket = int(math.ceil(len(vals)/float(factor)))
            return cls(val, tuple([build(vals[factor*i:factor*(i + 1)])
                                  for i in range(bucket)]))
        items = list(items)
        random.shuffle(items)
        return build([root] + items)

    @async
    def __call__(self, func, val):
        """Apply asynchronous function and collect results

        Returns list of results of functions application on each node.
        """
        v = yield func(self.value, val)
        if self.children:
            css = yield async_all(child(func, v) for child in self.children)
            do_return([v] + [c for cs in css for c in cs])
        else:
            do_return([v])

    def __str__(self):
        return '{{{}: {}}}'.format(self.value, list(self.children))

    def __repr__(self):
        return str(self)
