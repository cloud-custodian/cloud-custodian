# Copyright 2017 Capital One Services, LLC
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

from botocore.exceptions import ClientError
from concurrent.futures import as_completed

from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import QueryResourceManager, DescribeSource
from c7n.utils import local_session, chunks, type_schema, get_retry
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
from c7n.filters import FilterRegistry
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction


@resources.register('dms-instance')
class ReplicationInstance(QueryResourceManager):

    class resource_type(object):
        service = 'dms'
        type = 'rep'
        enum_spec = (
            'describe_replication_instances', 'ReplicationInstances', None)
        name = id = 'ReplicationInstanceIdentifier'
        date = 'InstanceCreateTime'
        dimension = None

        # The api supports filtering which we handle via describe source.
        filter_name = filter_type = None

    filters = FilterRegistry('dms-instance.filters')
    filters.register('marked-for-op', TagActionFilter)
    filter_registry = filters
    retry = staticmethod(get_retry(('Throttled',)))

    def get_source(self, source_type):
        if source_type == 'describe':
            return InstanceDescribe(self)
        return super(ReplicationInstance, self).get_source(source_type)

    def get_arns(self, resources):
        return [r['ReplicationInstanceArn'] for r in resources]

    def get_tags(self, resources):
        client = local_session(self.session_factory).client('dms')
        for r in resources:
            r['Tags'] = self.manager.retry(
                client.list_tags_for_resource(
                    ResourceArn=r['ReplicationInstanceArn'])['TagList'])
        return resources


class InstanceDescribe(DescribeSource):

    def get_resources(self, resource_ids):
        return self.query.filter(
            self.manager,
            **{
                'Filters': [
                    {'Name': 'replication-instance-id', 'Values': resource_ids}]})

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('dms')
        with self.manager.executor_factory(max_workers=2) as w:
            futures = []
            for resource_set in chunks(resources, 20):
                futures.append(
                    w.submit(self.process_resource_set, client, resources))

            for f in as_completed(futures):
                if f.exception():
                    self.manager.log.warning(
                        "Error retrieving replinstance tags: %s",
                        f.exception())
        return resources

    def process_resource_set(self, client, resources):
        for arn, r in zip(self.manager.get_arns(resources), resources):
            self.manager.log.info("arn %s" % arn)
            try:
                tags = client.list_tags_for_resource(
                    ResourceArn=arn).get('TagList', ())
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundFault':
                    continue
                raise
            r['Tags'] = tags


@ReplicationInstance.filter_registry.register('subnet')
class Subnet(SubnetFilter):

    RelatedIdsExpression = 'ReplicationSubnetGroup.Subnets[].SubnetIdentifier'


@ReplicationInstance.filter_registry.register('security-group')
class SecurityGroup(SecurityGroupFilter):

    RelatedIdsExpression = 'VpcSecurityGroups[].VpcSecurityGroupId'


@ReplicationInstance.action_registry.register('delete')
class InstanceDelete(BaseAction):

    schema = type_schema('delete')
    permissions = ('dms:DeleteReplicationInstance',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('dms')
        for arn, r in zip(self.manager.get_arns(resources), resources):
            client.delete_replication_instance(ReplicationInstanceArn=arn)


@ReplicationInstance.action_registry.register('tag')
class InstanceTag(Tag):
    """
    Add tag(s) to a replication instance

    :example:

        .. code-block:: yaml

            policies:
                - name: tag-dms-required
                  resource: dms-instance
                  filters:
                    - "tag:RequireTag": absent
                  actions:
                    - type: tag
                      key: RequiredTag
                      value: RequiredTagValue
    """
    permissions = ('dms:AddTagsToResource',)

    def process_resource_set(self, resources, tags):
        client = local_session(self.manager.session_factory).client('dms')
        tags_list = [{(k, v) for (k, v) in tags.items()}]
        for r in resources:
            try:
                client.add_tags_to_resource(
                    ResourceArn=r['ReplicationInstanceArn'],
                    Tags=tags_list)
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundFault':
                    continue
                raise


@ReplicationInstance.action_registry.register('remove-tag')
class InstanceRemoveTag(RemoveTag):
    """
    Remove tag(s) from a replication instance

    :example:

        .. code-block:: yaml

            policies:
                - name: delete-single-az-dms
                  resource: dms-instance
                  filters:
                    - "tag:InvalidTag": present
                  actions:
                    - type: remove-tag
                      tags: ["InvalidTag"]
    """
    permissions = ('dms:RemoveTagsFromResource',)

    def process_resource_set(self, resources, tags):
        client = local_session(self.manager.session_factory).client('dms')
        for r in resources:
            try:
                client.remove_tags_from_resource(
                    ResourceArn=r['ReplicationInstanceArn'],
                    TagKeys=tags)
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundFault':
                    continue
                raise


@ReplicationInstance.action_registry.register('mark-for-op')
class InstanceMarkForOp(TagDelayedAction):
    """
    Tag a replication instance for action at a later time

    :example:

        .. code-block:: yaml

            policies:
                - name: delete-single-az-dms
                  resource: dms-instance
                  filters:
                    - MultiAZ: False
                  actions:
                    - type: mark-for-op
                      tag: custodian_dms_cleanup
                      op: delete
                      days: 7
    """
    permissions = ('dms:AddTagsToResource',)

    def process_resource_set(self, resources, tags):
        client = local_session(self.manager.session_factory).client('dms')
        tags_list = [{(k, v) for (k, v) in tags.items()}]
        for r in resources:
            try:
                client.add_tags_to_resource(
                    ResourceArn=r['ReplicationInstanceArn'],
                    Tags=tags_list)
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundFault':
                    continue
                raise
