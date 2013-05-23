'''Connection mesh

Create composed ssh connection and work with it the same way as with single
ssh connection.

Example:
    conns = yield CompositeConnection([\'localhost\'] * 9, mesh=\'tree:3\')
    pids = list((yield conns(os.getpid)())))
    print(pids)  # [3269, 3277, 3285, 3270, 3278, 3290, 3271, 3276, 3282]
'''
import math
import random
from .ssh import SSHConnection
from ...monad import List, Proxy, async, async_all, do_return

__all__ = ('CompositeConnection',)


@async
def CompositeConnection(hosts, mesh='flat', **conn_opts):
    """Create composed ssh connection from list of hosts.

    hosts -- list of hosts
    mesh  -- for of connection mesh. Available option 'flat' - direct
             connections, 'tree:factor' - mesh has a form of tree with factor
             children.
    """
    if mesh == 'flat':
        do_return((yield ContList(SSHConnection(host, **conn_opts) for host in hosts)))

    elif mesh.startswith('tree:'):
        tree = Tree.from_list(hosts, int(mesh[len('tree:'):]))

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
            if vals:
                bucket = int(math.ceil(len(vals)/float(factor)))
                return cls(val, tuple(build(vals[bucket*i:bucket*(i+1)])
                           for i in range(factor) if bucket * i < len(vals)))
            else:
                return cls(val, tuple())
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