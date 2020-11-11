# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

import json

from c7n.actions import RemovePolicyBase, ModifyPolicyBase
from c7n.filters import CrossAccountAccessFilter, MetricsFilter
from c7n.filters.kms import KmsRelatedFilter
from c7n.manager import resources
from c7n.utils import local_session
from c7n.query import ConfigSource, DescribeSource, QueryResourceManager, TypeInfo
from c7n.actions import BaseAction
from c7n.utils import type_schema
from c7n.tags import universal_augment

from c7n.resources.securityhub import PostFinding


class DescribeQueue(DescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client('sqs')

        def _augment(r):
            try:
                queue = self.manager.retry(
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

        with self.manager.executor_factory(max_workers=2) as w:
            return universal_augment(
                self.manager, list(filter(None, w.map(_augment, resources))))


class QueueConfigSource(ConfigSource):

    def load_resource(self, item):
        resource = super().load_resource(item)
        resource['QueueUrl'] = item['resourceId']
        return resource


@resources.register('sqs')
class SQS(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'sqs'
        arn_type = ""
        enum_spec = ('list_queues', 'QueueUrls', None)
        detail_spec = ("get_queue_attributes", "QueueUrl", None, "Attributes")
        cfn_type = config_type = 'AWS::SQS::Queue'
        id = 'QueueUrl'
        arn = "QueueArn"
        filter_name = 'QueueNamePrefix'
        filter_type = 'scalar'
        name = 'QueueUrl'
        date = 'CreatedTimestamp'
        dimension = 'QueueName'
        universal_taggable = object()
        default_report_fields = (
            'QueueArn',
            'CreatedTimestamp',
            'ApproximateNumberOfMessages',
        )

    source_mapping = {
        'describe': DescribeQueue,
        'config': QueueConfigSource
    }

    def get_permissions(self):
        perms = super(SQS, self).get_permissions()
        perms.append('sqs:GetQueueAttributes')
        return perms

    def get_resources(self, ids, cache=True):
        ids_normalized = []
        for i in ids:
            if not i.startswith('https://'):
                ids_normalized.append(i)
                continue
            ids_normalized.append(i.rsplit('/', 1)[-1])
        return super(SQS, self).get_resources(ids_normalized, cache)


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


@SQS.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):
    """
    Filter a resource by its associcated kms key and optionally the aliasname
    of the kms key by using 'c7n:AliasName'
    The KmsMasterId returned for SQS sometimes has the alias name directly in the value.

    :example:

        .. code-block:: yaml

            policies:
                - name: sqs-kms-key-filters
                  resource: aws.sqs
                  filters:
                    - or:
                      - type: value
                        key: KmsMasterKeyId
                        value: "^(alias/aws/)"
                        op: regex
                      - type: kms-key
                        key: c7n:AliasName
                        value: "^(alias/aws/)"
                        op: regex
    """
    RelatedIdsExpression = 'KmsMasterKeyId'


@SQS.action_registry.register('post-finding')
class SQSPostFinding(PostFinding):

    resource_type = 'AwsSqsQueue'

    def format_resource(self, r):
        envelope, payload = self.format_envelope(r)
        payload.update(self.filter_empty({
            'KmsDataKeyReusePeriodSeconds': r.get('KmsDataKeyReusePeriodSeconds'),
            'KmsMasterKeyId': r.get('KmsMasterKeyId'),
            'QueueName': r['QueueArn'].split(':')[-1],
            'DeadLetterTargetArn': r.get('DeadLetterTargetArn')
        }))
        if 'KmsDataKeyReusePeriodSeconds' in payload:
            payload['KmsDataKeyReusePeriodSeconds'] = int(
                payload['KmsDataKeyReusePeriodSeconds'])
        return envelope


@SQS.action_registry.register('remove-statements')
class RemovePolicyStatement(RemovePolicyBase):
    """Action to remove policy statements from SQS

    :example:

    .. code-block:: yaml

           policies:
              - name: remove-sqs-cross-account
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
                    "Error processing sqs:%s", r['QueueUrl'])
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


@SQS.action_registry.register('modify-policy')
class ModifyPolicyStatement(ModifyPolicyBase):
    """Action to modify SQS Queue IAM policy statements.

    :example:

    .. code-block:: yaml

           policies:
              - name: sqs-yank-cross-account
                resource: sqs
                filters:
                  - type: cross-account
                actions:
                  - type: modify-policy
                    add-statements: [{
                        "Sid": "ReplaceWithMe",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": ["sqs:GetQueueAttributes"],
                        "Resource": queue_url,
                            }]
                    remove-statements: '*'
    """
    permissions = ('sqs:SetQueueAttributes', 'sqs:GetQueueAttributes')

    def process(self, resources):
        results = []
        client = local_session(self.manager.session_factory).client('sqs')
        for r in resources:
            policy = json.loads(r.get('Policy') or '{}')
            policy_statements = policy.setdefault('Statement', [])

            new_policy, removed = self.remove_statements(
                policy_statements, r, CrossAccountAccessFilter.annotation_key)
            if new_policy is None:
                new_policy = policy_statements
            new_policy, added = self.add_statements(new_policy)

            if not removed and not added:
                continue

            results += {
                'Name': r['QueueUrl'],
                'State': 'PolicyModified',
                'Statements': new_policy
            }

            policy['Statement'] = new_policy
            client.set_queue_attributes(
                QueueUrl=r['QueueUrl'],
                Attributes={'Policy': json.dumps(policy)}
            )
        return results


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
                  - type: set-encryption
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
        period={'type': 'integer', 'minimum': 60, 'maximum': 1209600})
    permissions = ('sqs:SetQueueAttributes',)

    def process(self, queues):
        client = local_session(self.manager.session_factory).client('sqs')
        period = str(self.data.get('period', 345600))
        for q in queues:
            client.set_queue_attributes(
                QueueUrl=q['QueueUrl'],
                Attributes={
                    'MessageRetentionPeriod': period})
