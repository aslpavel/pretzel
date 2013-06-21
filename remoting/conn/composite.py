"""Connection mesh

Create composite connection and work with it the same way as with single
connection.
"""
import math
import random
import functools
from .fork import ForkConnection
from .ssh import SSHConnection
from ...monad import List, Proxy, async, async_all, do_return

__all__ = ('composite_conn', 'composite_ssh_conn', 'composite_fork_conn',)


@async
def composite_conn(conn_facts, mesh=None):
    """Create composite connection from list of connection factories.

    Arguments:
        conn_facts: List of connection factories. Keep in mind that this factories
                    must be pickle-able in case of non flat mesh (you can use
                    functools.partial to keep connection type pickle-able)
        mesh: Mesh of composite connection. Available options are
             'flat' - direct connections (is default)
             'tree:factor' - mesh has a form of tree with factor children.
    Returns:
        Continuation list of connections
    """
    mesh = mesh or 'flat'
    conn_facts = tuple(conn_facts)

    if mesh == 'flat':
        conns = yield ContList(conn_facts)()
        do_return((yield ContList(conn(conn) for conn in conns)))  # to proxy

    elif mesh.startswith('tree:'):
        tree_factor = int(mesh.partition(':')[2])
        if tree_factor < 1:
            raise ValueError('tree factor must be positive')
        tree = Tree.from_list(conn_facts, tree_factor)

        @async
        def connect(conn_fact, parent):
            if conn_fact is None:
                do_return(None)
            if parent is None:
                conn = yield conn_fact()
                conn = yield conn(conn)  # to proxy
            else:
                conn = yield ~parent(conn_fact)()
            do_return(conn)
        conns = yield tree(connect, None)

        do_return(ContList(conns[1:]))  # strip None from beginning


def composite_ssh_conn(hosts, mesh=None, **conn_opts):
    """Create composite ssh connection from list of hosts

    Arguments:
        hosts: List of hosts
        mesh: Mesh of composite connection (see composite_conn)
        **conn_opts: Common connection options
    """
    if isinstance(hosts, str):
        hosts = (hosts,)
    conn_facts = (functools.partial(SSHConnection, host, **conn_opts)
                  for host in hosts)
    return composite_conn(conn_facts, mesh=mesh)


def composite_fork_conn(count, mesh=None, **conn_opts):
    """Create `count` composite fork connection

    Arguments:
        count: Number of fork connections
        mesh: Mesh of composite connection (see composite_conn)
        **conn_opts: Common connection options
    """
    conn_facts = (functools.partial(ForkConnection, **conn_opts),) * count
    return composite_conn(conn_facts, mesh=mesh)


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
                bucket = int(math.ceil(len(vals) / float(factor)))
                return cls(val, tuple(build(vals[bucket * i:bucket * (i + 1)])
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
