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

from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry, Filter

from c7n.manager import ResourceManager, resources
from c7n.utils import local_session, type_schema

log = logging.getLogger('custodian.kms')

filters = FilterRegistry('kms.filters')
actions = ActionRegistry('kms.actions')


@resources.register('kms')
class KMS(ResourceManager):

    filter_registry = filters
    action_registry = actions

    def resources(self):
        c = self.session_factory().client('kms')
        query = self.resource_query()  # FIXME: Not used
        self.log.info("Querying kms keys")
        keys = c.list_aliases()['Aliases']
        original_count = len(keys)
        keys = [k for k in keys if 'TargetKeyId' in k]
        log.debug(
            "Filtered aliases without targets from %d to %d" % (
                original_count, len(keys)))
        return self.filter_resources(keys)


@filters.register('grant-count')
class GrantCount(Filter):

    schema = type_schema(
        'grant-count', min={'type': 'integer', 'minimum': 0})

    def process(self, keys, event=None):
        with self.executor_factory(max_workers=10) as w:
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
