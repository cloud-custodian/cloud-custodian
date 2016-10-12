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
import json
import fnmatch
import itertools
import logging
import os
import time

from botocore.client import ClientError

from c7n.actions import EventAction
from c7n.cwe import CloudWatchEvents
from c7n.ctx import ExecutionContext
from c7n.credentials import SessionFactory
from c7n.manager import resources
from c7n.output import DEFAULT_NAMESPACE
from c7n import utils
from c7n.version import version

from c7n.resources import load_resources


def load(options, path, format='yaml', validate=True):
    if not os.path.exists(path):
        raise ValueError("Invalid path for config %r" % path)

    load_resources()
    with open(path) as fh:
        if format == 'yaml':
            data = utils.yaml_load(fh.read())
        elif format == 'json':
            data = utils.loads(fh.read())
            validate = False
    if validate:
        from c7n.schema import validate
        errors = validate(data)
        if errors:
            raise Exception("Failed to validate on policy %s \n %s" % (errors[1], errors[0]))
    return PolicyCollection(data, options)


class PolicyCollection(object):

    def __init__(self, data, options):
        self.data = data
        self.options = options

    def policies(self, filters=None, resource_type=None):
        # self.options is the CLI options specified in cli.setup_parser()
        policies = [Policy(p, self.options) for p in self.data.get(
            'policies', [])
                    if resource_type and resource_type == p.resource_type or 1]

        if not filters:
            return policies

        return [p for p in policies if fnmatch.fnmatch(p.name, filters)]

    filter = policies

    def __iter__(self):
        return iter(self.policies())

    def __contains__(self, policy_name):
        return policy_name in [p['name'] for p in self.data['policies']]


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

    def get_logs(self, start, end, period):
        """Retrieve logs for the policy"""
        raise NotImplementedError("not yet")

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
            if isinstance(m, basestring):
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


class PullMode(PolicyExecutionMode):
    """Pull mode execution of a policy.

    Queries resources from cloud provider for filtering and actions.
    """

    def run(self, *args, **kw):
        if self.policy.region and (
                self.policy.region != self.policy.options.region):
            self.policy.log.info(
                "Skipping policy %s target-region: %s current-region: %s",
                self.policy.name, self.policy.region,
                self.policy.options.region)
            return

        with self.policy.ctx:
            self.policy.log.info(
                "Running policy %s resource: %s region:%s c7n:%s",
                self.policy.name, self.policy.resource_type,
                self.policy.options.region,
                version)

            s = time.time()
            resources = self.policy.resource_manager.resources()
            rt = time.time() - s
            self.policy.log.info(
                "policy: %s resource:%s has count:%d time:%0.2f" % (
                    self.policy.name,
                    self.policy.resource_type,
                    len(resources), rt))
            self.policy.ctx.metrics.put_metric(
                "ResourceCount", len(resources), "Count", Scope="Policy")
            self.policy.ctx.metrics.put_metric(
                "ResourceTime", rt, "Seconds", Scope="Policy")
            self.policy._write_file(
                'resources.json', utils.dumps(resources, indent=2))

            if not resources:
                return []
            elif (self.policy.max_resources is not None and
                  len(resources) > self.policy.max_resources):
                msg = "policy %s matched %d resources max resources %s" % (
                    self.policy.name, len(resources), self.policy.max_resources)
                self.policy.log.warning(msg)
                raise RuntimeError(msg)

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
                        len(resources), time.time()-s))
                self.policy._write_file(
                    "action-%s" % a.name, utils.dumps(results))
            self.policy.ctx.metrics.put_metric(
                "ActionTime", time.time() - at, "Seconds", Scope="Policy")
            return resources


class LambdaMode(PolicyExecutionMode):
    """A policy that runs/executes in lambda."""

    POLICY_METRICS = ('ResourceCount',)

    def get_metrics(self, start, end, period):
        from c7n.mu import LambdaManager, PolicyLambda
        manager = LambdaManager(self.policy.session_factory)
        values = manager.metrics(
            [PolicyLambda(self.policy)], start, end, period)[0]
        values.update(
            super(LambdaMode, self).get_metrics(start, end, period))
        return values

    def resolve_resources(self, event):
        mode = self.policy.data.get('mode', {})
        resource_ids = CloudWatchEvents.get_ids(event, mode)
        if resource_ids is None:
            raise ValueError("Unknown push event mode %s" % self.data)

        self.policy.log.info('Found resource ids: %s' % resource_ids)
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

        self.policy.ctx.metrics.put_metric(
            'ResourceCount', len(resources), 'Count', Scope="Policy",
            buffer=False)

        if 'debug' in event:
            self.policy.log.info(
                "Invoking actions %s", self.policy.resource_manager.actions)
        for action in self.policy.resource_manager.actions:
            self.policy.log.info(
                "policy: %s invoking action: %s resources: %d",
                self.policy.name, action.name, len(resources))
            if isinstance(action, EventAction):
                action.process(resources, event)
            else:
                action.process(resources)
        return resources

    def provision(self):
        # Avoiding runtime lambda dep, premature optimization?
        from c7n.mu import PolicyLambda, LambdaManager

        with self.policy.ctx:
            self.policy.log.info(
                "Provisioning policy lambda %s", self.policy.name)
            try:
                manager = LambdaManager(self.policy.session_factory)
            except ClientError:
                # For cli usage by normal users, don't assume the role just use
                # it for the lambda
                manager = LambdaManager(
                    lambda assume=False: self.policy.session_factory(assume))
            return manager.publish(
                PolicyLambda(self.policy), 'current',
                role=self.policy.options.assume_role)


class PeriodicMode(LambdaMode, PullMode):
    """A policy that runs in pull mode within lambda."""

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    def run(self, event, lambda_context):
        return PullMode.run(self)


class CloudTrailMode(LambdaMode):
    """A lambda policy using cloudwatch events rules on cloudtrail api logs."""


class EC2InstanceState(LambdaMode):
    """a lambda policy that executes on ec2 instance state changes."""


class ASGInstanceState(LambdaMode):
    """a lambda policy that executes on an asg's ec2 instance state changes."""


class ConfigRuleMode(LambdaMode):
    """a lambda policy that executes as a config service rule.
        http://docs.aws.amazon.com/config/latest/APIReference/API_PutConfigRule.html
    """

    cfg_event = None

    def resolve_resources(self, event):
        return [utils.camelResource(
            self.cfg_event['configurationItem']['configuration'])]

    def run(self, event, lambda_context):
        self.cfg_event = json.loads(event['invokingEvent'])
        cfg_item = self.cfg_event['configurationItem']
        evaluation = None
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

    EXEC_MODE_MAP = {
        'pull': PullMode,
        'periodic': PeriodicMode,
        'cloudtrail': CloudTrailMode,
        'ec2-instance-state': EC2InstanceState,
        'asg-instance-state': ASGInstanceState,
        'config-rule': ConfigRuleMode}

    log = logging.getLogger('custodian.policy')

    def __init__(self, data, options, session_factory=None):
        self.data = data
        self.options = options
        assert "name" in self.data
        if session_factory is None:
            session_factory = SessionFactory(
                options.region,
                options.profile,
                options.assume_role)
        self.session_factory = session_factory
        self.ctx = ExecutionContext(self.session_factory, self, self.options)
        self.resource_manager = self.get_resource_manager()

    def __repr__(self):
        return "<Policy resource: %s name: %s>" % (
            self.resource_type, self.name)

    @property
    def name(self):
        return self.data['name']

    @property
    def resource_type(self):
        return self.data['resource']

    @property
    def region(self):
        return self.data.get('region')

    @property
    def max_resources(self):
        return self.data.get('max-resources')

    @property
    def tags(self):
        return self.data.get('tags', ())

    def get_execution_mode(self):
        exec_mode_type = self.data.get('mode', {'type': 'pull'}).get('type')
        return self.EXEC_MODE_MAP[exec_mode_type](self)

    @property
    def is_lambda(self):
        if 'mode' not in self.data:
            return False
        return True

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

    def get_metrics(self, start, end, period):
        mode = self.get_execution_mode()
        return mode.get_metrics(start, end, period)

    def __call__(self):
        """Run policy in default mode"""
        mode = self.get_execution_mode()
        if self.options.dryrun:
            return PullMode(self).run()
        elif isinstance(mode, LambdaMode):
            return mode.provision()
        else:
            return mode.run()

    run = __call__

    def _write_file(self, rel_path, value):
        with open(os.path.join(self.ctx.log_dir, rel_path), 'w') as fh:
            fh.write(value)

    def get_resource_manager(self):
        resource_type = self.data.get('resource')
        factory = resources.get(resource_type)
        if not factory:
            raise ValueError(
                "Invalid resource type: %s" % resource_type)
        return factory(self.ctx, self.data)
