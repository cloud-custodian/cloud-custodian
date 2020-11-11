# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging

from dateutil.tz import tz

from c7n.exceptions import PolicyValidationError
from c7n.policy import execution, ServerlessExecutionMode, PullMode
from c7n.utils import local_session, type_schema

from c7n_gcp import mu

DEFAULT_REGION = 'us-central1'


class FunctionMode(ServerlessExecutionMode):

    schema = type_schema(
        'gcp',
        **{'execution-options': {'$ref': '#/definitions/basic_dict'},
           'timeout': {'type': 'string'},
           'memory-size': {'type': 'integer'},
           'labels': {'$ref': '#/definitions/string_dict'},
           'network': {'type': 'string'},
           'max-instances': {'type': 'integer'},
           'service-account': {'type': 'string'},
           'environment': {'$ref': '#/definitions/string_dict'}}
    )

    def __init__(self, policy):
        self.policy = policy
        self.log = logging.getLogger('custodian.gcp.funcexec')
        self.region = policy.options.regions[0] if len(policy.options.regions) else DEFAULT_REGION

    def run(self):
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        self.log.info("Provisioning policy function %s", self.policy.name)
        manager = mu.CloudFunctionManager(self.policy.session_factory, self.region)
        return manager.publish(self._get_function())

    def deprovision(self):
        manager = mu.CloudFunctionManager(self.policy.session_factory, self.region)
        return manager.remove(self._get_function())

    def validate(self):
        pass

    def _get_function(self):
        raise NotImplementedError("subclass responsibility")


@execution.register('gcp-periodic')
class PeriodicMode(FunctionMode, PullMode):
    """Deploy a policy as a Cloud Functions triggered by Cloud Scheduler
    at user defined cron interval via Pub/Sub.

    Default region the function is deployed to is ``us-central1``. In
    case you want to change that, use the cli ``--region`` flag.
    """

    schema = type_schema(
        'gcp-periodic',
        rinherit=FunctionMode.schema,
        required=['schedule'],
        **{'trigger-type': {'enum': ['http', 'pubsub']},
           'tz': {'type': 'string'},
           'schedule': {'type': 'string'}})

    def validate(self):
        mode = self.policy.data['mode']
        if 'tz' in mode:
            error = PolicyValidationError(
                "policy:%s gcp-periodic invalid tz:%s" % (
                    self.policy.name, mode['tz']))
            # We can't catch all errors statically, our local tz retrieval
            # then the form gcp is using, ie. not all the same aliases are
            # defined.
            tzinfo = tz.gettz(mode['tz'])
            if tzinfo is None:
                raise error

    def _get_function(self):
        events = [mu.PeriodicEvent(
            local_session(self.policy.session_factory),
            self.policy.data['mode'],
            self.region
        )]
        return mu.PolicyFunction(self.policy, events=events)

    def run(self, event, context):
        return PullMode.run(self)


@execution.register('gcp-audit')
class ApiAuditMode(FunctionMode):
    """Custodian policy execution on gcp api audit logs events.

    Deploys as a Cloud Function triggered by api calls. This allows
    you to apply your policies as soon as an api call occurs. Audit
    logs creates an event for every api call that occurs in your gcp
    account. See `GCP Audit Logs
    <https://cloud.google.com/logging/docs/audit/>`_ for more
    details.

    Default region the function is deployed to is
    ``us-central1``. In case you want to change that, use the cli
    ``--region`` flag.
    """

    schema = type_schema(
        'gcp-audit',
        methods={'type': 'array', 'items': {'type': 'string'}},
        required=['methods'],
        rinherit=FunctionMode.schema)

    def resolve_resources(self, event):
        """Resolve a gcp resource from its audit trail metadata.
        """
        if self.policy.resource_manager.resource_type.get_requires_event:
            return [self.policy.resource_manager.get_resource(event)]
        resource_info = event.get('resource')
        if resource_info is None or 'labels' not in resource_info:
            self.policy.log.warning("Could not find resource information in event")
            return
        # copy resource name, the api doesn't like resource ids, just names.
        if 'resourceName' in event['protoPayload']:
            resource_info['labels']['resourceName'] = event['protoPayload']['resourceName']

        resource = self.policy.resource_manager.get_resource(resource_info['labels'])
        return [resource]

    def _get_function(self):
        events = [mu.ApiSubscriber(
            local_session(self.policy.session_factory),
            self.policy.data['mode'])]
        return mu.PolicyFunction(self.policy, events=events)

    def validate(self):
        if not self.policy.resource_manager.resource_type.get:
            raise PolicyValidationError(
                "Resource:%s does not implement retrieval method" % (
                    self.policy.resource_type))

    def run(self, event, context):
        """Execute a gcp serverless model"""
        from c7n.actions import EventAction

        resources = self.resolve_resources(event)
        if not resources:
            return

        resources = self.policy.resource_manager.filter_resources(
            resources, event)

        self.policy.log.info("Filtered resources %d" % len(resources))

        if not resources:
            return

        self.policy.ctx.metrics.put_metric(
            'ResourceCount', len(resources), 'Count', Scope="Policy",
            buffer=False)

        for action in self.policy.resource_manager.actions:
            if isinstance(action, EventAction):
                action.process(resources, event)
            else:
                action.process(resources)

        return resources
