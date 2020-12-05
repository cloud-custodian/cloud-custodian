# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import functools
from botocore.exceptions import ClientError

from concurrent.futures import as_completed

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import FilterRegistry, ValueFilter
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.manager import resources, ResourceManager
from c7n import query, utils
from c7n.utils import generate_arn, type_schema


ANNOTATION_KEY_MATCHED_METHODS = 'c7n:matched-resource-methods'
ANNOTATION_KEY_MATCHED_INTEGRATIONS = 'c7n:matched-method-integrations'


@resources.register('rest-account')
class RestAccount(ResourceManager):
    # note this is not using a regular resource manager or type info
    # its a pseudo resource, like an aws account

    filter_registry = FilterRegistry('rest-account.filters')
    action_registry = ActionRegistry('rest-account.actions')

    class resource_type(query.TypeInfo):
        service = 'apigateway'
        name = id = 'account_id'
        dimension = None
        arn = False

    @classmethod
    def get_permissions(cls):
        # this resource is not query manager based as its a pseudo
        # resource. in that it always exists, it represents the
        # service's account settings.
        return ('apigateway:GET',)

    @classmethod
    def has_arn(self):
        return False

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


class ApiDescribeSource(query.DescribeSource):

    def augment(self, resources):
        for r in resources:
            tags = r.setdefault('Tags', [])
            for k, v in r.pop('tags', {}).items():
                tags.append({
                    'Key': k,
                    'Value': v})
        return resources


@resources.register('rest-api')
class RestApi(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'apigateway'
        arn_type = '/restapis'
        enum_spec = ('get_rest_apis', 'items', None)
        id = 'id'
        name = 'name'
        date = 'createdDate'
        dimension = 'GatewayName'
        cfn_type = config_type = "AWS::ApiGateway::RestApi"
        universal_taggable = object()
        permissions_enum = ('apigateway:GET',)

    source_mapping = {
        'config': query.ConfigSource,
        'describe': ApiDescribeSource
    }

    @property
    def generate_arn(self):
        """
         Sample arn: arn:aws:apigateway:us-east-1::/restapis/rest-api-id
         This method overrides c7n.utils.generate_arn and drops
         account id from the generic arn.
        """
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                self.resource_type.service,
                region=self.config.region,
                resource_type=self.resource_type.arn_type)
        return self._generate_arn


@RestApi.filter_registry.register('cross-account')
class RestApiCrossAccount(CrossAccountAccessFilter):

    policy_attribute = 'policy'
    permissions = ('apigateway:GET',)


@RestApi.action_registry.register('update')
class UpdateApi(BaseAction):
    """Update configuration of a REST API.

    Non-exhaustive list of updateable attributes.
    https://docs.aws.amazon.com/apigateway/api-reference/link-relation/restapi-update/#remarks

    :example:

    contrived example to update description on api gateways

    .. code-block:: yaml

       policies:
         - name: apigw-description
           resource: rest-api
           filters:
             - description: empty
           actions:
             - type: update
               patch:
                - op: replace
                  path: /description
                  value: "not empty :-)"
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
            client.update_rest_api(
                restApiId=r['id'],
                patchOperations=self.data['patch'])


@RestApi.action_registry.register('delete')
class DeleteApi(BaseAction):
    """Delete a REST API.

    :example:

    contrived example to delete rest api

    .. code-block:: yaml

       policies:
         - name: apigw-delete
           resource: rest-api
           filters:
             - description: empty
           actions:
             - type: delete
    """
    permissions = ('apigateway:DELETE',)
    schema = type_schema('delete')

    def process(self, resources):
        client = utils.local_session(
            self.manager.session_factory).client('apigateway')
        for r in resources:
            try:
                client.delete_rest_api(restApiId=r['id'])
            except client.exceptions.NotFoundException:
                continue


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


@resources.register('rest-stage')
class RestStage(query.ChildResourceManager):

    class resource_type(query.TypeInfo):
        service = 'apigateway'
        parent_spec = ('rest-api', 'restApiId', None)
        enum_spec = ('get_stages', 'item', None)
        name = id = 'stageName'
        date = 'createdDate'
        universal_taggable = True
        cfn_type = config_type = "AWS::ApiGateway::Stage"
        arn_type = 'stages'
        permissions_enum = ('apigateway:GET',)

    child_source = 'describe'
    source_mapping = {
        'describe': DescribeRestStage,
        'config': query.ConfigSource
    }

    @property
    def generate_arn(self):
        self._generate_arn = functools.partial(
            generate_arn,
            self.resource_type.service,
            region=self.config.region)
        return self._generate_arn

    def get_arns(self, resources):
        arns = []
        for r in resources:
            arns.append(self.generate_arn('/restapis/' + r['restApiId'] +
             '/stages/' + r[self.get_model().id]))
        return arns


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
            self.manager.retry(
                client.update_stage,
                restApiId=r['restApiId'],
                stageName=r['stageName'],
                patchOperations=self.data['patch'])


@RestStage.action_registry.register('delete')
class DeleteStage(BaseAction):
    """Delete an api stage

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-rest-stage
            resource: rest-stage
            filters:
              - methodSettings."*/*".cachingEnabled: true
            actions:
              - type: delete
    """
    permissions = ('apigateway:DELETE',)
    schema = utils.type_schema('delete')

    def process(self, resources):
        client = utils.local_session(self.manager.session_factory).client('apigateway')
        for r in resources:
            try:
                self.manager.retry(
                    client.delete_stage,
                    restApiId=r['restApiId'],
                    stageName=r['stageName'])
            except client.exceptions.NotFoundException:
                pass


@resources.register('rest-resource')
class RestResource(query.ChildResourceManager):

    child_source = 'describe-rest-resource'

    class resource_type(query.TypeInfo):
        service = 'apigateway'
        parent_spec = ('rest-api', 'restApiId', None)
        enum_spec = ('get_resources', 'items', None)
        id = 'id'
        name = 'path'
        permissions_enum = ('apigateway:GET',)
        cfn_type = 'AWS::ApiGateway::Resource'


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


@resources.register('rest-vpclink')
class RestApiVpcLink(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'apigateway'
        enum_spec = ('get_vpc_links', 'items', None)
        id = 'id'
        name = 'name'
        permissions_enum = ('apigateway:GET',)
        cfn_type = 'AWS::ApiGateway::VpcLink'


@RestResource.filter_registry.register('rest-integration')
class FilterRestIntegration(ValueFilter):
    """Filter rest resources based on a key value for the rest method integration of the api

    :example:

    .. code-block:: yaml

        policies:
          - name: api-method-integrations-with-type-aws
            resource: rest-resource
            filters:
              - type: rest-integration
                key: type
                value: AWS
    """

    schema = utils.type_schema(
        'rest-integration',
        method={'type': 'string', 'enum': [
            'all', 'ANY', 'PUT', 'GET', "POST",
            "DELETE", "OPTIONS", "HEAD", "PATCH"]},
        rinherit=ValueFilter.schema)
    schema_alias = False
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
                        "Error retrieving integrations on resources %s",
                        ["%s:%s" % (r['restApiId'], r['path'])
                         for r, mt in task_set])
                    continue

                for i in f.result():
                    if self.match(i):
                        results.add(i['resourceId'])
                        resource_map[i['resourceId']].setdefault(
                            ANNOTATION_KEY_MATCHED_INTEGRATIONS, []).append(i)

        return [resource_map[rid] for rid in results]

    def process_task_set(self, client, task_set):
        results = []
        for r, m in task_set:
            try:
                integration = client.get_integration(
                    restApiId=r['restApiId'],
                    resourceId=r['id'],
                    httpMethod=m)
                integration.pop('ResponseMetadata', None)
                integration['restApiId'] = r['restApiId']
                integration['resourceId'] = r['id']
                integration['resourceHttpMethod'] = m
                results.append(integration)
            except ClientError as e:
                if e.response['Error']['Code'] == 'NotFoundException':
                    pass

        return results


@RestResource.action_registry.register('update-integration')
class UpdateRestIntegration(BaseAction):
    """Change or remove api integration properties based on key value

    :example:

    .. code-block:: yaml

        policies:
          - name: enforce-timeout-on-api-integration
            resource: rest-resource
            filters:
              - type: rest-integration
                key: timeoutInMillis
                value: 29000
            actions:
              - type: update-integration
                patch:
                  - op: replace
                    path: /timeoutInMillis
                    value: "3000"
    """

    schema = utils.type_schema(
        'update-integration',
        patch={'type': 'array', 'items': OP_SCHEMA},
        required=['patch'])
    permissions = ('apigateway:PATCH',)

    def validate(self):
        found = False
        for f in self.manager.iter_filters():
            if isinstance(f, FilterRestIntegration):
                found = True
                break
        if not found:
            raise ValueError(
                ("update-integration action requires ",
                 "rest-integration filter usage in policy"))
        return self

    def process(self, resources):
        client = utils.local_session(
            self.manager.session_factory).client('apigateway')
        ops = self.data['patch']
        for r in resources:
            for i in r.get(ANNOTATION_KEY_MATCHED_INTEGRATIONS, []):
                client.update_integration(
                    restApiId=i['restApiId'],
                    resourceId=i['resourceId'],
                    httpMethod=i['resourceHttpMethod'],
                    patchOperations=ops)


@RestResource.action_registry.register('delete-integration')
class DeleteRestIntegration(BaseAction):
    """Delete an api integration. Useful if the integration type is a security risk.

    :example:

    .. code-block:: yaml

        policies:
          - name: enforce-no-resource-integration-with-type-aws
            resource: rest-resource
            filters:
              - type: rest-integration
                key: type
                value: AWS
            actions:
              - type: delete-integration
    """
    permissions = ('apigateway:DELETE',)
    schema = utils.type_schema('delete-integration')

    def process(self, resources):
        client = utils.local_session(self.manager.session_factory).client('apigateway')

        for r in resources:
            for i in r.get(ANNOTATION_KEY_MATCHED_INTEGRATIONS, []):
                try:
                    client.delete_integration(
                        restApiId=i['restApiId'],
                        resourceId=i['resourceId'],
                        httpMethod=i['resourceHttpMethod'])
                except client.exceptions.NotFoundException:
                    continue


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
    schema_alias = False
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
                            ANNOTATION_KEY_MATCHED_METHODS, []).append(m)
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

    .. code-block:: yaml

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
        for f in self.manager.iter_filters():
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
            for m in r.get(ANNOTATION_KEY_MATCHED_METHODS, []):
                client.update_method(
                    restApiId=m['restApiId'],
                    resourceId=m['resourceId'],
                    httpMethod=m['httpMethod'],
                    patchOperations=ops)
