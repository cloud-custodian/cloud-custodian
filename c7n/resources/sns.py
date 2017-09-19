# Copyright 2016-2017 Capital One Services, LLC
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

import json

from c7n.actions import RemovePolicyBase
from c7n.filters import CrossAccountAccessFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session


@resources.register('sns')
class SNS(QueryResourceManager):

    class resource_type(object):
        service = 'sns'
        type = 'topic'
        enum_spec = ('list_topics', 'Topics', None)
        detail_spec = (
            'get_topic_attributes', 'TopicArn', 'TopicArn', 'Attributes')
        id = 'TopicArn'
        filter_name = None
        filter_type = None
        name = 'DisplayName'
        date = None
        dimension = 'TopicName'
        default_report_fields = (
            'TopicArn',
            'DisplayName',
            'SubscriptionsConfirmed',
            'SubscriptionsPending',
            'SubscriptionsDeleted'
        )


@SNS.filter_registry.register('cross-account')
class SNSCrossAccount(CrossAccountAccessFilter):
    """Filter to return all SNS topics with cross account access permissions

    The whitelist parameter will omit the accounts that match from the return

    :example:

        .. code-block:

            policies:
              - name: sns-cross-account
                resource: sns
                filters:
                  - type: cross-account
                    whitelist:
                      - permitted-account-01
                      - permitted-account-02
    """
    permissions = ('sns:GetTopicAttributes',)


@SNS.action_registry.register('remove-statements')
class RemovePolicyStatement(RemovePolicyBase):
    """Action to remove policy statements from SNS

    :example:

        .. code-block: yaml

           policies:
              - name: sns-cross-account
                resource: sns
                filters:
                  - type: cross-account
                actions:
                  - type: remove-statements
                    statement_ids: matched
    """

    permissions = ('sns:SetTopicAttributes', 'sns:GetTopicAttributes')

    def process(self, resources):
        results = []
        client = local_session(self.manager.session_factory).client('sns')
        for r in resources:
            try:
                results += filter(None, [self.process_resource(client, r)])
            except:
                self.log.exception(
                    "Error processing sns:%s", r['TopicArn'])
        return results

    def process_resource(self, client, resource):
        p = resource.get('Policy')
        if p is None:
            return

        p = json.loads(resource['Policy'])
        statements, found = self.process_policy(
            p, resource, CrossAccountAccessFilter.annotation_key)

        if not found:
            return

        client.set_topic_attributes(
            TopicArn=resource['TopicArn'],
            AttributeName='Policy',
            AttributeValue=json.dumps(p)
        )
        return {'Name': resource['TopicArn'],
                'State': 'PolicyRemoved',
                'Statements': found}
