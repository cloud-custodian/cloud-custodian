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

import json
from botocore.exceptions import ClientError

from c7n.actions import ActionRegistry, AutoTagUser, BaseAction
from c7n.filters import CrossAccountAccessFilter, FilterRegistry, ValueFilter
import c7n.filters.vpc as net_filters
from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.tags import RemoveTag, Tag, TagActionFilter, TagDelayedAction
from c7n.utils import get_retry, local_session, type_schema

filters = FilterRegistry('lambda.filters')
actions = ActionRegistry('lambda.actions')
filters.register('marked-for-op', TagActionFilter)
actions.register('auto-tag-user', AutoTagUser)


@resources.register('lambda')
class AWSLambda(QueryResourceManager):

    class resource_type(object):
        service = 'lambda'
        type = 'function'
        enum_spec = ('list_functions', 'Functions', None)
        name = id = 'FunctionName'
        filter_name = None
        date = 'LastModified'
        dimension = 'FunctionName'

    filter_registry = filters
    action_registry = actions
    retry = staticmethod(get_retry(('Throttled',)))

    def augment(self, functions):
        resources = super(AWSLambda, self).augment(functions)
        return filter(None, _lambda_function_tags(
            self.get_model(),
            resources,
            self.session_factory,
            self.executor_factory,
            self.retry,
            self.log))


def _lambda_function_tags(
        model, functions, session_factory, executor_factory, retry, log):
    """ Augment Lambda function with their respective tags
    """

    def process_tags(function):
        client = local_session(session_factory).client('lambda')
        arn = function['FunctionArn']
        try:
            tag_dict = retry(client.list_tags, Resource=arn)['Tags']
        except ClientError as e:
            log.warning("Exception getting Lambda tags  \n %s", e)
            return None
        tag_list = []
        for k, v in tag_dict.items():
            tag_list.append({'Key': k, 'Value': v})
        function['Tags'] = tag_list
        return function

    with executor_factory(max_workers=2) as w:
        return list(w.map(process_tags, functions))


def tag_function(session_factory, functions, tags, log):
    client = local_session(session_factory).client('lambda')
    tag_dict = {}
    for t in tags:
        tag_dict[t['Key']] = t['Value']
    for f in functions:
        arn = f['FunctionArn']
        try:
            client.tag_resource(Resource=arn, Tags=tag_dict)
        except Exception as err:
            log.exception(
                'Exception tagging lambda function %s: %s',
                f['FunctionName'], err)
            continue


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "VpcConfig.SecurityGroupIds[]"


@filters.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "VpcConfig.SubnetIds[]"


filters.register('network-location', net_filters.NetworkLocation)


@filters.register('event-source')
class LambdaEventSource(ValueFilter):
    # this uses iam policy, it should probably use
    # event source mapping api

    annotation_key = "c7n:EventSources"
    schema = type_schema('event-source', rinherit=ValueFilter.schema)
    permissions = ('lambda:GetPolicy',)

    def process(self, resources, event=None):
        def _augment(r):
            if 'c7n:Policy' in r:
                return
            client = local_session(
                self.manager.session_factory).client('lambda')
            try:
                r['c7n:Policy'] = client.get_policy(
                    FunctionName=r['FunctionName'])['Policy']
                return r
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDeniedException':
                    self.log.warning(
                        "Access denied getting policy lambda:%s",
                        r['FunctionName'])

        self.log.debug("fetching policy for %d lambdas" % len(resources))
        self.data['key'] = self.annotation_key

        with self.executor_factory(max_workers=3) as w:
            resources = filter(None, w.map(_augment, resources))
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


@filters.register('cross-account')
class LambdaCrossAccountAccessFilter(CrossAccountAccessFilter):
    """Filters lambda functions with cross-account permissions

    The whitelist parameter can be used to prevent certain accounts
    from being included in the results (essentially stating that these
    accounts permissions are allowed to exist)

    This can be useful when combining this filter with the delete action.

    :example:

        .. code-block: yaml

            policies:
              - name: lambda-cross-account
                resource: lambda
                filters:
                  - type: cross-account
                    whitelist:
                      - 'IAM-Policy-Cross-Account-Access'

    """
    permissions = ('lambda:GetPolicy',)

    def process(self, resources, event=None):

        def _augment(r):
            client = local_session(
                self.manager.session_factory).client('lambda')
            try:
                r['Policy'] = client.get_policy(
                    FunctionName=r['FunctionName'])['Policy']
                return r
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDeniedException':
                    self.log.warning(
                        "Access denied getting policy lambda:%s",
                        r['FunctionName'])

        self.log.debug("fetching policy for %d lambdas" % len(resources))
        with self.executor_factory(max_workers=3) as w:
            resources = filter(None, w.map(_augment, resources))

        return super(LambdaCrossAccountAccessFilter, self).process(
            resources, event)


@actions.register('mark-for-op')
class TagDelayedAction(TagDelayedAction):
    """Action to specify an action to occur at a later date

    :example:

        .. code-block: yaml

            policies:
              - name: lambda-delete-unused
                resource: lambda
                filters:
                  - "tag:custodian_cleanup": absent
                actions:
                  - type: mark-for-op
                    tag: custodian_cleanup
                    msg: "Unused lambda"
                    op: delete
                    days: 7
    """

    permissions = ('lambda:TagResource',)

    def process_resource_set(self, functions, tags):
        tag_function(self.manager.session_factory, functions, tags, self.log)


@actions.register('tag')
class Tag(Tag):
    """Action to add tag(s) to Lambda Function(s)

    :example:

        .. code-block: yaml

            policies:
              - name: lambda-add-owner-tag
                resource: lambda
                filters:
                  - "tag:OwnerName": missing
                actions:
                  - type: tag
                    key: OwnerName
                    value: OwnerName
    """

    permissions = ('lambda:TagResource',)

    def process_resource_set(self, functions, tags):
        tag_function(self.manager.session_factory, functions, tags, self.log)


@actions.register('remove-tag')
class RemoveTag(RemoveTag):
    """Action to remove tag(s) from Lambda Function(s)

    :example:

        .. code-block: yaml

            policies:
              - name: lambda-remove-old-tag
                resource: lambda
                filters:
                  - "tag:OldTagKey": present
                actions:
                  - type: remove-tag
                    tags: [OldTagKey1, OldTagKey2]
    """

    permissions = ('lambda:UntagResource',)

    def process_resource_set(self, functions, tag_keys):
        client = local_session(self.manager.session_factory).client('lambda')
        for f in functions:
            arn = f['FunctionArn']
            client.untag_resource(Resource=arn, TagKeys=tag_keys)


@actions.register('delete')
class Delete(BaseAction):
    """Delete a lambda function (including aliases and older versions).

    :example:

        .. code-block: yaml

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
