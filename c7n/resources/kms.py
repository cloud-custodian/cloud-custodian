# Copyright 2016 Capital One Services, LLC
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

import logging

from c7n.filters import Filter, CrossAccountAccessFilter, ValueFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema

log = logging.getLogger('custodian.kms')


class KeyBase(object):

    permissions = ('kms:ListResourceTags',)

    def augment(self, resources):
        client = local_session(
            self.session_factory).client('kms')
        for r in resources:
            key_id = r.get('AliasArn') or r.get('KeyArn')
            info = client.describe_key(KeyId=key_id)['KeyMetadata']
            r.update(info)

            tags = client.list_resource_tags(KeyId=key_id)['Tags']
            tag_list = []
            for t in tags:
                tag_list.append({'Key': t['TagKey'], 'Value': t['TagValue']})
            r['Tags'] = tag_list
        return resources


@resources.register('kms')
class KeyAlias(KeyBase, QueryResourceManager):

    class resource_type(object):
        service = 'kms'
        type = 'key-alias'
        enum_spec = ('list_aliases', 'Aliases', None)
        name = "AliasName"
        id = "AliasArn"
        dimension = None

    def augment(self, resources):
        return [r for r in resources if 'TargetKeyId' in r]


@resources.register('kms-key')
class Key(KeyBase, QueryResourceManager):

    class resource_type(object):
        service = 'kms'
        type = "key"
        enum_spec = ('list_keys', 'Keys', None)
        name = "KeyId"
        id = "KeyArn"
        dimension = None


@Key.filter_registry.register('key-rotation-status')
class KeyRotationStatus(ValueFilter):
    """Filters KMS keys by the rotation status

    :example:

        .. code-block: yaml

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
            resource['KeyRotationEnabled'] = client.get_key_rotation_status(
                KeyId=resource['KeyId'])

        with self.executor_factory(max_workers=2) as w:
            query_resources = [
                r for r in resources if 'KeyRotationEnabled' not in r]
            self.log.debug(
                "Querying %d kms-keys' rotation status" % len(query_resources))
            list(w.map(_key_rotation_status, query_resources))

        return [r for r in resources if self.match(r['KeyRotationEnabled'])]


@Key.filter_registry.register('cross-account')
@KeyAlias.filter_registry.register('cross-account')
class KMSCrossAccountAccessFilter(CrossAccountAccessFilter):
    """Filter KMS keys which have cross account permissions

    :example:

        .. code-block: yaml

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
            resources = filter(None, w.map(_augment, resources))

        return super(KMSCrossAccountAccessFilter, self).process(
            resources, event)


@KeyAlias.filter_registry.register('grant-count')
class GrantCount(Filter):
    """Filters KMS key grants

    This can be used to ensure issues around grant limits are monitored

    :example:

        .. code-block: yaml

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
            return filter(None, (w.map(self.process_key, keys)))

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
