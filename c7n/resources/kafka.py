# Copyright 2019 Capital One Services, LLC
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

from c7n.actions import Action
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema


@resources.register('kafka')
class Kafka(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'kafka'
        enum_spec = ('list_clusters', 'ClusterInfoList', None)
        arn = id = 'ClusterArn'
        name = 'ClusterName'
        date = 'CreationTime'
        filter_name = 'ClusterNameFilter'
        filter_type = 'scalar'

    def augment(self, resources):
        for r in resources:
            if 'Tags' not in r:
                continue
            tags = []
            for k, v in r['Tags'].items():
                tags.append({'Key': k, 'Value': v})
            r['Tags'] = tags
        return resources


@Kafka.filter_registry.register('security-group')
class KafkaSGFilter(SecurityGroupFilter):

    RelatedIdsExpression = "BrokerNodeGroupInfo.SecurityGroups[]"


@Kafka.filter_registry.register('subnet')
class KafkaSubnetFilter(SubnetFilter):

    RelatedIdsExpression = "BrokerNodeGroupInfo.ClientSubnets[]"


@Kafka.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')
    permissions = ('kafka:DeleteCluster',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('kafka')

        for r in resources:
            try:
                client.delete_cluster(ClusterArn=r['ClusterArn'])
            except client.exceptions.NotFoundException:
                continue
