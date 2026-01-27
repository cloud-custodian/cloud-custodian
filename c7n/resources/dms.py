# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from concurrent.futures import as_completed

from c7n.actions import BaseAction
from c7n.manager import resources
from c7n.query import (
    ConfigSource, QueryResourceManager, DescribeSource, TypeInfo, DescribeWithResourceTags)
from c7n.utils import local_session, chunks, type_schema, get_retry
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter, VpcFilter
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters import FilterRegistry
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction, universal_augment


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
                r['Tags'] = client.list_tags_for_resource(
                    ResourceArn=arn).get('TagList', [])
            except client.exceptions.ResourceNotFoundFault:
                continue


@resources.register('dms-instance')
class ReplicationInstance(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'dms'
        arn_type = 'rep'
        enum_spec = (
            'describe_replication_instances', 'ReplicationInstances', None)
        name = id = 'ReplicationInstanceIdentifier'
        arn = 'ReplicationInstanceArn'
        date = 'InstanceCreateTime'
        config_type = cfn_type = 'AWS::DMS::ReplicationInstance'
        permissions_augment = ("dms:ListTagsForResource",)

    filters = FilterRegistry('dms-instance.filters')
    filters.register('marked-for-op', TagActionFilter)
    filter_registry = filters
    retry = staticmethod(get_retry(('Throttled',)))

    source_mapping = {
        'describe': InstanceDescribe,
        'config': ConfigSource
    }


class EndpointDescribe(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, resources)


@resources.register('dms-endpoint')
class DmsEndpoints(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'dms'
        enum_spec = ('describe_endpoints', 'Endpoints', None)
        arn = id = 'EndpointArn'
        name = 'EndpointIdentifier'
        arn_type = 'endpoint'
        universal_taggable = object()
        config_type = cfn_type = 'AWS::DMS::Endpoint'
        permissions_augment = ("dms:ListTagsForResource",)

    source_mapping = {
        'describe': EndpointDescribe,
        'config': ConfigSource
    }


@DmsEndpoints.filter_registry.register('kms-key')
class EndpointKmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = 'KmsKeyId'


@ReplicationInstance.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = 'KmsKeyId'


@ReplicationInstance.filter_registry.register('subnet')
class Subnet(SubnetFilter):

    RelatedIdsExpression = 'ReplicationSubnetGroup.Subnets[].SubnetIdentifier'


@ReplicationInstance.filter_registry.register('security-group')
class SecurityGroup(SecurityGroupFilter):

    RelatedIdsExpression = 'VpcSecurityGroups[].VpcSecurityGroupId'


@ReplicationInstance.filter_registry.register('vpc')
class Vpc(VpcFilter):

    RelatedIdsExpression = 'ReplicationSubnetGroup.VpcId'


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

    .. code-block:: yaml

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

    AWS ModifyReplicationInstance Documentation:
      https://docs.aws.amazon.com/dms/latest/APIReference/API_ModifyReplicationInstance.html
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
            except (client.exceptions.InvalidResourceStateFault,
                    client.exceptions.ResourceNotFoundFault,
                    client.exceptions.ResourceAlreadyExistsFault,
                    client.exceptions.UpgradeDependencyFailureFault):
                continue


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

    def process_resource_set(self, client, resources, tags):
        client = local_session(self.manager.session_factory).client('dms')
        for r in resources:
            try:
                client.add_tags_to_resource(
                    ResourceArn=r['ReplicationInstanceArn'],
                    Tags=tags)
            except client.exceptions.ResourceNotFoundFault:
                continue


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

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            try:
                client.remove_tags_from_resource(
                    ResourceArn=r['ReplicationInstanceArn'],
                    TagKeys=tags)
            except client.exceptions.ResourceNotFoundFault:
                continue


@ReplicationInstance.action_registry.register('mark-for-op')
class InstanceMarkForOp(TagDelayedAction):
    """
    Tag a replication instance for action at a later time

    :example:

        .. code-block:: yaml

            policies:
                - name: delete-dms
                  resource: dms-instance
                  filters:
                    - MultiAZ: False
                  actions:
                    - type: mark-for-op
                      tag: custodian_dms_cleanup
                      op: delete
                      days: 7
    """


@DmsEndpoints.action_registry.register('modify-endpoint')
class ModifyDmsEndpoint(BaseAction):
    """Modify the attributes of a DMS endpoint

    :example:

    .. code-block:: yaml

          policies:
            - name: dms-endpoint-modify
              resource: dms-endpoint
              filters:
                - EngineName: sqlserver
                - SslMode: none
              actions:
                - type: modify-endpoint
                  SslMode: require

    AWS ModifyEndpoint Documentation
    https://docs.aws.amazon.com/dms/latest/APIReference/API_ModifyEndpoint.html
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
            except (client.exceptions.InvalidResourceStateFault,
                    client.exceptions.ResourceAlreadyExistsFault,
                    client.exceptions.ResourceNotFoundFault):
                continue


@DmsEndpoints.action_registry.register('delete')
class DeleteDmsEndpoint(BaseAction):
    """Delete a DMS endpoint

    :example:

    .. code-block:: yaml

          policies:
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
            except client.exceptions.ResourceNotFoundFault:
                continue


@resources.register("dms-replication-task")
class DMSReplicationTask(QueryResourceManager):
    class resource_type(TypeInfo):
        service = "dms"
        enum_spec = ('describe_replication_tasks', 'ReplicationTasks', None)
        arn_type = "task"
        arn = "ReplicationTaskArn"
        id = "ReplicationTaskArn"
        name = "ReplicationTaskIdentifier"
        cfn_type = config_type = "AWS::DMS::ReplicationTask"
        universal_taggable = object()
        permissions_augment = ("dms:ListTagsForResource",)

    source_mapping = {
       "describe": DescribeWithResourceTags,
       "config": ConfigSource
    }
