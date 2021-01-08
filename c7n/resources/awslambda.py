# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import jmespath
import json
from urllib.parse import urlparse, parse_qs

from botocore.exceptions import ClientError
from botocore.paginate import Paginator
from concurrent.futures import as_completed

from c7n.actions import BaseAction, RemovePolicyBase, ModifyVpcSecurityGroupsAction
from c7n.filters import CrossAccountAccessFilter, ValueFilter
from c7n.filters.kms import KmsRelatedFilter
import c7n.filters.vpc as net_filters
from c7n.manager import resources
from c7n import query
from c7n.resources.iam import CheckPermissions
from c7n.tags import universal_augment
from c7n.utils import local_session, type_schema, select_keys

from .securityhub import PostFinding

ErrAccessDenied = "AccessDeniedException"


class DescribeLambda(query.DescribeSource):

    def augment(self, resources):
        return universal_augment(
            self.manager, super(DescribeLambda, self).augment(resources))

    def get_resources(self, ids):
        client = local_session(self.manager.session_factory).client('lambda')
        resources = []
        for rid in ids:
            try:
                func = self.manager.retry(client.get_function, FunctionName=rid)
            except client.exceptions.ResourceNotFoundException:
                continue
            config = func.pop('Configuration')
            config.update(func)
            if 'Tags' in config:
                config['Tags'] = [
                    {'Key': k, 'Value': v} for k, v in config['Tags'].items()]
            resources.append(config)
        return resources


class ConfigLambda(query.ConfigSource):

    def load_resource(self, item):
        resource = super(ConfigLambda, self).load_resource(item)
        resource['c7n:Policy'] = item[
            'supplementaryConfiguration'].get('Policy')
        return resource


@resources.register('lambda')
class AWSLambda(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'lambda'
        arn_type = 'function'
        arn_separator = ":"
        enum_spec = ('list_functions', 'Functions', None)
        name = id = 'FunctionName'
        date = 'LastModified'
        dimension = 'FunctionName'
        config_type = 'AWS::Lambda::Function'
        cfn_type = 'AWS::Lambda::Function'
        universal_taggable = object()

    source_mapping = {
        'describe': DescribeLambda,
        'config': ConfigLambda
    }

    def get_resources(self, ids, cache=True, augment=False):
        return super(AWSLambda, self).get_resources(ids, cache, augment)


@AWSLambda.filter_registry.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "VpcConfig.SecurityGroupIds[]"


@AWSLambda.filter_registry.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "VpcConfig.SubnetIds[]"


@AWSLambda.filter_registry.register('vpc')
class VpcFilter(net_filters.VpcFilter):

    RelatedIdsExpression = "VpcConfig.VpcId"


AWSLambda.filter_registry.register('network-location', net_filters.NetworkLocation)


@AWSLambda.filter_registry.register('check-permissions')
class LambdaPermissions(CheckPermissions):

    def get_iam_arns(self, resources):
        return [r['Role'] for r in resources]


@AWSLambda.filter_registry.register('reserved-concurrency')
class ReservedConcurrency(ValueFilter):

    annotation_key = "c7n:FunctionInfo"
    value_key = '"c7n:FunctionInfo".Concurrency.ReservedConcurrentExecutions'
    schema = type_schema('reserved-concurrency', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('lambda:GetFunction',)

    def validate(self):
        self.data['key'] = self.value_key
        return super(ReservedConcurrency, self).validate()

    def process(self, resources, event=None):
        self.data['key'] = self.value_key
        client = local_session(self.manager.session_factory).client('lambda')

        def _augment(r):
            try:
                r[self.annotation_key] = self.manager.retry(
                    client.get_function, FunctionName=r['FunctionArn'])
                r[self.annotation_key].pop('ResponseMetadata')
            except ClientError as e:
                if e.response['Error']['Code'] == ErrAccessDenied:
                    self.log.warning(
                        "Access denied getting lambda:%s",
                        r['FunctionName'])
                raise
            return r

        with self.executor_factory(max_workers=3) as w:
            resources = list(filter(None, w.map(_augment, resources)))
            return super(ReservedConcurrency, self).process(resources, event)


def get_lambda_policies(client, executor_factory, resources, log):

    def _augment(r):
        try:
            r['c7n:Policy'] = client.get_policy(
                FunctionName=r['FunctionName'])['Policy']
        except client.exceptions.ResourceNotFoundException:
            return None
        except ClientError as e:
            if e.response['Error']['Code'] == 'AccessDeniedException':
                log.warning(
                    "Access denied getting policy lambda:%s",
                    r['FunctionName'])
        return r

    results = []
    futures = {}

    with executor_factory(max_workers=3) as w:
        for r in resources:
            if 'c7n:Policy' in r:
                results.append(r)
                continue
            futures[w.submit(_augment, r)] = r

        for f in as_completed(futures):
            if f.exception():
                log.warning("Error getting policy for:%s err:%s",
                            r['FunctionName'], f.exception())
                r = futures[f]
                continue
            results.append(f.result())

    return filter(None, results)


@AWSLambda.filter_registry.register('event-source')
class LambdaEventSource(ValueFilter):
    # this uses iam policy, it should probably use
    # event source mapping api

    annotation_key = "c7n:EventSources"
    schema = type_schema('event-source', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('lambda:GetPolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('lambda')
        self.log.debug("fetching policy for %d lambdas" % len(resources))
        resources = get_lambda_policies(
            client, self.executor_factory, resources, self.log)
        self.data['key'] = self.annotation_key
        return super(LambdaEventSource, self).process(resources, event)

    def __call__(self, r):
        if 'c7n:Policy' not in r:
            return False
        sources = set()
        data = json.loads(r['c7n:Policy'])
        for s in data.get('Statement', ()):
            if s['Effect'] != 'Allow':
                continue
            if 'Service' in s['Principal']:
                sources.add(s['Principal']['Service'])
            if sources:
                r[self.annotation_key] = list(sources)
        return self.match(r)


@AWSLambda.filter_registry.register('cross-account')
class LambdaCrossAccountAccessFilter(CrossAccountAccessFilter):
    """Filters lambda functions with cross-account permissions

    The whitelist parameter can be used to prevent certain accounts
    from being included in the results (essentially stating that these
    accounts permissions are allowed to exist)

    This can be useful when combining this filter with the delete action.

    :example:

    .. code-block:: yaml

            policies:
              - name: lambda-cross-account
                resource: lambda
                filters:
                  - type: cross-account
                    whitelist:
                      - 'IAM-Policy-Cross-Account-Access'

    """
    permissions = ('lambda:GetPolicy',)

    policy_attribute = 'c7n:Policy'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('lambda')
        self.log.debug("fetching policy for %d lambdas" % len(resources))
        resources = get_lambda_policies(
            client, self.executor_factory, resources, self.log)
        return super(LambdaCrossAccountAccessFilter, self).process(
            resources, event)


@AWSLambda.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):
    """
    Filter a resource by its associcated kms key and optionally the aliasname
    of the kms key by using 'c7n:AliasName'

    :example:

        .. code-block:: yaml

            policies:
                - name: lambda-kms-key-filters
                  resource: aws.lambda
                  filters:
                    - type: kms-key
                      key: c7n:AliasName
                      value: "^(alias/aws/lambda)"
                      op: regex
    """
    RelatedIdsExpression = 'KMSKeyArn'


@AWSLambda.action_registry.register('post-finding')
class LambdaPostFinding(PostFinding):

    resource_type = 'AwsLambdaFunction'

    def format_resource(self, r):
        envelope, payload = self.format_envelope(r)
        # security hub formatting beggars belief
        details = self.filter_empty(select_keys(r,
            ['CodeSha256',
             'DeadLetterConfig',
             'Environment',
             'Handler',
             'KMSKeyArn',
             'LastModified',
             'MemorySize',
             'MasterArn',
             'RevisionId',
             'Role',
             'Runtime',
             'TracingConfig',
             'Timeout',
             'Version',
             'VpcConfig']))
        # do the brain dead parts Layers, Code, TracingConfig
        if 'Layers' in r:
            r['Layers'] = {
                'Arn': r['Layers'][0]['Arn'],
                'CodeSize': r['Layers'][0]['CodeSize']}
        details.get('VpcConfig', {}).pop('VpcId', None)

        if 'Code' in r and r['Code'].get('RepositoryType') == "S3":
            parsed = urlparse(r['Code']['Location'])
            details['Code'] = {
                'S3Bucket': parsed.netloc.split('.', 1)[0],
                'S3Key': parsed.path[1:]}
            params = parse_qs(parsed.query)
            if params['versionId']:
                details['Code']['S3ObjectVersion'] = params['versionId'][0]
        payload.update(details)
        return envelope


@AWSLambda.action_registry.register('remove-statements')
class RemovePolicyStatement(RemovePolicyBase):
    """Action to remove policy/permission statements from lambda functions.

    :example:

    .. code-block:: yaml

            policies:
              - name: lambda-remove-cross-accounts
                resource: lambda
                filters:
                  - type: cross-account
                actions:
                  - type: remove-statements
                    statement_ids: matched
    """

    schema = type_schema(
        'remove-statements',
        required=['statement_ids'],
        statement_ids={'oneOf': [
            {'enum': ['matched']},
            {'type': 'array', 'items': {'type': 'string'}}]})

    permissions = ("lambda:GetPolicy", "lambda:RemovePermission")

    def process(self, resources):
        results = []
        client = local_session(self.manager.session_factory).client('lambda')
        for r in resources:
            try:
                if self.process_resource(client, r):
                    results.append(r)
            except Exception:
                self.log.exception(
                    "Error processing lambda %s", r['FunctionArn'])
        return results

    def process_resource(self, client, resource):
        if 'c7n:Policy' not in resource:
            try:
                resource['c7n:Policy'] = client.get_policy(
                    FunctionName=resource['FunctionName']).get('Policy')
            except ClientError as e:
                if e.response['Error']['Code'] != ErrAccessDenied:
                    raise
                resource['c7n:Policy'] = None

        if not resource['c7n:Policy']:
            return

        p = json.loads(resource['c7n:Policy'])

        statements, found = self.process_policy(
            p, resource, CrossAccountAccessFilter.annotation_key)
        if not found:
            return

        for f in found:
            client.remove_permission(
                FunctionName=resource['FunctionName'],
                StatementId=f['Sid'])


@AWSLambda.action_registry.register('set-concurrency')
class SetConcurrency(BaseAction):
    """Set lambda function concurrency to the desired level.

    Can be used to set the reserved function concurrency to an exact value,
    to delete reserved concurrency, or to set the value to an attribute of
    the resource.
    """

    schema = type_schema(
        'set-concurrency',
        required=('value',),
        **{'expr': {'type': 'boolean'},
           'value': {'oneOf': [
               {'type': 'string'},
               {'type': 'integer'},
               {'type': 'null'}]}})

    permissions = ('lambda:DeleteFunctionConcurrency',
                   'lambda:PutFunctionConcurrency')

    def validate(self):
        if self.data.get('expr', False) and not isinstance(self.data['value'], str):
            raise ValueError("invalid value expression %s" % self.data['value'])
        return self

    def process(self, functions):
        client = local_session(self.manager.session_factory).client('lambda')
        is_expr = self.data.get('expr', False)
        value = self.data['value']
        if is_expr:
            value = jmespath.compile(value)

        none_type = type(None)

        for function in functions:
            fvalue = value
            if is_expr:
                fvalue = value.search(function)
                if isinstance(fvalue, float):
                    fvalue = int(fvalue)
                if isinstance(value, int) or isinstance(value, none_type):
                    self.policy.log.warning(
                        "Function: %s Invalid expression value for concurrency: %s",
                        function['FunctionName'], fvalue)
                    continue
            if fvalue is None:
                client.delete_function_concurrency(
                    FunctionName=function['FunctionName'])
            else:
                client.put_function_concurrency(
                    FunctionName=function['FunctionName'],
                    ReservedConcurrentExecutions=fvalue)


@AWSLambda.action_registry.register('delete')
class Delete(BaseAction):
    """Delete a lambda function (including aliases and older versions).

    :example:

    .. code-block:: yaml

            policies:
              - name: lambda-delete-dotnet-functions
                resource: lambda
                filters:
                  - Runtime: dotnetcore1.0
                actions:
                  - delete
    """
    schema = type_schema('delete')
    permissions = ("lambda:DeleteFunction",)

    def process(self, functions):
        client = local_session(self.manager.session_factory).client('lambda')
        for function in functions:
            try:
                client.delete_function(FunctionName=function['FunctionName'])
            except ClientError as e:
                if e.response['Error']['Code'] == "ResourceNotFoundException":
                    continue
                raise
        self.log.debug("Deleted %d functions", len(functions))


@AWSLambda.action_registry.register('modify-security-groups')
class LambdaModifyVpcSecurityGroups(ModifyVpcSecurityGroupsAction):

    permissions = ("lambda:UpdateFunctionConfiguration",)

    def process(self, functions):
        client = local_session(self.manager.session_factory).client('lambda')
        groups = super(LambdaModifyVpcSecurityGroups, self).get_groups(
            functions)

        for idx, i in enumerate(functions):
            if 'VpcConfig' not in i:  # only continue if Lambda func is VPC-enabled
                continue
            try:
                client.update_function_configuration(FunctionName=i['FunctionName'],
                                            VpcConfig={'SecurityGroupIds': groups[idx]})
            except client.exceptions.ResourceNotFoundException:
                continue


@resources.register('lambda-layer')
class LambdaLayerVersion(query.QueryResourceManager):
    """Note custodian models the lambda layer version.

    Layers end up being a logical asset, the physical asset for use
    and management is the layer verison.

    To ease that distinction, we support querying just the latest
    layer version or having a policy against all layer versions.

    By default we query all versions, the following is an example
    to query just the latest.

    .. code-block:: yaml

        policies:
          - name: lambda-layer
            resource: lambda
            query:
              - version: latest

    """

    class resource_type(query.TypeInfo):
        service = 'lambda'
        enum_spec = ('list_layers', 'Layers', None)
        name = id = 'LayerName'
        date = 'CreatedDate'
        arn = "LayerVersionArn"
        arn_type = "layer"
        cfn_type = 'AWS::Lambda::LayerVersion'

    def augment(self, resources):
        versions = {}
        for r in resources:
            versions[r['LayerName']] = v = r['LatestMatchingVersion']
            v['LayerName'] = r['LayerName']

        if {'version': 'latest'} in self.data.get('query', []):
            return list(versions.values())

        layer_names = list(versions)
        client = local_session(self.session_factory).client('lambda')

        versions = []
        for layer_name in layer_names:
            pager = get_layer_version_paginator(client)
            for v in pager.paginate(
                    LayerName=layer_name).build_full_result().get('LayerVersions'):
                v['LayerName'] = layer_name
                versions.append(v)
        return versions


def get_layer_version_paginator(client):
    pager = Paginator(
        client.list_layer_versions,
        {'input_token': 'NextToken',
         'output_token': 'NextToken',
         'result_key': 'LayerVersions'},
        client.meta.service_model.operation_model('ListLayerVersions'))
    pager.PAGE_ITERATOR_CLS = query.RetryPageIterator
    return pager


@LambdaLayerVersion.filter_registry.register('cross-account')
class LayerCrossAccount(CrossAccountAccessFilter):

    permissions = ('lambda:GetLayerVersionPolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('lambda')
        for r in resources:
            r['c7n:Policy'] = self.manager.retry(
                client.get_layer_version_policy,
                LayerName=r['LayerName'],
                VersionNumber=r['Version']).get('Policy')
        return super(LayerCrossAccount, self).process(resources)

    def get_resource_policy(self, r):
        return r['c7n:Policy']


@LambdaLayerVersion.action_registry.register('remove-statements')
class LayerRemovePermissions(RemovePolicyBase):

    schema = type_schema(
        'remove-statements',
        required=['statement_ids'],
        statement_ids={'oneOf': [
            {'enum': ['matched']},
            {'type': 'array', 'items': {'type': 'string'}}]})

    permissions = (
        "lambda:GetLayerVersionPolicy",
        "lambda:RemoveLayerVersionPermission")

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('lambda')
        for r in resources:
            self.process_resource(client, r)

    def process_resource(self, client, r):
        if 'c7n:Policy' not in r:
            try:
                r['c7n:Policy'] = self.manager.retry(
                    client.get_layer_version_policy,
                    LayerName=r['LayerName'],
                    VersionNumber=r['Version'])
            except client.exceptions.ResourceNotFound:
                return

        p = json.loads(r['c7n:Policy'])

        statements, found = self.process_policy(
            p, r, CrossAccountAccessFilter.annotation_key)

        if not found:
            return

        for f in found:
            self.manager.retry(
                client.remove_layer_version_permission,
                LayerName=r['LayerName'],
                StatementId=f['Sid'],
                VersionNumber=r['Version'])


@LambdaLayerVersion.action_registry.register('delete')
class DeleteLayerVersion(BaseAction):

    schema = type_schema('delete')
    permissions = ('lambda:DeleteLayerVersion',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('lambda')

        for r in resources:
            try:
                self.manager.retry(
                    client.delete_layer_version,
                    LayerName=r['LayerName'],
                    VersionNumber=r['Version'])
            except client.exceptions.ResourceNotFound:
                continue


@LambdaLayerVersion.action_registry.register('post-finding')
class LayerPostFinding(PostFinding):

    resource_type = 'AwsLambdaLayerVersion'

    def format_resource(self, r):
        envelope, payload = self.format_envelope(r)
        payload.update(self.filter_empty(
            select_keys(r, ['Version', 'CreatedDate', 'CompatibleRuntimes'])))
        return envelope
