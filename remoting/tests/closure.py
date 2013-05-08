import pickle
import unittest
from ..closure import Closure

GLOBAL = 'test value'


class ClsoureTest(unittest.TestCase):
    def test(self):
        reload = lambda val: pickle.loads(pickle.dumps(val))

        # reference noting
        self.assertEqual(reload(Closure(lambda val: val))('id'), 'id')

        # reference global
        self.assertEqual(reload(Closure(lambda: GLOBAL))(), GLOBAL)

        # reference closure
        cl = reload(Closure((lambda a: lambda b: a + b)('closure')))
        self.assertEqual(cl(':arg'), 'closure:arg')
