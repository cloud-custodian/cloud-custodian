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

from botocore.exceptions import ClientError

from concurrent.futures import as_completed

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry, ValueFilter
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
        try:
            account = client.get_account()
        except ClientError as e:
            if e.response['Error']['Code'] == 'NotFoundException':
                return []
        account.pop('ResponseMetadata', None)
        account['account_id'] = 'apigw-settings'
        return [account]

    def resources(self):
        return self.filter_resources(self._get_account())

    def get_resources(self, resource_ids):
        return self._get_account()


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
    """Update the cloudwatch role associated to a rest account

    :example:

    .. code-block:: yaml

        policies:
          - name: correct-rest-account-log-role
            resource: rest-account
            filters:
              - cloudwatchRoleArn: arn:aws:iam::000000000000:role/GatewayLogger
            actions:
              - type: update
                patch:
                  - op: replace
                    path: /cloudwatchRoleArn
                    value: arn:aws:iam::000000000000:role/BetterGatewayLogger
    """

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
        parent_spec = ('rest-api', 'restApiId', None)
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
        # Using capture parent, changes the protocol
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
    """Update/remove values of an api stage

    :example:

    .. code-block:: yaml

        policies:
          - name: disable-stage-caching
            resource: rest-stage
            filters:
              - methodSettings."*/*".cachingEnabled: true
            actions:
              - type: update
                patch:
                  - op: replace
                    path: /*/*/caching/enabled
                    value: 'false'
    """

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

    child_source = 'describe-rest-resource'

    class resource_type(object):
        service = 'apigateway'
        parent_spec = ('rest-api', 'restApiId', None)
        enum_spec = ('get_resources', 'items', None)
        id = 'id'
        name = 'path'
        dimension = None


@query.sources.register('describe-rest-resource')
class DescribeRestResource(query.ChildDescribeSource):

    def get_query(self):
        query = super(DescribeRestResource, self).get_query()
        query.capture_parent_id = True
        return query

    def augment(self, resources):
        results = []
        # Using capture parent id, changes the protocol
        for parent_id, r in resources:
            r['restApiId'] = parent_id
            results.append(r)
        return results


ANNOTATION_KEY = 'c7n-matched-resource-methods'


@RestResource.filter_registry.register('rest-method')
class FilterRestMethod(ValueFilter):
    """Filter rest resources based on a key value for the rest method of the api

    :example:

    .. code-block:: yaml

        policies:
          - name: api-without-key-required
            resource: rest-resource
            filters:
              - type: rest-method
                key: apiKeyRequired
                value: false
    """

    schema = utils.type_schema(
        'rest-method',
        method={'type': 'string', 'enum': [
            'all', 'ANY', 'PUT', 'GET', "POST",
            "DELETE", "OPTIONS", "HEAD", "PATCH"]},
        rinherit=ValueFilter.schema)
    permissions = ('apigateway:GET',)

    def process(self, resources, event=None):
        method_set = self.data.get('method', 'all')
        # 10 req/s with burst to 40
        client = utils.local_session(
            self.manager.session_factory).client('apigateway')

        # uniqueness constraint validity across apis?
        resource_map = {r['id']: r for r in resources}

        futures = {}
        results = set()

        with self.executor_factory(max_workers=2) as w:
            tasks = []
            for r in resources:
                r_method_set = method_set
                if method_set == 'all':
                    r_method_set = r.get('resourceMethods', {}).keys()
                for m in r_method_set:
                    tasks.append((r, m))
            for task_set in utils.chunks(tasks, 20):
                futures[w.submit(
                    self.process_task_set, client, task_set)] = task_set

            for f in as_completed(futures):
                task_set = futures[f]
                if f.exception():
                    self.manager.log.warning(
                        "Error retrieving methods on resources %s",
                        ["%s:%s" % (r['restApiId'], r['path'])
                         for r, mt in task_set])
                    continue
                for m in f.result():
                    if self.match(m):
                        results.add(m['resourceId'])
                        resource_map[m['resourceId']].setdefault(
                            ANNOTATION_KEY, []).append(m)
        return [resource_map[rid] for rid in results]

    def process_task_set(self, client, task_set):
        results = []
        for r, m in task_set:
            method = client.get_method(
                restApiId=r['restApiId'],
                resourceId=r['id'],
                httpMethod=m)
            method.pop('ResponseMetadata', None)
            method['restApiId'] = r['restApiId']
            method['resourceId'] = r['id']
            results.append(method)
        return results


@RestResource.action_registry.register('update-method')
class UpdateRestMethod(BaseAction):
    """Change or remove api method behaviors based on key value

    :example:

    .. code-block: yaml

        policies:
          - name: enforce-iam-permissions-on-api
            resource: rest-resource
            filters:
              - type: rest-method
                key: authorizationType
                value: NONE
                op: eq
            actions:
              - type: update-method
                patch:
                  - op: replace
                    path: /authorizationType
                    value: AWS_IAM
    """

    schema = utils.type_schema(
        'update-method',
        patch={'type': 'array', 'items': OP_SCHEMA},
        required=['patch'])
    permissions = ('apigateway:GET',)

    def validate(self):
        found = False
        for f in self.manager.filters:
            if isinstance(f, FilterRestMethod):
                found = True
                break
        if not found:
            raise ValueError(
                ("update-method action requires ",
                 "rest-method filter usage in policy"))
        return self

    def process(self, resources):
        client = utils.local_session(
            self.manager.session_factory).client('apigateway')
        ops = self.data['patch']
        for r in resources:
            for m in r.get(ANNOTATION_KEY, []):
                client.update_method(
                    restApiId=m['restApiId'],
                    resourceId=m['resourceId'],
                    httpMethod=m['httpMethod'],
                    patchOperations=ops)
