import botocore.exceptions
from botocore.config import Config

from c7n import query
from c7n.actions import BaseAction
from c7n.filters import MetricsFilter
from c7n.filters.core import ValueFilter
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.filters.related import ChildResourceFilter
from c7n.manager import resources
from c7n.query import (ChildDescribeSource, ChildResourceManager, ChildResourceQuery, ConfigSource,
    DescribeSource, DescribeWithResourceTags, QueryResourceManager, RetryPageIterator, TypeInfo)
from c7n.resolver import ValuesFrom
from c7n.resources import load_resources
from c7n.resources.aws import ArnResolver
from c7n.tags import RemoveTag, Tag, universal_augment
from c7n.utils import chunks, get_retry, local_session, type_schema


@resources.register('event-bus')
class EventBus(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'events'
        arn_type = 'event-bus'
        arn = 'Arn'
        enum_spec = ('list_event_buses', 'EventBuses', None)
        detail_spec = ('describe_event_bus', 'Name', 'Name', None)
        config_type = cfn_type = 'AWS::Events::EventBus'
        id = name = 'Name'
        universal_taggable = object()
        permissions_augment = ("events:ListTagsForResource",)

    source_mapping = {'describe': DescribeWithResourceTags,
                      'config': ConfigSource}


@EventBus.filter_registry.register('cross-account')
class EventBusCrossAccountFilter(CrossAccountAccessFilter):
    # dummy permission
    permissions = ('events:ListEventBuses',)


@EventBus.filter_registry.register('kms-key')
class EventBusKmsFilter(KmsRelatedFilter):
    RelatedIdsExpression = 'KmsKeyIdentifier'


@EventBus.action_registry.register('delete')
class EventBusDelete(BaseAction):
    """Delete an event bus.

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudwatch-delete-event-bus
                resource: aws.event-bus
                filters:
                    - Name: test-event-bus
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('events:DeleteEventBus',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('events')

        for resource_set in chunks(resources, size=100):
            for r in resource_set:
                self.manager.retry(
                    client.delete_event_bus,
                    Name=r['Name'])


@resources.register('api-destination')
class ApiDestination(QueryResourceManager):
    """EventBridge API Destination Resource

    :example:

    .. code-block:: yaml

        policies:
          - name: list-api-destinations
            resource: aws.api-destination
            filters:
              - type: value
                key: ApiDestinationState
                value: ACTIVE
    """

    class resource_type(TypeInfo):
        service = 'events'
        arn_type = 'api-destination'
        arn = 'ApiDestinationArn'
        enum_spec = ('list_api_destinations', 'ApiDestinations', None)
        detail_spec = ('describe_api_destination', 'Name', 'Name', None)
        config_type = cfn_type = 'AWS::Events::ApiDestination'
        id = name = 'Name'
        universal_taggable = object()
        permissions_augment = ("events:ListTagsForResource",)

    source_mapping = {'describe': DescribeWithResourceTags,
                      'config': ConfigSource}


class EventRuleQuery(ChildResourceQuery):

    def get_parent_parameters(self, params, parent_id, parent_key):
        merged_params = dict(params)
        merged_params[parent_key] = parent_id
        return merged_params


@query.sources.register('event-rule')
class EventRuleSource(ChildDescribeSource):

    resource_query_factory = EventRuleQuery

    def augment(self, resources):
        return universal_augment(self.manager, resources)


@resources.register('event-rule')
class EventRule(ChildResourceManager):

    child_source = 'event-rule'
    class resource_type(TypeInfo):
        service = 'events'
        arn = 'Arn'
        enum_spec = ('list_rules', 'Rules', None)
        parent_spec = ('event-bus', 'EventBusName', None)
        name = "Name"
        id = "Name"
        filter_name = "NamePrefix"
        filter_type = "scalar"
        config_type = cfn_type = 'AWS::Events::Rule'
        universal_taggable = object()
        permissions_augment = ("events:ListTagsForResource",)


@EventRule.filter_registry.register('metrics')
class EventRuleMetrics(MetricsFilter):

    def get_dimensions(self, resource):
        return [{'Name': 'RuleName', 'Value': resource['Name']}]


class EventChildResourceFilter(ChildResourceFilter):

    # This function provides custom functionality to query event-rule-targets
    # using both event-rule and event-bus information.
    def get_related(self, resources):
        self.child_resources = {}
        child_resource_manager = self.get_resource_manager()
        client = local_session(child_resource_manager.session_factory).client('events')
        paginator_targets = client.get_paginator('list_targets_by_rule')
        paginator_targets.PAGE_ITERATOR_CLS = RetryPageIterator

        for r in resources:
            targets = paginator_targets.paginate(EventBusName=r['EventBusName'], Rule=r['Name']) \
            .build_full_result().get('Targets', [])
            for target in targets:
                target[self.ChildResourceParentKey] = r['Name']
                self.child_resources.setdefault(target[self.ChildResourceParentKey], []) \
                .append(target)

        return self.child_resources


@EventRule.filter_registry.register('event-rule-target')
class EventRuleTargetFilter(EventChildResourceFilter):

    """
    Filter event rules by their targets

    :example:

    .. code-block:: yaml

        policies:
            - name: find-event-rules-with-no-targets
              resource: aws.event-rule
              filters:
                - type: event-rule-target
                  key: "@"
                  value: empty

            - name: find-event-rules-by-target-properties
              resource: aws.event-rule
              filters:
                - type: event-rule-target
                  key: "[].Arn"
                  op: contains
                  value: "arn:aws:sqs:us-east-2:111111111111:my-queue"
    """

    RelatedResource = "c7n.resources.eventbridge.EventRuleTarget"
    RelatedIdsExpression = 'Name'
    AnnotationKey = "EventRuleTargets"

    schema = type_schema('event-rule-target', rinherit=ValueFilter.schema)
    permissions = ('events:ListTargetsByRule',)


@EventRule.filter_registry.register('invalid-targets')
class ValidEventRuleTargetFilter(EventChildResourceFilter):
    """
    Filter event rules for invalid targets, Use the `all` option to
    find any event rules that have all invalid targets, otherwise
    defaults to filtering any event rule with at least one invalid
    target.

    :example:

    .. code-block:: yaml

        policies:
            - name: find-event-rules-with-invalid-targets
              resource: aws.event-rule
              filters:
                - type: invalid-targets
                  all: true # defaults to false
    """

    RelatedResource = "c7n.resources.eventbridge.EventRuleTarget"
    RelatedIdsExpression = 'Name'
    AnnotationKey = "EventRuleTargets"

    schema = type_schema(
        'invalid-targets',
        **{
            'all': {
                'type': 'boolean',
                'default': False
            }
        }
    )

    permissions = ('events:ListTargetsByRule',)
    supported_resources = (
        "aws.sqs",
        "aws.event-bus",
        "aws.lambda",
        "aws.ecs",
        "aws.ecs-task",
        "aws.kinesis",
        "aws.sns",
        "aws.ssm-parameter",
        "aws.batch-compute",
        "aws.codepipeline",
        "aws.step-machine",
    )

    def validate(self):
        """
        Empty validate here to bypass the validation found in the base value filter
        as we're inheriting from the ChildResourceFilter/RelatedResourceFilter
        """
        return self

    def get_rules_with_children(self, resources):
        """
        Augments resources by adding the c7n:ChildArns to the resource dict
        """

        results = []

        # returns a map of {parent_reosurce_id: [{child_resource}, {child_resource2}, etc.]}
        child_resources = self.get_related(resources)

        # maps resources by their name to their data
        for r in resources:
            if child_resources.get(r['Name']):
                for c in child_resources[r['Name']]:
                    r.setdefault('c7n:ChildArns', []).append(c['Arn'])
                results.append(r)
        return results

    def process(self, resources, event=None):
        # Due to lazy loading of resources, we need to explicilty load the following
        # potential targets for a event rule target:

        load_resources(list(self.supported_resources))
        arn_resolver = ArnResolver(self.manager)
        resources = self.get_rules_with_children(resources)
        resources = [r for r in resources if self.filter_unsupported_resources(r)]
        results = []

        if self.data.get('all'):
            op = any
        else:
            op = all

        for r in resources:
            resolved = arn_resolver.resolve(r['c7n:ChildArns'])
            if not op(resolved.values()):
                for i, j in resolved.items():
                    if not j:
                        r.setdefault('c7n:InvalidTargets', []).append(i)
                results.append(r)
        return results

    def filter_unsupported_resources(self, r):
        for carn in r.get('c7n:ChildArns'):
            if 'aws.' + str(ArnResolver.resolve_type(carn)) not in self.supported_resources:
                self.log.info(
                    f"Skipping resource {r.get('Arn')}, target type {carn} is not supported")
                return False
            return True


@EventRule.action_registry.register('delete')
class EventRuleDelete(BaseAction):
    """
    Delete an event rule, force target removal with the `force` option

    :example:

    .. code-block:: yaml

        policies:
            - name: force-delete-rules
              resource: aws.event-rule
              filters:
                - Name: my-event-rule
              actions:
                - type: delete
                  force: true
    """

    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = ('events:DeleteRule', 'events:RemoveTargets', 'events:ListTargetsByRule',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('events')
        children = {}
        target_error_msg = "Rule can't be deleted since it has targets."
        for r in resources:
            try:
                client.delete_rule(Name=r['Name'], EventBusName=r['EventBusName'])
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Message'] != target_error_msg:
                    raise
                if not self.data.get('force'):
                    self.log.warning(
                        'Unable to delete %s event rule due to attached rule targets,'
                        'set force to true to remove targets' % r['Name'])
                    raise
                child_manager = self.manager.get_resource_manager('aws.event-rule-target')
                if not children:
                    children = EventRuleTargetFilter({}, child_manager).get_related(resources)
                targets = list(set([t['Id'] for t in children.get(r['Name'])]))
                client.remove_targets(Rule=r['Name'], Ids=targets, EventBusName=r['EventBusName'])
                client.delete_rule(Name=r['Name'], EventBusName=r['EventBusName'])


@EventRule.action_registry.register('set-rule-state')
class SetRuleState(BaseAction):
    """
    This action allows to enable/disable a rule

    :example:

    .. code-block:: yaml

        policies:
            - name: test-rule
              resource: aws.event-rule
              filters:
                - Name: my-event-rule
              actions:
                - type: set-rule-state
                  enabled: true
    """

    schema = type_schema(
        'set-rule-state',
        **{'enabled': {'default': True, 'type': 'boolean'}}
    )
    permissions = ('events:EnableRule', 'events:DisableRule',)

    def process(self, resources):
        config = Config(
            retries={
                'max_attempts': 8,
                'mode': 'standard'
            }
        )
        client = local_session(self.manager.session_factory).client('events', config=config)
        retry = get_retry(('TooManyRequestsException', 'ResourceConflictException'))
        enabled = self.data.get('enabled')
        for resource in resources:
            try:
                if enabled:
                    retry(
                        client.enable_rule,
                        Name=resource['Name']
                    )
                else:
                    retry(
                        client.disable_rule,
                        Name=resource['Name']
                    )
            except (client.exceptions.ResourceNotFoundException,
                    client.exceptions.ManagedRuleException):
                continue


class EventRuleTargetQuery(query.ChildResourceQuery):

    # This function provides custom functionality to query event-rule-targets
    # using both event-rule and event-bus information.
    def filter(self, resource_manager, parent_ids=None, **params):
        """Query a set of resources."""
        m = self.resolve(resource_manager.resource_type)
        client = local_session(self.session_factory).client(m.service)

        enum_op, path, extra_args = m.enum_spec
        if extra_args:
            params.update(extra_args)

        parent_type, parent_key, annotate_parent = m.parent_spec
        parents = self.manager.get_resource_manager(parent_type)
        parent_resources = []
        for p in parents.resources(augment=False):
            parent_resources.append((p))

        # Have to query separately for each parent's children.
        results = []
        for parent in parent_resources:
            params['EventBusName'] = parent['EventBusName']
            merged_params = self.get_parent_parameters(params, parent['Name'], parent_key)
            subset = self._invoke_client_enum(
                client, enum_op, merged_params, path, retry=self.manager.retry)
            if annotate_parent:
                for r in subset:
                    r[self.parent_key] = parent['Name']
                    r[parent_key] = parent
            if subset:
                results.extend(subset)
        return results

    def get_parent_parameters(self, params, parent_id, parent_key):
        merged_params = dict(params)
        merged_params[parent_key] = parent_id
        return merged_params


@query.sources.register('event-rule-target')
class EventRuleTargetSource(ChildDescribeSource):

    resource_query_factory = EventRuleTargetQuery


@resources.register('event-rule-target')
class EventRuleTarget(ChildResourceManager):

    child_source = 'event-rule-target'
    class resource_type(TypeInfo):
        service = 'events'
        arn = False
        arn_type = 'event-rule-target'
        enum_spec = ('list_targets_by_rule', 'Targets', None)
        parent_spec = ('event-rule', 'Rule', True)
        name = id = 'Id'


@EventRuleTarget.filter_registry.register('cross-account')
class CrossAccountFilter(CrossAccountAccessFilter):
    schema = type_schema(
        'cross-account',
        # white list accounts
        whitelist_from=ValuesFrom.schema,
        whitelist={'type': 'array', 'items': {'type': 'string'}})

    # dummy permission
    permissions = ('events:ListTargetsByRule',)

    def __call__(self, r):
        account_id = r['Arn'].split(':', 5)[4]
        return account_id not in self.accounts


@EventRuleTarget.action_registry.register('delete')
class DeleteTarget(BaseAction):
    schema = type_schema('delete')
    permissions = ('events:RemoveTargets',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('events')
        rule_targets = {}
        for r in resources:
            event_bus = r['Rule']['EventBusName']
            rule_id = r['c7n:parent-id']
            rule_targets.setdefault((rule_id, event_bus), []).append(r['Id'])

        for (rule_id, event_bus), target_ids in rule_targets.items():
            client.remove_targets(
                Ids=target_ids,
                Rule=rule_id,
                EventBusName=event_bus)


class EventBridgePipesDescribe(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        for r in resources:
            if 'Tags' in r:
                r['Tags'] = [{'Key': k, 'Value': v} for k, v in r['Tags'].items()]
        return resources


@resources.register('eventbridge-pipes')
class EventBridgePipes(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'pipes'
        arn_type = 'pipe'
        enum_spec = ('list_pipes', 'Pipes', None)
        detail_spec = (
            'describe_pipe', 'Name', 'Name', None)
        id = name = 'Name'
        arn = 'Arn'
        cfn_type = 'AWS::Pipes::Pipe'

    retry = staticmethod(
        get_retry((
            'InternalException',
            'ConflictException',
            'ThrottlingException',)))
    source_mapping = {
        'describe': EventBridgePipesDescribe,
    }


@EventBridgePipes.action_registry.register('tag')
class TagPipe(Tag):
    permissions = ('pipes:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        tags = {tag['Key']: tag['Value'] for tag in new_tags}
        for r in resources:
            self.manager.retry(client.tag_resource, resourceArn=r['Arn'], tags=tags)


@EventBridgePipes.action_registry.register('remove-tag')
class UntagTagPipe(RemoveTag):
    permissions = ('pipes:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            self.manager.retry(client.untag_resource, resourceArn=r['Arn'], tagKeys=tags)


@EventBridgePipes.action_registry.register('stop')
class StopPipe(BaseAction):
    permissions = ('pipes:StopPipe',)
    schema = type_schema('stop')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('pipes')
        for resource in resources:
            self.manager.retry(
                client.stop_pipe,
                Name=resource['Name'],
                ignore_err_codes=('NotFoundException',)
            )


@EventBridgePipes.action_registry.register('delete')
class DeletePipe(BaseAction):
    permissions = ('pipes:DeletePipe',)
    schema = type_schema('delete')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('pipes')
        for resource in resources:
            self.manager.retry(
                client.delete_pipe,
                Name=resource['Name'],
                ignore_err_codes=('NotFoundException',)
            )
