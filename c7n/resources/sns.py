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

from c7n.actions import RemovePolicyBase, ModifyPolicyBase
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


@SNS.action_registry.register('modify-statements')
class ModifyPolicyStatement(ModifyPolicyBase):
    """Action to modify policy statements from SNS

    :example:

    .. code-block:: yaml

           policies:
              - name: sns-cross-account
                resource: sns
                filters:
                  - type: cross-account
                actions:
                  - type: modify-statements
                    add-statements: [statement]
                    remove-statements: [statement] or *
    """
    
    permissions = ('sns:SetTopicAttributes', 'sns:GetTopicAttributes')

    def process(self, resources):
        replace = False
        results = []
        client = local_session(self.manager.session_factory).client('sns')
        additions = self.data.get('add-statements', [])
        deletions = self.data.get('remove-statements', [])

        
        if unicode == type(deletions) and deletions == "*":
            replace = True

        for r in resources:
            new_policy = {u'Version': u'2012-10-17', u'Statement': [] }
            try:
                if replace:
                    new_policy = self.process_replace(client, r)
                if len(additions) and len(deletions) and not replace:
                    new_policy['Statement'] += self.process_add_and_delete(client, r)
                if len(additions) and not len(deletions) and not replace:
                    new_policy['Statement'] += self.process_addition(client, r).get('Statement')
                if not len(additions) and len(deletions) and not replace:
                    new_policy['Statement'] += self.process_deletion(client, r)
                results += {
                    'Name': r['TopicArn'],
                    'State': 'PolicyModified',
                    'Statements': new_policy
                }
            except Exception:
                self.log.exception(
                    "Error processing sns:%s", r['TopicArn'])
            else:
                client.set_topic_attributes(
                    TopicArn=r['TopicArn'],
                    AttributeName='Policy',
                    AttributeValue=json.dumps(new_policy)
                )
        return results

    def process_add_and_delete(self, client, resource):
        policy = resource.get('Policy') or '{}'
        policy = json.loads(policy)
        new_policy = self.add_policy(policy, resource)
        new_policy, found = self.remove_policy(
            policy, resource, CrossAccountAccessFilter.annotation_key)
        return new_policy

    def process_addition(self, client, resource):
        policy = resource.get('Policy') or '{}'
        policy = json.loads(policy)
        new_policy = self.add_policy(policy, resource)
        # new_policy = json.dumps(new_policy)
        if policy == new_policy:
            return policy
        return new_policy

    def process_deletion(self, client, resource):
        policy = resource.get('Policy') or '{}'
        policy = json.loads(policy)
        new_policy, found = self.remove_policy(
            policy, resource, CrossAccountAccessFilter.annotation_key)
        return new_policy

    def process_replace(self, client, resource):
        base = {
            "Version": "2012-10-17"
        }
        new_policy = self.replace_policy(base)
        return new_policy