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


from c7n.actions import ActionRegistry
from c7n.filters import FilterRegistry

from c7n.manager import resources
from c7n import query, utils


@resources.register('rest-account')
class RestAccount(resources.ResourceManager):
    filter_registry = FilterRegistry()
    action_registry = ActionRegistry()

    class resource_type(object):
        name = id = 'fake-id'
        dimensions = None

    @classmethod
    def get_permissions(cls):
        return ('iam:ListAccountAliases',)

    def get_model(self):
        return self.resource_type

    def _get_account(self):
        client = utils.local_session(self.session_factory).client('apigateway')
        account = client.get_account()
        account['fake-id'] = 'apigw-settings'
        return account

    def resources(self):
        return self.filter_resources([self._get_account()])

    def get_resources(self, resource_ids):
        return [self._get_account()]


@resources.register('rest-api')
class RestAPI(query.QueryResourceManager):

    class resource_type(object):
        service = 'apigateway'
        type = 'restapis'
        enum_spec = ('get_rest_apis', 'items', None)
        id = 'id'
        filter_name = None
        name = 'name'
        date = 'createdDate'
        dimension = 'GatewayName'


@resources.register('rest-stage')
class RestStage(query.ChildResourceManager):

    class resource_type(object):
        service = 'apigateway'
        parent_spec = ('rest-api', 'restApiId')
        enum_spec = ('get_stages', 'item', None)
        name = id = 'stageName'
        date = 'createdDate'
        dimension = None

    def augment(self, resources):
        # Normalize stage tags to look like other resources
        for r in resources:
            tags = r.setdefault('Tags', [])
            for k, v in r.pop('tags', {}).items():
                tags.append({
                    'Key': k,
                    'Value': v})
        return resources
