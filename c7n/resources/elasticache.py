# Copyright 2016 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import functools
import logging
import re

from datetime import datetime

from concurrent.futures import as_completed
from dateutil.tz import tzutc
from dateutil.parser import parse

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry, AgeFilter, OPERATORS
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n import tags
from c7n.utils import (
    local_session, get_account_id, generate_arn,
    get_retry, chunks, snapshot_identifier, type_schema)

log = logging.getLogger('custodian.elasticache')

filters = FilterRegistry('elasticache.filters')
actions = ActionRegistry('elasticache.actions')
#registered marked-for-op filter
filters.register('marked-for-op', tags.TagActionFilter) 

TTYPE = re.compile('cache.t')

@resources.register('cache-cluster')
class ElastiCacheCluster(QueryResourceManager):

    resource_type = 'aws.elasticache.cluster'
    filter_registry = filters
    action_registry = actions
    _generate_arn = _account_id = None
    retry = staticmethod(get_retry(('Throttled',)))

    @property
    def account_id(self):
        if self._account_id is None:
            session = local_session(self.session_factory)
            self._account_id = get_account_id(session)
        return self._account_id

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                'elasticache',
                region=self.config.region,
                account_id=self.account_id,
                resource_type='cluster',
                separator=':')
        return self._generate_arn

    def augment(self, clusters):
        filter(None, _elasticache_cluster_tags(
            self.get_model(),
            clusters, self.session_factory, self.executor_factory,
            self.generate_arn, self.retry))
        return clusters


# added mark-for-op
@actions.register('mark-for-op')
class TagDelayedAction(tags.TagDelayedAction):
    
    batch_size = 1
    
    def process_resource_set(self, clusters, tags):
        client = local_session(self.manager.session_factory).client('elasticache')
        for cluster in clusters:
            arn = self.manager.generate_arn(cluster['CacheClusterId'])
            client.add_tags_to_resource(ResourceName=arn, Tags=tags)

# added unmark
@actions.register('remove-tag')
@actions.register('unmark')
class RemoveTag(tags.RemoveTag):

    concurrency = 2
    batch_size = 5

    def process_resource_set(self, clusters, tag_keys):
        client = local_session(
            self.manager.session_factory).client('elasticache')
        for cluster in clusters:
            arn = self.manager.generate_arn(cluster['CacheClusterId'])
            client.remove_tags_from_resource(
                ResourceName=arn, TagKeys=tag_keys)            
            
@actions.register('delete')
class DeleteElastiCacheCluster(BaseAction):

    schema = type_schema(
        'delete', **{'skip-snapshot': {'type': 'boolean'}})

    def process(self, clusters):
        skip = self.data.get('skip-snapshot', False)
        client = local_session(self.manager.session_factory).client('elasticache')

        clusters_to_delete = []
        replication_groups_to_delete = set()
        for cluster in clusters:
            if cluster.get('ReplicationGroupId', ''):
                replication_groups_to_delete.add(cluster['ReplicationGroupId'])
            else:
                clusters_to_delete.append(cluster)
        # added if statement to handle differences in parameters if snapshot is skipped
        for cluster in clusters_to_delete:
            params = {'CacheClusterId': cluster['CacheClusterId']}
            if _cluster_eligible_for_snapshot(cluster) and not skip:
                params['FinalSnapshotIdentifier'] = snapshot_identifier(
                    'Final', cluster['CacheClusterId'])
                self.log.debug("Taking final snapshot of %s" %cluster['CacheClusterId'])
            else:
                self.log.debug("Skipping final snapshot of %s" %cluster['CacheClusterId'])
            client.delete_cache_cluster(**params)
            self.log.info(
                'Deleted ElastiCache cluster: %s',
                cluster['CacheClusterId'])

        for replication_group in replication_groups_to_delete:
            params = {'ReplicationGroupId': replication_group,
                      'RetainPrimaryCluster': False}
            if not skip:
                params['FinalSnapshotIdentifier'] = snapshot_identifier(
                    'Final', replication_group)
            client.delete_replication_group(**params)

            self.log.info(
                'Deleted ElastiCache replication group: %s',
                replication_group)


@actions.register('snapshot')
class SnapshotElastiCacheCluster(BaseAction):

    def process(self, clusters):
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for cluster in clusters:
                if not _cluster_eligible_for_snapshot(cluster):
                    continue
                futures.append(w.submit(
                    self.process_cluster_snapshot,
                    cluster))

            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception creating ElastiCache cluster snapshot  \n %s",
                        f.exception())
        return clusters

    def process_cluster_snapshot(self, cluster):
        c = local_session(self.manager.session_factory).client('elasticache')
        c.create_snapshot(
            SnapshotName=snapshot_identifier(
                'Backup',
                cluster['CacheClusterId']),
            CacheClusterId=cluster['CacheClusterId'])


@resources.register('cache-subnet-group')
class ElastiCacheSubnetGroup(QueryResourceManager):

    resource_type = 'aws.elasticache.subnet-group'


@resources.register('cache-snapshot')
class ElastiCacheSnapshot(QueryResourceManager):

    resource_type = 'aws.elasticache.snapshot'
    filter_registry = FilterRegistry('elasticache-snapshot.filters')
    action_registry = ActionRegistry('elasticache-snapshot.actions')
    filter_registry.register('marked-for-op', tags.TagActionFilter) 
    _generate_arn = _account_id = None
    retry = staticmethod(get_retry(('Throttled',)))

    @property
    def account_id(self):
        if self._account_id is None:
            session = local_session(self.session_factory)
            self._account_id = get_account_id(session)
        return self._account_id

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                'elasticache',
                region=self.config.region,
                account_id=self.account_id,
                resource_type='snapshot',
                separator=':')
        return self._generate_arn

    def augment(self, clusters):
        filter(None, _elasticache_snapshot_tags(
            self.get_model(),
            clusters, self.session_factory, self.executor_factory,
            self.generate_arn, self.retry))
        return clusters


@ElastiCacheSnapshot.filter_registry.register('age')
class ElastiCacheSnapshotAge(AgeFilter):

    schema = type_schema(
        'age', days={'type': 'number'},
        op={'type': 'string', 'enum': OPERATORS.keys()})

    date_attribute = 'dummy'

    def get_resource_date(self, snapshot):
        """ Override superclass method as there is no single snapshot date attribute.
        """
        def to_datetime(v):
            if not isinstance(v, datetime):
                v = parse(v)
            if not v.tzinfo:
                v = v.replace(tzinfo=tzutc())
            return v

        # Return the earliest of the node snaphot creation times.
        return min([to_datetime(ns['SnapshotCreateTime'])
                    for ns in snapshot['NodeSnapshots']])


@ElastiCacheSnapshot.action_registry.register('delete')
class DeleteElastiCacheSnapshot(BaseAction):

    def process(self, snapshots):
        log.info("Deleting %d ElastiCache snapshots", len(snapshots))
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for snapshot_set in chunks(reversed(snapshots), size=50):
                futures.append(
                    w.submit(self.process_snapshot_set, snapshot_set))
                for f in as_completed(futures):
                    if f.exception():
                        self.log.error(
                            "Exception deleting snapshot set \n %s",
                            f.exception())
        return snapshots

    def process_snapshot_set(self, snapshots_set):
        c = local_session(self.manager.session_factory).client('elasticache')
        for s in snapshots_set:
            c.delete_snapshot(SnapshotName=s['SnapshotName'])

# added mark-for-op
@ElastiCacheSnapshot.action_registry.register('mark-for-op')
class ElastiCacheSnapshotTagDelayedAction(tags.TagDelayedAction):
    
    batch_size = 1
    
    def process_resource_set(self, snapshots, tags):
        client = local_session(self.manager.session_factory).client('elasticache')
        for snapshot in snapshots:
            arn = self.manager.generate_arn(snapshot['SnapshotName'])
            client.add_tags_to_resource(ResourceName=arn, Tags=tags)

# added unmark
@ElastiCacheSnapshot.action_registry.register('remove-tag')
@ElastiCacheSnapshot.action_registry.register('unmark')
class ElastiCacheSnapshotRemoveTag(tags.RemoveTag):

    concurrency = 2
    batch_size = 5

    def process_resource_set(self, snapshots, tag_keys):
        client = local_session(
            self.manager.session_factory).client('elasticache')
        for snapshot in snapshots:
            arn = self.manager.generate_arn(snapshot['SnapshotName'])
            client.remove_tags_from_resource(
                ResourceName=arn, TagKeys=tag_keys)

def _elasticache_cluster_tags(
        model, clusters, session_factory, executor_factory, generator, retry):
    """ Augment ElastiCache clusters with their respective tags
    """

    def process_tags(cluster):
        client = local_session(session_factory).client('elasticache')
        arn = generator(cluster[model.id])
        # added if statement to ensure snapshot is available in order to list tags
        if not cluster['CacheClusterStatus'] == 'available':
            return
        tag_list = retry(
            client.list_tags_for_resource,
            ResourceName=arn)['TagList']
        cluster['Tags'] = tag_list or []
        return cluster

    with executor_factory(max_workers=2) as w:
        return list(w.map(process_tags, clusters))


def _elasticache_snapshot_tags(
        model, snapshots, session_factory, executor_factory, generator, retry):
    """ Augment ElastiCache snapshots with their respective tags
    """

    # added if statement to ensure snapshot is available in order to list tags
    def process_tags(snapshot):
        client = local_session(session_factory).client('elasticache')
        arn = generator(snapshot[model.id])
        if not snapshot['SnapshotStatus'] == 'available':
            return
        tag_list = retry(
            client.list_tags_for_resource,
            ResourceName=arn)['TagList']
        snapshot['Tags'] = tag_list or []
        return snapshot

    with executor_factory(max_workers=2) as w:
        return list(w.map(process_tags, snapshots))


def _cluster_eligible_for_snapshot(cluster):
    # added regex search to filter unsupported cachenode types
    return (
        cluster['Engine'] != 'memcached' and not 
        TTYPE.match(cluster['CacheNodeType'])
        )