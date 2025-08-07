# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
from urllib.parse import urlparse, parse_qs

from botocore.exceptions import ClientError
from botocore.paginate import Paginator
from concurrent.futures import as_completed
from datetime import timedelta, datetime

from c7n.actions import Action, RemovePolicyBase, ModifyVpcSecurityGroupsAction
from c7n.filters import CrossAccountAccessFilter, ValueFilter, Filter
from c7n.filters.costhub import CostHubRecommendation
from c7n.filters.kms import KmsRelatedFilter
import c7n.filters.vpc as net_filters
from c7n.manager import resources
from c7n import query, utils
from c7n.resources.aws import shape_validate
from c7n.resources.iam import CheckPermissions, SpecificIamRoleManagedPolicy
from c7n.tags import universal_augment
from c7n.utils import (
    local_session,
    type_schema,
    select_keys,
    get_human_size,
    parse_date,
    get_retry,
    jmespath_search,
    jmespath_compile
)
from botocore.config import Config
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
        arn = 'FunctionArn'
        arn_type = 'function'
        arn_separator = ":"
        enum_spec = ('list_functions', 'Functions', None)
        name = id = 'FunctionName'
        date = 'LastModified'
        dimension = 'FunctionName'
        config_type = 'AWS::Lambda::Function'
        cfn_type = 'AWS::Lambda::Function'
        universal_taggable = object()
        permissions_augment = ("lambda:ListTags",)

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


@AWSLambda.filter_registry.register('url-config')
class URLConfig(ValueFilter):

    annotation_key = "c7n:UrlConfig"
    schema = type_schema('url-config', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('lambda:GetFunctionUrlConfig',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('lambda')

        def _augment(r):
            try:
                r[self.annotation_key] = self.manager.retry(
                    client.get_function_url_config, FunctionName=r['FunctionArn'])
                r[self.annotation_key].pop('ResponseMetadata')
            except client.exceptions.ResourceNotFoundException:
                r[self.annotation_key] = {}
            return r

        with self.executor_factory(max_workers=2) as w:
            resources = list(filter(None, w.map(_augment, resources)))

        return super().process(resources, event)

    def __call__(self, i):
        return super().__call__(i[self.annotation_key])


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

    RelatedIdsExpression = 'KMSKeyArn'


@AWSLambda.filter_registry.register('has-specific-managed-policy')
class HasSpecificManagedPolicy(SpecificIamRoleManagedPolicy):
    """Filter an lambda function that has an IAM execution role that has a
    specific managed IAM policy.

    :example:

    .. code-block:: yaml

        policies:
          - name: lambda-has-admin-policy
            resource: aws.lambda
            filters:
              - type: has-specific-managed-policy
                value: admin-policy

    """

    permissions = ('iam:ListAttachedRolePolicies',)

    def process(self, resources, event=None):
        client = utils.local_session(self.manager.session_factory).client('iam')

        results = []
        roles = {
            r['Role']: {
                'RoleName': r['Role'].split('/')[-1]
            }
            for r in resources
        }

        for role in roles.values():
            self.get_managed_policies(client, [role])
        for r in resources:
            role_arn = r['Role']
            matched_keys = [k for k in roles[role_arn][self.annotation_key] if self.match(k)]
            self.merge_annotation(role, self.matched_annotation_key, matched_keys)
            if matched_keys:
                results.append(r)

        return results


@AWSLambda.action_registry.register('update')
class UpdateLambda(Action):
    """Update a lambda's configuration.

    This action also has specific support for enacting recommendations
    from the AWS Cost Optimization Hub for resizing.

    :example:

      .. code-block:: yaml

         policies:
           - name: lambda-rightsize
             resource: aws.lambda
             filters:
               - type: cost-optimization
                 attrs:
                   - actionType: Rightsize
             actions:
               - update

    """
    schema = type_schema('update', properties={'type': 'object'})
    permissions = ("lambda:UpdateFunctionConfiguration",)

    def validate(self):
        props = self.data.get('properties', {})
        props['FunctionName'] = 'validation'
        shape_validate(props, 'UpdateFunctionConfigurationRequest', 'lambda')

    def process(self, resources):
        client = utils.local_session(self.manager.session_factory).client('lambda')
        retry = get_retry(('TooManyRequestsException', 'ResourceConflictException'))

        for r in resources:
            params = self.get_parameters(r)
            params.pop('FunctionName', None)
            try:
                retry(
                    client.update_function_configuration,
                    FunctionName=r['FunctionName'],
                    **params
                )
            except client.exceptions.ResourceNotFoundException:
                continue

    def get_parameters(self, r):
        params = self.data.get('properties', {})
        hub_recommendation = r.get(CostHubRecommendation.annotation_key)
        if hub_recommendation and hub_recommendation['actionType'] == 'Rightsize':
            size = int(hub_recommendation['recommendedResourceSummary'].split(' ')[0])
            params['MemorySize'] = size
        return params


@AWSLambda.action_registry.register('set-xray-tracing')
class LambdaEnableXrayTracing(Action):
    """
    This action allows for enable Xray tracing to Active

    :example:

    .. code-block:: yaml

      actions:
        - type: enable-xray-tracing
    """

    schema = type_schema(
        'set-xray-tracing',
        **{'state': {'default': True, 'type': 'boolean'}}
    )
    permissions = ("lambda:UpdateFunctionConfiguration",)

    def get_mode_val(self, state):
        if state:
            return "Active"
        return "PassThrough"

    def process(self, resources):
        """
            Enables the Xray Tracing for the function.

            Args:
                resources: AWS lamdba resources
            Returns:
                None
        """
        config = Config(
            retries={
                'max_attempts': 8,
                'mode': 'standard'
            }
        )
        client = local_session(self.manager.session_factory).client('lambda', config=config)
        updateState = self.data.get('state', True)
        retry = get_retry(('TooManyRequestsException', 'ResourceConflictException'))

        mode = self.get_mode_val(updateState)
        for resource in resources:
            state = bool(resource["TracingConfig"]["Mode"] == "Active")
            if updateState != state:
                function_name = resource["FunctionName"]
                self.log.info(f"Set Xray tracing to {mode} for lambda {function_name}")
                try:
                    retry(
                        client.update_function_configuration,
                        FunctionName=function_name,
                        TracingConfig={
                            'Mode': mode
                        }
                    )
                except client.exceptions.ResourceNotFoundException:
                    continue


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
        # check and set the correct formatting value for kms key arn if it exists
        kms_value = r.get('KMSKeyArn')
        if kms_value is not None:
            details['KmsKeyArn'] = kms_value
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


@AWSLambda.action_registry.register('trim-versions')
class VersionTrim(Action):
    """Delete old versions of a function.

    By default this will only remove the non $LATEST
    version of a function that are not referenced by
    an alias. Optionally it can delete only versions
    older than a given age.

    :example:

      .. code-block:: yaml

         policies:
           - name: lambda-gc
             resource: aws.lambda
             actions:
               - type: trim-versions
                 exclude-aliases: true  # default true
                 older-than: 60 # default not-set
                 retain-latest: true # default false

    retain-latest refers to whether the latest numeric
    version will be retained, the $LATEST alias will
    still point to the last revision even without this set,
    so this is safe wrt to the function availability, its more
    about desire to retain an explicit version of the current
    code, rather than just the $LATEST alias pointer which will
    be automatically updated.
    """
    permissions = ('lambda:ListAliases', 'lambda:ListVersionsByFunction',
                   'lambda:DeleteFunction',)

    schema = type_schema(
        'trim-versions',
        **{'exclude-aliases': {'default': True, 'type': 'boolean'},
           'retain-latest': {'default': True, 'type': 'boolean'},
           'older-than': {'type': 'number'}})

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('lambda')
        matched = total = 0
        for r in resources:
            fmatched, ftotal = self.process_lambda(client, r)
            matched += fmatched
            total += ftotal
        self.log.info('trim-versions cleaned %s of %s lambda storage' % (
            get_human_size(matched), get_human_size(total)))

    def get_aliased_versions(self, client, r):
        aliases_pager = client.get_paginator('list_aliases')
        aliases_pager.PAGE_ITERATOR_CLASS = query.RetryPageIterator
        aliases = aliases_pager.paginate(
            FunctionName=r['FunctionName']).build_full_result().get('Aliases')

        aliased_versions = set()
        for a in aliases:
            aliased_versions.add("%s:%s" % (
                a['AliasArn'].rsplit(':', 1)[0], a['FunctionVersion']))
        return aliased_versions

    def process_lambda(self, client, r):
        exclude_aliases = self.data.get('exclude-aliases', True)
        retain_latest = self.data.get('retain-latest', False)
        date_threshold = self.data.get('older-than')
        date_threshold = (
            date_threshold and
            parse_date(datetime.utcnow()) - timedelta(days=date_threshold) or
            None)
        aliased_versions = ()

        if exclude_aliases:
            aliased_versions = self.get_aliased_versions(client, r)

        versions_pager = client.get_paginator('list_versions_by_function')
        versions_pager.PAGE_ITERATOR_CLASS = query.RetryPageIterator
        pager = versions_pager.paginate(FunctionName=r['FunctionName'])

        matched = total = 0
        latest_sha = None

        for page in pager:
            versions = page.get('Versions')
            for v in versions:
                if v['Version'] == '$LATEST':
                    latest_sha = v['CodeSha256']
                    continue
                total += v['CodeSize']
                if v['FunctionArn'] in aliased_versions:
                    continue
                if date_threshold and parse_date(v['LastModified']) > date_threshold:
                    continue
                # Retain numbered version, not required, but it feels like a good thing
                # to do. else the latest alias will still point.
                if retain_latest and latest_sha and v['CodeSha256'] == latest_sha:
                    continue
                matched += v['CodeSize']
                self.manager.retry(
                    client.delete_function, FunctionName=v['FunctionArn'])
        return (matched, total)


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

        _, found = self.process_policy(
            p, resource, CrossAccountAccessFilter.annotation_key)
        if not found:
            return

        for f in found:
            client.remove_permission(
                FunctionName=resource['FunctionName'],
                StatementId=f['Sid'])


@AWSLambda.action_registry.register('set-concurrency')
class SetConcurrency(Action):
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
            value = jmespath_compile(value)

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
class Delete(Action):
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
            if 'c7n:Policy' in r:
                continue
            try:
                rpolicy = self.manager.retry(
                    client.get_layer_version_policy,
                    LayerName=r['LayerName'],
                    VersionNumber=r['Version']).get('Policy')
            except client.exceptions.ResourceNotFoundException:
                rpolicy = {}
            r['c7n:Policy'] = rpolicy
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

        _, found = self.process_policy(
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
class DeleteLayerVersion(Action):

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


@AWSLambda.filter_registry.register('lambda-edge')
class LambdaEdgeFilter(Filter):
    """
    Filter for lambda@edge functions. Lambda@edge only exists in us-east-1

    :example:

        .. code-block:: yaml

            policies:
                - name: lambda-edge-filter
                  resource: lambda
                  region: us-east-1
                  filters:
                    - type: lambda-edge
                      state: True
    """
    permissions = ('cloudfront:ListDistributions',)

    schema = type_schema('lambda-edge',
        **{'state': {'type': 'boolean'}})

    def get_lambda_cf_map(self):
        cfs = self.manager.get_resource_manager('distribution').resources()
        func_expressions = ('DefaultCacheBehavior.LambdaFunctionAssociations.Items',
          'CacheBehaviors.Items[].LambdaFunctionAssociations.Items[]')
        lambda_dist_map = {}
        for d in cfs:
            for exp in func_expressions:
                if jmespath_search(exp, d):
                    for function in jmespath_search(exp, d):
                        # Geting rid of the version number in the arn
                        lambda_edge_arn = ':'.join(function['LambdaFunctionARN'].split(':')[:-1])
                        lambda_dist_map.setdefault(lambda_edge_arn, set()).add(d['Id'])
        return lambda_dist_map

    def process(self, resources, event=None):
        results = []
        if self.manager.config.region != 'us-east-1' and self.data.get('state'):
            return []
        annotation_key = 'c7n:DistributionIds'
        lambda_edge_cf_map = self.get_lambda_cf_map()
        for r in resources:
            if (r['FunctionArn'] in lambda_edge_cf_map and self.data.get('state')):
                r[annotation_key] = list(lambda_edge_cf_map.get(r['FunctionArn']))
                results.append(r)
            elif (r['FunctionArn'] not in lambda_edge_cf_map and not self.data.get('state')):
                results.append(r)
        return results


class DescribeEventSourceMappings(query.ChildDescribeSource):

    def augment(self, resources):
        client = local_session(self.manager.session_factory).client(
            self.manager.resource_type.service)

        resources = universal_augment(self.manager, super().augment(resources))

        # Part 1: Add tags from parent resources to child resources
        # This is used to identify the child resources from the parent lambda function
        parent_resources = self.manager.get_parent_manager().resources()
        parent_tag_map = {
            p['FunctionArn']: [
                {'Key': tag['Key'], 'Value': tag['Value']} for tag in p.get('Tags', [])
            ]
            for p in parent_resources
        }
        for r in resources:
            parent_tags = parent_tag_map.get(r['FunctionArn'], [])
            child_tags = r.get('Tags', [])
            r['Tags'] = parent_tags + child_tags

        # Part 2: Get all event source mappings and add orphaned ones to resources
        existing_uuids = {r['UUID'] for r in resources}
        paginator = client.get_paginator('list_event_source_mappings')
        paginator.PAGE_ITERATOR_CLS = query.RetryPageIterator
        for page in paginator.paginate():
            for mapping in page.get('EventSourceMappings', []):
                if mapping['UUID'] not in existing_uuids:
                    resources.append(mapping)

        return resources


@resources.register('lambda-event-source-mapping')
class LambdaEventSourceMapping(query.ChildResourceManager):

    class resource_type(query.TypeInfo):
        service = 'lambda'
        enum_spec = ('list_event_source_mappings', 'EventSourceMappings', None)
        detail_spec = ('get_event_source_mapping', 'UUID', 'UUID', None)
        name = id = 'UUID'
        arn = "EventSourceMappingArn"
        cfn_type = 'AWS::Lambda::EventSourceMapping'
        permissions_augment = ("lambda:ListEventSourceMappings", "lambda:GetEventSourceMapping",
                                 "lambda:ListTags")
        parent_spec = ('lambda', 'FunctionName', True)

    source_mapping = {
        'describe-child': DescribeEventSourceMappings,
    }

    # def augment(self, resources):
    #     # Call the original augment method from ChildResourceManager
    #     resources = super().augment(resources)

    #     # Part 1: Add tags from parent resources to child resources
    #    parent_resources = self.get_parent_manager().resources()
    #parent_tag_map = {p['FunctionArn']: [{'Key': tag['Key'], 'Value': tag['Value']} for tag in p.get('Tags', [])] for p in parent_resources}

    #     client = local_session(self.session_factory).client('lambda')
    #     tagging_client = local_session(self.session_factory).client('resourcegroupstaggingapi')

    #     # Collect ARNs for Event Source Mappings
    #     resource_arns = [r['EventSourceMappingArn'] for r in resources]

    #     # Fetch tags using Resource Tagging API
    #     try:
    #         response = tagging_client.get_resources(
    #             ResourceARNList=resource_arns,
    #             TagFilters=[]
    #         )
    #         tag_map = {
    #             tag['ResourceARN']: [{'Key': t['Key'], 'Value': t['Value']} for t in tag.get('Tags', [])]
    #             for tag in response.get('ResourceTagMappingList', [])
    #         }
    #     except ClientError as e:
    #         self.log.warning(f"Failed to fetch tags using Resource Tagging API: {e}")
    #         tag_map = {}

    #     for resource in resources:
    #         # Get tags from parent resources
    #         parent_tags = parent_tag_map.get(resource['FunctionArn'], [])

    #         # Get tags from child resources (Event Source Mapping)
    #         child_tags = tag_map.get(resource['EventSourceMappingArn'], [])

    #         # Merge parent and child tags
    #         merged_tags = parent_tags + child_tags
    #         resource['Tags'] = merged_tags

    #     # Part 2: Get all event source mappings and add orphaned ones to resources
    #     existing_uuids = {r['UUID'] for r in resources}
    #     paginator = client.get_paginator('list_event_source_mappings')
    #     paginator.PAGE_ITERATOR_CLS = query.RetryPageIterator
    #     for page in paginator.paginate():
    #         for mapping in page.get('EventSourceMappings', []):
    #             if mapping['UUID'] not in existing_uuids:
    #                 resources.append(mapping)

    #     return resources


@LambdaEventSourceMapping.filter_registry.register('kms-key')
class KmsEventSourceMappingFilter(KmsRelatedFilter):
    RelatedIdsExpression = 'KMSKeyArn'
