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

import copy
import json
import fnmatch
import itertools
import logging
import os
import time

import boto3
from botocore.client import ClientError
import jmespath

from c7n.actions import EventAction
from c7n.cwe import CloudWatchEvents
from c7n.ctx import ExecutionContext
from c7n.credentials import SessionFactory
from c7n.manager import resources
from c7n.output import DEFAULT_NAMESPACE
from c7n import mu
from c7n import utils
from c7n.logs_support import (
    normalized_log_entries,
    log_entries_in_range,
    log_entries_from_s3,
    log_entries_from_group,
)
from c7n.version import version

from c7n.resources import load_resources


def load(options, path, format='yaml', validate=True, vars=None):
    # should we do os.path.expanduser here?
    if not os.path.exists(path):
        raise IOError("Invalid path for config %r" % path)

    load_resources()
    data = utils.load_file(path, format=format, vars=vars)

    if format == 'json':
        validate = False

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


def get_service_region_map(regions, resource_types):
    # we're not interacting with the apis just using the sdk meta information.
    session = boto3.Session(
        region_name='us-east-1',
        aws_access_key_id='never',
        aws_secret_access_key='found')

    resource_service_map = {r: resources.get(r).resource_type.service
                            for r in resource_types if r != 'account'}
    # support for govcloud and china, we only utilize these regions if they
    # are explicitly passed in on the cli.
    partition_regions = {}
    for p in ('aws-cn', 'aws-us-gov'):
        for r in session.get_available_regions('s3', partition_name=p):
            partition_regions[r] = p

    partitions = ['aws']
    for r in regions:
        if r in partition_regions:
            partitions.append(partition_regions[r])

    service_region_map = {}
    for s in set(itertools.chain(resource_service_map.values())):
        for partition in partitions:
            service_region_map.setdefault(s, []).extend(
                session.get_available_regions(s, partition_name=partition))
    return service_region_map, resource_service_map


class PolicyCollection(object):

    log = logging.getLogger('c7n.policies')

    def __init__(self, policies, options):
        self.options = options
        self.policies = policies

    @classmethod
    def from_data(cls, data, options):
        policies = [Policy(p, options,
                           session_factory=cls.test_session_factory())
                    for p in data.get('policies', ())]
        return PolicyCollection(policies, options)

    def __add__(self, other):
        return PolicyCollection(self.policies + other.policies, self.options)

    def expand_regions(self, regions):
        """Return a set of policies targetted to the given regions.

        Supports symbolic regions like 'all'. This will automatically
        filter out policies if their being targetted to a region that
        does not support the service. Global services will target a
        single region (us-east-1 if only all specified, else first
        region in the list).

        Note for region partitions (govcloud and china) an explicit
        region from the partition must be passed in.
        """
        policies = []
        service_region_map, resource_service_map = get_service_region_map(
            regions, self.resource_types)

        for p in self.policies:
            available_regions = service_region_map.get(
                resource_service_map.get(p.resource_type), ())

            # its a global service/endpoint, use user provided region
            # or us-east-1.
            if not available_regions and regions:
                candidates = [r for r in regions if r != 'all']
                candidate = candidates and candidates[0] or 'us-east-1'
                svc_regions = [candidate]
            elif 'all' in regions:
                svc_regions = available_regions
            else:
                svc_regions = regions

            for region in svc_regions:
                if available_regions and region not in available_regions:
                    level = ('all' in self.options.regions and
                             logging.DEBUG or logging.WARNING)
                    self.log.log(
                        level, "policy:%s resources:%s not available in region:%s",
                        p.name, p.resource_type, region)
                    continue
                options_copy = copy.copy(self.options)
                options_copy.region = str(region)

                if len(regions) > 1 or 'all' in regions and getattr(
                        self.options, 'output_dir', None):
                    options_copy.output_dir = (
                        self.options.output_dir.rstrip('/') + '/%s' % region)

                policies.append(
                    Policy(p.data, options_copy,
                           session_factory=self.test_session_factory()))
        return PolicyCollection(policies, self.options)

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

    @classmethod
    def test_session_factory(self):
        """ For testing: patched by tests to use a custom session_factory """
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
            self.policy.log.debug(
                "Running policy %s resource: %s region:%s c7n:%s",
                self.policy.name, self.policy.resource_type,
                self.policy.options.region or 'default',
                version)

            s = time.time()
            resources = self.policy.resource_manager.resources()
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
            elif (self.policy.max_resources is not None and
                  len(resources) > self.policy.max_resources):
                msg = "policy %s matched %d resources max resources %s" % (
                    self.policy.name, len(resources),
                    self.policy.max_resources)
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
                        len(resources), time.time() - s))
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
        elif log_source.use_s3():
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

    def get_logs(self, start, end):
        manager = mu.LambdaManager(self.policy.session_factory)
        log_gen = manager.logs(mu.PolicyLambda(self.policy), start, end)
        return log_entries_in_range(
            log_gen,
            start,
            end,
        )


class PeriodicMode(LambdaMode, PullMode):
    """A policy that runs in pull mode within lambda."""

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    def run(self, event, lambda_context):
        return PullMode.run(self)


class CloudTrailMode(LambdaMode):
    """A lambda policy using cloudwatch events rules on cloudtrail api logs."""

    def validate(self):
        events = self.policy.data['mode'].get('events')
        assert events, "cloud trail mode requires specifiying events to subscribe"
        for e in events:
            if isinstance(e, basestring):
                assert e in CloudWatchEvents.trail_events, "event shortcut not defined"
            if isinstance(e, dict):
                jmespath.compile(e['ids'])


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
                options.assume_role,
                options.external_id)
        self.session_factory = session_factory
        self.ctx = ExecutionContext(self.session_factory, self, self.options)
        self.resource_manager = self.get_resource_manager()

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

    def validate(self):
        m = self.get_execution_mode()
        m.validate()
        for f in self.resource_manager.filters:
            f.validate()
        for a in self.resource_manager.actions:
            a.validate()

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
        if self.options.dryrun:
            resources = PullMode(self).run()
        elif isinstance(mode, LambdaMode):
            resources = mode.provision()
        else:
            resources = mode.run()
        # clear out resource manager post run, to clear cache
        self.resource_manager = self.get_resource_manager()
        return resources

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
