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
import logging

from c7n.filters import Filter

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session, type_schema

log = logging.getLogger('custodian.kms')


@resources.register('kms')
class KeyAlias(QueryResourceManager):

    class Meta(object):
        service = 'kms'
        type = 'key-alias'
        enum_spec = ('list_aliases', 'Aliases', None)
        name = "AliasName"
        id = "AliasArn"

    resource_type = Meta

    def augment(self, resources):
        return [r for r in resources if 'TargetKeyId' in r]


@resources.register('kms-key')
class Key(QueryResourceManager):

    class Meta(object):
        service = 'kms'
        type = "key"
        enum_spec = ('list_keys', 'Keys', None)
        name = "KeyId"
        id = "KeyArn"

    resource_type = Meta


@KeyAlias.filter_registry.register('grant-count')
class GrantCount(Filter):

    schema = type_schema(
        'grant-count', min={'type': 'integer', 'minimum': 0})

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
