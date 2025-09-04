# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.actions import Action
from c7n.manager import resources
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters import CrossAccountAccessFilter
from c7n.query import (
    ConfigSource,
    DescribeWithResourceTags, QueryResourceManager, ResourceQuery, TypeInfo)
from c7n.filters.vpc import SubnetFilter
from c7n.utils import local_session, type_schema, get_retry, jmespath_search, jmespath_compile
from c7n.tags import (
    TagDelayedAction, RemoveTag, TagActionFilter, Tag)


class ConfigStream(ConfigSource):

    def load_resource(self, item):
        resource = super().load_resource(item)
        for ck, dk in {
                'Arn': 'StreamARN',
                'Name': 'StreamName'}.items():
            resource[dk] = resource.pop(ck, None)
        if 'StreamEncryption' in resource:
            encrypt = resource.pop('StreamEncryption')
            resource['EncryptionType'] = encrypt['EncryptionType']
            resource['KeyId'] = encrypt['KeyId']
        return resource


@resources.register('kinesis')
class KinesisStream(QueryResourceManager):
    retry = staticmethod(
        get_retry((
            'LimitExceededException',)))

    class resource_type(TypeInfo):
        service = 'kinesis'
        arn_type = 'stream'
        enum_spec = ('list_streams', 'StreamNames', None)
        detail_spec = (
            'describe_stream', 'StreamName', None, 'StreamDescription')
        name = id = 'StreamName'
        dimension = 'StreamName'
        universal_taggable = True
        config_type = cfn_type = 'AWS::Kinesis::Stream'
        permissions_augment = ("kinesis:DescribeStream", "kinesis:ListTagsForStream",)

    source_mapping = {
        'describe': DescribeWithResourceTags,
        'config': ConfigStream
    }


@KinesisStream.action_registry.register('encrypt')
class Encrypt(Action):

    schema = type_schema('encrypt',
                         key={'type': 'string'},
                         required=('key',))

    # not see any documentation on what permission is actually neeeded.
    # https://docs.aws.amazon.com/IAM/latest/UserGuide/list_amazonkinesis.html
    permissions = ("kinesis:UpdateShardCount",)

    def process(self, resources):
        # get KeyId
        key = "alias/" + self.data.get('key')
        self.key_id = local_session(self.manager.session_factory).client(
            'kms').describe_key(KeyId=key)['KeyMetadata']['KeyId']
        client = local_session(self.manager.session_factory).client('kinesis')
        for r in resources:
            if not r['StreamStatus'] == 'ACTIVE':
                continue
            client.start_stream_encryption(
                StreamName=r['StreamName'],
                EncryptionType='KMS',
                KeyId=self.key_id
            )


@KinesisStream.action_registry.register('delete')
class Delete(Action):
    """ Delete a set of kinesis streams.

    Additionally, if we're configured with 'force', we will remove
    all existing consumers before deleting the stream itself. For
    'force' to work, we would require the
    `kinesis:DeregisterStreamConsumer` permission as well.

    :Example:

    .. code-block:: yaml

        policies:
          - name: kinesis-stream-deletion
            resource: kinesis
            filters:
              - type: marked-for-op
                op: delete
            actions:
              - type: delete
                force: true
    """

    schema = type_schema('delete', force={'type': 'boolean'})

    def get_permissions(self):
        permissions = ("kinesis:DeleteStream",)
        if self.data.get('force'):
            permissions += ('kinesis:DeregisterStreamConsumer',)
        return permissions

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('kinesis')
        not_active = [r['StreamName'] for r in resources
                      if r['StreamStatus'] != 'ACTIVE']
        self.log.warning(
            "The following streams cannot be deleted (wrong state): %s" % (
                ", ".join(not_active)))
        for r in resources:
            if not r['StreamStatus'] == 'ACTIVE':
                continue
            client.delete_stream(
                StreamName=r['StreamName'],
                EnforceConsumerDeletion=self.data.get('force', False))


@KinesisStream.filter_registry.register('kms-key')
class KmsFilterDataStream(KmsRelatedFilter):

    RelatedIdsExpression = 'KeyId'


class FirehoseQuery(ResourceQuery):
    # this is a work around for api pagination semantics of kinesis
    # firehose being different then other services, there isn't an
    # explicit last/pagination token per se, so it doesn't fit into
    # standard pagination semantics. it looks like for data streams
    # they retro fitted standard pagination semantics, as it also has
    # the exclusive start parameter.

    # https://github.com/cloud-custodian/cloud-custodian/issues/10302
    # https://docs.aws.amazon.com/firehose/latest/APIReference/API_ListDeliveryStreams.html
    # https://docs.aws.amazon.com/kinesis/latest/APIReference/API_ListStreams.html
    def _invoke_client_enum(self, client, enum_op, params, path, retry=None):
        data = self._enumerate_firehoses(client, enum_op, params, path)
        return data

    def _enumerate_firehoses(self, client, enum_op, params, path):
        path = jmespath_compile(path)
        op = getattr(client, enum_op)
        data = []
        while True:
            result = op(**params)
            data.extend(path.search(result))
            if not result.get('HasMoreDeliveryStreams', False):
                break
            params['ExclusiveStartDeliveryStreamName'] = data[-1]
        return data


class DescribeFirehoseStream(DescribeWithResourceTags):

    resource_query_factory = FirehoseQuery


@resources.register('firehose')
class DeliveryStream(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'firehose'
        arn_type = 'deliverystream'
        enum_spec = ('list_delivery_streams', 'DeliveryStreamNames', {'Limit': 100})
        detail_spec = (
            'describe_delivery_stream', 'DeliveryStreamName', None,
            'DeliveryStreamDescription')
        name = id = 'DeliveryStreamName'
        date = 'CreateTimestamp'
        dimension = 'DeliveryStreamName'
        universal_taggable = object()
        config_type = cfn_type = 'AWS::KinesisFirehose::DeliveryStream'

    source_mapping = {
        'describe': DescribeFirehoseStream,
        'config': ConfigSource
    }


@DeliveryStream.filter_registry.register('kms-key')
class KmsFilterDeliveryStream(KmsRelatedFilter):

    RelatedIdsExpression = 'DeliveryStreamEncryptionConfiguration.KeyARN'


@DeliveryStream.action_registry.register('delete')
class FirehoseDelete(Action):

    schema = type_schema('delete')
    permissions = ("firehose:DeleteDeliveryStream",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('firehose')
        creating = [r['DeliveryStreamName'] for r in resources
                    if r['DeliveryStreamStatus'] == 'CREATING']
        if creating:
            self.log.warning(
                "These delivery streams can't be deleted (wrong state): %s" % (
                    ", ".join(creating)))
        for r in resources:
            if not r['DeliveryStreamStatus'] == 'ACTIVE':
                continue
            client.delete_delivery_stream(
                DeliveryStreamName=r['DeliveryStreamName'])


@DeliveryStream.action_registry.register('encrypt-s3-destination')
class FirehoseEncryptS3Destination(Action):
    """Action to set encryption key a Firehose S3 destination

    :example:

    .. code-block:: yaml

            policies:
              - name: encrypt-s3-destination
                resource: firehose
                filters:
                  - KmsMasterKeyId: absent
                actions:
                  - type: encrypt-s3-destination
                    key_arn: <arn of KMS key/alias>
    """
    schema = type_schema(
        'encrypt-s3-destination',
        key_arn={'type': 'string'}, required=('key_arn',))

    permissions = ("firehose:UpdateDestination",)

    DEST_MD = {
        'SplunkDestinationDescription': {
            'update': 'SplunkDestinationUpdate',
            'clear': ['S3BackupMode'],
            'encrypt_path': 'S3DestinationDescription.EncryptionConfiguration',
            'remap': [('S3DestinationDescription', 'S3Update')]
        },
        'ElasticsearchDestinationDescription': {
            'update': 'ElasticsearchDestinationUpdate',
            'clear': ['S3BackupMode'],
            'encrypt_path': 'S3DestinationDescription.EncryptionConfiguration',
            'remap': [('S3DestinationDescription', 'S3Update')],
        },
        'ExtendedS3DestinationDescription': {
            'update': 'ExtendedS3DestinationUpdate',
            'clear': ['S3BackupMode'],
            'encrypt_path': 'EncryptionConfiguration',
            'remap': []
        },
        'RedshiftDestinationDescription': {
            'update': 'RedshiftDestinationUpdate',
            'clear': ['S3BackupMode', "ClusterJDBCURL", "CopyCommand", "Username"],
            'encrypt_path': 'S3DestinationDescription.EncryptionConfiguration',
            'remap': [('S3DestinationDescription', 'S3Update')]
        },
    }

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('firehose')
        key = self.data.get('key_arn')
        for r in resources:
            if not r['DeliveryStreamStatus'] == 'ACTIVE':
                continue
            version = r['VersionId']
            name = r['DeliveryStreamName']
            d = r['Destinations'][0]
            destination_id = d['DestinationId']

            for dtype, dmetadata in self.DEST_MD.items():
                if dtype not in d:
                    continue
                dinfo = d[dtype]
                for k in dmetadata['clear']:
                    dinfo.pop(k, None)
                if dmetadata['encrypt_path']:
                    encrypt_info = jmespath_search(dmetadata['encrypt_path'], dinfo)
                else:
                    encrypt_info = dinfo
                encrypt_info.pop('NoEncryptionConfig', None)
                encrypt_info['KMSEncryptionConfig'] = {'AWSKMSKeyARN': key}

                for old_k, new_k in dmetadata['remap']:
                    if old_k in dinfo:
                        dinfo[new_k] = dinfo.pop(old_k)
                params = dict(DeliveryStreamName=name,
                              DestinationId=destination_id,
                              CurrentDeliveryStreamVersionId=version)
                params[dmetadata['update']] = dinfo
                client.update_destination(**params)


@resources.register('kinesis-analytics')
class AnalyticsApp(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "kinesisanalytics"
        enum_spec = ('list_applications', 'ApplicationSummaries', None)
        detail_spec = ('describe_application', 'ApplicationName',
                       'ApplicationName', 'ApplicationDetail')
        name = "ApplicationName"
        arn = id = "ApplicationARN"
        arn_type = 'application'
        universal_taggable = object()
        cfn_type = 'AWS::KinesisAnalytics::Application'

    source_mapping = {
        'config': ConfigSource,
        'describe': DescribeWithResourceTags
    }


@AnalyticsApp.action_registry.register('delete')
class AppDelete(Action):

    schema = type_schema('delete')
    permissions = ("kinesisanalytics:DeleteApplication",)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('kinesisanalytics')
        for r in resources:
            client.delete_application(
                ApplicationName=r['ApplicationName'],
                CreateTimestamp=r['CreateTimestamp'])


@resources.register('kinesis-analyticsv2')
class KinesisAnalyticsAppV2(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "kinesisanalyticsv2"
        enum_spec = ('list_applications', 'ApplicationSummaries', None)
        detail_spec = ('describe_application', 'ApplicationName',
                       'ApplicationName', 'ApplicationDetail')
        name = "ApplicationName"
        arn = id = "ApplicationARN"
        arn_type = 'application'
        universal_taggable = object()
        config_type = cfn_type = 'AWS::KinesisAnalyticsV2::Application'
        permission_prefix = "kinesisanalytics"

    permissions = ("kinesisanalytics:DescribeApplication",)

    source_mapping = {
        'config': ConfigSource,
        'describe': DescribeWithResourceTags,
    }


@KinesisAnalyticsAppV2.action_registry.register('delete')
class KinesisAnalyticsAppV2Delete(Action):

    schema = type_schema('delete')
    permissions = ("kinesisanalytics:DeleteApplication",)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('kinesisanalyticsv2')
        for r in resources:
            client.delete_application(
                ApplicationName=r['ApplicationName'],
                CreateTimestamp=r['CreateTimestamp'])


@KinesisAnalyticsAppV2.filter_registry.register('subnet')
class KinesisAnalyticsSubnetFilter(SubnetFilter):

    RelatedIdsExpression = 'ApplicationConfigurationDescription.' \
        'VpcConfigurationDescriptions[].SubnetIds[]'


@resources.register('kinesis-video')
class KinesisVideoStream(QueryResourceManager):
    retry = staticmethod(
        get_retry((
            'ClientLimitExceededException',)))

    class resource_type(TypeInfo):
        service = 'kinesisvideo'
        arn_type = 'stream'
        enum_spec = ('list_streams', 'StreamInfoList', {'MaxResults': 10000})
        name = id = 'StreamName'
        arn = 'StreamARN'
        dimension = 'StreamName'

    source_mapping = {
        'describe': DescribeWithResourceTags,
        'config': ConfigSource
    }


KinesisVideoStream.action_registry.register('mark-for-op', TagDelayedAction)
KinesisVideoStream.filter_registry.register('marked-for-op', TagActionFilter)


@KinesisVideoStream.action_registry.register('delete')
class DeleteVideoStream(Action):
    """Delete a Kinesis Video stream

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-kinesis-video
            resource: kinesis-video
            actions:
              - type: delete
    """

    schema = type_schema('delete')
    permissions = ("kinesisvideo:DeleteStream",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('kinesisvideo')
        resources = self.filter_resources(resources, 'Status', ('ACTIVE',))
        for r in resources:
            try:
                client.delete_stream(StreamARN=r['StreamARN'])
            except client.exceptions.ResourceNotFoundException:
                continue


@KinesisVideoStream.filter_registry.register('kms-key')
class KmsFilterVideoStream(KmsRelatedFilter):

    RelatedIdsExpression = 'KmsKeyId'


@KinesisVideoStream.action_registry.register("tag")
class TagVideoStream(Tag):
    """Action to add tag/tags to Kinesis Video streams resource

    :example:

    .. code-block:: yaml

            policies:
              - name: kinesis-video-tag
                resource: kinesis-video
                filters:
                  - "tag:KinesisVideoTag": absent
                actions:
                  - type: tag
                    key: KinesisVideoTag
                    value: "KinesisVideo Tag Value"
    """
    permissions = ('kinesisvideo:TagResource',)

    def process_resource_set(self, client, resource_set, tag_keys):
        for r in resource_set:
            self.manager.retry(
                client.tag_resource,
                ResourceARN=r['StreamARN'],
                Tags=tag_keys,
                ignore_err_codes=("ResourceNotFoundException",))


@KinesisVideoStream.action_registry.register('remove-tag')
class VideoStreamRemoveTag(RemoveTag):
    """Action to remove tag/tags from a Kinesis Video streams resource

    :example:

    .. code-block:: yaml

            policies:
              - name: kinesisvideo-remove-tag
                resource: kinesis-video
                filters:
                  - "tag:KinesisVideoTag": present
                actions:
                  - type: remove-tag
                    tags: ["KinesisVideoTag"]
    """

    permissions = ('kinesisvideo:UntagResource',)

    def process_resource_set(self, client, resource_set, tag_keys):
        for r in resource_set:
            self.manager.retry(
                client.untag_resource,
                ResourceARN=r['StreamARN'],
                TagKeyList=tag_keys,
                ignore_err_codes=("ResourceNotFoundException",))


@KinesisStream.filter_registry.register('cross-account')
class KinesisStreamCrossAccount(CrossAccountAccessFilter):
    """Filters all Kinesis Data Streams with cross-account access

    :example:

    .. code-block:: yaml

            policies:
              - name: kinesis-cross-account
                resource: kinesis
                filters:
                  - type: cross-account
                    whitelist_from:
                      expr: "accounts.*.accountNumber"
                      url: accounts_url
    """

    permissions = ('kinesis:GetResourcePolicy',)
    policy_annotation = "c7n:Policy"

    def get_resource_policy(self, r):
        client = local_session(self.manager.session_factory).client('kinesis')
        if self.policy_annotation in r:
            return r[self.policy_annotation]
        result = self.manager.retry(
                client.get_resource_policy,
                ResourceARN=r['StreamARN'],
                ignore_err_codes=('ResourceNotFoundException'))
        if result:
            policy = result.get(self.policy_attribute, None)
            r[self.policy_annotation] = policy
        return policy
