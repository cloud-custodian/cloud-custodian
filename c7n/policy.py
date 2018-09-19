# Copyright 2015-2018 Capital One Services, LLC
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

from datetime import datetime
from dateutil import tz, parser
import json
import fnmatch
import itertools
import logging
import os
import time


import jmespath
import six

from c7n.actions import EventAction
from c7n.cwe import CloudWatchEvents
from c7n.ctx import ExecutionContext
from c7n.exceptions import PolicyValidationError, ClientError, ResourceLimitExceeded
from c7n.output import DEFAULT_NAMESPACE
from c7n.resources import load_resources
from c7n.registry import PluginRegistry
from c7n.provider import clouds
from c7n import mu
from c7n import query
from c7n import utils
from c7n.logs_support import (
    normalized_log_entries,
    log_entries_in_range,
    log_entries_from_s3,
    log_entries_from_group,
)
from c7n.version import version

log = logging.getLogger('c7n.policy')


def load(options, path, format='yaml', validate=True, vars=None):
    # should we do os.path.expanduser here?
    if not os.path.exists(path):
        raise IOError("Invalid path for config %r" % path)

    load_resources()
    data = utils.load_file(path, format=format, vars=vars)

    if format == 'json':
        validate = False

    if isinstance(data, list):
        log.warning('yaml in invalid format. The "policies:" line is probably missing.')
        return None

    # Test for empty policy file
    if not data or data.get('policies') is None:
        return None

    if validate:
        from c7n.schema import validate
        errors = validate(data)
        if errors:
            raise Exception(
                "Failed to validate on policy %s \n %s" % (
                    errors[1], errors[0]))

    collection = PolicyCollection.from_data(data, options)
    if validate:
        # non schema validation of policies
        [p.validate() for p in collection]
    return collection


class PolicyCollection(object):

    log = logging.getLogger('c7n.policies')

    def __init__(self, policies, options):
        self.options = options
        self.policies = policies

    @classmethod
    def from_data(cls, data, options):
        policies = [Policy(p, options,
                           session_factory=cls.session_factory())
                    for p in data.get('policies', ())]
        return cls(policies, options)

    def __add__(self, other):
        return self.__class__(self.policies + other.policies, self.options)

    def filter(self, policy_name=None, resource_type=None):
        results = []
        for policy in self.policies:
            if resource_type:
                if policy.resource_type != resource_type:
                    continue
            if policy_name:
                if not fnmatch.fnmatch(policy.name, policy_name):
                    continue
            results.append(policy)
        return PolicyCollection(results, self.options)

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


class PolicyExecutionMode(object):
    """Policy execution semantics"""

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

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
            if isinstance(m, six.string_types):
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
        if not self.is_runnable():
            return

        with self.policy.ctx:
            self.policy.log.debug(
                "Running policy %s resource: %s region:%s c7n:%s",
                self.policy.name, self.policy.resource_type,
                self.policy.options.region or 'default',
                version)

            s = time.time()
            try:
                resources = self.policy.resource_manager.resources()
            except ResourceLimitExceeded as e:
                self.policy.log.error(str(e))
                self.policy.ctx.metrics.put_metric(
                    'ResourceLimitExceeded', e.selection_count, "Count")
                raise

            rt = time.time() - s
            self.policy.log.info(
                "policy: %s resource:%s region:%s count:%d time:%0.2f" % (
                    self.policy.name,
                    self.policy.resource_type,
                    self.policy.options.region,
                    len(resources), rt))
            self.policy.ctx.metrics.put_metric(
                "ResourceCount", len(resources), "Count", Scope="Policy")
            self.policy.ctx.metrics.put_metric(
                "ResourceTime", rt, "Seconds", Scope="Policy")
            self.policy._write_file(
                'resources.json', utils.dumps(resources, indent=2))

            if not resources:
                return []

            if self.policy.options.dryrun:
                self.policy.log.debug("dryrun: skipping actions")
                return resources

            at = time.time()
            for a in self.policy.resource_manager.actions:
                s = time.time()
                results = a.process(resources)
                self.policy.log.info(
                    "policy: %s action: %s"
                    " resources: %d"
                    " execution_time: %0.2f" % (
                        self.policy.name, a.name,
                        len(resources), time.time() - s))
                if results:
                    self.policy._write_file(
                        "action-%s" % a.name, utils.dumps(results))
            self.policy.ctx.metrics.put_metric(
                "ActionTime", time.time() - at, "Seconds", Scope="Policy")
            return resources

    def get_logs(self, start, end):
        log_source = self.policy.ctx.output
        log_gen = ()
        if self.policy.options.log_group is not None:
            session = utils.local_session(self.policy.session_factory)
            log_gen = log_entries_from_group(
                session,
                self.policy.options.log_group,
                start,
                end,
            )
        elif log_source.type == 's3':
            raw_entries = log_entries_from_s3(
                self.policy.session_factory,
                log_source,
                start,
                end,
            )
            # log files can be downloaded out of order, so sort on timestamp
            # log_gen isn't really a generator once we do this, but oh well
            log_gen = sorted(
                normalized_log_entries(raw_entries),
                key=lambda e: e.get('timestamp', 0),
            )
        else:
            log_path = os.path.join(log_source.root_dir, 'custodian-run.log')
            with open(log_path) as log_fh:
                raw_entries = log_fh.readlines()
                log_gen = normalized_log_entries(raw_entries)
        return log_entries_in_range(
            log_gen,
            start,
            end,
        )

    def is_runnable(self):
        now = datetime.now(self.policy.tz)
        if self.policy.start and self.policy.start > now:
            self.policy.log.info(
                "Skipping policy %s start-date: %s is after current date: %s",
                self.policy.name, self.policy.start, now)
            return False
        if self.policy.end and self.policy.end < now:
            self.policy.log.info(
                "Skipping policy %s end-date: %s is before current date: %s",
                self.policy.name, self.policy.end, now)
            return False
        if self.policy.region and (
                self.policy.region != self.policy.options.region):
            self.policy.log.info(
                "Skipping policy %s target-region: %s current-region: %s",
                self.policy.name, self.policy.region,
                self.policy.options.region)
            return False
        return True


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
            'packages': {'type': 'array'},
            # Lambda passthrough config
            'runtime': {'enum': ['python2.7', 'python3.6']},
            'role': {'type': 'string'},
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

    def get_metrics(self, start, end, period):
        from c7n.mu import LambdaManager, PolicyLambda
        manager = LambdaManager(self.policy.session_factory)
        values = manager.metrics(
            [PolicyLambda(self.policy)], start, end, period)[0]
        values.update(
            super(LambdaMode, self).get_metrics(start, end, period))
        return values

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
            self.policy.session_factory.region = region
            self.policy.session_factory.assume_role = member_role
            self.policy.log.info(
                "Assuming member role: %s", member_role)
            return True
        return False

    def resolve_resources(self, event):
        self.assume_member(event)
        mode = self.policy.data.get('mode', {})
        resource_ids = CloudWatchEvents.get_ids(event, mode)
        if resource_ids is None:
            raise ValueError("Unknown push event mode %s", self.data)
        self.policy.log.info('Found resource ids: %s', resource_ids)
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
        Fortunately we already have replacements.

        TODO: better customization around execution context outputs
        TODO: support centralized lambda exec across accounts.
        """

        mode = self.policy.data.get('mode', {})
        if not bool(mode.get("log", True)):
            root = logging.getLogger()
            map(root.removeHandler, root.handlers[:])
            root.handlers = [logging.NullHandler()]

        resources = self.resolve_resources(event)
        if not resources:
            return resources
        resources = self.policy.resource_manager.filter_resources(
            resources, event)

        if 'debug' in event:
            self.policy.log.info("Filtered resources %d" % len(resources))

        if not resources:
            self.policy.log.info(
                "policy: %s resources: %s no resources matched" % (
                    self.policy.name, self.policy.resource_type))
            return

        with self.policy.ctx:
            self.policy.ctx.metrics.put_metric(
                'ResourceCount', len(resources), 'Count', Scope="Policy",
                buffer=False)

            if 'debug' in event:
                self.policy.log.info(
                    "Invoking actions %s", self.policy.resource_manager.actions)

            self.policy._write_file(
                'resources.json', utils.dumps(resources, indent=2))

            for action in self.policy.resource_manager.actions:
                self.policy.log.info(
                    "policy: %s invoking action: %s resources: %d",
                    self.policy.name, action.name, len(resources))
                if isinstance(action, EventAction):
                    results = action.process(resources, event)
                else:
                    results = action.process(resources)
                self.policy._write_file(
                    "action-%s" % action.name, utils.dumps(results))
        return resources

    def provision(self):
        with self.policy.ctx:
            self.policy.log.info(
                "Provisioning policy lambda %s", self.policy.name)
            try:
                manager = mu.LambdaManager(self.policy.session_factory)
            except ClientError:
                # For cli usage by normal users, don't assume the role just use
                # it for the lambda
                manager = mu.LambdaManager(
                    lambda assume=False: self.policy.session_factory(assume))
            return manager.publish(
                mu.PolicyLambda(self.policy), 'current',
                role=self.policy.options.assume_role)

    def get_logs(self, start, end):
        manager = mu.LambdaManager(self.policy.session_factory)
        log_gen = manager.logs(mu.PolicyLambda(self.policy), start, end)
        return log_entries_in_range(
            log_gen,
            start,
            end,
        )


@execution.register('periodic')
class PeriodicMode(LambdaMode, PullMode):
    """A policy that runs in pull mode within lambda."""

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    schema = utils.type_schema(
        'periodic', schedule={'type': 'string'}, rinherit=LambdaMode.schema)

    def run(self, event, lambda_context):
        return PullMode.run(self)


@execution.register('cloudtrail')
class CloudTrailMode(LambdaMode):
    """A lambda policy using cloudwatch events rules on cloudtrail api logs."""

    schema = utils.type_schema(
        'cloudtrail',
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
        events = self.policy.data['mode'].get('events')
        assert events, "cloud trail mode requires specifiying events to subscribe"
        for e in events:
            if isinstance(e, six.string_types):
                assert e in CloudWatchEvents.trail_events, "event shortcut not defined: %s" % e
            if isinstance(e, dict):
                jmespath.compile(e['ids'])
        if isinstance(self.policy.resource_manager, query.ChildResourceManager):
            if not getattr(self.policy.resource_manager.resource_type,
                           'supports_trailevents', False):
                raise ValueError(
                    "resource:%s does not support cloudtrail mode policies" % (
                        self.policy.resource_type))


@execution.register('ec2-instance-state')
class EC2InstanceState(LambdaMode):
    """
    A lambda policy that executes on ec2 instance state changes.

    https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html
    """

    schema = utils.type_schema(
        'ec2-instance-state', rinherit=LambdaMode.schema,
        events={'type': 'array', 'items': {
            'enum': ['pending', 'running', 'shutting-down',
                     'stopped', 'stopping', 'terminated']}})


@execution.register('asg-instance-state')
class ASGInstanceState(LambdaMode):
    """a lambda policy that executes on an asg's ec2 instance state changes."""

    schema = utils.type_schema(
        'asg-instance-state', rinherit=LambdaMode.schema,
        events={'type': 'array', 'items': {
            'enum': ['launch-success', 'launch-failure',
                     'terminate-success', 'terminate-failure']}})


@execution.register('guard-duty')
class GuardDutyMode(LambdaMode):
    """Incident Response for AWS Guard Duty"""

    schema = utils.type_schema('guard-duty', rinherit=LambdaMode.schema)

    supported_resources = ('account', 'ec2', 'iam-user')

    id_exprs = {
        'account': jmespath.compile('detail.accountId'),
        'ec2': jmespath.compile('detail.resource.instanceDetails.instanceId'),
        'iam-user': jmespath.compile('detail.resource.accessKeyDetails.userName')}

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


@execution.register('config-rule')
class ConfigRuleMode(LambdaMode):
    """a lambda policy that executes as a config service rule.
        http://docs.aws.amazon.com/config/latest/APIReference/API_PutConfigRule.html
    """

    cfg_event = None
    schema = utils.type_schema('config-rule', rinherit=LambdaMode.schema)

    def resolve_resources(self, event):
        source = self.policy.resource_manager.get_source('config')
        return [source.load_resource(self.cfg_event['configurationItem'])]

    def run(self, event, lambda_context):
        self.cfg_event = json.loads(event['invokingEvent'])
        cfg_item = self.cfg_event['configurationItem']
        evaluation = None
        resources = []
        # TODO config resource type matches policy check
        if event['eventLeftScope'] or cfg_item['configurationItemStatus'] in (
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


class Policy(object):

    log = logging.getLogger('custodian.policy')

    def __init__(self, data, options, session_factory=None):
        self.data = data
        self.options = options
        assert "name" in self.data
        if session_factory is None:
            session_factory = clouds[self.provider_name]().get_session_factory(options)
        self.session_factory = session_factory
        self.ctx = ExecutionContext(self.session_factory, self, self.options)
        self.resource_manager = self.load_resource_manager()

    def __repr__(self):
        return "<Policy resource: %s name: %s region: %s>" % (
            self.resource_type, self.name, self.options.region)

    @property
    def name(self):
        return self.data['name']

    @property
    def resource_type(self):
        return self.data['resource']

    @property
    def provider_name(self):
        if '.' in self.resource_type:
            provider_name, resource_type = self.resource_type.split('.', 1)
        else:
            provider_name = 'aws'
        return provider_name

    @property
    def region(self):
        return self.data.get('region')

    @property
    def tz(self):
        return tz.gettz(self.data.get('tz', 'UTC'))

    @property
    def start(self):
        if self.data.get('start'):
            return parser.parse(self.data.get('start'), ignoretz=True).replace(tzinfo=self.tz)
        return None

    @property
    def end(self):
        if self.data.get('end'):
            return parser.parse(self.data.get('end'), ignoretz=True).replace(tzinfo=self.tz)
        return None

    @property
    def max_resources(self):
        return self.data.get('max-resources')

    @property
    def max_resources_percent(self):
        return self.data.get('max-resources-percent')

    @property
    def tags(self):
        return self.data.get('tags', ())

    def get_execution_mode(self):
        exec_mode_type = self.data.get('mode', {'type': 'pull'}).get('type')
        exec_mode = execution[exec_mode_type]
        if exec_mode is None:
            return None
        return exec_mode(self)

    @property
    def is_lambda(self):
        if 'mode' not in self.data:
            return False
        return True

    def validate(self):
        m = self.get_execution_mode()
        if m is None:
            raise PolicyValidationError(
                "Invalid Execution mode in policy %s" % (self.data,))
        m.validate()
        self.validate_policy_start_stop()
        for f in self.resource_manager.filters:
            f.validate()
        for a in self.resource_manager.actions:
            a.validate()

    def get_variables(self):
        # Global policy variable expansion, we have to carry forward on
        # various filter/action local vocabularies. Where possible defer
        # by using a format string.
        #
        # See https://github.com/capitalone/cloud-custodian/issues/2330
        return {
            # standard runtime variables for interpolation
            'account': '{account}',
            'account_id': self.options.account_id,
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
            'now': utils.FormatDate(datetime.utcnow()),
            # account increase limit action
            'service': '{service}',
            # s3 set logging action :-( see if we can revisit this one.
            'bucket_region': '{bucket_region}',
            'bucket_name': '{bucket_name}',
            'source_bucket_name': '{source_bucket_name}',
            'target_bucket_name': '{target_bucket_name}',
            'target_prefix': '{target_prefix}',
            'LoadBalancerName': '{LoadBalancerName}'
        }

    def expand_variables(self, variables):
        """Expand variables in policy data.

        Updates the policy data in-place.
        """
        # format string values returns a copy
        updated = utils.format_string_values(self.data, **variables)

        # Several keys should only be expanded at runtime, perserve them.
        if 'member-role' in updated.get('mode', {}):
            updated['mode']['member-role'] = self.data['mode']['member-role']

        # Update ourselves in place
        self.data = updated
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

    def push(self, event, lambda_ctx):
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

    def get_logs(self, start, end):
        mode = self.get_execution_mode()
        return mode.get_logs(start, end)

    def get_metrics(self, start, end, period):
        mode = self.get_execution_mode()
        return mode.get_metrics(start, end, period)

    def get_permissions(self):
        """get permissions needed by this policy"""
        permissions = set()
        permissions.update(self.resource_manager.get_permissions())
        for f in self.resource_manager.filters:
            permissions.update(f.get_permissions())
        for a in self.resource_manager.actions:
            permissions.update(a.get_permissions())
        return permissions

    def __call__(self):
        """Run policy in default mode"""
        mode = self.get_execution_mode()
        self.session_factory.policy_name = self.name
        if self.options.dryrun:
            resources = PullMode(self).run()
        elif isinstance(mode, ServerlessExecutionMode):
            resources = mode.provision()
        else:
            resources = mode.run()
        # clear out resource manager post run, to clear cache
        self.resource_manager = self.load_resource_manager()
        return resources

    run = __call__

    def _write_file(self, rel_path, value):
        with open(os.path.join(self.ctx.log_dir, rel_path), 'w') as fh:
            fh.write(value)

    def load_resource_manager(self):
        resource_type = self.data.get('resource')

        provider = clouds.get(self.provider_name)
        if provider is None:
            raise ValueError(
                "Invalid cloud provider: %s" % self.provider_name)

        factory = provider.resources.get(
            resource_type.rsplit('.', 1)[-1])
        if not factory:
            raise ValueError(
                "Invalid resource type: %s" % resource_type)
        return factory(self.ctx, self.data)

    def validate_policy_start_stop(self):
        policy_name = self.data.get('name')
        policy_tz = self.data.get('tz')
        policy_start = self.data.get('start')
        policy_end = self.data.get('end')

        if policy_tz:
            try:
                p_tz = tz.gettz(policy_tz)
            except Exception as e:
                raise ValueError(
                    "Policy: %s TZ not parsable: %s, %s" % (policy_name, policy_tz, e))
            if not isinstance(p_tz, tz.tzfile):
                raise ValueError(
                    "Policy: %s TZ not parsable: %s" % (policy_name, policy_tz))

        for i in [policy_start, policy_end]:
            if i:
                try:
                    parser.parse(i)
                except Exception as e:
                    raise ValueError(
                        "Policy: %s Date/Time not parsable: %s, %s" % (policy_name, i, e))
