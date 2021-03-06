import bson
from mock import patch
from pymongo.errors import OperationFailure

from shardmonster import api, operations
from shardmonster.tests.base import ShardingTestCase

class TestOperations(ShardingTestCase):
    def test_multishard_find(self):
        api.set_shard_at_rest('dummy', 1, 'dest1/test_sharding')
        api.set_shard_at_rest('dummy', 2, 'dest2/test_sharding')
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 2, 'y': 1}
        self.db1.dummy.insert(doc1)
        self.db2.dummy.insert(doc2)

        c = operations.multishard_find('dummy', {'y': 1})
        results = sorted(list(c), key=lambda d: d['x'])
        self.assertEquals([doc1, doc2], results)


    def test_multishard_find_during_migration(self):
        # Indiciate a migration has started on shard #2 and insert a document
        # with the same ID into both databases with slightly different data in
        # each location. Then ensure we only get the result from shard #1
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest1/test_sharding")
        # We require a shard at rest on the target server to ensure the location
        # is picked up as a queryable location
        api.set_shard_at_rest('dummy', 3, "dest2/test_sharding")
        api.start_migration('dummy', 2, "dest2/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc_id = bson.ObjectId()
        doc2_fresh = {'_id': doc_id, 'x': 2, 'y': 1, 'is_fresh': True}
        doc2_stale = {'_id': doc_id, 'x': 2, 'y': 1, 'is_fresh': False}
        self.db1.dummy.insert(doc1)
        self.db1.dummy.insert(doc2_fresh)
        self.db2.dummy.insert(doc2_stale)

        c = operations.multishard_find('dummy', {'y': 1})
        results = sorted(list(c), key=lambda d: d['x'])
        self.assertEquals([doc1, doc2_fresh], results)


    def test_multishard_find_during_post_migration(self):
        # Indiciate a migration has started on shard #2 and insert a document
        # with the same ID into both databases with slightly different data in
        # each location. Then ensure we only get the result from shard #1
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest1/test_sharding")
        api.start_migration('dummy', 2, "dest2/test_sharding")
        api.set_shard_to_migration_status(
            'dummy', 2, api.ShardStatus.POST_MIGRATION_PAUSED_AT_DESTINATION)
        doc1 = {'x': 1, 'y': 1}
        doc_id = bson.ObjectId()
        doc2_fresh = {'_id': doc_id, 'x': 2, 'y': 1, 'is_fresh': True}
        doc2_stale = {'_id': doc_id, 'x': 2, 'y': 1, 'is_fresh': False}
        self.db1.dummy.insert(doc1)
        self.db1.dummy.insert(doc2_fresh)
        self.db2.dummy.insert(doc2_stale)

        c = operations.multishard_find('dummy', {'y': 1})
        results = sorted(list(c), key=lambda d: d['x'])
        self.assertEquals([doc1, doc2_stale], results)
    

    def test_multishard_find_with_sort(self):
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest2/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 1, 'y': 2}
        doc3 = {'x': 2, 'y': 1}
        doc4 = {'x': 2, 'y': 2}
        self.db1.dummy.insert(doc1)
        self.db1.dummy.insert(doc2)
        self.db2.dummy.insert(doc3)
        self.db2.dummy.insert(doc4)

        results = operations.multishard_find(
            'dummy', {}, sort=[('x', 1), ('y', 1)])
        self.assertEquals([doc1, doc2, doc3, doc4], list(results))

        results = operations.multishard_find(
            'dummy', {}, sort=[('x', -1), ('y', 1)])
        self.assertEquals([doc3, doc4, doc1, doc2], list(results))

        results = operations.multishard_find(
            'dummy', {}, sort=[('x', 1), ('y', -1)])
        self.assertEquals([doc2, doc1, doc4, doc3], list(results))

        results = operations.multishard_find(
            'dummy', {}, sort=[('x', -1), ('y', -1)])
        self.assertEquals([doc4, doc3, doc2, doc1], list(results))
    
        # Insert a document the same as doc4 to ensure sorts will cope with
        # things that are basically the same
        doc5 = {'x': 2, 'y': 2, 'z': 1}
        self.db2.dummy.insert(doc5)
        results = operations.multishard_find(
            'dummy', {}, sort=[('x', -1), ('y', -1)])
        results = results[:2]
        self.assertTrue(doc4 in results)
        self.assertTrue(doc5 in results)
    

    def test_multishard_find_with_sort_fn(self):
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest2/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 1, 'y': 2}
        doc3 = {'x': 2, 'y': 1}
        doc4 = {'x': 2, 'y': 2}
        self.db1.dummy.insert(doc1)
        self.db1.dummy.insert(doc2)
        self.db2.dummy.insert(doc3)
        self.db2.dummy.insert(doc4)

        results = operations.multishard_find(
            'dummy', {}).sort([('x', 1), ('y', 1)])
        self.assertEquals([doc1, doc2, doc3, doc4], list(results))

        results = operations.multishard_find(
            'dummy', {}).sort([('x', -1), ('y', 1)])
        self.assertEquals([doc3, doc4, doc1, doc2], list(results))


    def test_multishard_find_with_sort_and_limit(self):
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest2/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 1, 'y': 2}
        doc3 = {'x': 2, 'y': 1}
        doc4 = {'x': 2, 'y': 2}
        self.db1.dummy.insert(doc1)
        self.db1.dummy.insert(doc2)
        self.db2.dummy.insert(doc3)
        self.db2.dummy.insert(doc4)

        results = operations.multishard_find(
            'dummy', {}, sort=[('x', 1), ('y', 1)], limit=3)
        self.assertEquals([doc1, doc2, doc3], list(results))
    

    def test_multishard_find_with_limit(self):
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest2/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 1, 'y': 2}
        doc3 = {'x': 2, 'y': 1}
        doc4 = {'x': 2, 'y': 2}
        self.db1.dummy.insert(doc1)
        self.db1.dummy.insert(doc2)
        self.db2.dummy.insert(doc3)
        self.db2.dummy.insert(doc4)

        results = operations.multishard_find('dummy', {}, limit=3)
        self.assertEquals(3, len(list(results)))

    
    def test_multishard_find_with_limit_as_method(self):
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest2/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 1, 'y': 2}
        doc3 = {'x': 2, 'y': 1}
        doc4 = {'x': 2, 'y': 2}
        self.db1.dummy.insert(doc1)
        self.db1.dummy.insert(doc2)
        self.db2.dummy.insert(doc3)
        self.db2.dummy.insert(doc4)

        results = operations.multishard_find('dummy', {}).limit(3)
        self.assertEquals(3, len(list(results)))


    def test_multishard_find_with_shardkey_present(self):
        # Create an unlikely scenario where data is present in both locations
        # even though the data is "at rest". Then do a query with the shard
        # key present. As the shard key is present the query should be
        # targetted enough to ignore the dummy data
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest2/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc2_bad = {'x': 2, 'y': 1, 'bad': True}
        doc2_good = {'x': 2, 'y': 1, 'bad': False}
        self.db1.dummy.insert(doc1)
        self.db1.dummy.insert(doc2_bad)
        self.db2.dummy.insert(doc2_good)

        results = operations.multishard_find('dummy', {'x': 2, 'y': 1})
        self.assertEquals([doc2_good], list(results))

    def test_insert(self):
        # Perform an insert with shards set to specific locations.
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest2/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 2, 'y': 1}
        operations.multishard_insert('dummy', doc1)
        operations.multishard_insert('dummy', doc2)

        results = list(self.db1.dummy.find({'y': 1}))
        self.assertEquals([doc1], results)

        results = list(self.db2.dummy.find({'y': 1}))
        self.assertEquals([doc2], results)


    def test_update(self):
        # Put the same document in multiple locations (a mid-migration status)
        # then do an update and ensure that only the correct place has been
        # updated.
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        self.db1.dummy.insert(doc1)

        api.start_migration('dummy', 1, 'dest2/test_sharding')
        api.set_shard_to_migration_status(
            'dummy', 1, api.ShardStatus.MIGRATING_COPY)
        self.db2.dummy.insert(doc1)

        result = operations.multishard_update('dummy', {}, {'$inc': {'y': 1}})
        self.assertEquals(1, result['n'])

        # Query the correct shard first and see that the counter has been
        # incremented
        result, = operations.multishard_find('dummy', {'x': 1})
        self.assertEquals(2, result['y'])

        # Now spoof the metadata such that the system thinks the data is on
        # shard2. The counter should still be 1 here.
        api.set_shard_at_rest('dummy', 1, "dest2/test_sharding")
        result, = operations.multishard_find('dummy', {'x': 1})
        self.assertEquals(1, result['y'])


    def test_multi_update(self):
        # Test that an update will hit multiple clusters at once
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest2/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 2, 'y': 1}
        self.db1.dummy.insert(doc1)
        self.db2.dummy.insert(doc2)

        result = operations.multishard_update('dummy', {}, {'$inc': {'y': 1}})
        self.assertEquals(2, result['n'])

        result, = operations.multishard_find('dummy', {'x': 1})
        self.assertEquals(2, result['y'])

        result, = operations.multishard_find('dummy', {'x': 2})
        self.assertEquals(2, result['y'])


    def test_multishard_count_with_motion(self):
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest1/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 1, 'y': 2}
        doc3 = {'x': 2, 'y': 1}
        doc4 = {'x': 2, 'y': 2}
        self.db1.dummy.insert(doc1)
        self.db1.dummy.insert(doc2)
        self.db1.dummy.insert(doc3)
        self.db1.dummy.insert(doc4)

        results = operations.multishard_find('dummy', {}).count()
        self.assertEquals(4, results)

        # Mimic the shard now being in the second location and there being
        # documents left here
        api.start_migration('dummy', 2, "dest2/test_sharding")
        api.set_shard_to_migration_status(
            'dummy', 2, api.ShardStatus.POST_MIGRATION_PAUSED_AT_DESTINATION)

        self.db2.dummy.insert(doc3)
        self.db2.dummy.insert(doc4)
    
        results = operations.multishard_find('dummy', {}).count()
        self.assertEquals(4, results)


    def test_remove(self):
        # Perform removes with shards set to specific locations.
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest2/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 2, 'y': 1}
        self.db1.dummy.insert(doc1)
        self.db1.dummy.insert(doc2)
        self.db2.dummy.insert(doc1)
        self.db2.dummy.insert(doc2)

        operations.multishard_remove('dummy', {'x': 1, 'y': 1})

        self.assertEquals(0, self.db1.dummy.find({'x': 1}).count())
        self.assertEquals(1, self.db2.dummy.find({'x': 1}).count())


    def test_multi_remove(self):
        # Tests remove across multiple clusters
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest2/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 2, 'y': 1}
        self.db1.dummy.insert(doc1)
        self.db2.dummy.insert(doc2)

        operations.multishard_remove('dummy', {'y': 1})

        self.assertEquals(0, self.db1.dummy.find({}).count())
        self.assertEquals(0, self.db2.dummy.find({}).count())


    def test_aggregate(self):
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest2/test_sharding")

        for y in range(10):
            doc1 = {'x': 1, 'y': y}
            doc2 = {'x': 2, 'y': y}
            self.db1.dummy.insert(doc1)
            self.db2.dummy.insert(doc2)

        pipeline = [
            {'$match': {'x': 2}},
            {'$group': {'_id': 'total', 's': {'$sum': '$y'}}},
        ]
        result = operations.multishard_aggregate('dummy', pipeline)['result']
        self.assertEquals([{'_id': 'total', 's': 45}], result)


    @patch('shardmonster.operations._should_pause_write')
    @patch('shardmonster.operations.time.sleep')
    def test_wait_for_pause_to_end(self, mock_sleep, mock_should_pause):
        mock_should_pause.side_effect = [True, True, False]

        operations._wait_for_pause_to_end("collection", {'field': 1})

        mock_should_pause.assert_called_with("collection", {'field': 1})
        self.assertEquals(3, mock_should_pause.call_count)
        self.assertEquals(2, mock_sleep.call_count)


    def test_should_pause_write(self):
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_to_migration_status(
            'dummy', 1, api.ShardStatus.POST_MIGRATION_PAUSED_AT_DESTINATION)
        self.assertTrue(operations._should_pause_write("dummy", {'x': 1}))


    def test_multishard_rewind(self):
        api.set_shard_at_rest('dummy', 1, 'dest1/test_sharding')
        api.set_shard_at_rest('dummy', 2, 'dest2/test_sharding')
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 2, 'y': 1}
        self.db1.dummy.insert(doc1)
        self.db2.dummy.insert(doc2)

        cursor = operations.multishard_find('dummy', {'y': 1}, sort=[('x', 1)])
        found = cursor.next()
        self.assertEquals((1, 1), (found['x'], found['y']))
        cursor.rewind()
        found = cursor.next()
        self.assertEquals((1, 1), (found['x'], found['y']))

    def test_save(self):
        # A save differs from an insert in that it may perform an insert or it
        # may perform an update, depending on whether an _id exists
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.set_shard_at_rest('dummy', 2, "dest2/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 2, 'y': 1}
        operations.multishard_save('dummy', doc1)
        operations.multishard_save('dummy', doc2)

        doc1['z'] = 10
        doc2['z'] = 20
        operations.multishard_save('dummy', doc1)
        operations.multishard_save('dummy', doc2)
    
        results = list(self.db1.dummy.find({'y': 1}))
        self.assertEquals([doc1], results)

        results = list(self.db2.dummy.find({'y': 1}))

        self.assertEquals([doc2], results)


    def test_hint(self):
        # The easier way to test if a hint is being applied is to apply a bad
        # hint and watch things blow up
        api.set_shard_at_rest('dummy', 1, 'dest1/test_sharding')
        api.set_shard_at_rest('dummy', 2, 'dest2/test_sharding')
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 2, 'y': 1}
        self.db1.dummy.insert(doc1)
        self.db2.dummy.insert(doc2)

        # This should explode due to a lack of index
        try:
            c = operations.multishard_find('dummy', {'x': 1})
            c = c.hint([('apples', 1)])
            list(c)
        except OperationFailure as e:
            self.assertTrue("bad hint" in str(e))


    def test_indexed_read(self):
        api.set_shard_at_rest('dummy', 1, 'dest1/test_sharding')
        api.set_shard_at_rest('dummy', 2, 'dest2/test_sharding')
        doc1 = {'x': 1, 'y': 1}
        doc2 = {'x': 2, 'y': 1}
        self.db1.dummy.insert(doc1)
        self.db2.dummy.insert(doc2)

        cursor = operations.multishard_find(
            'dummy', {'y': 1}, sort=[('x', 1), ('y', 1)])
        self.assertEquals(doc1, cursor[0])
        cursor = operations.multishard_find(
            'dummy', {'y': 1}, sort=[('x', -1), ('y', 1)])
        self.assertEquals(doc2, cursor[0])
