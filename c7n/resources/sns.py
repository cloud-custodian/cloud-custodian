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
from c7n.filters import CrossAccountAccessFilter, PolicyChecker
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.resolver import ValuesFrom
from c7n.utils import local_session, type_schema


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


class SNSPolicyChecker(PolicyChecker):

    @property
    def allowed_endpoints(self):
        return self.checker_config.get('allowed_endpoints', ())

    @property
    def allowed_protocols(self):
        return self.checker_config.get('allowed_protocols', ())

    # check if any of the allowed_endpoints are a substring
    # to any of the values in the condition
    def handle_sns_endpoint(self, s, c):
        for value in c['values']:
            if not any(endpoint in value for endpoint in self.allowed_endpoints):
                return False
        return True

    def handle_sns_protocol(self, s, c):
        return bool(set(c['values']).difference(self.allowed_protocols))


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

    valid_protocols = (
        "http",
        "https",
        "email",
        "email-json",
        "sms",
        "sqs",
        "application",
        "lambda"
    )

    schema = type_schema(
        'cross-account',
        rinherit=CrossAccountAccessFilter.schema,
        whitelist_endpoints={'type': 'array', 'items': {'type': 'string'}},
        whitelist_endpoints_from=ValuesFrom.schema,
        whitelist_protocols={'type': 'array', 'items': {'type': 'string', 'enum': valid_protocols}},
        whitelist_protocols_from=ValuesFrom.schema
    )

    permissions = ('sns:GetTopicAttributes',)

    checker_factory = SNSPolicyChecker

    def process(self, resources, event=None):
        self.everyone_only = self.data.get('everyone_only', False)
        self.conditions = set(self.data.get(
            'whitelist_conditions',
            ("aws:userid", "aws:username")))
        self.actions = self.data.get('actions', ())
        self.accounts = self.get_accounts()
        self.endpoints = self.get_endpoints()
        self.protocols = self.get_protocols()
        self.vpcs = self.get_vpcs()
        self.vpces = self.get_vpces()
        self.checker = self.checker_factory(
            {'allowed_accounts': self.accounts,
             'allowed_endpoints': self.endpoints,
             'allowed_protocols': self.protocols,
             'allowed_vpc': self.vpcs,
             'allowed_vpce': self.vpces,
             'check_actions': self.actions,
             'everyone_only': self.everyone_only,
             'whitelist_conditions': self.conditions})
        return list(filter(self, resources))

    def get_endpoints(self):
        endpoints = set(self.data.get('whitelist_endpoints', ()))
        if 'whitelist_endpoints_from' in self.data:
            values = ValuesFrom(self.data['whitelist_endpoints_from'], self.manager)
            endpoints = endpoints.union(values.get_values())
        return endpoints

    def get_protocols(self):
        protocols = set(self.data.get('whitelist_protocols', ()))
        if 'whitelist_protocols_from' in self.data:
            values = ValuesFrom(self.data['whitelist_protocols_from'], self.manager)
            protocols = protocols.union(
                [p for p in values.get_values() if p in self.valid_protocols]
            )
        return protocols


@SNS.action_registry.register('remove-statements')
class RemovePolicyStatement(RemovePolicyBase):
    """Action to remove policy statements from SNS

    :example:

    .. code-block:: yaml

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
            except Exception:
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
