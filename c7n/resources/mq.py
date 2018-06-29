# Copyright 2018 Capital One Services, LLC
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
from c7n.filters.metrics import MetricsFilter
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema


@resources.register('message-broker')
class MessageBroker(QueryResourceManager):

    class resource_type(object):
        service = 'mq'
        enum_spec = ('list_brokers', 'BrokerSummaries', None)
        detail_spec = (
            'describe_broker', 'BrokerId', 'BrokerId', None)

        id = 'BrokerId'
        name = 'BrokerName'
        date = None
        dimension = 'Broker'
        filter_name = None
        metrics_namespace = 'AWS/AmazonMQ'


@MessageBroker.filter_registry.register('subnet')
class MQSubnetFilter(SubnetFilter):

    RelatedIdsExpression = 'SubnetIds[]'


@MessageBroker.filter_registry.register('security-group')
class MQSGFilter(SecurityGroupFilter):

    RelatedIdsExpression = 'SecurityGroups[]'


@MessageBroker.filter_registry.register('metrics')
class MQMetrics(MetricsFilter):

    def get_dimensions(self, resource):
        # Fetching for Active broker instance only, https://amzn.to/2tLBhEB
        return [{'Name': self.model.dimension,
                 'Value': "{}-1".format(resource['BrokerName'])}]


@MessageBroker.action_registry.register('delete')
class Delete(Action):
    """Delete a set of message brokers
    """

    schema = type_schema('delete')
    permissions = ("mq:DeleteBroker",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('mq')
        for r in resources:
            try:
                client.delete_broker(BrokerId=r['BrokerId'])
            except client.exceptions.NotFoundException:
                continue
