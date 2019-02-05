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
from __future__ import absolute_import, division, print_function, unicode_literals

import functools

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.tags import (RemoveTag, Tag, universal_augment)
from c7n.utils import generate_arn


@resources.register('cloudhsm-cluster')
class CloudHSMCluster(QueryResourceManager):

    class resource_type(object):
        service = 'cloudhsmv2'
        type = 'cluster'
        resource_type = 'cloudhsm'
        enum_spec = ('describe_clusters', 'Clusters', None)
        id = name = 'ClusterId'
        filter_name = 'Filters'
        filter_type = 'scalar'
        dimension = None
        # universal_taggable = True
        # Note: resourcegroupstaggingapi still points to hsm-classic

    augment = universal_augment
    _generate_arn = None

    @property
    def generate_arn(self):
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                'cloudhsm',
                region=self.config.region,
                account_id=self.account_id,
                resource_type='cluster',
                separator='/')
        return self._generate_arn


@CloudHSMCluster.action_registry.register('tag')
class Tag(Tag):
    """Action to add tag(s) to CloudHSM Cluster(s)

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudhsm
                resource: aws.cloudhsm-cluster
                filters:
                  - "tag:OwnerName": missing
                actions:
                  - type: tag
                    key: OwnerName
                    value: OwnerName
    """

    permissions = ('cloudhsmv2:TagResource',)

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
              - name: cloudhsm
                resource: aws.cloudhsm-cluster
                filters:
                  - "tag:OldTagKey": present
                actions:
                  - type: remove-tag
                    tags: [OldTagKey1, OldTagKey2]
    """

    permissions = ('cloudhsmv2:UntagResource',)

    def process_resource_set(self, client, clusters, tag_keys):
        for c in clusters:
            client.untag_resource(ResourceId=c['ClusterId'], TagKeyList=tag_keys)


@resources.register('hsm')
class CloudHSM(QueryResourceManager):

    class resource_type(object):
        service = 'cloudhsm'
        enum_spec = ('list_hsms', 'HsmList', None)
        id = 'HsmArn'
        name = 'Name'
        date = dimension = None
        detail_spec = (
            "describe_hsm", "HsmArn", None, None)
        filter_name = None


@resources.register('hsm-hapg')
class PartitionGroup(QueryResourceManager):

    class resource_type(object):
        service = 'cloudhsm'
        enum_spec = ('list_hapgs', 'HapgList', None)
        detail_spec = ('describe_hapg', 'HapgArn', None, None)
        id = 'HapgArn'
        name = 'HapgSerial'
        date = 'LastModifiedTimestamp'
        dimension = None
        filter_name = None


@resources.register('hsm-client')
class HSMClient(QueryResourceManager):

    class resource_type(object):
        service = 'cloudhsm'
        enum_spec = ('list_luna_clients', 'ClientList', None)
        detail_spec = ('describe_luna_client', 'ClientArn', None, None)
        id = 'ClientArn'
        name = 'Label'
        date = dimension = None
        filter_name = None
