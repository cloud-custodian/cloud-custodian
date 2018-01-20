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

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry

from c7n.manager import resources, ResourceManager
from c7n import query, utils


@resources.register('rest-account')
class RestAccount(ResourceManager):
    filter_registry = FilterRegistry('rest-account.filters')
    action_registry = ActionRegistry('rest-account.actions')

    class resource_type(object):
        service = 'apigateway'
        name = id = 'account_id'
        dimensions = None

    @classmethod
    def get_permissions(cls):
        return ('apigateway:GET',)

    def get_model(self):
        return self.resource_type

    def _get_account(self):
        client = utils.local_session(self.session_factory).client('apigateway')
        account = client.get_account()
        account.pop('ResponseMetadata', None)
        account['account_id'] = 'apigw-settings'
        return account

    def resources(self):
        return self.filter_resources([self._get_account()])

    def get_resources(self, resource_ids):
        return [self._get_account()]


OP_SCHEMA = {
    'type': 'object',
    'required': ['op', 'path'],
    'additonalProperties': False,
    'properties': {
        'op': {'enum': ['add', 'remove', 'update', 'copy', 'replace', 'test']},
        'path': {'type': 'string'},
        'value': {'type': 'string'},
        'from': {'type': 'string'}
        }
    }


@RestAccount.action_registry.register('update')
class UpdateAccount(BaseAction):

    permissions = ('apigateway:PATCH',)
    schema = utils.type_schema(
        'update',
        patch={'type': 'array', 'items': OP_SCHEMA},
        required=['patch'])

    def process(self, resources):
        client = utils.local_session(
            self.manager.session_factory).client('apigateway')
        client.update_account(patchOperations=self.data['patch'])


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

    child_source = 'describe-rest-stage'

    class resource_type(object):
        service = 'apigateway'
        parent_spec = ('rest-api', 'restApiId')
        enum_spec = ('get_stages', 'item', None)
        name = id = 'stageName'
        date = 'createdDate'
        dimension = None


@query.sources.register('describe-rest-stage')
class DescribeRestStage(query.ChildDescribeSource):

    def get_query(self):
        query = super(DescribeRestStage, self).get_query()
        query.capture_parent_id = True
        return query

    def augment(self, resources):
        results = []
        # Using capture parent id, changes the protocol
        for parent_id, r in resources:
            r['restApiId'] = parent_id
            tags = r.setdefault('Tags', [])
            for k, v in r.pop('tags', {}).items():
                tags.append({
                    'Key': k,
                    'Value': v})
            results.append(r)
        return results


@RestStage.action_registry.register('update')
class UpdateStage(BaseAction):

    permissions = ('apigateway:PATCH',)
    schema = utils.type_schema(
        'update',
        patch={'type': 'array', 'items': OP_SCHEMA},
        required=['patch'])

    def process(self, resources):
        client = utils.local_session(
            self.manager.session_factory).client('apigateway')
        for r in resources:
            client.update_stage(
                restApiId=r['restApiId'],
                stageName=r['stageName'],
                patchOperations=self.data['patch'])


@resources.register('rest-resource')
class RestResource(query.ChildResourceManager):

    class resource_type(object):
        service = 'apigateway'
        parent_spec = ('rest-api', 'restApiId')
        enum_spec = ('get_resources', 'items', None)
        id = 'id'
        name = 'path'
        dimension = None


#@resources.register('rest-method')
#class RestMethod(query.ChildResourceManager):
#    class resource_type(object):
#        service = 'apigateway'
#        parent_spec = ('rest-resource')
