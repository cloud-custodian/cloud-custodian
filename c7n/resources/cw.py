# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import itertools
import re
from collections import defaultdict
from concurrent.futures import as_completed
from datetime import datetime, timedelta

import botocore.exceptions
from botocore.config import Config

from c7n import query
from c7n.actions import Action, BaseAction
from c7n.exceptions import PolicyValidationError
from c7n.filters import Filter, MetricsFilter
from c7n.filters.core import parse_date, ValueFilter
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.filters.kms import KmsRelatedFilter
from c7n.filters.related import ChildResourceFilter
from c7n.manager import resources
from c7n.query import (
    QueryResourceManager, ChildResourceManager,
    TypeInfo, DescribeSource, ConfigSource, DescribeWithResourceTags, RetryPageIterator)
from c7n.resolver import ValuesFrom
from c7n.resources import load_resources
from c7n.resources.aws import ArnResolver
from c7n.tags import universal_augment
from c7n.utils import type_schema, local_session, chunks, get_retry, jmespath_search


class DescribeAlarm(DescribeSource):
    def augment(self, resources):
        return universal_augment(self.manager, super().augment(resources))


@resources.register('alarm')
class Alarm(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'cloudwatch'
        arn_type = 'alarm'
        enum_spec = ('describe_alarms', 'MetricAlarms', None)
        id = 'AlarmName'
        arn = 'AlarmArn'
        filter_name = 'AlarmNames'
        filter_type = 'list'
        name = 'AlarmName'
        date = 'AlarmConfigurationUpdatedTimestamp'
        cfn_type = config_type = 'AWS::CloudWatch::Alarm'
        universal_taggable = object()
        permissions_augment = ("cloudwatch:ListTagsForResource",)

    source_mapping = {
        'describe': DescribeAlarm,
        'config': ConfigSource
    }

    retry = staticmethod(get_retry(('Throttled',)))


@Alarm.action_registry.register('delete')
class AlarmDelete(BaseAction):
    """Delete a cloudwatch alarm.

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudwatch-delete-stale-alarms
                resource: alarm
                filters:
                  - type: value
                    value_type: age
                    key: StateUpdatedTimestamp
                    value: 30
                    op: ge
                  - StateValue: INSUFFICIENT_DATA
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('cloudwatch:DeleteAlarms',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('cloudwatch')

        for resource_set in chunks(resources, size=100):
            self.manager.retry(
                client.delete_alarms,
                AlarmNames=[r['AlarmName'] for r in resource_set])


@Alarm.filter_registry.register('is-composite-child')
class IsCompositeChild(Filter):
    schema = type_schema('is-composite-child', state={"type": "boolean"})
    permissions = ('cloudwatch:DescribeAlarms',)

    def process(self, resources, event=None):
        state = self.data.get("state", True)
        # Get the composite alarms since filtered out in enum_spec
        composite_alarms = self.manager.get_resource_manager("composite-alarm").resources()
        composite_alarm_rules = jmespath_search('[].AlarmRule', composite_alarms)

        child_alarm_names = set()
        # Loop through, find child alarm names
        for rule in composite_alarm_rules:
            names = self.extract_alarm_names_from_rule(rule)
            child_alarm_names.update(names)

        if state:
            # If we want to filter out alarms that are a child of a composite alarm
            return [r for r in resources if r['AlarmName'] in child_alarm_names]

        return [r for r in resources if r['AlarmName'] not in child_alarm_names]

    def extract_alarm_names_from_rule(self, rule):
        # Check alarm references (OK/ALARM/INSUFFICIENT_DATA)
        pattern = r"\b(?:ALARM|OK|INSUFFICIENT_DATA)\s*\(\s*([^\)]+)\s*\)"
        matches = re.findall(pattern, rule)
        return set(matches)


@resources.register('composite-alarm')
class CompositeAlarm(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'cloudwatch'
        arn_type = 'alarm'
        enum_spec = ('describe_alarms', 'CompositeAlarms', {'AlarmTypes': ['CompositeAlarm']})
        id = name = 'AlarmName'
        arn = 'AlarmArn'
        date = 'AlarmConfigurationUpdatedTimestamp'
        cfn_type = 'AWS::CloudWatch::CompositeAlarm'
        universal_taggable = object()

    augment = universal_augment

    retry = staticmethod(get_retry(('Throttled',)))


@CompositeAlarm.action_registry.register('delete')
class CompositeAlarmDelete(BaseAction):
    """Delete a cloudwatch composite alarm.

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudwatch-delete-composite-alarms
                resource: aws.composite-alarm
                filters:
                  - type: value
                    value_type: age
                    key: StateUpdatedTimestamp
                    value: 30
                    op: ge
                  - StateValue: INSUFFICIENT_DATA
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('cloudwatch:DeleteAlarms',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('cloudwatch')

        for resource_set in chunks(resources, size=100):
            self.manager.retry(
                client.delete_alarms,
                AlarmNames=[r['AlarmName'] for r in resource_set])


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


class EventRuleQuery(query.ChildResourceQuery):

    def get_parent_parameters(self, params, parent_id, parent_key):
        merged_params = dict(params)
        merged_params[parent_key] = parent_id
        return merged_params


@query.sources.register('event-rule')
class EventRuleSource(query.ChildDescribeSource):

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

    RelatedResource = "c7n.resources.cw.EventRuleTarget"
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

    RelatedResource = "c7n.resources.cw.EventRuleTarget"
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
class EventRuleTargetSource(query.ChildDescribeSource):

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


@resources.register('log-group')
class LogGroup(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'logs'
        arn_type = 'log-group'
        enum_spec = ('describe_log_groups', 'logGroups', None)
        id = name = 'logGroupName'
        arn = 'arn'  # see get-arns override re attribute usage
        filter_name = 'logGroupNamePrefix'
        filter_type = 'scalar'
        dimension = 'LogGroupName'
        date = 'creationTime'
        universal_taggable = True
        cfn_type = 'AWS::Logs::LogGroup'
        permissions_augment = ("logs:ListTagsForResource",)

    augment = universal_augment

    def get_arns(self, resources):
        # log group arn in resource describe has ':*' suffix, not all
        # apis can use that form, so normalize to standard arn.
        return [r['arn'][:-2] for r in resources]


@resources.register('insight-rule')
class InsightRule(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'cloudwatch'
        arn_type = 'insight-rule'
        enum_spec = ('describe_insight_rules', 'InsightRules', None)
        name = id = 'Name'
        universal_taggable = object()
        permission_augment = ('cloudWatch::ListTagsForResource',)
        cfn_type = 'AWS::CloudWatch::InsightRule'

    def augment(self, rules):
        client = local_session(self.session_factory).client('cloudwatch')

        def _add_tags(r):
            arn = self.generate_arn(r['Name'])
            r['Tags'] = client.list_tags_for_resource(
                ResourceARN=arn).get('Tags', [])
            return r

        return list(map(_add_tags, rules))


@InsightRule.action_registry.register('disable')
class InsightRuleDisable(BaseAction):
    """Disable a cloudwatch contributor insight rule.

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudwatch-disable-insight-rule
                resource: insight-rule
                filters:
                  - type: value
                    key: State
                    value: ENABLED
                    op: eq
                actions:
                  - disable
    """

    schema = type_schema('disable')
    permissions = ('cloudwatch:DisableInsightRules',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('cloudwatch')

        for resource_set in chunks(resources, size=100):
            self.manager.retry(
                client.disable_insight_rules,
                RuleNames=[r['Name'] for r in resource_set])


@InsightRule.action_registry.register('delete')
class InsightRuleDelete(BaseAction):
    """Delete a cloudwatch contributor insight rule

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudwatch-delete-insight-rule
                resource: insight-rule
                filters:
                  - type: value
                    key: State
                    value: ENABLED
                    op: eq
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('cloudwatch:DeleteInsightRules',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('cloudwatch')

        for resource_set in chunks(resources, size=100):
            self.manager.retry(
                client.delete_insight_rules,
                RuleNames=[r['Name'] for r in resource_set])


@LogGroup.filter_registry.register('metrics')
class LogGroupMetrics(MetricsFilter):

    def get_dimensions(self, resource):
        return [{'Name': 'LogGroupName', 'Value': resource['logGroupName']}]


@resources.register('log-metric')
class LogMetric(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'logs'
        enum_spec = ('describe_metric_filters', 'metricFilters', None)
        arn = False
        id = name = 'filterName'
        date = 'creationTime'
        cfn_type = 'AWS::Logs::MetricFilter'


@LogMetric.filter_registry.register('alarm')
class LogMetricAlarmFilter(ValueFilter):
    """
    Filter log metric filters based on associated alarms.

    :example:

    .. code-block:: yaml

        policies:
          - name: log-metrics-with-alarms
            resource: aws.log-metric
            filters:
              - type: alarm
                key: AlarmName
                value: present
    """

    schema = type_schema('alarm', rinherit=ValueFilter.schema)
    annotation_key = 'c7n:MetricAlarms'
    FetchThreshold = 10  # below this number of resources, fetch alarms individually

    def augment(self, resources):
        """Add alarm details to log metric filter resources

        This includes all alarms where the metric name and namespace match
        a log metric filter's metric transformation.
        """

        if len(resources) < self.FetchThreshold:
            client = local_session(self.manager.session_factory).client('cloudwatch')
            for r in resources:
                r[self.annotation_key] = list(itertools.chain(*(
                    self.manager.retry(
                        client.describe_alarms_for_metric,
                        Namespace=t['metricNamespace'],
                        MetricName=t['metricName'])['MetricAlarms']
                    for t in r.get('metricTransformations', ())
                )))
        else:
            alarms = self.manager.get_resource_manager('aws.alarm').resources()

            # We'll be matching resources to alarms based on namespace and
            # metric name - this lookup table makes that smoother
            alarms_by_metric = defaultdict(list)
            for alarm in alarms:
                alarms_by_metric[(alarm['Namespace'], alarm['MetricName'])].append(alarm)

            for r in resources:
                r[self.annotation_key] = list(itertools.chain(*(
                    alarms_by_metric.get((t['metricNamespace'], t['metricName']), [])
                    for t in r.get('metricTransformations', ())
                )))

    def get_permissions(self):
        return [
            *self.manager.get_resource_manager('aws.alarm').get_permissions(),
            'cloudwatch:DescribeAlarmsForMetric'
        ]

    def process(self, resources, event=None):
        self.augment(resources)

        matched = []
        for r in resources:
            if any((self.match(alarm) for alarm in r[self.annotation_key])):
                matched.append(r)
        return matched


@LogGroup.action_registry.register('retention')
class Retention(BaseAction):
    """Action to set the retention period (in days) for CloudWatch log groups

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudwatch-set-log-group-retention
                resource: log-group
                actions:
                  - type: retention
                    days: 200
    """

    schema = type_schema('retention', days={'type': 'integer'})
    permissions = ('logs:PutRetentionPolicy',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('logs')
        days = self.data['days']
        for r in resources:
            self.manager.retry(
                client.put_retention_policy,
                logGroupName=r['logGroupName'],
                retentionInDays=days)


@LogGroup.action_registry.register('delete')
class Delete(BaseAction):
    """

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudwatch-delete-stale-log-group
                resource: log-group
                filters:
                  - type: last-write
                    days: 182.5
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('logs:DeleteLogGroup',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('logs')
        for r in resources:
            try:
                self.manager.retry(
                    client.delete_log_group, logGroupName=r['logGroupName'])
            except client.exceptions.ResourceNotFoundException:
                continue


@LogGroup.filter_registry.register('last-write')
class LastWriteDays(Filter):
    """Filters CloudWatch log groups by last write

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudwatch-stale-groups
                resource: log-group
                filters:
                  - type: last-write
                    days: 60
    """

    schema = type_schema(
        'last-write', days={'type': 'number'})
    permissions = ('logs:DescribeLogStreams',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('logs')
        self.date_threshold = parse_date(datetime.utcnow()) - timedelta(
            days=self.data['days'])
        return [r for r in resources if self.check_group(client, r)]

    def check_group(self, client, group):
        streams = self.manager.retry(
            client.describe_log_streams,
            logGroupName=group['logGroupName'],
            orderBy='LastEventTime',
            descending=True,
            limit=3).get('logStreams')
        group['streams'] = streams
        if not streams:
            last_timestamp = group['creationTime']
        elif 'lastIngestionTime' in streams[0]:
            last_timestamp = streams[0]['lastIngestionTime']
        else:
            last_timestamp = streams[0]['creationTime']

        last_write = parse_date(last_timestamp)
        group['lastWrite'] = last_write
        return self.date_threshold > last_write


@LogGroup.filter_registry.register('cross-account')
class LogCrossAccountFilter(CrossAccountAccessFilter):
    schema = type_schema(
        'cross-account',
        # white list accounts
        whitelist_from=ValuesFrom.schema,
        whitelist={'type': 'array', 'items': {'type': 'string'}})

    permissions = ('logs:DescribeSubscriptionFilters',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('logs')
        accounts = self.get_accounts()
        results = []
        with self.executor_factory(max_workers=1) as w:
            futures = []
            for rset in chunks(resources, 50):
                futures.append(
                    w.submit(
                        self.process_resource_set, client, accounts, rset))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Error checking log groups cross-account %s",
                        f.exception())
                    continue
                results.extend(f.result())
        return results

    def process_resource_set(self, client, accounts, resources):
        results = []
        for r in resources:
            found = False
            filters = self.manager.retry(
                client.describe_subscription_filters,
                logGroupName=r['logGroupName']).get('subscriptionFilters', ())
            for f in filters:
                if 'destinationArn' not in f:
                    continue
                account_id = f['destinationArn'].split(':', 5)[4]
                if account_id not in accounts:
                    r.setdefault('c7n:CrossAccountViolations', []).append(
                        account_id)
                    found = True
            if found:
                results.append(r)
        return results


@LogGroup.filter_registry.register('subscription-filter')
class LogSubscriptionFilter(ValueFilter):
    """Filters CloudWatch log groups by subscriptions

    :example:

    .. code-block:: yaml

            policies:
              - name: cloudwatch-groups-with-subscriptions
                resource: log-group
                filters:
                  - type: subscription-filter
                    key: destinationArn
                    value: arn:aws:lambda:us-east-1:123456789876:function:forwarder
    """
    schema = type_schema('subscription-filter', rinherit=ValueFilter.schema)
    annotation_key = 'c7n:SubscriptionFilters'
    permissions = ('logs:DescribeSubscriptionFilters',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('logs')
        results = []
        for r in resources:
            filters = self.manager.retry(
                client.describe_subscription_filters,
                logGroupName=r['logGroupName']).get('subscriptionFilters', ())
            if not any(filters):
                continue
            for f in filters:
                r.setdefault(self.annotation_key, []).append(f)
            if (len(self.data) == 1) or any((self.match(sub) for sub in r[self.annotation_key])):
                results.append(r)
        return results


@LogGroup.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):
    RelatedIdsExpression = 'kmsKeyId'


@LogGroup.action_registry.register('set-encryption')
class EncryptLogGroup(BaseAction):
    """Encrypt/Decrypt a log group

    :example:

    .. code-block:: yaml

        policies:
          - name: encrypt-log-group
            resource: log-group
            filters:
              - kmsKeyId: absent
            actions:
              - type: set-encryption
                kms-key: alias/mylogkey
                state: True

          - name: decrypt-log-group
            resource: log-group
            filters:
              - kmsKeyId: kms:key:arn
            actions:
              - type: set-encryption
                state: False
    """
    schema = type_schema(
        'set-encryption',
        **{'kms-key': {'type': 'string'},
           'state': {'type': 'boolean'}})
    permissions = (
        'logs:AssociateKmsKey', 'logs:DisassociateKmsKey', 'kms:DescribeKey')

    def validate(self):
        if not self.data.get('state', True):
            return self
        key = self.data.get('kms-key', '')
        if not key:
            raise ValueError('Must specify either a KMS key ARN or Alias')
        if 'alias/' not in key and ':key/' not in key:
            raise PolicyValidationError(
                "Invalid kms key format %s" % key)
        return self

    def resolve_key(self, key):
        if not key:
            return

        # Qualified arn for key
        if key.startswith('arn:') and ':key/' in key:
            return key

        # Alias
        key = local_session(
            self.manager.session_factory).client(
                'kms').describe_key(
                    KeyId=key)['KeyMetadata']['Arn']
        return key

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        client = session.client('logs')

        state = self.data.get('state', True)
        key = self.resolve_key(self.data.get('kms-key'))

        for r in resources:
            try:
                if state:
                    client.associate_kms_key(
                        logGroupName=r['logGroupName'], kmsKeyId=key)
                else:
                    client.disassociate_kms_key(logGroupName=r['logGroupName'])
            except client.exceptions.ResourceNotFoundException:
                continue


@LogGroup.action_registry.register('put-subscription-filter')
class SubscriptionFilter(BaseAction):
    """Create/Update a subscription filter and associate with a log group

    :example:

    .. code-block:: yaml

        policies:
          - name: cloudwatch-put-subscription-filter
            resource: log-group
            actions:
              - type: put-subscription-filter
                filter_name: AllLambda
                filter_pattern: ip
                destination_arn: arn:aws:logs:us-east-1:1234567890:destination:lambda
                distribution: Random
                role_arn: "arn:aws:iam::{account_id}:role/testCrossAccountRole"
    """
    schema = type_schema(
        'put-subscription-filter',
        filter_name={'type': 'string'},
        filter_pattern={'type': 'string'},
        destination_arn={'type': 'string'},
        distribution={'enum': ['Random', 'ByLogStream']},
        role_arn={'type': 'string'},
        required=['filter_name', 'destination_arn'])
    permissions = ('logs:PutSubscriptionFilter',)

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        client = session.client('logs')
        params = dict(
            filterName=self.data.get('filter_name'),
            filterPattern=self.data.get('filter_pattern', ''),
            destinationArn=self.data.get('destination_arn'),
            distribution=self.data.get('distribution', 'ByLogStream'))

        if self.data.get('role_arn'):
            params['roleArn'] = self.data.get('role_arn')

        for r in resources:
            client.put_subscription_filter(
                logGroupName=r['logGroupName'], **params)


@resources.register("cloudwatch-dashboard")
class CloudWatchDashboard(QueryResourceManager):
    class resource_type(TypeInfo):
        service = "cloudwatch"
        enum_spec = ('list_dashboards', 'DashboardEntries', None)
        arn_type = "dashboard"
        arn = "DashboardArn"
        id = "DashboardName"
        name = "DashboardName"
        cfn_type = "AWS::CloudWatch::Dashboard"
        universal_taggable = object()
        global_resource = True

    source_mapping = {
       "describe": DescribeWithResourceTags,
    }


@resources.register("destination")
class Destination(QueryResourceManager):
    class resource_type(TypeInfo):
        service = "logs"
        arn = "arn"
        arn_separator = ":"
        arn_type = "destination"
        cfn_type = "AWS::Logs::Destination"
        date = "creationTime"
        enum_spec = ('describe_destinations', 'destinations', None)
        id = name = "destinationName"
        universal_taggable = object()

    retry = staticmethod(get_retry(('ServiceUnavailableException', 'OperationAbortedException')))

    source_mapping = {
       "describe": DescribeWithResourceTags,
    }


@Destination.filter_registry.register('cross-account')
class DestinationCrossAccount(CrossAccountAccessFilter):

    permissions = ('logs:DescribeDestinations',)
    policy_attribute = 'accessPolicy'


@Destination.action_registry.register('delete')
class DestinationDelete(BaseAction):
    """Action to delete a destination

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-destination
            resource: aws.destination
            filters:
              - type: cross-account
            actions:
              - delete
    """
    schema = type_schema('delete')

    permissions = ('logs:DeleteDestination',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('logs')
        for r in resources:
            self.manager.retry(
                client.delete_destination,
                ignore_err_codes=('ResourceNotFoundException',),
                destinationName=r['destinationName'],
            )


@resources.register("delivery-destination")
class DeliveryDestination(QueryResourceManager):
    class resource_type(TypeInfo):
        service = "logs"
        enum_spec = ('describe_delivery_destinations', 'deliveryDestinations', None)
        arn_type = "delivery-destination"
        arn_separator = ":"
        arn = "arn"
        id = name = "name"
        cfn_type = "AWS::Logs::DeliveryDestination"
        universal_taggable = object()

    retry = staticmethod(get_retry(
        ('ConflictException', 'ServiceUnavailableException', 'ThrottlingException',)
    ))
    source_mapping = {
       "describe": DescribeWithResourceTags,
    }


@DeliveryDestination.filter_registry.register('cross-account')
class DeliveryDestinationCrossAccount(CrossAccountAccessFilter):

    policy_attribute = 'c7n:Policy'
    permissions = ('logs:GetDeliveryDestinationPolicy',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('logs')

        for r in resources:
            resp = self.manager.retry(
                client.get_delivery_destination_policy,
                deliveryDestinationName=r['name'],
                ignore_err_codes=('ResourceNotFoundException',)
            )
            r[self.policy_attribute] = resp['policy'].get('deliveryDestinationPolicy', {})
        return super().process(resources)


@DeliveryDestination.action_registry.register('delete')
class DeliveryDestinationDelete(BaseAction):
    """Action to delete a delivery destination

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-delivery-destination
            resource: aws.delivery-destination
            filters:
              - type: value
                key: deliveryDestinationType
                value: S3
            actions:
              - delete
    """
    schema = type_schema('delete')

    permissions = ('logs:DeleteDeliveryDestination',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('logs')
        for r in resources:
            self.manager.retry(
                client.delete_delivery_destination,
                ignore_err_codes=('ResourceNotFoundException',),
                name=r['name'],
            )


@resources.register('cloudwatch-synthetics')
class SyntheticsCanary(QueryResourceManager):
    """AWS CloudWatch Synthetics Canary

    Example:
        .. code-block:: yaml

            policies:
              - name: stop-failed-canaries
                resource: aws.cloudwatch-synthetics
                filters:
                  - State.CurrentStatus.State: FAILED
                actions:
                  - type: delete
    """

    class resource_type(TypeInfo):
        service = 'synthetics'
        id = 'Id'
        name = 'Name'
        date = 'Created'
        arn_type = 'canary'
        arn = 'Arn'
        dimension = 'CanaryName'
        config_type = cfn_type = 'AWS::Synthetics::Canary'
        enum_spec = ('describe_canaries', 'Canaries', None)
        detail_spec = ('get_canary', 'Name', 'Name' 'Canary')
        universal_taggable = True

    permissions = (
    "synthetics:DescribeCanaries",
    "synthetics:ListTagsForResource",
    "synthetics:StartCanary",
    "synthetics:StopCanary",
    "synthetics:DeleteCanary",)

    def augment(self, resources):
        client = local_session(self.session_factory).client('synthetics')
        region = self.config.region

        sts = local_session(self.session_factory).client('sts')
        real_account_id = sts.get_caller_identity()["Account"]

        for r in resources:
            arn = r.get("Arn")
            if not arn:
                arn = f"arn:aws:synthetics:{region}:{real_account_id}:canary:{r['Name']}"
                r["Arn"] = arn
            # AWS returns tags as a dict { "Key": "Value" }
            tag_dict = client.list_tags_for_resource(ResourceArn=arn).get("Tags", {})

            # Custodian expects [{"Key": k, "Value": v}, ...]
            r["Tags"] = [{"Key": k, "Value": v} for k, v in tag_dict.items()]

        return resources


@SyntheticsCanary.action_registry.register('start')
class StartCanary(BaseAction):
    schema = type_schema('start')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('synthetics')
        for r in resources:
            client.start_canary(Name=r['Name'])


@SyntheticsCanary.action_registry.register('stop')
class StopCanary(BaseAction):
    schema = type_schema('stop')

    def process(self, resources):
        """Stop all running resources"""
        client = local_session(self.manager.session_factory).client('synthetics')
        for r in resources:
            client.stop_canary(Name=r['Name'])


@SyntheticsCanary.action_registry.register('delete')
class DeleteCanary(BaseAction):
    schema = type_schema('delete')

    def process(self, resources):
        """Delete resources"""
        client = local_session(self.manager.session_factory).client('synthetics')
        for r in resources:
            client.delete_canary(Name=r['Name'])


@SyntheticsCanary.filter_registry.register('state')
class CanaryStateFilter(ValueFilter):
    """Filter canaries by their current state"""

    schema = type_schema('state', rinherit=ValueFilter.schema)
    permissions = ('synthetics:DescribeCanaries',)

    def __call__(self, r):
        return self.match(r.get('Status', {}).get('State'))