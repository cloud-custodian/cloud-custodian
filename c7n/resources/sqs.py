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

from botocore.exceptions import ClientError

import json

from c7n.actions import RemovePolicyBase
from c7n.filters import CrossAccountAccessFilter, MetricsFilter
from c7n.manager import resources
from c7n.utils import local_session
from c7n.query import QueryResourceManager
from c7n.actions import BaseAction
from c7n.utils import type_schema


@resources.register('sqs')
class SQS(QueryResourceManager):

    class resource_type(object):
        service = 'sqs'
        type = 'queue'
        enum_spec = ('list_queues', 'QueueUrls', None)
        detail_spec = ("get_queue_attributes", "QueueUrl", None, "Attributes")
        id = 'QueueUrl'
        filter_name = 'QueueNamePrefix'
        filter_type = 'scalar'
        name = 'QueueUrl'
        date = 'CreatedTimestamp'
        dimension = 'QueueName'

        default_report_fields = (
            'QueueArn',
            'CreatedTimestamp',
            'ApproximateNumberOfMessages',
        )

    def get_permissions(self):
        perms = super(SQS, self).get_permissions()
        perms.append('sqs:GetQueueAttributes')
        return perms

    def augment(self, resources):

        def _augment(r):
            client = local_session(self.session_factory).client('sqs')
            try:
                queue = client.get_queue_attributes(
                    QueueUrl=r,
                    AttributeNames=['All'])['Attributes']
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDenied':
                    self.log.warning("Denied access to sqs %s" % r)
                    return
                raise

            queue['QueueUrl'] = r
            return queue

        self.log.debug('retrieving details for %d queues' % len(resources))
        with self.executor_factory(max_workers=4) as w:
            return list(filter(None, w.map(_augment, resources)))


@SQS.filter_registry.register('metrics')
class MetricsFilter(MetricsFilter):

    def get_dimensions(self, resource):
        return [
            {'Name': 'QueueName',
             'Value': resource['QueueUrl'].rsplit('/', 1)[-1]}]


@SQS.filter_registry.register('cross-account')
class SQSCrossAccount(CrossAccountAccessFilter):
    """Filter SQS queues which have cross account permissions

    :example:

        .. code-block: yaml

            policies:
              - name: sqs-cross-account
                resource: sqs
                filters:
                  - type: cross-account
    """
    permissions = ('sqs:GetQueueAttributes',)


@SQS.action_registry.register('remove-statements')
class RemovePolicyStatement(RemovePolicyBase):
    """Action to remove policy statements from SQS

    :example:

        .. code-block: yaml

           policies:
              - name: sqs-cross-account
                resource: sqs
                filters:
                  - type: cross-account
                actions:
                  - type: remove-statements
                    statement_ids: matched
    """

    permissions = ('sqs:GetQueueAttributes', 'sqs:SetQueueAttributes')

    def process(self, resources):
        results = []
        client = local_session(self.manager.session_factory).client('sqs')
        for r in resources:
            try:
                results += filter(None, [self.process_resource(client, r)])
            except Exception:
                self.log.exception(
                    "Error processing sns:%s", r['QueueUrl'])
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

        client.set_queue_attributes(
            QueueUrl=resource['QueueUrl'],
            Attributes={
                'Policy':json.dumps(p)
            }
        )

        return {'Name': resource['QueueUrl'],
                'State': 'PolicyRemoved',
                'Statements': found}


@SQS.action_registry.register('delete')
class DeleteSqsQueue(BaseAction):
    """Action to delete a SQS queue

    To prevent unwanted deletion of SQS queues, it is recommended
    to include a filter

    :example:

        .. code-block: yaml

            policies:
              - name: sqs-delete
                resource: sqs
                filters:
                  - KmsMasterKeyId: absent
                actions:
                  - type: delete
    """

    schema = type_schema('delete')
    permissions = ('sqs:DeleteQueue',)

    def process(self, queues):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_queue, queues))

    def process_queue(self, queue):
        client = local_session(self.manager.session_factory).client('sqs')
        try:
            client.delete_queue(QueueUrl=queue['QueueUrl'])
        except ClientError as e:
            self.log.exception(
                "Exception deleting queue:\n %s" % e)


@SQS.action_registry.register('set-encryption')
class SetEncryption(BaseAction):
    """Action to set encryption key on SQS queue

    :example:

        .. code-block: yaml

            policies:
              - name: sqs-set-encrypt
                resource: sqs
                filters:
                  - KmsMasterKeyId: absent
                actions:
                  - type: set_encryption
                    key: "<alias of kms key>"
    """
    schema = type_schema(
        'set-encryption',
        key={'type': 'string'},required=('key',))

    permissions = ('sqs:SetQueueAttributes',)

    def process(self, queues):
        # get KeyId
        key = "alias/" + self.data.get('key')
        self.key_id = local_session(self.manager.session_factory).client(
            'kms').describe_key(KeyId=key)['KeyMetadata']['KeyId']
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_queue, queues))

    def process_queue(self, queue):
        client = local_session(self.manager.session_factory).client('sqs')
        try:
            client.set_queue_attributes(
                QueueUrl=queue['QueueUrl'],
                Attributes={
                    'KmsMasterKeyId':self.key_id
                }
            )
        except ClientError as e:
            self.log.exception(
                "Exception modifying queue:\n %s" % e)
