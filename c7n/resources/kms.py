# Copyright 2015-2017 Capital One Services, LLC
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
from concurrent.futures import as_completed

import json
import logging

from c7n.actions import RemovePolicyBase, BaseAction
from c7n.filters import Filter, CrossAccountAccessFilter, ValueFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema
from c7n.tags import universal_augment

log = logging.getLogger('custodian.kms')


@resources.register('kms')
class KeyAlias(QueryResourceManager):

    class resource_type(object):
        service = 'kms'
        type = 'key-alias'
        enum_spec = ('list_aliases', 'Aliases', None)
        name = "AliasName"
        id = "AliasArn"
        dimension = None
        filter_name = None

    def augment(self, resources):
        return [r for r in resources if 'TargetKeyId' in r]


@resources.register('kms-key')
class Key(QueryResourceManager):

    class resource_type(object):
        service = 'kms'
        type = "key"
        enum_spec = ('list_keys', 'Keys', None)
        name = "KeyId"
        id = "KeyArn"
        dimension = None
        filter_name = None
        universal_taggable = True

    def augment(self, resources):
        client = local_session(
            self.session_factory).client('kms')

        for r in resources:
            try:
                key_id = r.get('KeyArn')
                info = client.describe_key(KeyId=key_id)['KeyMetadata']
                r.update(info)

            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDeniedException':
                    self.log.warning(
                        "Access denied when describing key:%s",
                        key_id)
                else:
                    raise

        return universal_augment(self, resources)


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
    permissions = ('kms:GetKeyRotationStatus',)

    def process(self, resources, event=None):

        def _key_rotation_status(resource):
            client = local_session(self.manager.session_factory).client('kms')
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
              - name: kms-key-cross-account
                resource: kms-key
                filters:
                  - type: cross-account
    """
    permissions = ('kms:GetKeyPolicy',)

    def process(self, resources, event=None):
        def _augment(r):
            client = local_session(
                self.manager.session_factory).client('kms')
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
        with self.executor_factory(max_workers=3) as w:
            return list(filter(None, (w.map(self.process_key, keys))))

    def process_key(self, key):
        client = local_session(self.manager.session_factory).client('kms')
        p = client.get_paginator('list_grants')
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

    .. code-block: yaml

        policy:
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
    schema = type_schema(
        'set-rotation',
        state={'type': 'boolean'})

    def set_rotation(self, key):
        client = local_session(self.manager.session_factory).client('kms')
        if self.data.get('state', True):
            client.enable_key_rotation(KeyId=key['KeyId'])
            return
        client.disable_key_rotation(KeyId=key['KeyId'])

    def process(self, keys):
        for k in keys:
            futures = {}

            with self.executor_factory(max_workers=2) as w:
                futures[w.submit(self.set_rotation, k)] = k

            for f in as_completed(futures):
                if f.exception():
                    key = futures[f]
                    self.log.error('error setting key rotation on %s: %s' % (
                        key['Arn'], f.exception()))
