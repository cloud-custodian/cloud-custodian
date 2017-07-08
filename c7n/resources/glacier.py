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

from botocore.exceptions import ClientError

from c7n.actions import ActionRegistry, AutoTagUser
from c7n.filters import FilterRegistry, CrossAccountAccessFilter
from c7n.query import QueryResourceManager
from c7n.manager import resources
from c7n.tags import (
    TagActionFilter, UniversalTag, UniversalUntag, UniversalTagDelayedAction)
from c7n.utils import get_retry, local_session


@resources.register('glacier')
class Glacier(QueryResourceManager):

    filter_registry = FilterRegistry('glacier.filters')
    filter_registry.register('marked-for-op', TagActionFilter)

    action_registry = ActionRegistry('glacier.actions')
    action_registry.register('auto-tag-user', AutoTagUser)
    action_registry.register('mark', UniversalTag)
    action_registry.register('tag', UniversalTag)
    action_registry.register('mark-for-op', UniversalTagDelayedAction)
    action_registry.register('remove-tag', UniversalUntag)
    action_registry.register('unmark', UniversalUntag)
    action_registry.register('untag', UniversalUntag)

    permissions = ('glacier:ListTagsForVault',)
    retry = staticmethod(get_retry(('Throttled',)))

    class resource_type(object):
        service = 'glacier'
        enum_spec = ('list_vaults', 'VaultList', None)
        name = "VaultName"
        id = "VaultARN"
        dimension = None

    def augment(self, resources):
        def process_tags(resource):
            client = local_session(self.session_factory).client('glacier')
            tag_dict = self.retry(
                client.list_tags_for_vault,
                vaultName=resource[self.get_model().name])['Tags']
            tag_list = []
            for k, v in tag_dict.items():
                tag_list.append({'Key': k, 'Value': v})
            resource['Tags'] = tag_list
            return resource

        with self.executor_factory(max_workers=2) as w:
            return list(w.map(process_tags, resources))


@Glacier.filter_registry.register('cross-account')
class GlacierCrossAccountAccessFilter(CrossAccountAccessFilter):
    """Filter to return all glacier vaults with cross account access permissions

    The whitelist parameter will omit the accounts that match from the return

    :example:

        .. code-block:

            policies:
              - name: glacier-cross-account
                resource: glacier
                filters:
                  - type: cross-account
                    whitelist:
                      - permitted-account-01
                      - permitted-account-02
    """
    permissions = ('glacier:GetVaultAccessPolicy',)

    def process(self, resources, event=None):
        def _augment(r):
            client = local_session(
                self.manager.session_factory).client('glacier')
            try:
                r['Policy'] = client.get_vault_access_policy(
                    vaultName=r['VaultName'])['policy']['Policy']
                return r
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDeniedException':
                    self.log.warning(
                        "Access denied getting policy glacier:%s",
                        r['FunctionName'])

        self.log.debug("fetching policy for %d glacier" % len(resources))
        with self.executor_factory(max_workers=3) as w:
            resources = filter(None, w.map(_augment, resources))

        return super(GlacierCrossAccountAccessFilter, self).process(
            resources, event)
