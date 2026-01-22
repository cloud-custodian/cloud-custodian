# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime
import json
import fnmatch
import itertools
import logging
import os
import time
from typing import List

from dateutil import parser, tz as tzutil

from c7n.cwe import CloudWatchEvents
from c7n.ctx import ExecutionContext
from c7n.exceptions import PolicyValidationError, ClientError, ResourceLimitExceeded
from c7n.filters import FilterRegistry, And, Or, Not
from c7n.manager import iter_filters
from c7n.output import DEFAULT_NAMESPACE
from c7n.resources import load_resources
from c7n.registry import PluginRegistry
from c7n.provider import clouds, get_resource_class
from c7n import deprecated, utils
from c7n.version import version
from c7n.query import RetryPageIterator
from c7n.varfmt import VarFormat
from c7n.utils import get_policy_provider, jmespath_compile

log = logging.getLogger('c7n.policy')


def load(options, path, format=None, validate=True, vars=None):
    # should we do os.path.expanduser here?
    if not os.path.exists(path):
        raise IOError("Invalid path for config %r" % path)

    from c7n.schema import validate as schema_validate, StructureParser
    if os.path.isdir(path):
        from c7n.loader import DirectoryLoader
        collection = DirectoryLoader(options).load_directory(path, validate)
        if validate:
            [p.validate() for p in collection]
        return collection

    if os.path.isfile(path):
        data = utils.load_file(path, format=format, vars=vars)

    structure = StructureParser()
    structure.validate(data)
    rtypes = structure.get_resource_types(data)
    load_resources(rtypes)

    if isinstance(data, list):
        log.warning('yaml in invalid format. The "policies:" line is probably missing.')
        return None

    if validate:
        errors = schema_validate(data, resource_types=rtypes)
        if errors:
            raise PolicyValidationError(
                "Failed to validate policy %s \n %s" % (
                    errors[1], errors[0]))

    # Test for empty policy file
    if not data or data.get('policies') is None:
        return None

    collection = PolicyCollection.from_data(data, options)
    if validate:
        # non schema validation of policies
        [p.validate() for p in collection]
    return collection


class PolicyCollection:

    log = logging.getLogger('c7n.policies')

    def __init__(self, policies: 'List[Policy]', options):
        self.options = options
        self.policies = policies

    @classmethod
    def from_data(cls, data: dict, options, session_factory=None):
        # session factory param introduction needs an audit and review
        # on tests.
        sf = session_factory if session_factory else cls.session_factory()
        policies = [Policy(p, options, session_factory=sf)
                    for p in data.get('policies', ())]
        return cls(policies, options)

    def __add__(self, other):
        return self.__class__(self.policies + other.policies, self.options)

    def filter(self, policy_patterns=(), resource_types=(), modes=()):
        results = self.policies
        results = self._filter_by_patterns(results, policy_patterns)
        results = self._filter_by_resource_types(results, resource_types)
        results = self._filter_by_modes(results, modes)
        # next line brings the result set in the original order of self.policies
        results = [x for x in self.policies if x in results]
        return PolicyCollection(results, self.options)

    def _filter_by_patterns(self, policies, patterns):
        """
        Takes a list of policies and returns only those matching the given glob
        patterns
        """
        if not patterns:
            return policies

        results = []
        for pattern in patterns:
            result = self._filter_by_pattern(policies, pattern)
            results.extend(x for x in result if x not in results)
        return results

    def _filter_by_pattern(self, policies, pattern):
        """
        Takes a list of policies and returns only those matching the given glob
        pattern
        """
        results = []
        for policy in policies:
            if fnmatch.fnmatch(policy.name, pattern):
                results.append(policy)

        if not results:
            self.log.warning((
                'Policy pattern "{}" '
                'did not match any policies.').format(pattern))

        return results

    def _filter_by_resource_types(self, policies, resource_types):
        """
        Takes a list of policies and returns only those matching the given
        resource types
        """
        if not resource_types:
            return policies

        results = []
        for resource_type in resource_types:
            result = self._filter_by_resource_type(policies, resource_type)
            results.extend(x for x in result if x not in results)
        return results

    def _filter_by_resource_type(self, policies, resource_type):
        """
        Takes a list policies and returns only those matching the given resource
        type
        """
        results = []
        for policy in policies:
            if policy.resource_type == resource_type:
                results.append(policy)

        if not results:
            self.log.warning((
                'Resource type "{}" '
                'did not match any policies.').format(resource_type))

        return results

    def _filter_by_modes(self, policies, modes):
        """
        Takes a list of policies and returns only those matching a given mode
        """
        if not modes:
            return policies
        results = []
        for mode in modes:
            result = self._filter_by_mode(policies, mode)
            results.extend(x for x in result if x not in results)
        return results

    def _filter_by_mode(self, policies, mode):
        """
        Takes a list of policies and returns only those matching a given mode
        """
        results = []
        for policy in policies:
            if policy.get_execution_mode().type == mode:
                results.append(policy)
        if not results:
            self.log.warning((
                'Filter by modes type "{}" '
                'did not match any policies.').format(mode))
        return results

    def __iter__(self):
        return iter(self.policies)

    def __contains__(self, policy_name):
        for p in self.policies:
            if p.name == policy_name:
                return True
        return False

    def __len__(self):
        return len(self.policies)

    @property
    def resource_types(self):
        """resource types used by the collection."""
        rtypes = set()
        for p in self.policies:
            rtypes.add(p.resource_type)
        return rtypes

    # cli/collection tests patch this
    @classmethod
    def session_factory(cls):
        return None


class PolicyExecutionMode:
    """Policy execution semantics"""

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')
    permissions = ()

    def __init__(self, policy):
        self.policy = policy

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        """Provision any resources needed for the policy."""

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("subclass responsibility")

    def validate(self):
        """Validate configuration settings for execution mode."""

    def get_permissions(self):
        return self.permissions

    def get_metrics(self, start, end, period):
        """Retrieve any associated metrics for the policy."""
        values = {}
        default_dimensions = {
            'Policy': self.policy.name, 'ResType': self.policy.resource_type,
            'Scope': 'Policy'}

        metrics = list(self.POLICY_METRICS)

        # Support action, and filter custom metrics
        for el in itertools.chain(
                self.policy.resource_manager.actions,
                self.policy.resource_manager.filters):
            if el.metrics:
                metrics.extend(el.metrics)

        session = utils.local_session(self.policy.session_factory)
        client = session.client('cloudwatch')

        for m in metrics:
            if isinstance(m, str):
                dimensions = default_dimensions
            else:
                m, m_dimensions = m
                dimensions = dict(default_dimensions)
                dimensions.update(m_dimensions)
            results = client.get_metric_statistics(
                Namespace=DEFAULT_NAMESPACE,
                Dimensions=[
                    {'Name': k, 'Value': v} for k, v
                    in dimensions.items()],
                Statistics=['Sum', 'Average'],
                StartTime=start,
                EndTime=end,
                Period=period,
                MetricName=m)
            values[m] = results['Datapoints']
        return values

    def get_deprecations(self):
        # The execution mode itself doesn't have a data dict, so we grab the
        # mode part from the policy data dict itself.
        return deprecated.check_deprecations(self, data=self.policy.data.get('mode', {}))


class ServerlessExecutionMode(PolicyExecutionMode):
    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        raise NotImplementedError("subclass responsibility")

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        """Provision any resources needed for the policy."""
        raise NotImplementedError("subclass responsibility")


execution = PluginRegistry('c7n.execution')


@execution.register('pull')
class PullMode(PolicyExecutionMode):
    """Pull mode execution of a policy.

    Queries resources from cloud provider for filtering and actions.
    """

    schema = utils.type_schema('pull')

    def run(self, *args, **kw):
        if not self.policy.is_runnable():
            return []

        with self.policy.ctx as ctx:
            self.policy.log.debug(
                "Running policy:%s resource:%s region:%s c7n:%s",
                self.policy.name,
                self.policy.resource_type,
                self.policy.options.region or 'default',
                version,
            )

            s = time.time()
            try:
                resources = self.policy.resource_manager.resources()
            except ResourceLimitExceeded as e:
                self.policy.log.error(str(e))
                ctx.metrics.put_metric(
                    'ResourceLimitExceeded', e.selection_count, "Count"
                )
                raise

            rt = time.time() - s
            self.policy.log.info(
                "policy:%s resource:%s region:%s count:%d time:%0.2f",
                self.policy.name,
                self.policy.resource_type,
                self.policy.options.region,
                len(resources),
                rt,
            )
            ctx.metrics.put_metric(
                "ResourceCount", len(resources), "Count", Scope="Policy"
            )
            ctx.metrics.put_metric("ResourceTime", rt, "Seconds", Scope="Policy")
            ctx.output.write_file('resources.json', utils.dumps(resources, indent=2))

            if not resources:
                return []

            if self.policy.options.dryrun:
                self.policy.log.debug("dryrun: skipping actions")
                return resources

            at = time.time()
            for a in self.policy.resource_manager.actions:
                s = time.time()
                with ctx.tracer.subsegment('action:%s' % a.type):
                    results = a.process(resources)
                self.policy.log.info(
                    "policy:%s action:%s"
                    " resources:%d"
                    " execution_time:%0.2f"
                    % (self.policy.name, a.name, len(resources), time.time() - s)
                )
                if results:
                    ctx.output.write_file("action-%s" % a.name, utils.dumps(results))
            ctx.metrics.put_metric(
                "ActionTime", time.time() - at, "Seconds", Scope="Policy"
            )
            return resources


class LambdaMode(ServerlessExecutionMode):
    """A policy that runs/executes in lambda."""

    POLICY_METRICS = ('ResourceCount',)

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'execution-options': {'type': 'object'},
            'function-prefix': {'type': 'string'},
            'member-role': {'type': 'string'},
            'packages': {'type': 'array', 'items': {'type': 'string'}},
            # Lambda passthrough config
            'layers': {'type': 'array', 'items': {'type': 'string'}},
            'concurrency': {'type': 'integer'},
            'runtime': {'enum': ['python3.10', 'python3.11', 'python3.12',
                                 'python3.13']},
            'role': {'type': 'string'},
            'handler': {'type': 'string'},
            'pattern': {'type': 'object', 'minProperties': 1},
            'timeout': {'type': 'number'},
            'memory': {'type': 'number'},
            'environment': {'type': 'object'},
            'tags': {'type': 'object'},
            'dead_letter_config': {'type': 'object'},
            'kms_key_arn': {'type': 'string'},
            'tracing_config': {'type': 'object'},
            'security_groups': {'type': 'array'},
            'subnets': {'type': 'array'}
        }
    }

    def validate(self):
        super(LambdaMode, self).validate()
        prefix = self.policy.data['mode'].get('function-prefix', 'custodian-')
        MAX_LAMBDA_FUNCTION_NAME_LENGTH = 64
        if len(prefix + self.policy.name) > MAX_LAMBDA_FUNCTION_NAME_LENGTH:
            raise PolicyValidationError(
                "Custodian Lambda policies have a max length with prefix of %s"
                " policy:%s prefix:%s" % (
                    MAX_LAMBDA_FUNCTION_NAME_LENGTH,
                    self.policy.name,
                    prefix
                )
            )
        MAX_LAMBDA_FUNCTION_DESCRIPTION_LENGTH = 256
        if len(self.policy.description) > MAX_LAMBDA_FUNCTION_DESCRIPTION_LENGTH:
            raise PolicyValidationError(
                'Custodian Lambda policies have a max description length of %s'
                ' policy: %s description: %s' % (
                    MAX_LAMBDA_FUNCTION_DESCRIPTION_LENGTH,
                    self.policy.name,
                    self.policy.description
                )
            )
        tags = self.policy.data['mode'].get('tags')
        if not tags:
            return
        reserved_overlap = [t for t in tags if t.startswith('custodian-')]
        if reserved_overlap:
            log.warning((
                'Custodian reserves policy lambda '
                'tags starting with custodian - policy specifies %s' % (
                    ', '.join(reserved_overlap))))

    def get_member_account_id(self, event):
        return event.get('account')

    def get_member_region(self, event):
        return event.get('region')

    def assume_member(self, event):
        # if a member role is defined we're being run out of the master, and we need
        # to assume back into the member for policy execution.
        member_role = self.policy.data['mode'].get('member-role')
        member_id = self.get_member_account_id(event)
        region = self.get_member_region(event)
        if member_role and member_id and region:
            # In the master account we might be multiplexing a hot lambda across
            # multiple member accounts for each event/invocation.
            member_role = member_role.format(account_id=member_id)
            utils.reset_session_cache()
            self.policy.options['account_id'] = member_id
            self.policy.options['region'] = region
            self.policy.session_factory.region = region
            self.policy.session_factory.assume_role = member_role
            self.policy.log.info(
                "Assuming member role:%s", member_role)
            return True
        return False

    def resolve_resources(self, event):
        self.assume_member(event)
        mode = self.policy.data.get('mode', {})
        resource_ids = CloudWatchEvents.get_ids(event, mode)
        if resource_ids is None:
            raise ValueError("Unknown push event mode %s", self.data)
        self.policy.log.info('Found resource ids:%s', resource_ids)
        # Handle multi-resource type events, like ec2 CreateTags
        resource_ids = self.policy.resource_manager.match_ids(resource_ids)
        if not resource_ids:
            self.policy.log.warning("Could not find resource ids")
            return []

        resources = self.policy.resource_manager.get_resources(resource_ids)
        if 'debug' in event:
            self.policy.log.info("Resources %s", resources)
        return resources

    def run(self, event, lambda_context):
        """Run policy in push mode against given event.

        Lambda automatically generates cloud watch logs, and metrics
        for us, albeit with some deficienies, metrics no longer count
        against valid resources matches, but against execution.

        If metrics execution option is enabled, custodian will generate
        metrics per normal.
        """
        self.setup_exec_environment(event)
        if not self.policy.is_runnable(event):
            return
        resources = self.resolve_resources(event)
        if not resources:
            return resources
        rcount = len(resources)
        resources = self.policy.resource_manager.filter_resources(
            resources, event)

        if 'debug' in event:
            self.policy.log.info(
                "Filtered resources %d of %d", len(resources), rcount)

        if not resources:
            self.policy.log.info(
                "policy:%s resources:%s no resources matched" % (
                    self.policy.name, self.policy.resource_type))
            return
        return self.run_resource_set(event, resources)

    def setup_exec_environment(self, event):
        mode = self.policy.data.get('mode', {})
        if not bool(mode.get("log", True)):
            root = logging.getLogger()
            map(root.removeHandler, root.handlers[:])
            root.handlers = [logging.NullHandler()]

    def run_resource_set(self, event, resources):
        from c7n.actions import EventAction

        with self.policy.ctx as ctx:
            ctx.metrics.put_metric(
                'ResourceCount', len(resources), 'Count', Scope="Policy", buffer=False
            )

            if 'debug' in event:
                self.policy.log.info(
                    "Invoking actions %s", self.policy.resource_manager.actions
                )

            ctx.output.write_file('resources.json', utils.dumps(resources, indent=2))

            for action in self.policy.resource_manager.actions:
                self.policy.log.info(
                    "policy:%s invoking action:%s resources:%d",
                    self.policy.name,
                    action.name,
                    len(resources),
                )
                if isinstance(action, EventAction):
                    results = action.process(resources, event)
                else:
                    results = action.process(resources)
                ctx.output.write_file("action-%s" % action.name, utils.dumps(results))
        return resources

    @property
    def policy_lambda(self):
        from c7n import mu
        return mu.PolicyLambda

    def provision(self):
        # auto tag lambda policies with mode and version, we use the
        # version in mugc to effect cleanups.
        tags = self.policy.data['mode'].setdefault('tags', {})
        tags['custodian-info'] = "mode=%s:version=%s" % (
            self.policy.data['mode']['type'], version)
        # auto tag with schedule name and group to link function to
        # EventBridge schedule when using schedule mode
        if self.policy.data['mode']['type'] == 'schedule':
            prefix = self.policy.data['mode'].get('function-prefix', 'custodian-')
            name = self.policy.data['name']
            group = self.policy.data['mode'].get('group-name', 'default')
            tags['custodian-schedule'] = f'name={prefix + name}:group={group}'

        from c7n import mu
        with self.policy.ctx:
            self.policy.log.info(
                "Provisioning policy lambda: %s region: %s", self.policy.name,
                self.policy.options.region)
            try:
                manager = mu.LambdaManager(self.policy.session_factory)
            except ClientError:
                # For cli usage by normal users, don't assume the role just use
                # it for the lambda
                manager = mu.LambdaManager(
                    lambda assume=False: self.policy.session_factory(assume))
            return manager.publish(
                self.policy_lambda(self.policy),
                role=self.policy.options.assume_role)


@execution.register('periodic')
class PeriodicMode(LambdaMode, PullMode):
    """A policy that runs in pull mode within lambda.

    Runs Custodian in AWS lambda at user defined cron interval using EventBridge rules.
    """

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    schema = utils.type_schema(
        'periodic', schedule={'type': 'string'}, rinherit=LambdaMode.schema)

    def run(self, event, lambda_context):
        return PullMode.run(self)


@execution.register('schedule')
class ScheduleMode(LambdaMode, PullMode):
    """A policy that runs in pull mode within lambda.

    Runs Custodian in AWS lambda at user defined cron interval using EventBridge Scheduler.
    """

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    schema = utils.type_schema(
        'schedule',
        schedule={'type': 'string'},
        timezone={'type': 'string'},
        **{'start-date': {'type': 'string'},
           'end-date': {'type': 'string'},
           'scheduler-role': {'type': 'string'},
           'group-name': {'type': 'string'}},
        required=['schedule'],
        rinherit=LambdaMode.schema)

    def run(self, event, lambda_context):
        return PullMode.run(self)


@execution.register('phd')
class PHDMode(LambdaMode):
    """Personal Health Dashboard event based policy execution.

    PHD events are triggered by changes in the operations health of
    AWS services and data center resources,

    See `Personal Health Dashboard
    <https://aws.amazon.com/premiumsupport/technology/personal-health-dashboard/>`_
    for more details.
    """

    schema = utils.type_schema(
        'phd',
        events={'type': 'array', 'items': {'type': 'string'}},
        categories={'type': 'array', 'items': {
            'enum': ['issue', 'accountNotification', 'scheduledChange']}},
        statuses={'type': 'array', 'items': {
            'enum': ['open', 'upcoming', 'closed']}},
        rinherit=LambdaMode.schema)

    def validate(self):
        super(PHDMode, self).validate()
        if self.policy.resource_type == 'account':
            return
        if 'health-event' not in self.policy.resource_manager.filter_registry:
            raise PolicyValidationError(
                "policy:%s phd event mode not supported for resource:%s" % (
                    self.policy.name, self.policy.resource_type))
        if 'events' not in self.policy.data['mode']:
            raise PolicyValidationError(
                'policy:%s phd event mode requires events for resource:%s' % (
                    self.policy.name, self.policy.resource_type))

    @staticmethod
    def process_event_arns(client, event_arns):
        entities = []
        paginator = client.get_paginator('describe_affected_entities')
        for event_set in utils.chunks(event_arns, 10):
            # Note: we aren't using event_set here, just event_arns.
            entities.extend(list(itertools.chain(
                            *[p['entities'] for p in paginator.paginate(
                                filter={'eventArns': event_arns})])))
        return entities

    def resolve_resources(self, event):
        session = utils.local_session(self.policy.resource_manager.session_factory)
        health = session.client('health', region_name='us-east-1')
        he_arn = event['detail']['eventArn']
        resource_arns = self.process_event_arns(health, [he_arn])

        m = self.policy.resource_manager.get_model()
        if 'arn' in m.id.lower():
            resource_ids = [r['entityValue'].rsplit('/', 1)[-1] for r in resource_arns]
        else:
            resource_ids = [r['entityValue'] for r in resource_arns]

        resources = self.policy.resource_manager.get_resources(resource_ids)
        for r in resources:
            r.setdefault('c7n:HealthEvent', []).append(he_arn)
        return resources


@execution.register('cloudtrail')
class CloudTrailMode(LambdaMode):
    """A lambda policy using cloudwatch events rules on cloudtrail api logs."""

    schema = utils.type_schema(
        'cloudtrail',
        delay={'type': 'integer',
               'description': 'sleep for delay seconds before processing an event'},
        events={'type': 'array', 'items': {
            'oneOf': [
                {'type': 'string'},
                {'type': 'object',
                 'required': ['event', 'source', 'ids'],
                 'properties': {
                     'source': {'type': 'string'},
                     'ids': {'type': 'string'},
                     'event': {'type': 'string'}}}]
        }},
        rinherit=LambdaMode.schema)

    def validate(self):
        super(CloudTrailMode, self).validate()
        from c7n import query
        events = self.policy.data['mode'].get('events')
        assert events, "cloud trail mode requires specifiying events to subscribe"
        for e in events:
            if isinstance(e, str):
                assert e in CloudWatchEvents.trail_events, "event shortcut not defined: %s" % e
            if isinstance(e, dict):
                jmespath_compile(e['ids'])
        if isinstance(self.policy.resource_manager, query.ChildResourceManager):
            if not getattr(self.policy.resource_manager.resource_type,
                           'supports_trailevents', False):
                raise ValueError(
                    "resource:%s does not support cloudtrail mode policies" % (
                        self.policy.resource_type))

    def resolve_resources(self, event):
        # override to enable delay before fetching resources
        delay = self.policy.data.get('mode', {}).get('delay')
        if delay:
            time.sleep(delay)
        return super().resolve_resources(event)


@execution.register('ec2-instance-state')
class EC2InstanceState(LambdaMode):
    """
    A lambda policy that executes on ec2 instance state changes.

    See `EC2 lifecycles
    <https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html>`_
    for more details.
    """

    schema = utils.type_schema(
        'ec2-instance-state', rinherit=LambdaMode.schema,
        events={'type': 'array', 'items': {
            'enum': ['pending', 'running', 'shutting-down',
                     'stopped', 'stopping', 'terminated']}})


@execution.register('asg-instance-state')
class ASGInstanceState(LambdaMode):
    """a lambda policy that executes on an asg's ec2 instance state changes.

    See `ASG Events
    <https://docs.aws.amazon.com/autoscaling/ec2/userguide/cloud-watch-events.html>`_
    for more details.
    """

    schema = utils.type_schema(
        'asg-instance-state', rinherit=LambdaMode.schema,
        events={'type': 'array', 'items': {
            'enum': ['launch-success', 'launch-failure',
                     'terminate-success', 'terminate-failure']}})


@execution.register('guard-duty')
class GuardDutyMode(LambdaMode):
    """Incident Response for AWS Guard Duty.

    AWS Guard Duty is a threat detection service that continuously
    monitors for malicious activity and unauthorized behavior. This
    mode allows you to execute polcies when various alerts are created
    by AWS Guard Duty for automated incident response. See `Guard Duty
    <https://aws.amazon.com/guardduty/>`_ for more details.
    """

    schema = utils.type_schema('guard-duty', rinherit=LambdaMode.schema)

    supported_resources = ('account', 'ec2', 'iam-user')

    id_exprs = {
        'account': jmespath_compile('detail.accountId'),
        'ec2': jmespath_compile('detail.resource.instanceDetails.instanceId'),
        'iam-user': jmespath_compile('detail.resource.accessKeyDetails.userName')}

    def get_member_account_id(self, event):
        return event['detail']['accountId']

    def resolve_resources(self, event):
        self.assume_member(event)
        rid = self.id_exprs[self.policy.resource_type].search(event)
        resources = self.policy.resource_manager.get_resources([rid])
        # For iam users annotate with the access key specified in the finding event
        if resources and self.policy.resource_type == 'iam-user':
            resources[0]['c7n:AccessKeys'] = {
                'AccessKeyId': event['detail']['resource']['accessKeyDetails']['accessKeyId']}
        return resources

    def validate(self):
        super(GuardDutyMode, self).validate()
        if self.policy.data['resource'] not in self.supported_resources:
            raise ValueError(
                "Policy:%s resource:%s Guard duty mode only supported for %s" % (
                    self.policy.data['name'],
                    self.policy.data['resource'],
                    self.supported_resources))

    def provision(self):
        if self.policy.data['resource'] == 'ec2':
            self.policy.data['mode']['resource-filter'] = 'Instance'
        elif self.policy.data['resource'] == 'iam-user':
            self.policy.data['mode']['resource-filter'] = 'AccessKey'
        return super(GuardDutyMode, self).provision()


@execution.register('config-poll-rule')
class ConfigPollRuleMode(LambdaMode, PullMode):
    """This mode represents a periodic/scheduled AWS config evaluation.

    The primary benefit this mode offers is to support additional resources
    beyond what config supports natively, as it can post evaluations for
    any resource which has a cloudformation type.

    If a resource is natively supported by config it's highly recommended
    to use a `config-rule` mode instead. Deployment will fail unless
    the policy explicitly opts out of that check with `ignore-support-check`.
    This can be useful in cases when a policy resource has native Config
    support, but filters based on related resource attributes.

    :example:

    VPCs have native Config support, but flow logs are a separate resource.
    This policy forces `config-poll-rule` mode to bypass the Config support
    check and evaluate VPC compliance on a schedule.

    .. code-block:: yaml

        policies:
          - name: vpc-flow-logs
            resource: vpc
            mode:
              type: config-poll-rule
              role: arn:aws:iam::{account_id}:role/MyRole
              ignore-support-check: True
            filters:
              - not:
                - type: flow-logs
                  destination-type: "s3"
                  enabled: True
                  status: active
                  traffic-type: all
                  destination: "arn:aws:s3:::mys3flowlogbucket"

    This mode effectively receives no data from config, instead it's
    periodically executed by config and polls and evaluates all
    resources. It is equivalent to a periodic policy, except it also
    pushes resource evaluations to config.
    """
    schema = utils.type_schema(
        'config-poll-rule',
        schedule={'enum': [
            "One_Hour",
            "Three_Hours",
            "Six_Hours",
            "Twelve_Hours",
            "TwentyFour_Hours"]},
        **{'ignore-support-check': {'type': 'boolean'}},
        rinherit=LambdaMode.schema)

    def validate(self):
        super().validate()
        if not self.policy.data['mode'].get('schedule'):
            raise PolicyValidationError(
                "policy:%s config-poll-rule schedule required" % (
                    self.policy.name))
        if (
            self.policy.resource_manager.resource_type.config_type
            and not self.policy.data['mode'].get('ignore-support-check')
        ):
            raise PolicyValidationError(
                "resource:%s fully supported by config and should use mode: config-rule" % (
                    self.policy.resource_type))
        if self.policy.data['mode'].get('pattern'):
            raise PolicyValidationError(
                "policy:%s AWS Config does not support event pattern filtering" % (
                    self.policy.name))
        if not self.policy.resource_manager.resource_type.cfn_type:
            raise PolicyValidationError((
                'policy:%s resource:%s does not have a cloudformation type'
                ' and is there-fore not supported by config-poll-rule'))

    @staticmethod
    def get_obsolete_evaluations(client, cfg_rule_name, ordering_ts, evaluations):
        """Get list of evaluations that are no longer applicable due to resources being deleted
        """
        latest_resource_ids = set()
        for latest_eval in evaluations:
            latest_resource_ids.add(latest_eval['ComplianceResourceId'])

        obsolete_evaluations = []
        paginator = client.get_paginator('get_compliance_details_by_config_rule')
        paginator.PAGE_ITERATOR_CLS = RetryPageIterator
        old_evals = paginator.paginate(
            ConfigRuleName=cfg_rule_name,
            ComplianceTypes=['COMPLIANT', 'NON_COMPLIANT'],
            PaginationConfig={'PageSize': 100}).build_full_result().get('EvaluationResults', [])

        for old_eval in old_evals:
            eval_res_qual = old_eval['EvaluationResultIdentifier']['EvaluationResultQualifier']
            old_resource_id = eval_res_qual['ResourceId']
            if old_resource_id not in latest_resource_ids:
                obsolete_evaluation = {
                    'ComplianceResourceType': eval_res_qual['ResourceType'],
                    'ComplianceResourceId': old_resource_id,
                    'Annotation': 'The rule does not apply.',
                    'ComplianceType': 'NOT_APPLICABLE',
                    'OrderingTimestamp': ordering_ts}
                obsolete_evaluations.append(obsolete_evaluation)
        return obsolete_evaluations

    def _get_client(self):
        return utils.local_session(
            self.policy.session_factory).client('config')

    def put_evaluations(self, client, token, evaluations):
        for eval_set in utils.chunks(evaluations, 100):
            self.policy.resource_manager.retry(
                client.put_evaluations,
                Evaluations=eval_set,
                ResultToken=token)

    def run(self, event, lambda_context):
        cfg_event = json.loads(event['invokingEvent'])
        resource_type = self.policy.resource_manager.resource_type.cfn_type
        resource_id = self.policy.resource_manager.resource_type.config_id or \
            self.policy.resource_manager.resource_type.id
        client = self._get_client()
        token = event.get('resultToken')
        cfg_rule_name = event['configRuleName']
        ordering_ts = cfg_event['notificationCreationTime']
        policy_data = self.policy.data.copy()
        policy_data.pop("filters", None)

        matched_resources = set()
        unmatched_resources = set()
        for r in PullMode.run(self):
            matched_resources.add(r[resource_id])
        for r in self.policy.resource_manager.get_resource_manager(
                self.policy.resource_type,
                policy_data).resources():
            if r[resource_id] not in matched_resources:
                unmatched_resources.add(r[resource_id])

        non_compliant_evals = [dict(
            ComplianceResourceType=resource_type,
            ComplianceResourceId=r,
            ComplianceType='NON_COMPLIANT',
            OrderingTimestamp=ordering_ts,
            Annotation='The resource is not compliant with policy:%s.' % (
                self.policy.name))
            for r in matched_resources]
        compliant_evals = [dict(
            ComplianceResourceType=resource_type,
            ComplianceResourceId=r,
            ComplianceType='COMPLIANT',
            OrderingTimestamp=ordering_ts,
            Annotation='The resource is compliant with policy:%s.' % (
                self.policy.name))
            for r in unmatched_resources]
        evaluations = non_compliant_evals + compliant_evals
        obsolete_evaluations = self.get_obsolete_evaluations(
            client, cfg_rule_name, ordering_ts, evaluations)
        evaluations = evaluations + obsolete_evaluations

        if evaluations and token:
            self.put_evaluations(client, token, evaluations)

        return list(matched_resources)


@execution.register('config-rule')
class ConfigRuleMode(LambdaMode):
    """a lambda policy that executes as a config service rule.

    The policy is invoked on configuration changes to resources.

    See `AWS Config <https://aws.amazon.com/config/>`_ for more details.
    """
    cfg_event = None
    schema = utils.type_schema('config-rule', rinherit=LambdaMode.schema)

    def validate(self):
        super(ConfigRuleMode, self).validate()
        if not self.policy.resource_manager.resource_type.config_type:
            raise PolicyValidationError(
                "policy:%s AWS Config does not support resource-type:%s" % (
                    self.policy.name, self.policy.resource_type))
        if self.policy.data['mode'].get('pattern'):
            raise PolicyValidationError(
                "policy:%s AWS Config does not support event pattern filtering" % (
                    self.policy.name))

    def resolve_resources(self, event):
        source = self.policy.resource_manager.get_source('config')
        return [source.load_resource(self.cfg_event['configurationItem'])]

    def run(self, event, lambda_context):
        self.cfg_event = json.loads(event['invokingEvent'])
        cfg_item = self.cfg_event['configurationItem']
        evaluation = None
        resources = []

        # TODO config resource type matches policy check
        if event.get('eventLeftScope') or cfg_item['configurationItemStatus'] in (
                "ResourceDeleted",
                "ResourceNotRecorded",
                "ResourceDeletedNotRecorded"):
            evaluation = {
                'annotation': 'The rule does not apply.',
                'compliance_type': 'NOT_APPLICABLE'}

        if evaluation is None:
            resources = super(ConfigRuleMode, self).run(event, lambda_context)
            match = self.policy.data['mode'].get('match-compliant', False)
            self.policy.log.info(
                "found resources:%d match-compliant:%s", len(resources or ()), match)
            if (match and resources) or (not match and not resources):
                evaluation = {
                    'compliance_type': 'COMPLIANT',
                    'annotation': 'The resource is compliant with policy:%s.' % (
                        self.policy.name)}
            else:
                evaluation = {
                    'compliance_type': 'NON_COMPLIANT',
                    'annotation': 'Resource is not compliant with policy:%s' % (
                        self.policy.name)
                }

        client = utils.local_session(
            self.policy.session_factory).client('config')
        client.put_evaluations(
            Evaluations=[{
                'ComplianceResourceType': cfg_item['resourceType'],
                'ComplianceResourceId': cfg_item['resourceId'],
                'ComplianceType': evaluation['compliance_type'],
                'Annotation': evaluation['annotation'],
                # TODO ? if not applicable use current timestamp
                'OrderingTimestamp': cfg_item[
                    'configurationItemCaptureTime']}],
            ResultToken=event.get('resultToken', 'No token found.'))
        return resources


def get_session_factory(provider_name, options):
    try:
        return clouds[provider_name]().get_session_factory(options)
    except KeyError:
        raise RuntimeError(
            "%s provider not installed" % provider_name)


class PolicyConditionAnd(And):
    def get_resource_type_id(self):
        return 'name'


class PolicyConditionOr(Or):
    def get_resource_type_id(self):
        return 'name'


class PolicyConditionNot(Not):
    def get_resource_type_id(self):
        return 'name'


class PolicyConditions:

    filter_registry = FilterRegistry('c7n.policy.filters')
    filter_registry.register('and', PolicyConditionAnd)
    filter_registry.register('or', PolicyConditionOr)
    filter_registry.register('not', PolicyConditionNot)

    def __init__(self, policy, data):
        self.policy = policy
        # for value_from usage / we use the conditions class
        # to mimic a resource manager interface. we can't use
        # the actual resource manager as we're overriding block
        # filters which work w/ resource type metadata and our
        # resource here is effectively the execution variables.
        self.config = self.policy.options
        rm = self.policy.resource_manager
        self._cache = rm._cache
        self.session_factory = rm.session_factory
        # used by c7n-org to extend evaluation conditions
        self.env_vars = {}
        self.update(data)

    def update(self, data):
        self.data = data
        self.filters = self.data.get('conditions', [])
        self.initialized = False

    def validate(self):
        if not self.initialized:
            self.filters.extend(self.convert_deprecated())
            self.filters = self.filter_registry.parse(self.filters, self)
            self.initialized = True

    def evaluate(self, event=None):
        policy_vars = dict(self.env_vars)
        policy_vars.update({
            'name': self.policy.name,
            'region': self.policy.options.region,
            'resource': self.policy.resource_type,
            'provider': self.policy.provider_name,
            'account_id': self.policy.options.account_id,
            'now': datetime.now(tzutil.tzutc()),
            'policy': self.policy.data
        })

        # Evaluating conditions from c7n-org file (e.g. account.tags) during Policy-Runtime
        # causes the Policy skipping its execution as those account-specific conditions are
        # only available during Policy-Deployment.
        # See issue #7967.
        # Solution is to remove those conditions during Runtime => "if self.env_vars == {}"
        # As this dict is only populated via c7n-org during Deployment.
        if not self.env_vars:
            self.filters = [f for f in self.filters if not f.data['key'].startswith('account.')]

        # note for no filters/conditions, this uses all([]) == true property.
        state = all([f.process([policy_vars], event) for f in self.filters])
        if not state:
            self.policy.log.info(
                'Skipping policy:%s due to execution conditions', self.policy.name)
        return state

    def iter_filters(self, block_end=False):
        return iter_filters(self.filters, block_end=block_end)

    def convert_deprecated(self):
        """These deprecated attributes are now recorded as deprecated against the policy."""
        filters = []
        if 'region' in self.policy.data:
            filters.append({'region': self.policy.data['region']})
        if 'start' in self.policy.data:
            filters.append({
                'type': 'value',
                'key': 'now',
                'value_type': 'date',
                'op': 'gte',
                'value': self.policy.data['start']})
        if 'end' in self.policy.data:
            filters.append({
                'type': 'value',
                'key': 'now',
                'value_type': 'date',
                'op': 'lte',
                'value': self.policy.data['end']})
        return filters

    def get_deprecations(self):
        """Return any matching deprecations for the policy fields itself."""
        deprecations = []
        for f in self.filters:
            deprecations.extend(f.get_deprecations())
        return deprecations


class Policy:

    log = logging.getLogger('custodian.policy')

    deprecations = (
        deprecated.field('region', 'region in condition block'),
        deprecated.field('start', 'value filter in condition block'),
        deprecated.field('end', 'value filter in condition block'),
    )

    def __init__(self, data, options, session_factory=None):
        self.data = data
        self.options = options
        assert "name" in self.data
        if session_factory is None:
            session_factory = get_session_factory(self.provider_name, options)
        self.session_factory = session_factory
        self.ctx = ExecutionContext(self.session_factory, self, self.options)
        self.resource_manager = self.load_resource_manager()
        self.conditions = PolicyConditions(self, data)

    def __repr__(self):
        return "<Policy resource:%s name:%s region:%s>" % (
            self.resource_type, self.name, self.options.region)

    @property
    def name(self) -> str:
        return self.data['name']

    @property
    def description(self) -> str:
        return self.data.get('description', '')

    @property
    def resource_type(self) -> str:
        return self.data['resource']

    @property
    def provider_name(self) -> str:
        return get_policy_provider(self.data)

    def is_runnable(self, event=None):
        return self.conditions.evaluate(event)

    # Runtime circuit breakers
    @property
    def max_resources(self):
        return self.data.get('max-resources')

    @property
    def max_resources_percent(self):
        return self.data.get('max-resources-percent')

    @property
    def tags(self):
        return self.data.get('tags', ())

    def get_cache(self):
        return self.resource_manager._cache

    @property
    def execution_mode(self):
        return self.data.get('mode', {'type': 'pull'})['type']

    def get_execution_mode(self):
        try:
            exec_mode = execution[self.execution_mode]
        except KeyError:
            return None
        return exec_mode(self)

    @property
    def is_lambda(self):
        if 'mode' not in self.data:
            return False
        return True

    def validate(self):
        self.conditions.validate()
        m = self.get_execution_mode()
        if m is None:
            raise PolicyValidationError(
                "Invalid Execution mode in policy %s" % (self.data,))
        m.validate()
        self.validate_policy_start_stop()
        self.resource_manager.validate()
        for f in self.resource_manager.filters:
            f.validate()
        for a in self.resource_manager.actions:
            a.validate()

    def get_variables(self, variables=None):
        """Get runtime variables for policy interpolation.

        Runtime variables are merged with the passed in variables
        if any.
        """
        # Global policy variable expansion, we have to carry forward on
        # various filter/action local vocabularies. Where possible defer
        # by using a format string.
        #
        # See https://github.com/cloud-custodian/cloud-custodian/issues/2330
        if not variables:
            variables = {}

        partition = utils.get_partition(self.options.region)
        if 'mode' in self.data:
            if 'role' in self.data['mode'] and not self.data['mode']['role'].startswith("arn:aws"):
                self.data['mode']['role'] = "arn:%s:iam::%s:role/%s" % \
                    (partition, self.options.account_id, self.data['mode']['role'])

        variables.update({
            # standard runtime variables for interpolation
            'account': '{account}',
            'account_id': self.options.account_id,
            'partition': partition,
            'region': self.options.region,
            # non-standard runtime variables from local filter/action vocabularies
            #
            # notify action
            'policy': self.data,
            'event': '{event}',
            # mark for op action
            'op': '{op}',
            'action_date': '{action_date}',
            # tag action pyformat-date handling
            # defer expansion until runtime for serverless modes
            'now': (
                utils.DeferredFormatString('now')
                if isinstance(self.get_execution_mode(), ServerlessExecutionMode)
                else utils.FormatDate(datetime.utcnow())
            ),
            # account increase limit action
            'service': '{service}',
            # s3 set logging action :-( see if we can revisit this one.
            'bucket_region': '{bucket_region}',
            'bucket_name': '{bucket_name}',
            'source_bucket_name': '{source_bucket_name}',
            'source_bucket_region': '{source_bucket_region}',
            'target_bucket_name': '{target_bucket_name}',
            'target_prefix': '{target_prefix}',
            'LoadBalancerName': '{LoadBalancerName}'
        })
        return variables

    def expand_variables(self, variables):
        """Expand variables in policy data.

        Updates the policy data in-place.
        """
        # format string values returns a copy
        var_fmt = VarFormat()
        updated = utils.format_string_values(
            self.data, formatter=var_fmt.format, **variables)

        # Several keys should only be expanded at runtime, perserve them.
        if 'member-role' in updated.get('mode', {}):
            updated['mode']['member-role'] = self.data['mode']['member-role']

        # Update ourselves in place
        self.data = updated

        # NOTE update the policy conditions base on the new self.data
        self.conditions.update(self.data)

        # Reload filters/actions using updated data, we keep a reference
        # for some compatiblity preservation work.
        m = self.resource_manager
        self.resource_manager = self.load_resource_manager()

        # XXX: Compatiblity hack
        # Preserve notify action subject lines which support
        # embedded jinja2 as a passthrough to the mailer.
        for old_a, new_a in zip(m.actions, self.resource_manager.actions):
            if old_a.type == 'notify' and 'subject' in old_a.data:
                new_a.data['subject'] = old_a.data['subject']

    def push(self, event, lambda_ctx=None):
        mode = self.get_execution_mode()
        return mode.run(event, lambda_ctx)

    def provision(self):
        """Provision policy as a lambda function."""
        mode = self.get_execution_mode()
        return mode.provision()

    def poll(self):
        """Query resources and apply policy."""
        mode = self.get_execution_mode()
        return mode.run()

    def get_permissions(self):
        """get permissions needed by this policy"""
        permissions = set()
        permissions.update(self.resource_manager.get_permissions())
        for f in self.resource_manager.filters:
            permissions.update(f.get_permissions())
        for a in self.resource_manager.actions:
            permissions.update(a.get_permissions())
        return permissions

    def _trim_runtime_filters(self):
        from c7n.filters.core import trim_runtime
        trim_runtime(self.conditions.filters)
        trim_runtime(self.resource_manager.filters)

    def __call__(self):
        """Run policy in default mode"""
        mode = self.get_execution_mode()
        if (isinstance(mode, ServerlessExecutionMode) or
                self.options.dryrun):
            self._trim_runtime_filters()

        if self.options.dryrun:
            resources = PullMode(self).run()
        elif not self.is_runnable():
            resources = []
        elif isinstance(mode, ServerlessExecutionMode):
            resources = mode.provision()
        else:
            resources = mode.run()

        return resources

    run = __call__

    def _write_file(self, rel_path, value):
        """This method is no longer called within c7n, and despite being a private
        method, caution is taken here to not break any external callers.
        """
        log.warning("policy _write_file is deprecated, use ctx.output.write_file")
        self.ctx.output.write_file(rel_path, value)

    def load_resource_manager(self):
        factory = get_resource_class(self.data.get('resource'))
        return factory(self.ctx, self.data)

    def validate_policy_start_stop(self):
        policy_name = self.data.get('name')
        policy_tz = self.data.get('tz')
        policy_start = self.data.get('start')
        policy_end = self.data.get('end')

        if policy_tz:
            try:
                p_tz = tzutil.gettz(policy_tz)
            except Exception as e:
                raise PolicyValidationError(
                    "Policy: %s TZ not parsable: %s, %s" % (
                        policy_name, policy_tz, e))

            # Type will be tzwin on windows, but tzwin is null on linux
            if not (isinstance(p_tz, tzutil.tzfile) or
                    (tzutil.tzwin and isinstance(p_tz, tzutil.tzwin))):
                raise PolicyValidationError(
                    "Policy: %s TZ not parsable: %s" % (
                        policy_name, policy_tz))

        for i in [policy_start, policy_end]:
            if i:
                try:
                    parser.parse(i)
                except Exception as e:
                    raise ValueError(
                        "Policy: %s Date/Time not parsable: %s, %s" % (policy_name, i, e))

    def get_deprecations(self):
        """Return any matching deprecations for the policy fields itself."""
        return deprecated.check_deprecations(self, "policy")
