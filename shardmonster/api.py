from shardmonster.connection import (
    add_cluster, connect_to_controller, _get_cluster_coll)
from shardmonster.metadata import (
    _get_realm_coll, _get_shards_coll, ShardStatus, activate_caching,
    get_caching_duration)
from shardmonster import operations

__all__ = [
    "activate_caching", "connect_to_controller", "get_caching_duration",
    "add_cluster", "set_shard_at_rest"]

_collection_cache = {}


def create_indices():
    realm_coll = _get_realm_coll()
    realm_coll.ensure_index([('name', 1)], unique=True)
    realm_coll.ensure_index([('collection', 1)], unique=True)

    shards_coll = _get_shards_coll()
    shards_coll.ensure_index(
        [('realm', 1), ('shard_key', 1)], unique=True)

    cluster_coll = _get_cluster_coll()
    cluster_coll.ensure_index([('name', 1)], unique=True)


def create_realm(realm, shard_field, collection_name, default_dest):
    _get_realm_coll().insert({
        'name': realm,
        'shard_field': shard_field,
        'collection': collection_name,
        'default_dest': default_dest})


def ensure_realm_exists(name, shard_field, collection_name, default_dest):
    """Ensures that a realm of the given name exists and matches the expected
    settings.

    :param str name: The name of the realm
    :param shard_field: The field in documents that should be used as the shard
        field. The only supported values that can go in this field are strings
        and integers.
    :param str collection_name: The name of the collection that this realm
        corresponds to. In general, the collection name should match the realm
        name.
    :param str default_dest: The default destination for any data that isn't
        explicitly sharded to a specific location.
    :return: None
    """
    coll = _get_realm_coll()

    cursor = coll.find({'name': name})
    if cursor.count():
        # realm with this name already exists
        existing = cursor[0]
        if (existing['shard_field'] != shard_field
            or existing['collection'] != collection_name
            or existing['default_dest'] != default_dest):
            raise Exception('Cannot change realm')
        else:
            return
        
    cursor = coll.find({'collection': collection_name})
    if cursor.count():
        # realm for this collection already exists
        existing = cursor[0]
        if (existing['shard_field'] != shard_field
            or existing['name'] != name
            or existing['default_dest'] != default_dest):
            raise Exception(
                'Realm for collection %s already exists' % collection_name)
        else:
            return

    create_realm(name, shard_field, collection_name, default_dest)


def set_shard_at_rest(realm, shard_key, location):
    """Marks a shard as being at rest in the given location. This is used for
    initiating shards in preparation for migration.

    :param str realm: The name of the realm for the shard
    :param shard_key: The key of the shard
    :param str location: The location that the data is at (or should be in the
        case of a brand new shard)
    :return: None
    """
    shards_coll = _get_shards_coll()
    shards_coll.update({
        'realm': realm,
        'shard_key': shard_key,
    },
    {
        '$set': {
            'location': location,
            'status': ShardStatus.AT_REST,
        },
        '$unset': {
            'new_location': 1,
        },
    },
    upsert=True)


def set_shard_to_migration_status(realm, shard_key, status):
    """Marks a shard as being at a specific migration status.
    """
    shards_coll = _get_shards_coll()
    shards_coll.update(
        {'realm': realm, 'shard_key': shard_key},
        {'$set': {'status': status}}
    )


def start_migration(realm, shard_key, new_location):
    """Marks a shard as being in the process of being migrated.
    """
    shards_coll = _get_shards_coll()

    shard_metas = list(
        shards_coll.find({'realm': realm, 'shard_key': shard_key},))

    if not shard_metas:
        raise Exception(
            'Could not find shard metadata - use set_shard_at_rest first')

    shard_meta, = shard_metas
    if shard_meta['location'] == new_location:
        raise Exception('Shard is already at %s' % (new_location,))

    shards_coll.update(
        {'realm': realm, 'shard_key': shard_key},
        {'$set': {
            'status': ShardStatus.MIGRATING_COPY,
            'new_location': new_location,
        }},
    )


def _reset_sharding_info():
    """Wipes all shard info. For internal test use only.
    """
    _get_realm_coll().remove({})
    _get_shards_coll().remove({})


class ShardAwareCollectionProxy(object):
    def __init__(self, collection_name):
        self.collection_name = collection_name

    def find(self, *args, **kwargs):
        return operations.multishard_find(
            self.collection_name, *args, **kwargs)

    def update(self, *args, **kwargs):
        return operations.multishard_update(
            self.collection_name, *args, **kwargs)

    def insert(self, *args, **kwargs):
        return operations.multishard_insert(
            self.collection_name, *args, **kwargs)

    def remove(self, *args, **kwargs):
        return operations.multishard_remove(
            self.collection_name, *args, **kwargs)

    def save(self, *args, **kwargs):
        return operations.multishard_save(
            self.collection_name, *args, **kwargs)


def make_collection_shard_aware(collection_name):
    """Returns a new object that proxies the given collection and makes it
    shard aware.
    """
    return ShardAwareCollectionProxy(collection_name)
