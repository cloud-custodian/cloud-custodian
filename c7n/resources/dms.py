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
from c7n.filters.kms import KmsRelatedFilter
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


@resources.register('dms-endpoint')
class DmsEndpoints(QueryResourceManager):

    class resource_type(object):
        service = 'dms'
        enum_spec = ('describe_endpoints', 'Endpoints', None)
        detail_spec = None
        id = 'EndpointArn'
        name = 'EndpointIdentifier'
        date = None
        dimension = None
        filter_name = None


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


@ReplicationInstance.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = 'KmsKeyId'


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


@ReplicationInstance.action_registry.register('modify-instance')
class ModifyReplicationInstance(BaseAction):
    """Modify replication instance(s) to apply new settings

    :example:

    .. code-block: yaml

        policies:
          - name: enable-minor-version-upgrade
            resource: dms-instance
            filters:
              - AutoMinorVersionUpgrade: False
            actions:
              - type: modify-instance
                ApplyImmediately: True
                AutoMinorVersionUpgrade: True
                PreferredMaintenanceWindow: mon:23:00-mon:23:59

    AWS ModifyReplicationInstance Documentation: https://goo.gl/ePye9N
    """
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['modify-instance']},
            'ReplicationInstanceArn': {'type': 'string'},
            'AllocatedStorage': {'type': 'integer'},
            'ApplyImmediately': {'type': 'boolean'},
            'ReplicationInstanceClass': {'type': 'string'},
            'VpcSecurityGroupIds': {
                'type': 'array', 'items': {'type': 'string'}
            },
            'PreferredMaintenanceWindow': {'type': 'string'},
            'MultiAZ': {'type': 'boolean'},
            'EngineVersion': {'type': 'string'},
            'AllowMajorVersionUpgrade': {'type': 'boolean'},
            'AutoMinorVersionUpgrade': {'type': 'boolean'},
            'ReplicationInstanceIdentifier': {'type': 'string'}
        }
    }
    permissions = ('dms:ModifyReplicationInstance',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('dms')
        params = dict(self.data)
        params.pop('type')
        for r in resources:
            params['ReplicationInstanceArn'] = r['ReplicationInstanceArn']
            try:
                client.modify_replication_instance(**params)
            except ClientError as e:
                ecode = e.response['Error']['Code']
                if ecode in (
                        'InvalidResourceStateFault',
                        'ResourceAlreadyExistsFault',
                        'ResourceNotFoundFault'):
                    continue
                elif ecode == 'UpgradeDependencyFailureFault':
                    self.log.exception(
                        'Exception modifying instance %s :%s' % (
                            r['ReplicationInstanceArn'], e))
                    continue
                raise


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


@DmsEndpoints.action_registry.register('modify-endpoint')
class ModifyDmsEndpoint(BaseAction):
    """Modify the attributes of a DMS endpoint

    :example:

    .. code-block: yaml

        - policies:
            - name: dms-endpoint-modify
              resource: dms-endpoint
              filters:
                - EngineName: sqlserver
                - SslMode: none
              actions:
                - type: modify-endpoint
                  SslMode: require

    AWS ModifyEndpoint Documentation: https://goo.gl/eDFfuf
    """
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['modify-endpoint']},
            'Port': {'type': 'integer', 'minimum': 1, 'maximum': 65536},
            'ServerName': {'type': 'string'},
            'SslMode': {'type': 'string', 'enum': [
                'none', 'require', 'verify-ca', 'verify-full']},
            'CertificateArn': {'type': 'string'},
            'DatabaseName': {'type': 'string'},
            'EndpointIdentifier': {'type': 'string'},
            'EngineName': {'enum': [
                'mysql', 'oracle', 'postgres',
                'mariadb', 'aurora', 'redshift',
                'S3', 'sybase', 'dynamodb', 'mongodb',
                'sqlserver']},
            'ExtraConnectionAttributes': {'type': 'string'},
            'Username': {'type': 'string'},
            'Password': {'type': 'string'},
            'DynamoDbSettings': {
                'type': 'object',
                'additionalProperties': False,
                'required': ['ServiceAccessRoleArn'],
                'properties': {'ServiceAccessRoleArn': {'type': 'string'}}
            },
            'S3Settings': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'BucketFolder': {'type': 'string'},
                    'BucketName': {'type': 'string'},
                    'CompressionType': {
                        'type': 'string', 'enum': ['none', 'gzip']
                    },
                    'CsvDelimiter': {'type': 'string'},
                    'CsvRowDelimiter': {'type': 'string'},
                    'ExternalTableDefinition': {'type': 'string'},
                    'ServiceAccessRoleArn': {'type': 'string'}
                }
            },
            'MongoDbSettings': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'AuthMechanism': {
                        'type': 'string', 'enum': [
                            'default', 'mongodb_cr', 'scram_sha_1']
                    },
                    'AuthSource': {'type': 'string'},
                    'Username': {'type': 'string'},
                    'Password': {'type': 'string'},
                    'DatabaseName': {'type': 'string'},
                    'DocsToInvestigate': {'type': 'integer', 'minimum': 1},
                    'ExtractDocId': {'type': 'string'},
                    'NestingLevel': {
                        'type': 'string', 'enum': [
                            'NONE', 'none', 'ONE', 'one']},
                    'Port': {
                        'type': 'integer', 'minimum': 1, 'maximum': 65535},
                    'ServerName': {'type': 'string'}
                }
            }
        }
    }
    permissions = ('dms:ModifyEndpoint',)

    def process(self, endpoints):
        client = local_session(self.manager.session_factory).client('dms')
        params = dict(self.data)
        params.pop('type')
        for e in endpoints:
            params['EndpointArn'] = e['EndpointArn']
            params['EndpointIdentifier'] = params.get(
                'EndpointIdentifier', e['EndpointIdentifier'])
            params['EngineName'] = params.get('EngineName', e['EngineName'])
            try:
                client.modify_endpoint(**params)
            except ClientError as e:
                if e.response['Error']['Code'] in (
                        'InvalidResourceStateFault',
                        'ResourceAlreadyExistsFault',
                        'ResourceNotFoundFault'):
                    continue
                raise


@DmsEndpoints.action_registry.register('delete')
class DeleteDmsEndpoint(BaseAction):
    """Delete a DMS endpoint

    :example:

    .. code-block: yaml

        - policies:
            - name: dms-endpoint-no-ssl-delete
              resource: dms-endpoint
              filters:
                - EngineName: mariadb
                - SslMode: none
              actions:
                - delete

    """
    schema = type_schema('delete')
    permissions = ('dms:DeleteEndpoint',)

    def process(self, endpoints):
        client = local_session(self.manager.session_factory).client('dms')
        for e in endpoints:
            EndpointArn = e['EndpointArn']
            try:
                client.delete_endpoint(EndpointArn=EndpointArn)
            except ClientError as e:
                self.log.exception(
                    'Exception deleting endpoint %s :%s' % (
                        EndpointArn, e))
                continue
