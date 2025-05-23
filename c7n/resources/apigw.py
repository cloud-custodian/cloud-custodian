# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import functools
import re
from botocore.exceptions import ClientError

from concurrent.futures import as_completed
from contextlib import suppress

from c7n.actions import ActionRegistry, BaseAction
from c7n.exceptions import PolicyValidationError
from c7n.filters import (
    FilterRegistry, ValueFilter, MetricsFilter, WafV2FilterBase,
    WafClassicRegionalFilterBase)
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.filters.policystatement import HasStatementFilter
from c7n.filters.related import RelatedResourceFilter
from c7n.manager import resources, ResourceManager
from c7n.resources.aws import shape_schema
from c7n import query, utils
from c7n.utils import generate_arn, type_schema, get_retry, jmespath_search, get_partition


ANNOTATION_KEY_MATCHED_METHODS = 'c7n:matched-resource-methods'
ANNOTATION_KEY_MATCHED_INTEGRATIONS = 'c7n:matched-method-integrations'


@resources.register('rest-account')
class RestAccount(ResourceManager):
    # note this is not using a regular resource manager or type info
    # its a pseudo resource, like an aws account

    filter_registry = FilterRegistry('rest-account.filters')
    action_registry = ActionRegistry('rest-account.actions')
    retry = staticmethod(get_retry(('TooManyRequestsException',)))

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
            account = self.retry(client.get_account)
        except ClientError as e:
            if e.response['Error']['Code'] == 'NotFoundException':
                return []
            raise
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


@RestApi.filter_registry.register('metrics')
class Metrics(MetricsFilter):

    def get_dimensions(self, resource):
        return [{'Name': 'ApiName',
                 'Value': resource['name']}]


@RestApi.filter_registry.register('cross-account')
class RestApiCrossAccount(CrossAccountAccessFilter):

    policy_attribute = 'policy'
    permissions = ('apigateway:GET',)

    def get_resource_policy(self, r):
        policy = super().get_resource_policy(r)
        if policy:
            policy = policy.replace('\\', '')
        else:
            # api gateway default iam policy is public
            # authorizers and app code may mitigate but
            # the iam policy intent here is clear.
            policy = {'Statement': [{
                'Action': 'execute-api:Invoke',
                'Effect': 'Allow',
                'Principal': '*'}]}
        return policy


@RestApi.filter_registry.register('has-statement')
class HasStatementRestApi(HasStatementFilter):

    permissions = ('apigateway:GET',)
    policy_attribute = 'policy'

    def get_std_format_args(self, table):
        return {
            'api_name': table[self.manager.resource_type.name],
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region,
        }

    def process(self, resources, event=None):
        for r in resources:
            if policy := r.get(self.policy_attribute):
                r[self.policy_attribute] = policy.replace('\\', '')
        return super().process(resources, event)


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
        retry = get_retry(('TooManyRequestsException',))

        for r in resources:
            try:
                retry(client.delete_rest_api, restApiId=r['id'])
            except client.exceptions.NotFoundException:
                continue


@query.sources.register('describe-rest-stage')
class DescribeRestStage(query.ChildDescribeSource):

    def __init__(self, manager):
        self.manager = manager
        self.query = query.ChildResourceQuery(
            self.manager.session_factory, self.manager, capture_parent_id=True)

    def get_query(self):
        return super(DescribeRestStage, self).get_query(capture_parent_id=True)

    def augment(self, resources):
        results = []
        rest_apis = self.manager.get_resource_manager(
            'rest-api').resources()
        # Using capture parent, changes the protocol
        for parent_id, r in resources:
            r['restApiId'] = parent_id
            for rest_api in rest_apis:
                if rest_api['id'] == parent_id:
                    r['restApiType'] = rest_api['endpointConfiguration']['types']
            r['stageArn'] = "arn:aws:{service}:{region}::" \
                            "/restapis/{rest_api_id}/stages/" \
                            "{stage_name}".format(
                service="apigateway",
                region=self.manager.config.region,
                rest_api_id=parent_id,
                stage_name=r['stageName'])
            tags = r.setdefault('Tags', [])
            for k, v in r.pop('tags', {}).items():
                tags.append({
                    'Key': k,
                    'Value': v})
            results.append(r)
        return results

    def get_resources(self, ids, cache=True):
        deployment_ids = []
        client = utils.local_session(
            self.manager.session_factory).client('apigateway')
        for id in ids:
            # if we get stage arn, we pick rest_api_id and stageName to get deploymentId
            if id.startswith('arn:aws:apigateway'):
                _, ident = id.rsplit(':', 1)
                parts = ident.split('/', 4)
                # if we get stage name in arn, use stage_name to get stage information
                # from stage information, pick deploymentId
                if len(parts) > 3:
                    response = self.manager.retry(
                        client.get_stage,
                        restApiId=parts[2],
                        stageName=parts[4])
                    deployment_ids.append(response[self.manager.resource_type.id])
            else:
                deployment_ids.append(id)
        return super(DescribeRestStage, self).get_resources(deployment_ids, cache)


@resources.register('rest-stage')
class RestStage(query.ChildResourceManager):

    class resource_type(query.TypeInfo):
        service = 'apigateway'
        parent_spec = ('rest-api', 'restApiId', None)
        enum_spec = ('get_stages', 'item', None)
        name = 'stageName'
        id = 'deploymentId'
        config_id = 'stageArn'
        date = 'createdDate'
        universal_taggable = True
        cfn_type = config_type = "AWS::ApiGateway::Stage"
        arn_type = 'stages'
        permissions_enum = ('apigateway:GET',)
        supports_trailevents = True

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
             '/stages/' + r[self.get_model().name]))
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
        return super(DescribeRestResource, self).get_query(capture_parent_id=True)

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


@resources.register('rest-client-certificate')
class RestClientCertificate(query.QueryResourceManager):
    """TLS client certificates generated by API Gateway

    :example:

    .. code-block:: yaml

            policies:
              - name: old-client-certificates
                resource: rest-client-certificate
                filters:
                  - key: createdDate
                    value_type: age
                    value: 90
                    op: greater-than
    """
    class resource_type(query.TypeInfo):
        service = 'apigateway'
        enum_spec = ('get_client_certificates', 'items', None)
        id = 'clientCertificateId'
        name = 'client_certificate_id'
        permissions_enum = ('apigateway:GET',)
        cfn_type = 'AWS::ApiGateway::ClientCertificate'


@RestStage.filter_registry.register('client-certificate')
class StageClientCertificateFilter(RelatedResourceFilter):
    """Filter API stages by a client certificate

    :example:

    .. code-block:: yaml

            policies:
              - name: rest-stages-old-certificate
                resource: rest-stage
                filters:
                  - type: client-certificate
                    key: createdDate
                    value_type: age
                    value: 90
                    op: greater-than
    """
    schema = type_schema('client-certificate', rinherit=ValueFilter.schema)
    RelatedResource = "c7n.resources.apigw.RestClientCertificate"
    RelatedIdsExpression = 'clientCertificateId'
    annotation_key = "c7n:matched-client-certificate"

    def process(self, resources, event=None):
        related = self.get_related(resources)
        matched = []
        for r in resources:
            if self.process_resource(r, related):
                # Add the full certificate details rather than just the ID
                self.augment(related, r)
                matched.append(r)
        return matched

    def augment(self, related, resource):
        rid = resource[self.RelatedIdsExpression]
        with suppress(KeyError):
            resource[self.annotation_key] = {
                self.data['key']: jmespath_search(self.data['key'], related[rid])
            }


@RestStage.filter_registry.register('waf-enabled')
class WafEnabled(WafClassicRegionalFilterBase):
    """Filter API Gateway stage by waf-regional web-acl

    :example:

    .. code-block:: yaml

            policies:
              - name: filter-apigw-waf-regional
                resource: rest-stage
                filters:
                  - type: waf-enabled
                    state: false
                    web-acl: test
    """

    def get_associated_web_acl(self, resource):
        return self.get_web_acl_by_arn(resource.get('webAclArn'))


@RestStage.action_registry.register('set-waf')
class SetWaf(BaseAction):
    """Enable waf protection on API Gateway stage.

    :example:

    .. code-block:: yaml

            policies:
              - name: set-waf-for-stage
                resource: rest-stage
                filters:
                  - type: waf-enabled
                    state: false
                    web-acl: test
                actions:
                  - type: set-waf
                    state: true
                    web-acl: test

              - name: disassociate-wafv2-associate-waf-regional-apigw
                resource: rest-stage
                filters:
                  - type: wafv2-enabled
                    state: true
                actions:
                  - type: set-waf
                    state: true
                    web-acl: test

    """
    permissions = ('waf-regional:AssociateWebACL', 'waf-regional:ListWebACLs')

    schema = type_schema(
        'set-waf', required=['web-acl'], **{
            'web-acl': {'type': 'string'},
            # 'force': {'type': 'boolean'},
            'state': {'type': 'boolean'}})

    def validate(self):
        found = False
        for f in self.manager.iter_filters():
            if isinstance(f, WafEnabled) or isinstance(f, WafV2Enabled):
                found = True
                break
        if not found:
            # try to ensure idempotent usage
            raise PolicyValidationError(
                "set-waf should be used in conjunction with waf-enabled or wafv2-enabled \
                filter on %s" % (self.manager.data,))
        return self

    def process(self, resources):
        wafs = self.manager.get_resource_manager('waf-regional').resources(augment=False)
        name_id_map = {w['Name']: w['WebACLId'] for w in wafs}
        target_acl = self.data.get('web-acl', '')
        target_acl_id = name_id_map.get(target_acl, target_acl)
        state = self.data.get('state', True)
        if state and target_acl_id not in name_id_map.values():
            raise ValueError("invalid web acl: %s" % (target_acl))

        client = utils.local_session(
            self.manager.session_factory).client('waf-regional')

        for r in resources:
            r_arn = self.manager.get_arns([r])[0]
            if state:
                client.associate_web_acl(WebACLId=target_acl_id, ResourceArn=r_arn)
            else:
                client.disassociate_web_acl(WebACLId=target_acl_id, ResourceArn=r_arn)


@RestStage.filter_registry.register('wafv2-enabled')
class WafV2Enabled(WafV2FilterBase):
    """Filter API Gateway stage by wafv2 web-acl

    :example:

    .. code-block:: yaml

            policies:
              - name: filter-wafv2-apigw
                resource: rest-stage
                filters:
                  - type: wafv2-enabled
                    state: false
                    web-acl: testv2
    """

    def get_associated_web_acl(self, resource):
        return self.get_web_acl_by_arn(resource.get('webAclArn'))


@RestStage.action_registry.register('set-wafv2')
class SetWafv2(BaseAction):
    """Enable wafv2 protection on API Gateway stage.

    :example:

    .. code-block:: yaml

            policies:
              - name: set-wafv2-for-stage
                resource: rest-stage
                filters:
                  - type: wafv2-enabled
                    state: false
                    web-acl: testv2
                actions:
                  - type: set-wafv2
                    state: true
                    web-acl: testv2

              - name: disassociate-waf-regional-associate-wafv2-apigw
                resource: rest-stage
                filters:
                  - type: waf-enabled
                    state: true
                actions:
                  - type: set-wafv2
                    state: true
                    web-acl: testv2

    """
    permissions = ('wafv2:AssociateWebACL', 'wafv2:ListWebACLs')

    schema = type_schema(
        'set-wafv2', **{
            'web-acl': {'type': 'string'},
            'state': {'type': 'boolean'}})

    retry = staticmethod(get_retry((
        'ThrottlingException',
        'RequestLimitExceeded',
        'Throttled',
        'ThrottledException',
        'Throttling',
        'Client.RequestLimitExceeded')))

    def validate(self):
        found = False
        for f in self.manager.iter_filters():
            if isinstance(f, WafV2Enabled) or isinstance(f, WafEnabled):
                found = True
                break
        if not found:
            # try to ensure idempotent usage
            raise PolicyValidationError(
                "set-wafv2 should be used in conjunction with wafv2-enabled or waf-enabled \
                    filter on %s" % (self.manager.data,))
        if self.data.get('state'):
            if 'web-acl' not in self.data:
                raise PolicyValidationError((
                    "set-wafv2 filter parameter state is true, "
                    "requires `web-acl` on %s" % (self.manager.data,)))

        return self

    def process(self, resources):
        wafs = self.manager.get_resource_manager('wafv2').resources(augment=False)
        name_id_map = {w['Name']: w['ARN'] for w in wafs}
        state = self.data.get('state', True)
        target_acl_arn = ''

        if state:
            target_acl = self.data.get('web-acl', '')
            target_acl_ids = [v for k, v in name_id_map.items() if
                              re.match(target_acl, k)]
            if len(target_acl_ids) != 1:
                raise ValueError(f'{target_acl} matching to none or the '
                                 f'multiple web-acls')
            target_acl_arn = target_acl_ids[0]

        if state and target_acl_arn not in name_id_map.values():
            raise ValueError("invalid web acl: %s" % target_acl_arn)

        client = utils.local_session(self.manager.session_factory).client('wafv2')

        for r in resources:
            r_arn = self.manager.get_arns([r])[0]
            if state:
                self.retry(client.associate_web_acl,
                           WebACLArn=target_acl_arn,
                           ResourceArn=r_arn)
            else:
                self.retry(client.disassociate_web_acl,
                           ResourceArn=r_arn)


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


@resources.register('apigw-domain-name')
class CustomDomainName(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        enum_spec = ('get_domain_names', 'items', None)
        arn_type = '/domainnames'
        id = name = 'domainName'
        service = 'apigateway'
        universal_taggable = True
        cfn_type = 'AWS::ApiGateway::DomainName'
        date = 'createdDate'

    @classmethod
    def get_permissions(cls):
        return ('apigateway:GET',)

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


@CustomDomainName.action_registry.register('update-security')
class DomainNameRemediateTls(BaseAction):

    schema = type_schema(
        'update-security',
        securityPolicy={'type': 'string', 'enum': [
            'TLS_1_0', 'TLS_1_2']},
        required=['securityPolicy'])

    permissions = ('apigateway:PATCH',)

    def process(self, resources, event=None):
        client = utils.local_session(
            self.manager.session_factory).client('apigateway')
        retryable = ('TooManyRequestsException', 'ConflictException')
        retry = utils.get_retry(retryable, max_attempts=8)

        for r in resources:
            try:
                retry(client.update_domain_name,
                      domainName=r['domainName'],
                      patchOperations=[
                          {
                              'op': 'replace',
                              'path': '/securityPolicy',
                              'value': self.data.get('securityPolicy')
                          },
                      ]
                      )
            except ClientError as e:
                if e.response['Error']['Code'] in retryable:
                    continue


class ApiGwV2DescribeSource(query.DescribeSource):

    def augment(self, resources):
        # convert tags from {'Key': 'Value'} to standard aws format
        for r in resources:
            r['Tags'] = [
                {'Key': k, 'Value': v} for k, v in r.pop('Tags', {}).items()]
        return resources


@resources.register('apigwv2')
class ApiGwV2(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'apigatewayv2'
        arn_type = '/apis'
        enum_spec = ('get_apis', 'Items', None)
        id = 'ApiId'
        name = 'name'
        date = 'createdDate'
        dimension = 'ApiId'
        cfn_type = config_type = "AWS::ApiGatewayV2::Api"
        permission_prefix = 'apigateway'
        permissions_enum = ('apigateway:GET',)
        universal_taggable = object()

    source_mapping = {
        'config': query.ConfigSource,
        'describe': ApiGwV2DescribeSource
    }

    @property
    def generate_arn(self):
        """
         Sample arn: arn:aws:apigateway:us-east-1::/apis/api-id
         This method overrides c7n.utils.generate_arn and drops
         account id from the generic arn.
        """
        if self._generate_arn is None:
            self._generate_arn = functools.partial(
                generate_arn,
                "apigateway",
                region=self.config.region,
                resource_type=self.resource_type.arn_type,
            )

        return self._generate_arn


@ApiGwV2.action_registry.register('update')
class UpdateApiV2(BaseAction):
    """Update configuration of a WebSocket or HTTP API.

    https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/apigatewayv2/client/update_api.html

    :example:

    .. code-block:: yaml

       policies:
         - name: apigw-update
           resource: apigwv2
           filters:
             - Name: c7n-test
           actions:
             - type: update
               CorsConfiguration:
                 AllowCredentials: False
                 MaxAge: 60
               Description: My APIv2
               DisableExecuteApiEndpoint: False
    """

    permissions = ('apigateway:PATCH',)
    schema = utils.type_schema(
        'update',
        **shape_schema('apigatewayv2', 'UpdateApiRequest', drop_fields=('ApiId'))
    )

    def process(self, resources):
        client = utils.local_session(
            self.manager.session_factory).client('apigatewayv2')
        params = dict(self.data)
        params.pop('type')
        for r in resources:
            self.manager.retry(client.update_api,
                ApiId=r['ApiId'],
                **params
            )


@ApiGwV2.action_registry.register('delete')
class DeleteApiV2(BaseAction):
    """Delete an HTTP or WebSocket API.

    :example:

    .. code-block:: yaml

        policies:
        - name: apigwv2-delete
          resource: apigwv2
          filters:
            - Name: empty
          actions:
            - type: delete
    """

    permissions = ('apigateway:DELETE',)
    schema = type_schema('delete')

    def process(self, resources):
        client = utils.local_session(
            self.manager.session_factory).client('apigatewayv2')
        for r in resources:
            self.manager.retry(
                client.delete_api,
                ignore_err_codes=('NotFoundException',),
                ApiId=r['ApiId']
            )


class StageDescribe(query.ChildDescribeSource):

    def augment(self, resources):
        # convert tags from {'Key': 'Value'} to standard aws format
        for r in resources:
            r['Tags'] = [
                {'Key': k, 'Value': v} for k, v in r.pop('Tags', {}).items()]
        return resources


@resources.register("apigwv2-stage")
class ApiGatewayV2Stage(query.ChildResourceManager):
    class resource_type(query.TypeInfo):
        service = "apigatewayv2"
        enum_spec = ('get_stages', 'Items', None)
        parent_spec = ('aws.apigwv2', 'ApiId', True)
        arn_type = "/apis"
        id = name = "StageName"
        cfn_type = config_type = "AWS::ApiGatewayV2::Stage"
        universal_taggable = object()
        permission_prefix = 'apigateway'
        permissions_enum = ('apigateway:GET',)

    source_mapping = {
        "describe-child": StageDescribe,
        "config": query.ConfigSource
    }

    def get_arns(self, resources):
        partition = get_partition(self.config.region)
        return [
            "arn:{}:apigateway:{}::/apis/{}/stages/{}".format(
                partition, self.config.region, r['c7n:parent-id'], r['StageName']
            )
            for r in resources]


@ApiGatewayV2Stage.action_registry.register('update')
class UpdateApiV2Stage(BaseAction):
    """Update configuration of a WebSocket or HTTP API stage.

    https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/apigatewayv2/client/update_stage.html

    :example:

    .. code-block:: yaml

       policies:
         - name: apigw-stage-update
           resource: apigwv2-stage
           filters:
             - description: empty
           actions:
             - type: update
               AutoDeploy: True
               Description: My APIv2
               DefaultRouteSettings:
                 DetailedMetricsEnabled: True
    """

    permissions = ('apigateway:PATCH',)
    schema = utils.type_schema(
        'update',
        **shape_schema('apigatewayv2', 'UpdateStageRequest', drop_fields=('ApiId', 'StageName'))
    )

    def process(self, resources):
        client = utils.local_session(
            self.manager.session_factory).client('apigatewayv2')
        params = dict(self.data)
        params.pop('type')
        for r in resources:
            self.manager.retry(client.update_stage,
                ApiId=r['c7n:parent-id'],
                StageName=r['StageName'],
                **params
            )


@ApiGatewayV2Stage.action_registry.register('delete')
class DeleteApiV2Stage(BaseAction):
    """Delete an HTTP or WebSocket API stage.

    :example:

    .. code-block:: yaml

        policies:
        - name: apigwv2-stage-delete
          resource: apigwv2-stage
          filters:
            - ApiGatewayManaged: False
          actions:
            - type: delete
    """

    permissions = ('apigateway:DELETE',)
    schema = type_schema('delete')

    def process(self, resources):
        client = utils.local_session(
            self.manager.session_factory).client('apigatewayv2')
        for r in resources:
            self.manager.retry(
                client.delete_stage,
                ignore_err_codes=('NotFoundException',),
                ApiId=r['c7n:parent-id'],
                StageName=r['StageName']
            )
