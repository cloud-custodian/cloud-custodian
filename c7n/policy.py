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
import fnmatch
import logging
import os
import time

from botocore.client import ClientError

from c7n.actions import EventAction
from c7n.cwe import CloudWatchEvents
from c7n.ctx import ExecutionContext
from c7n.credentials import SessionFactory
from c7n.manager import resources
from c7n import utils

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
            raise errors[0]
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


class Policy(object):

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
    def is_lambda(self):
        if not 'mode' in self.data:
            return False
        return True

    def push(self, event, lambda_ctx):
        """Run policy in push mode against given event.

        Lambda automatically generates cloud watch logs, and metrics
        for us, albeit with some deficienies, metrics no longer count
        against valid resources matches, but against execution.
        Fortunately we already have replacements.

        TODO: better customization around execution context outputs
        TODO: support centralized lambda exec across accounts.
        """
        mode = self.data.get('mode', {})
        mode_type = mode.get('type')

        if mode_type == 'periodic':
            return self.poll()

        resource_ids = CloudWatchEvents.get_ids(event, mode)
        if resource_ids is None:
            raise ValueError("Unknown push event mode %s" % self.data)

        self.log.info('Found resource ids: %s' % resource_ids)
        if not resource_ids:
            self.log.warning("Could not find resource ids")
            return

        resources = self.resource_manager.get_resources(resource_ids)
        if 'debug' in event:
            self.log.info("Resources %s", resources)

        resources = self.resource_manager.filter_resources(resources, event)
        if 'debug' in event:
            self.log.info("Filtered resources %d" % len(resources))

        if not resources:
            self.log.info("policy: %s resources: %s no resources matched" % (
                self.name, self.resource_type))
            return

        if 'debug' in event:
            self.log.info("Invoking actions %s", self.resource_manager.actions)
        for action in self.resource_manager.actions:
            self.log.info(
                "policy: %s invoking action: %s resources: %d",
                self.name, action.name, len(resources))
            if isinstance(action, EventAction):
                action.process(resources, event)
            else:
                action.process(resources)

    def provision(self):
        """Provision policy as a lambda function."""
        # Avoiding runtime lambda dep, premature optimization?
        from c7n.mu import PolicyLambda, LambdaManager

        with self.ctx:
            self.log.info(
                "Provisioning policy lambda %s", self.name)
            try:
                manager = LambdaManager(self.session_factory)
            except ClientError:
                # For cli usage by normal users, don't assume the role just use
                # it for the lambda
                manager = LambdaManager(
                    lambda assume=False: self.session_factory(assume))
            return manager.publish(
                PolicyLambda(self), 'current', role=self.options.assume_role)

    def poll(self):
        """Query resources and apply policy."""
        with self.ctx:
            self.log.info("Running policy %s resource: %s",
                          self.name, self.resource_type)
            s = time.time()
            resources = self.resource_manager.resources()
            rt = time.time() - s
            self.log.info(
                "policy: %s resource:%s has count:%d time:%0.2f" % (
                    self.name, self.resource_type, len(resources), rt))
            self.ctx.metrics.put_metric(
                "ResourceCount", len(resources), "Count", Scope="Policy")
            self.ctx.metrics.put_metric(
                "ResourceTime", rt, "Seconds", Scope="Policy")
            self._write_file(
                'resources.json', utils.dumps(resources, indent=2))

            if not resources:
                return []

            if self.options.dryrun and not self.resource_manager.supports_dry_run:
                self.log.debug("dryrun: skipping actions")
                return resources

            at = time.time()
            for a in self.resource_manager.actions:
                s = time.time()
                results = a.process(resources)
                self.log.info(
                    "policy: %s action: %s resources: %d execution_time: %0.2f" % (
                        self.name, a.name, len(resources), time.time()-s))
                self._write_file("action-%s" % a.name, utils.dumps(results))
            self.ctx.metrics.put_metric(
                "ActionTime", time.time() - at, "Seconds", Scope="Policy")
            return resources

    def __call__(self):
        """Run policy in default mode"""
        if self.is_lambda and not self.options.dryrun:
            return self.provision()
        else:
            return self.poll()

    run = __call__

    def _write_file(self, rel_p, value):
        with open(
                os.path.join(self.ctx.log_dir, rel_p), 'w') as fh:
            fh.write(value)

    def get_resource_manager(self):
        resource_type = self.data.get('resource')
        factory = resources.get(resource_type)
        if not factory:
            raise ValueError(
                "Invalid resource type: %s" % resource_type)
        return factory(self.ctx, self.data)
