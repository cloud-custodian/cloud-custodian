# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
from botocore.exceptions import ClientError
from c7n.manager import resources
from c7n.actions import BaseAction, RemovePolicyBase
from c7n.exceptions import PolicyValidationError
from c7n.filters import iamaccess
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource
from c7n.filters.kms import KmsRelatedFilter
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction, Action
from c7n.utils import local_session, type_schema, jmespath_search
from c7n.filters.policystatement import HasStatementFilter
from c7n.filters.core import ValueFilter


class DescribeSecret(DescribeSource):

    def _augment_secret(self, secret, client):
        detail_op, param_name, param_key, _ = self.manager.resource_type.detail_spec
        op = getattr(client, detail_op)
        kw = {param_name: secret[param_key]}

        try:
            secret.update(self.manager.retry(
                op, **kw
            ))
        except ClientError as e:
            code = e.response['Error']['Code']
            if code != 'AccessDeniedException':
                raise
            # Same logic as S3 augment: describe is expected to be restricted
            # by resource-based policies
            self.manager.log.warning(
                "Secret:%s unable to invoke method:%s error:%s ",
                secret[param_key], detail_op, e.response['Error']['Message']
            )
            secret.setdefault('c7n:DeniedMethods', []).append(detail_op)

    def augment(self, secrets):
        client = local_session(self.manager.session_factory).client(
            self.manager.resource_type.service
        )
        with self.manager.executor_factory(max_workers=self.manager.max_workers) as w:
            for s in secrets:
                w.submit(self._augment_secret, s, client)

        return secrets


@resources.register('secrets-manager')
class SecretsManager(QueryResourceManager):

    permissions = ('secretsmanager:ListSecrets', 'secretsmanager:DescribeSecret')

    class resource_type(TypeInfo):
        service = 'secretsmanager'
        enum_spec = ('list_secrets', 'SecretList', None)
        detail_spec = ('describe_secret', 'SecretId', 'Name', None)
        config_type = cfn_type = 'AWS::SecretsManager::Secret'
        name = id = 'Name'
        arn = 'ARN'

    source_mapping = {
        'describe': DescribeSecret
    }


SecretsManager.filter_registry.register('marked-for-op', TagActionFilter)


@SecretsManager.filter_registry.register('cross-account')
class CrossAccountAccessFilter(iamaccess.CrossAccountAccessFilter):

    policy_annotation = "c7n:AccessPolicy"
    permissions = ("secretsmanager:GetResourcePolicy",)

    def process(self, resources, event=None):
        self.client = local_session(self.manager.session_factory).client('secretsmanager')
        return super(CrossAccountAccessFilter, self).process(resources)

    def get_resource_policy(self, r):
        if self.policy_annotation in r:
            return r[self.policy_annotation]
        r[self.policy_annotation] = p = self.client.get_resource_policy(
            SecretId=r['Name']).get('ResourcePolicy', None)
        return p


@SecretsManager.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):
    RelatedIdsExpression = 'KmsKeyId'


@SecretsManager.filter_registry.register('has-statement')
class HasStatementFilter(HasStatementFilter):

    def get_std_format_args(self, secret):
        return {
            'secret_arn': secret['ARN'],
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region
        }

    def process(self, resources, event=None):
        self.client = local_session(self.manager.session_factory).client('secretsmanager')
        for r in resources:
            try:
                policy = self.client.get_resource_policy(SecretId=r['Name'])
                if policy.get('ResourcePolicy'):
                    r['Policy'] = policy['ResourcePolicy']
            except self.client.exceptions.ResourceNotFoundException:
                continue

        return list(filter(None, map(self.process_resource, resources)))


@SecretsManager.filter_registry.register('replica-attribute')
class ReplicaAttributeFilter(ValueFilter):
    """Filter secrets based on an attribute in any replica (not primary).

    This filter will fetch replica details on demand, annotate the resource,
    and then use ValueFilter's match logic on replicas only.

    :example:

    .. code-block:: yaml

        policies:
          - name: secretsmanager-replica-lastaccessed
            resource: aws.secrets-manager
            filters:
              - type: replica-attribute
                key: LastAccessedDate
                op: ge
                value: '2023-01-01'
                value_type: date
    """

    schema = type_schema(
        'replica-attribute',
        rinherit=ValueFilter.schema
    )
    permissions = ('secretsmanager:DescribeSecret',)

    def process(self, resources, event=None):
        session_factory = self.manager.session_factory
        service = self.manager.resource_type.service

        # Cache clients by region to avoid creating multiple clients for the same region
        client_cache = {}

        for r in resources:
            # Always fetch and annotate replica details when this filter is invoked
            fetched_replicas = []
            for replica in r.get('ReplicationStatus', []):
                region = replica.get('Region')
                # Use cached client if available
                if region not in client_cache:
                    client_cache[region] = local_session(session_factory).client(
                        service, region_name=region
                    )
                replica_client = client_cache[region]
                try:
                    detail_op, param_name, param_key, _ = self.manager.resource_type.detail_spec
                    op_func = getattr(replica_client, detail_op)
                    kw = {param_name: r[param_key]}
                    replica_detail = self.manager.retry(op_func, **kw)
                    replica_detail['Region'] = region
                    fetched_replicas.append(replica_detail)
                except ClientError as e:
                    self.manager.log.warning(
                        "Replica Secret:%s in region:%s unable to invoke method:%s error:%s ",
                        r[param_key], region, detail_op, e.response['Error']['Message']
                    )
            if fetched_replicas:
                r['c7n:Replicas'] = fetched_replicas

        matched = []
        for r in resources:
            # Only check already-fetched replicas, not the primary
            for replica in r.get('c7n:Replicas', []):
                if self.match(replica):
                    matched.append(r)
                    break
        return matched


@SecretsManager.filter_registry.register('secret-current-version')
class SecretVersionFilter(ValueFilter):
    """Filter secrets based on attributes of their current (AWSCURRENT) version.

    The filter retrieves the version metadata for the AWSCURRENT labeled version and
    makes all its attributes available for filtering.

    :example:

    .. code-block:: yaml

        policies:
            - name: current-secret-version-age
              resource: aws.secrets-manager
              filters:
                - type: secret-current-version
                  key: CreatedDate
                  op: gt
                  value: 90
                  value_type: age
    """
    schema = type_schema(
        'secret-current-version',
        rinherit=ValueFilter.schema
    )
    permissions = ('secretsmanager:ListSecretVersionIds',)
    annotation_key = 'c7n:CurrentSecretVersion'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('secretsmanager')

        for r in resources:
            if self.annotation_key not in r:
                versions = self.manager.retry(
                    client.list_secret_version_ids,
                    SecretId=r['ARN'],
                    ignore_err_codes=('ResourceNotFoundException',)
                )
                if versions:
                    current_versions = [
                        v for v in versions.get('Versions', [])
                        if 'AWSCURRENT' in v.get('VersionStages', [])
                    ]
                    r[self.annotation_key] = current_versions
        return list(filter(None, map(self.process_resource, resources)))

    def process_resource(self, resource):
        cv = resource.get(self.annotation_key, [])
        if cv and self.match(cv[0]):
            return resource
        return None


@SecretsManager.action_registry.register('tag')
class TagSecretsManagerResource(Tag):
    """Action to create tag(s) on a Secret resource

    :example:

    .. code-block:: yaml

        policies:
            - name: tag-secret
              resource: secrets-manager
              actions:
                - type: tag
                  key: tag-key
                  value: tag-value
    """

    permissions = ('secretsmanager:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        for r in resources:
            tags = {t['Key']: t['Value'] for t in r.get('Tags', ())
                    if not t['Key'].startswith('aws:')}
            for t in new_tags:
                tags[t['Key']] = t['Value']
            formatted_tags = [{'Key': k, 'Value': v} for k, v in tags.items()]
            client.tag_resource(SecretId=r['ARN'], Tags=formatted_tags)


@SecretsManager.action_registry.register('remove-tag')
class RemoveTagSecretsManagerResource(RemoveTag):
    """Action to remove tag(s) on a Secret resource

    :example:

    .. code-block:: yaml

        policies:
            - name: untag-secret
              resource: secrets-manager
              actions:
                - type: remove-tag
                  tags: ['tag-to-be-removed']
    """

    permissions = ('secretsmanager:UntagResource',)

    def process_resource_set(self, client, resources, keys):
        for r in resources:
            client.untag_resource(SecretId=r['ARN'], TagKeys=keys)


@SecretsManager.action_registry.register('mark-for-op')
class MarkSecretForOp(TagDelayedAction):
    """Action to mark a Secret resource for deferred action :example:

    .. code-block:: yaml

        policies:
            - name: mark-secret-for-delete
              resource: secrets-manager
              actions:
                - type: mark-for-op
                  op: tag
                  days: 1
    """


@SecretsManager.action_registry.register('delete')
class DeleteSecretsManager(BaseAction):
    """Delete a secret and all of its versions.
    The recovery window is the number of days from 7 to 30 that
    Secrets Manager waits before permanently deleting the secret
    with default as 30

    :example:

    .. code-block:: yaml

            policies:
              - name: delete-cross-account-secrets
                resource: aws.secrets-manager
                filters:
                  - type: cross-account
                actions:
                  - type: delete
                    recovery_window: 10
    """

    schema = type_schema('delete', recovery_window={'type': 'integer'})
    permissions = ('secretsmanager:DeleteSecret',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('secretsmanager')

        for r in resources:
            if 'ReplicationStatus' in r:
                rep_regions = jmespath_search('ReplicationStatus[*].Region', r)
                self.manager.retry(client.remove_regions_from_replication,
                  SecretId=r['ARN'], RemoveReplicaRegions=rep_regions)
            self.manager.retry(client.delete_secret,
              SecretId=r['ARN'], RecoveryWindowInDays=self.data.get('recovery_window', 30))


@SecretsManager.action_registry.register('remove-statements')
class SecretsManagerRemovePolicyStatement(RemovePolicyBase):
    """
    Action to remove resource based policy statements from secrets manager

    :example:

    .. code-block:: yaml

        policies:
          - name: secrets-manager-cross-account
            resource: aws.secrets-manager
            filters:
              - type: cross-account
            actions:
              - type: remove-statements
                statement_ids: matched
    """

    permissions = ("secretsmanager:DeleteResourcePolicy", "secretsmanager:PutResourcePolicy",)

    def validate(self):
        for f in self.manager.iter_filters():
            if isinstance(f, CrossAccountAccessFilter):
                return self
        raise PolicyValidationError(
            '`remove-statements` may only be used in '
            'conjunction with `cross-account` filter on %s' % (self.manager.data,))

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('secretsmanager')
        for r in resources:
            try:
                self.process_resource(client, r)
            except Exception:
                self.log.exception("Error processing secretsmanager:%s", r['ARN'])

    def process_resource(self, client, resource):
        p = json.loads(resource.get('c7n:AccessPolicy'))
        if p is None:
            return

        statements, found = self.process_policy(
            p, resource, CrossAccountAccessFilter.annotation_key)

        if not found:
            return
        if statements:
            client.put_resource_policy(
                SecretId=resource['ARN'],
                ResourcePolicy=json.dumps(p)
            )
        else:
            client.delete_resource_policy(SecretId=resource['ARN'])


@SecretsManager.action_registry.register('set-encryption')
class SetEncryptionAction(Action):
    """
    Set kms encryption key for secrets, key supports ARN, ID, or alias

    :example:

    .. code-block:: yaml

        policies:
            - name: set-secret-encryption
              resource: aws.secrets-manager
              actions:
                - type: set-encryption
                  key: alias/foo/bar
    """

    schema = type_schema('set-encryption', key={'type': 'string'}, required=['key'])
    permissions = ('secretsmanager:UpdateSecret', )

    def process(self, resources):
        key = self.data['key']
        client = local_session(self.manager.session_factory).client('secretsmanager')
        for r in resources:
            client.update_secret(
                SecretId=r['Name'],
                KmsKeyId=key
            )
