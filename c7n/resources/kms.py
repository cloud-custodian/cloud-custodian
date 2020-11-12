# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.exceptions import ClientError

import json

from c7n.actions import RemovePolicyBase, BaseAction
from c7n.filters import Filter, CrossAccountAccessFilter, ValueFilter
from c7n.manager import resources
from c7n.query import (
    ConfigSource, DescribeSource, QueryResourceManager, RetryPageIterator, TypeInfo)
from c7n.utils import local_session, type_schema, select_keys
from c7n.tags import universal_augment

from .securityhub import PostFinding


@resources.register('kms')
class KeyAlias(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'kms'
        arn_type = 'alias'
        enum_spec = ('list_aliases', 'Aliases', None)
        name = "AliasName"
        id = "AliasArn"
        cfn_type = 'AWS::KMS::Alias'

    def augment(self, resources):
        return [r for r in resources if 'TargetKeyId' in r]


class DescribeKey(DescribeSource):

    FetchThreshold = 10  # ie should we describe all keys or just fetch them directly

    def get_resources(self, ids, cache=True):
        # this forms a threshold beyond which we'll fetch individual keys of interest.
        # else we'll need to fetch through the full set and client side filter.
        if len(ids) < self.FetchThreshold:
            client = local_session(self.manager.session_factory).client('kms')
            results = []
            for rid in ids:
                try:
                    results.append(
                        self.manager.retry(
                            client.describe_key,
                            KeyId=rid)['KeyMetadata'])
                except client.exceptions.NotFoundException:
                    continue
            return results
        return super().get_resources(ids, cache)

    def augment(self, resources):
        aliases = KeyAlias(self.manager.ctx, {}).resources()
        alias_map = {}
        for a in aliases:
            key_id = a['TargetKeyId']
            alias_map[key_id] = alias_map.get(key_id, []) + [a['AliasName']]

        client = local_session(self.manager.session_factory).client('kms')
        for r in resources:
            try:
                key_id = r.get('KeyId')
                key_arn = r.get('KeyArn', key_id)
                info = client.describe_key(KeyId=key_arn)['KeyMetadata']
                if key_id in alias_map:
                    info['AliasNames'] = alias_map[key_id]
                r.update(info)
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDeniedException':
                    self.manager.log.warning(
                        "Access denied when describing key:%s",
                        key_id)
                else:
                    raise

        return universal_augment(self.manager, resources)


@resources.register('kms-key')
class Key(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'kms'
        arn_type = "key"
        enum_spec = ('list_keys', 'Keys', None)
        name = id = "KeyId"
        arn = 'Arn'
        universal_taggable = True
        cfn_type = config_type = 'AWS::KMS::Key'

    source_mapping = {
        'config': ConfigSource,
        'describe': DescribeKey
    }


@Key.filter_registry.register('key-rotation-status')
class KeyRotationStatus(ValueFilter):
    """Filters KMS keys by the rotation status

    :example:

    .. code-block:: yaml

            policies:
              - name: kms-key-disabled-rotation
                resource: kms-key
                filters:
                  - type: key-rotation-status
                    key: KeyRotationEnabled
                    value: false
    """

    schema = type_schema('key-rotation-status', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('kms:GetKeyRotationStatus',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('kms')

        def _key_rotation_status(resource):
            try:
                resource['KeyRotationEnabled'] = client.get_key_rotation_status(
                    KeyId=resource['KeyId'])
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDeniedException':
                    self.log.warning(
                        "Access denied when getting rotation status on key:%s",
                        resource.get('KeyArn'))
                else:
                    raise

        with self.executor_factory(max_workers=2) as w:
            query_resources = [
                r for r in resources if 'KeyRotationEnabled' not in r]
            self.log.debug(
                "Querying %d kms-keys' rotation status" % len(query_resources))
            list(w.map(_key_rotation_status, query_resources))

        return [r for r in resources if self.match(
                r.get('KeyRotationEnabled', {}))]


@Key.filter_registry.register('cross-account')
@KeyAlias.filter_registry.register('cross-account')
class KMSCrossAccountAccessFilter(CrossAccountAccessFilter):
    """Filter KMS keys which have cross account permissions

    :example:

    .. code-block:: yaml

            policies:
              - name: check-kms-key-cross-account
                resource: kms-key
                filters:
                  - type: cross-account
    """
    permissions = ('kms:GetKeyPolicy',)

    def process(self, resources, event=None):
        client = local_session(
            self.manager.session_factory).client('kms')

        def _augment(r):
            key_id = r.get('TargetKeyId', r.get('KeyId'))
            assert key_id, "Invalid key resources %s" % r
            r['Policy'] = client.get_key_policy(
                KeyId=key_id, PolicyName='default')['Policy']
            return r

        self.log.debug("fetching policy for %d kms keys" % len(resources))
        with self.executor_factory(max_workers=1) as w:
            resources = list(filter(None, w.map(_augment, resources)))

        return super(KMSCrossAccountAccessFilter, self).process(
            resources, event)


@KeyAlias.filter_registry.register('grant-count')
class GrantCount(Filter):
    """Filters KMS key grants

    This can be used to ensure issues around grant limits are monitored

    :example:

    .. code-block:: yaml

            policies:
              - name: kms-grants
                resource: kms
                filters:
                  - type: grant-count
                    min: 100
    """

    schema = type_schema(
        'grant-count', min={'type': 'integer', 'minimum': 0})
    permissions = ('kms:ListGrants',)

    def process(self, keys, event=None):
        client = local_session(self.manager.session_factory).client('kms')
        results = []
        for k in keys:
            results.append(self.process_key(client, k))
        return [r for r in results if r]

    def process_key(self, client, key):
        p = client.get_paginator('list_grants')
        p.PAGE_ITERATOR_CLS = RetryPageIterator
        grant_count = 0
        for rp in p.paginate(KeyId=key['TargetKeyId']):
            grant_count += len(rp['Grants'])
        key['GrantCount'] = grant_count

        grant_threshold = self.data.get('min', 5)
        if grant_count < grant_threshold:
            return None

        self.manager.ctx.metrics.put_metric(
            "ExtantGrants", grant_count, "Count",
            Scope=key['AliasName'][6:])

        return key


class ResourceKmsKeyAlias(ValueFilter):

    schema = type_schema('kms-alias', rinherit=ValueFilter.schema)
    schema_alias = False

    def get_permissions(self):
        return KeyAlias(self.manager.ctx, {}).get_permissions()

    def get_matching_aliases(self, resources, event=None):
        key_aliases = KeyAlias(self.manager.ctx, {}).resources()
        key_aliases_dict = {a['TargetKeyId']: a for a in key_aliases}

        matched = []
        for r in resources:
            if r.get('KmsKeyId'):
                r['KeyAlias'] = key_aliases_dict.get(
                    r.get('KmsKeyId').split("key/", 1)[-1])
                if self.match(r.get('KeyAlias')):
                    matched.append(r)
        return matched


@Key.action_registry.register('remove-statements')
@KeyAlias.action_registry.register('remove-statements')
class RemovePolicyStatement(RemovePolicyBase):
    """Action to remove policy statements from KMS

    :example:

    .. code-block:: yaml

           policies:
              - name: kms-key-cross-account
                resource: kms-key
                filters:
                  - type: cross-account
                actions:
                  - type: remove-statements
                    statement_ids: matched
    """

    permissions = ('kms:GetKeyPolicy', 'kms:PutKeyPolicy')

    def process(self, resources):
        results = []
        client = local_session(self.manager.session_factory).client('kms')
        for r in resources:
            key_id = r.get('TargetKeyId', r.get('KeyId'))
            assert key_id, "Invalid key resources %s" % r
            try:
                results += filter(None, [self.process_resource(client, r, key_id)])
            except Exception:
                self.log.exception(
                    "Error processing sns:%s", key_id)
        return results

    def process_resource(self, client, resource, key_id):
        if 'Policy' not in resource:
            try:
                resource['Policy'] = client.get_key_policy(
                    KeyId=key_id, PolicyName='default')['Policy']
            except ClientError as e:
                if e.response['Error']['Code'] != "NotFoundException":
                    raise
                resource['Policy'] = None

        if not resource['Policy']:
            return

        p = json.loads(resource['Policy'])
        statements, found = self.process_policy(
            p, resource, CrossAccountAccessFilter.annotation_key)

        if not found:
            return

        # NB: KMS supports only one key policy 'default'
        # http://docs.aws.amazon.com/kms/latest/developerguide/programming-key-policies.html#list-policies
        client.put_key_policy(
            KeyId=key_id,
            PolicyName='default',
            Policy=json.dumps(p)
        )

        return {'Name': key_id,
                'State': 'PolicyRemoved',
                'Statements': found}


@Key.action_registry.register('set-rotation')
class KmsKeyRotation(BaseAction):
    """Toggle KMS key rotation

    :example:

    .. code-block:: yaml

        policies:
          - name: enable-cmk-rotation
            resource: kms-key
            filters:
              - type: key-rotation-status
                key: KeyRotationEnabled
                value: False
            actions:
              - type: set-rotation
                state: True
    """
    permissions = ('kms:EnableKeyRotation',)
    schema = type_schema('set-rotation', state={'type': 'boolean'})

    def process(self, keys):
        client = local_session(self.manager.session_factory).client('kms')
        for k in keys:
            if self.data.get('state', True):
                client.enable_key_rotation(KeyId=k['KeyId'])
                continue
            client.disable_key_rotation(KeyId=k['KeyId'])


@KeyAlias.action_registry.register('post-finding')
@Key.action_registry.register('post-finding')
class KmsPostFinding(PostFinding):

    resource_type = 'AwsKmsKey'

    def format_resource(self, r):
        if 'TargetKeyId' in r:
            resolved = self.manager.get_resource_manager(
                'kms-key').get_resources([r['TargetKeyId']])
            if not resolved:
                return
            r = resolved[0]
            r[self.manager.resource_type.id] = r['KeyId']
        envelope, payload = self.format_envelope(r)
        payload.update(self.filter_empty(
            select_keys(r, [
                'AWSAccount', 'CreationDate', 'KeyId',
                'KeyManager', 'Origin', 'KeyState'])))
        return envelope
