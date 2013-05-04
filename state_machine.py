import array

__all__ = ('StateMachine',)


class StateMachine(object):
    """Graph state machine
    """
    __slots__ = ('graph', 'state', 'names',)

    def __init__(self, graph, names=None):
        self.graph = graph
        self.names = names
        self.state = 0

    def __call__(self, state):
        if self.graph[self.state] & (1 << state):
            if self.state == state:
                return False
            self.state = state
            return True
        else:
            raise ValueError('invalid state transition {} -> {}'.
                             format(self.state_name(), self.state_name(state)))

    def reset(self):
        self.state = 0

    def state_name(self, state=None):
        state = self.state if state is None else state
        if self.names:
            return self.names[state]
        else:
            return str(state)

    def __str__(self):
        return '{}(state:{})'.format(type(self).__name__, self.state_name())

    def __repr__(self):
        return str(self)

    @classmethod
    def compile_graph(cls, graph_tree):
        """Create transition graph from dictionary representation

        Dictionary with state as key and available transition states as its
        value. State must be and integer. Initial state is 0.
        """
        max_state = 0
        graph = {}
        for src, dsts in graph_tree.items():
            max_state = max(max_state, src)
            for dst in dsts:
                max_state = max(max_state, dst)
                graph[src] = graph.get(src, 0) | 1 << dst

        if max_state >= 63:
            return list(graph.get(src, 0) for src in range(max_state + 1))
        else:
            return array.array('B' if max_state <= 7 else
                               'H' if max_state <= 15 else
                               'I' if max_state <= 31 else 'Q',
                               (graph.get(src, 0) for src in range(max_state + 1)))
