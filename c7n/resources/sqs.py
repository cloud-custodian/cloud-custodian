# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

import json
import re

from c7n.actions import RemovePolicyBase, ModifyPolicyBase
from c7n.filters import CrossAccountAccessFilter, MetricsFilter
from c7n.filters.core import Filter
from c7n.filters.kms import KmsRelatedFilter
import c7n.filters.policystatement as polstmt_filter
from c7n.manager import resources
from c7n.utils import local_session
from c7n.query import ConfigSource, DescribeSource, QueryResourceManager, TypeInfo
from c7n.actions import BaseAction
from c7n.utils import type_schema
from c7n.tags import universal_augment

from c7n.resources.aws import Arn
from c7n.resources.securityhub import PostFinding


class DescribeQueue(DescribeSource):

    def augment(self, resources):
        client = self.manager.get_client()

        def _augment(r):
            try:
                queue = self.manager.retry(
                    client.get_queue_attributes,
                    QueueUrl=r,
                    AttributeNames=['All'])['Attributes']
                queue['QueueUrl'] = r
                queue['QueueName'] = queue['QueueArn'].rsplit(':', 1)[-1]
            except ClientError as e:
                if e.response['Error']['Code'] == 'AWS.SimpleQueueService.NonExistentQueue':
                    return
                if e.response['Error']['Code'] == 'AccessDenied':
                    self.manager.log.warning("Denied access to sqs %s" % r)
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
        enum_spec = ('list_queues', 'QueueUrls', {'MaxResults': 1000})
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
        permissions_augment = ("sqs:ListQueueTags",)
        default_report_fields = (
            'QueueArn',
            'CreatedTimestamp',
            'ApproximateNumberOfMessages',
        )

    source_mapping = {
        'describe': DescribeQueue,
        'config': QueueConfigSource
    }

    def get_client(self):
        # Work around the fact that boto picks a legacy endpoint by default
        # which leads to queue urls pointing to legacy instead of standard
        # which is at odds with config's resource id for the queues.
        # additionally we need the standard endpoint to work with vpc endpoints.
        #
        # sqs canonoical endpoints
        #  https://docs.aws.amazon.com/general/latest/gr/sqs-service.html
        # boto3 bug
        #  https://github.com/boto/botocore/issues/2683 - index of several other bugs
        #  https://github.com/boto/boto3/issues/1900
        #
        # boto3 is transitioning to standard urls per https://github.com/boto/botocore/issues/2705
        #
        endpoint = 'https://sqs.{region}.amazonaws.com'.format(region=self.config.region)
        # these only seem to have the legacy endpoints, so fall through to boto behavior.
        if self.config.region in ('cn-north-1', 'cn-northwest-1'):
            endpoint = None
        params = {}
        if endpoint:
            params['endpoint_url'] = endpoint
        return local_session(self.session_factory).client('sqs', **params)

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
        resources = super(SQS, self).get_resources(ids_normalized, cache)
        return [r for r in resources if Arn.parse(r['QueueArn']).resource in ids_normalized]


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


@SQS.filter_registry.register('has-statement')
class HasStatementFilter(polstmt_filter.HasStatementFilter):
    def get_std_format_args(self, queue):
        return {
            'queue_arn': queue['QueueArn'],
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region
        }


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

    permissions = ('sqs:GetQueueAttributes', 'sqs:RemovePermission', 'sqs:SetQueueAttributes')

    def process(self, resources):
        results = []
        client = self.manager.get_client()
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
        _, found = self.process_policy(
            p, resource, CrossAccountAccessFilter.annotation_key)

        if not found:
            return

        # It's generally safer to call remove_permission for each permission we want to remove.
        # However, if any of the permissions we want to remove does not have an Sid (which is
        # possible), it can't be removed individually. In that case, we have to call
        # set_queue_attributes to redefine the whole policy without the perm(s) we want to remove.
        any_missing_sid = any(not f.get('Sid') for f in found)
        if any_missing_sid:
            client.set_queue_attributes(
                QueueUrl=resource['QueueUrl'],
                # process_policy removes the perms we don't want from the p object
                Attributes={'Policy': json.dumps(p)}
            )
        else:
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
        client = self.manager.get_client()
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
        client = self.manager.get_client()
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

    you can also optionally set data key 'reuse-period', or use with
    the service managed encryption by not specifying a key.

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
        **{
            "enabled": {'type': 'boolean'},
            "reuse-period": {'type': 'integer', 'minimum': 60, 'maximum': 86400},
            "key": {'type': 'string'}}
    )

    permissions = ('sqs:SetQueueAttributes',)
    uuid_regex = re.compile('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')

    def process(self, queues):
        # compatibility, if key is given and not arn/key id/ or prefixed with
        # alias, add alias to it.
        key = self.data.get('key', None)
        if (key
            and not key.startswith('alias')
            and not key.startswith('arn:')
                and not self.uuid_regex.search(key)):
            key = "alias/" + key

        client = self.manager.get_client()

        reuse_period = self.data.get('reuse-period', 300)
        params = {}
        if not self.data.get('enabled', True):
            params['SqsManagedSseEnabled'] = 'false'
            params['KmsMasterKeyId'] = ''
        elif self.data.get('enable', True) and not key:
            params['SqsManagedSseEnabled'] = 'true'
            params['KmsMasterKeyId'] = ''
        elif self.data.get('enable', True) and key:
            params['SqsManagedSseEnabled'] = 'false'
            params['KmsMasterKeyId'] = key
            params['KmsDataKeyReusePeriodSeconds'] = str(reuse_period)

        for q in queues:
            self.process_queue(client, q, params)

    def process_queue(self, client, queue, params):
        try:
            client.set_queue_attributes(
                QueueUrl=queue['QueueUrl'],
                Attributes=params
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
        client = self.manager.get_client()
        period = str(self.data.get('period', 345600))
        for q in queues:
            client.set_queue_attributes(
                QueueUrl=q['QueueUrl'],
                Attributes={
                    'MessageRetentionPeriod': period})


@SQS.filter_registry.register('dead-letter')
class DeadLetterFilter(Filter):
    """
    Filter for sqs queues that are dead letter queues

    :example:

    .. code-block:: yaml

        policies:
         - name: find-dead-letter-queues
           resource: aws.sqs
           filters:
             - type: dead-letter
    """

    schema = type_schema('dead-letter')
    permissions = ()

    def process(self, resources, event=None):
        # we need to inspect all the queues regardless of any filters that
        # may have been applied earlier
        all_resources = self.manager.get_resource_manager("sqs").resources()
        all_queue_arn_map = {r['QueueArn']: r for r in all_resources}
        queue_arn_map = {r['QueueArn']: r for r in resources}
        has_redrive = []
        for r in all_resources:
            if r.get("RedrivePolicy"):
                has_redrive.append(r['QueueArn'])
        result = []
        # dead letter queues must exist in the same region and account as the
        # original queue so it should be safe to look for them in our existing
        # resources
        for r in all_resources:
            if r['QueueArn'] in has_redrive:
                queue = all_queue_arn_map[r['QueueArn']]
                target = json.loads(queue['RedrivePolicy']).get('deadLetterTargetArn')
                if queue_arn_map.get(target):
                    result.append(target)
        # in case there are multiple queues pointing at the same dead letter queue
        # we need to only return the unique queues
        return [queue_arn_map[r] for r in set(result)]
