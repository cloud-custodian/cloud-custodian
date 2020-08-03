# Copyright 2017 Capital One Services, LLC
# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import (RemoveTag, Tag, universal_augment)


@resources.register('cloudhsm-cluster')
class CloudHSMCluster(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudhsmv2'
        arn_type = 'cluster'
        permission_prefix = arn_service = 'cloudhsm'
        enum_spec = ('describe_clusters', 'Clusters', None)
        id = name = 'ClusterId'
        filter_name = 'Filters'
        filter_type = 'scalar'
        # universal_taggable = True
        # Note: resourcegroupstaggingapi still points to hsm-classic

    augment = universal_augment


@CloudHSMCluster.action_registry.register('tag')
class Tag(Tag):
    """Action to add tag(s) to CloudHSM Cluster(s)

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudhsm-tag
                resource: aws.cloudhsm-cluster
                filters:
                  - "tag:OwnerName": missing
                actions:
                  - type: tag
                    key: OwnerName
                    value: OwnerName
    """

    permissions = ('cloudhsm:TagResource',)

    def process_resource_set(self, client, clusters, tags):
        for c in clusters:
            try:
                client.tag_resource(ResourceId=c['ClusterId'], TagList=tags)
            except client.exceptions.CloudHsmResourceNotFoundException:
                continue


@CloudHSMCluster.action_registry.register('remove-tag')
class RemoveTag(RemoveTag):
    """Action to remove tag(s) from CloudHSM Cluster(s)

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudhsm-remove-tag
                resource: aws.cloudhsm-cluster
                filters:
                  - "tag:OldTagKey": present
                actions:
                  - type: remove-tag
                    tags: [OldTagKey1, OldTagKey2]
    """

    permissions = ('cloudhsm:UntagResource',)

    def process_resource_set(self, client, clusters, tag_keys):
        for c in clusters:
            client.untag_resource(ResourceId=c['ClusterId'], TagKeyList=tag_keys)


@resources.register('hsm')
class CloudHSM(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudhsm'
        enum_spec = ('list_hsms', 'HsmList', None)
        arn = id = 'HsmArn'
        arn_type = 'cluster'
        name = 'Name'
        detail_spec = ("describe_hsm", "HsmArn", None, None)


@resources.register('hsm-hapg')
class PartitionGroup(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudhsm'
        enum_spec = ('list_hapgs', 'HapgList', None)
        detail_spec = ('describe_hapg', 'HapgArn', None, None)
        arn = id = 'HapgArn'
        name = 'HapgSerial'
        date = 'LastModifiedTimestamp'


@resources.register('hsm-client')
class HSMClient(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudhsm'
        enum_spec = ('list_luna_clients', 'ClientList', None)
        detail_spec = ('describe_luna_client', 'ClientArn', None, None)
        arn = id = 'ClientArn'
        name = 'Label'
