from shardmonster import api, sharder
from shardmonster.tests.base import ShardingTestCase

class TestSharder(ShardingTestCase):
    def setUp(self):
        api.activate_caching(0.5)
        super(TestSharder, self).setUp()


    def tearDown(self):
        # Deactivate caching by setting a 0 timeout
        api.activate_caching(0)
        super(TestSharder, self).tearDown()


    def test_basic_copy(self):
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        doc1 = {'x': 1, 'y': 1}
        doc1['_id'] = self.db1.dummy.insert(doc1)

        api.start_migration('dummy', 1, "dest2/test_sharding")

        sharder._do_copy('dummy', 1)

        # The data should now be on the second database
        doc2, = self.db2.dummy.find({})
        self.assertEquals(doc1, doc2)


    def test_sync_after_copy(self):
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.start_migration('dummy', 1, "dest2/test_sharding")

        # Mimic the state the shard would be in after a document was copied
        # from one location to another
        doc1 = {'x': 1, 'y': 1}
        doc1['_id'] = self.db1.dummy.insert(doc1)
        self.db2.dummy.insert(doc1)

        # Get the initial oplog position, do an update and then sync from the
        # initial position
        initial_oplog_pos = sharder._get_oplog_pos()
        self.db1.dummy.update({'x': 1}, {'$inc': {'y': 1}})
        api.set_shard_to_migration_status(
            'dummy', 1, api.ShardStatus.MIGRATING_SYNC)
        sharder._sync_from_oplog('dummy', 1, initial_oplog_pos)

        # The data on the second database should now reflect the update that
        # went through
        doc2, = self.db2.dummy.find({})
        self.assertEquals(2, doc2['y'])


    def test_delete_after_migration(self):
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.start_migration('dummy', 1, "dest2/test_sharding")

        # Mimic the state the shard would be in after a document was copied
        # from one location to another
        doc1 = {'x': 1, 'y': 1}
        doc1['_id'] = self.db1.dummy.insert(doc1)
        self.db2.dummy.insert(doc1)

        api.set_shard_to_migration_status(
            'dummy', 1, api.ShardStatus.POST_MIGRATION_DELETE)
        sharder._delete_source_data('dummy', 1)

        # The data on the first database should now be gone and the data
        # on the second database should be ok.
        self.assertEquals(0, self.db1.dummy.find({}).count())
        doc1_actual, = self.db2.dummy.find({})
        self.assertEquals(doc1, doc1_actual)


    def test_sync_ignores_other_collection(self):
        api.set_shard_at_rest('dummy', 1, "dest1/test_sharding")
        api.start_migration('dummy', 1, "dest2/test_sharding")

        # Mimic the state the shard would be in after a document was copied
        # from one location to another
        doc1 = {'x': 1, 'y': 1}
        doc1['_id'] = self.db1.dummy.insert(doc1)
        self.db2.dummy.insert(doc1)

        # Get the initial oplog position, do an update to a different collection
        # and then sync from the initial position
        initial_oplog_pos = sharder._get_oplog_pos()
        self.db1.other_coll.insert(doc1)
        self.db1.other_coll.update({'x': 1}, {'$inc': {'y': 1}})
        api.set_shard_to_migration_status(
            'dummy', 1, api.ShardStatus.MIGRATING_SYNC)
        sharder._sync_from_oplog('dummy', 1, initial_oplog_pos)

        # The data on the second database should be in the same state as it
        # was before
        doc2, = self.db2.dummy.find({})
        self.assertEquals(1, doc2['y'])
