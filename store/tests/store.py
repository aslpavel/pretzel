import io
import random
import unittest
from ..store import StreamStore

__all__ = ('StoreTest',)


class StoreTest(unittest.TestCase):
    """Store unit tests
    """
    def test_simple(self):
        """Simple tests
        """
        stream = io.BytesIO()
        with StreamStore(stream, 1) as store:
            # empty
            self.assertEqual(store.save(b''), 0)
            self.assertEqual(store.load(0), b'')

            # unnamed
            desc_data = b'some test data'
            desc = store.save(desc_data)
            self.assertEqual(store.load(desc), desc_data)

            # named
            name, name_data = b'name', b'some test value'
            store[name] = name_data
            self.assertEqual(store[name], name_data)

        with StreamStore(stream, 1) as store:
            self.assertEqual(store.load(desc), desc_data)
            self.assertEqual(store[name], name_data)

    def test_stress(self):
        """Stress tests
        """
        count = 1 << 14
        datas = [str(random.randint(0, count)).encode() * random.randint(1, 16)
                 for _ in range(count)]

        stream = io.BytesIO()
        descs = []

        with StreamStore(stream) as store:
            for data in datas:
                descs.append(store.save(data))

        with StreamStore(stream) as store:
            for data, desc in zip(datas, descs):
                self.assertEqual(data, store.load(desc))

            # delete half
            for desc in descs[int(count / 2):]:
                store.delete(desc)

            datas = datas[:int(count / 2)]
            descs = descs[:int(count / 2)]

        with StreamStore(stream) as store:
            for data, desc in zip(datas, descs):
                self.assertEqual(data, store.load(desc))

            # create
            for _ in range(count):
                data = str(random.randint(0, count)).encode() * random.randint(1, 16)
                datas.append(data)
                descs.append(store.save(data))

        with StreamStore(stream) as store:
            for data, desc in zip(datas, descs):
                self.assertEqual(data, store.load(desc))
