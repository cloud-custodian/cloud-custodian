# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import time

from dateutil.tz import tz

from c7n import utils
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

    def resolve_resources(self, event):
        raise NotImplementedError("subclass responsibility")  # pragma: no cover

    def run(self, event, context):
        """Execute a gcp serverless model"""
        from c7n.actions import EventAction

        s = time.time()
        resources = self.resolve_resources(event)
        if not resources:
            return  # pragma: no cover

        resources = self.policy.resource_manager.filter_resources(resources, event)

        if not resources:  # pragma: no cover
            self.policy.log.info(
                "policy: %s resources: %s no resources found"
                % (self.policy.name, self.policy.resource_type)
            )
            return
        rt = time.time() - s

        with self.policy.ctx as ctx:
            self.policy.log.info("Filtered resources %d" % len(resources))

            ctx.metrics.put_metric("ResourceCount", len(resources), "Count", Scope="Policy")
            ctx.metrics.put_metric("ResourceTime", rt, "Seconds", Scope="Policy")
            ctx.output.write_file("resources.json", utils.dumps(resources, indent=2))

            for action in self.policy.resource_manager.actions:
                if isinstance(action, EventAction):  # pragma: no cover
                    action.process(resources, event)
                else:
                    action.process(resources)

            return resources

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

    `target-type`: `pubsub` is recommended
    """

    schema = type_schema(
        'gcp-periodic',
        rinherit=FunctionMode.schema,
        required=['schedule'],
        **{'target-type': {'enum': ['http', 'pubsub']},
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
        if mode.get('target-type', 'http') == 'http':
            if mode.get('service-account') is None:
                raise PolicyValidationError(
                    'policy:%s gcp-periodic requires service-account for http target'
                    % self.policy.name
                )

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


@execution.register('gcp-scc')
class SecurityCenterMode(FunctionMode):
    """Custodian policy execution on GCP Security Command Center (SCC) findings.

    Deploys as a Cloud Function triggered by SCC findings. This allows
    you to apply your policies as soon as a SCC finding occurs.
    See `Security Command Center
    <https://cloud.google.com/security-command-center/docs/concepts-security-command-center-overview#introduction>`_
    for more details.

    .. code-block:: yaml

      - name: delete-high-severity-firewall-findings
        resource: gcp.firewall
        mode:
          service-account: SERVICE_ACCOUNT_NAME@PROJECT.iam.gserviceaccount.com
          type: gcp-scc
          org: ORG_ID
        filters:
        - type: value
          key: severity
          value: HIGH
        actions:
          - delete

    Default region the function is deployed to is
    ``us-central1``. In case you want to change that, use the cli
    ``--region`` flag.
    """

    schema = type_schema(
        'gcp-scc',
        org={'type': 'integer'},
        required=['org'],
        rinherit=FunctionMode.schema)

    def resolve_resources(self, event):
        """Resolve a gcp resource from its scc finding.
        """
        if not event["finding"].get("resourceName"):
            self.policy.log.warning("Could not find resourceName in event")
            return

        project_id = event["resource"].get("project", "").split('/')[-1]
        finding_details = {
            "resourceName": event["finding"]["resourceName"],
            "project_id": project_id
        }

        resource = self.policy.resource_manager.get_resource(finding_details)
        # add finding fields to resource
        resource.update({"finding": event["finding"]})

        return [resource]

    def _resource_topic(self):
        return "custodian-auto-scc-{}".format(self.policy.resource_manager.type)

    def _get_function(self):
        events = [
            mu.PubSubSource(local_session(self.policy.session_factory),
            {"topic": self._resource_topic()}),
            mu.SecurityCenterSubscriber(local_session(self.policy.session_factory),
             {"topic": self._resource_topic(),
             "org": self.policy.data["mode"]["org"]}, self.policy.resource_manager)]
        return mu.PolicyFunction(self.policy, events=events)

    def validate(self):
        if not self.policy.resource_manager.resource_type.get:
            raise PolicyValidationError(
                "Resource:%s does not implement retrieval method get" % (
                    self.policy.resource_type))
        if not self.policy.resource_manager.resource_type.scc_type:
            raise PolicyValidationError(
                "Resource:%s is not supported by scc currently" % (
                    self.policy.resource_type))
