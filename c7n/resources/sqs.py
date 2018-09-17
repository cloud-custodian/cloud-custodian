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
from c7n.filters import CrossAccountAccessFilter, MetricsFilter, FilterRegistry
from c7n.manager import resources
from c7n.utils import local_session
from c7n.query import QueryResourceManager
from c7n.actions import BaseAction
from c7n.utils import type_schema
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction, universal_augment


filters = FilterRegistry('sqs.filters')
filters.register('marked-for-op', TagActionFilter)


@resources.register('sqs')
class SQS(QueryResourceManager):

    class resource_type(object):
        service = 'sqs'
        type = None
        # type = 'queue'
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

    filter_registry = filters

    def get_permissions(self):
        perms = super(SQS, self).get_permissions()
        perms.append('sqs:GetQueueAttributes')
        return perms

    def get_arns(self, resources):
        return [r['QueueArn'] for r in resources]

    def get_resources(self, ids, cache=True):
        ids_normalized = []
        for i in ids:
            if not i.startswith('https://'):
                ids_normalized.append(i)
                continue
            ids_normalized.append(i.rsplit('/', 1)[-1])
        return super(SQS, self).get_resources(ids_normalized, cache)

    def augment(self, resources):
        client = local_session(self.session_factory).client('sqs')

        def _augment(r):
            try:
                queue = self.retry(
                    client.get_queue_attributes,
                    QueueUrl=r,
                    AttributeNames=['All'])['Attributes']
                queue['QueueUrl'] = r
            except ClientError as e:
                if e.response['Error']['Code'] == 'AWS.SimpleQueueService.NonExistentQueue':
                    return
                if e.response['Error']['Code'] == 'AccessDenied':
                    self.log.warning("Denied access to sqs %s" % r)
                    return
                raise
            return queue

        with self.executor_factory(max_workers=2) as w:
            return universal_augment(
                self, list(filter(None, w.map(_augment, resources))))


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

    .. code-block:: yaml

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

    .. code-block:: yaml

           policies:
              - name: sqs-cross-account
                resource: sqs
                filters:
                  - type: cross-account
                actions:
                  - type: remove-statements
                    statement_ids: matched
    """

    permissions = ('sqs:GetQueueAttributes', 'sqs:RemovePermission')

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

        for f in found:
            client.remove_permission(
                QueueUrl=resource['QueueUrl'],
                Label=f['Sid'])

        return {'Name': resource['QueueUrl'],
                'State': 'PolicyRemoved',
                'Statements': found}


@SQS.action_registry.register('mark-for-op')
class MarkForOpQueue(TagDelayedAction):
    """Action to specify an action to occur at a later date

    :example:

    .. code-block:: yaml

            policies:
              - name: sqs-delete-unused
                resource: sqs
                filters:
                  - "tag:custodian_cleanup": absent
                actions:
                  - type: mark-for-op
                    tag: custodian_cleanup
                    msg: "Unused queues"
                    op: delete
                    days: 7
    """

    permissions = ('sqs:TagQueue',)

    def process_resource_set(self, queues, tags):
        client = local_session(self.manager.session_factory).client(
            'sqs')
        tag_dict = {}
        for t in tags:
            tag_dict[t['Key']] = t['Value']
        for queue in queues:
            queue_url = queue['QueueUrl']
            try:
                client.tag_queue(QueueUrl=queue_url, Tags=tag_dict)
            except Exception as err:
                self.log.exception(
                    'Exception tagging queue %s: %s',
                    queue['QueueArn'], err)
                continue


@SQS.action_registry.register('tag')
class TagQueue(Tag):
    """Action to create tag(s) on a queue

    :example:

    .. code-block:: yaml

            policies:
              - name: tag-sqs
                resource: sqs
                filters:
                  - "tag:target-tag": absent
                actions:
                  - type: tag
                    key: target-tag
                    value: target-tag-value
    """

    permissions = ('sqs:TagQueue',)

    def process_resource_set(self, queues, tags):
        client = local_session(self.manager.session_factory).client(
            'sqs')
        tag_dict = {}
        for t in tags:
            tag_dict[t['Key']] = t['Value']
        for queue in queues:
            queue_url = queue['QueueUrl']
            try:
                client.tag_queue(QueueUrl=queue_url, Tags=tag_dict)
            except Exception as err:
                self.log.exception(
                    'Exception tagging queue %s: %s',
                    queue['QueueArn'], err)
                continue


@SQS.action_registry.register('remove-tag')
class UntagQueue(RemoveTag):
    """Action to remove tag(s) on a queue

    :example:

    .. code-block:: yaml

            policies:
              - name: sqs-remove-tag
                resource: sqs
                filters:
                  - "tag:OutdatedTag": present
                actions:
                  - type: remove-tag
                    tags: ["OutdatedTag"]
    """

    permissions = ('sqs:UntagQueue',)

    def process_resource_set(self, queues, tags):
        client = local_session(self.manager.session_factory).client(
            'sqs')
        for queue in queues:
            queue_url = queue['QueueUrl']
            try:
                client.untag_queue(QueueUrl=queue_url, TagKeys=tags)
            except Exception as err:
                self.log.exception(
                    'Exception while removing tags from queue %s: %s',
                    queue['QueueArn'], err)
                continue


@SQS.action_registry.register('delete')
class DeleteSqsQueue(BaseAction):
    """Action to delete a SQS queue

    To prevent unwanted deletion of SQS queues, it is recommended
    to include a filter

    :example:

    .. code-block:: yaml

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
        client = local_session(self.manager.session_factory).client('sqs')
        for q in queues:
            self.process_queue(client, q)

    def process_queue(self, client, queue):
        try:
            client.delete_queue(QueueUrl=queue['QueueUrl'])
        except (client.exceptions.QueueDoesNotExist,
                client.exceptions.QueueDeletedRecently):
            pass


@SQS.action_registry.register('set-encryption')
class SetEncryption(BaseAction):
    """Action to set encryption key on SQS queue

    :example:

    .. code-block:: yaml

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
        key={'type': 'string'}, required=('key',))

    permissions = ('sqs:SetQueueAttributes',)

    def process(self, queues):
        # get KeyId
        key = "alias/" + self.data.get('key')
        session = local_session(self.manager.session_factory)
        key_id = session.client(
            'kms').describe_key(KeyId=key)['KeyMetadata']['KeyId']
        client = session.client('sqs')

        for q in queues:
            self.process_queue(client, q, key_id)

    def process_queue(self, client, queue, key_id):
        try:
            client.set_queue_attributes(
                QueueUrl=queue['QueueUrl'],
                Attributes={'KmsMasterKeyId': key_id}
            )
        except (client.exceptions.QueueDoesNotExist,) as e:
            self.log.exception(
                "Exception modifying queue:\n %s" % e)


@SQS.action_registry.register('set-retention-period')
class SetRetentionPeriod(BaseAction):
    """Action to set the retention period on an SQS queue (in seconds)

    :example:

    .. code-block:: yaml

        policies:
          - name: sqs-reduce-long-retention-period
            resource: sqs
            filters:
              - type: value
                key: MessageRetentionPeriod
                value_type: integer
                value: 345600
                op: ge
            actions:
              - type: set-retention-period
                period: 86400
    """
    schema = type_schema(
        'set-retention-period',
        period={'type': 'integer',
                'minimum': 60, 'exclusiveMinimum': True,
                'maximum': 1209600, 'exclusiveMaximum': True})

    permissions = ('sqs:SetQueueAttributes',)

    def process(self, queues):
        client = local_session(self.manager.session_factory).client('sqs')
        period = str(self.data.get('period', 345600))
        for q in queues:
            client.set_queue_attributes(
                QueueUrl=q['QueueUrl'],
                Attributes={
                    'MessageRetentionPeriod': period})
