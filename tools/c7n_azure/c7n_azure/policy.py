# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import logging
import re
import time

from azure.mgmt.eventgrid.models import \
    StorageQueueEventSubscriptionDestination, StringInAdvancedFilter, EventSubscriptionFilter

from c7n_azure.azure_events import AzureEvents, AzureEventSubscription
from c7n_azure.constants import (
    AUTH_TYPE_EMBED,
    AUTH_TYPE_MSI,
    AUTH_TYPE_UAI,
    FUNCTION_EVENT_TRIGGER_MODE,
    FUNCTION_TIME_TRIGGER_MODE,
    RESOURCE_GROUPS_TYPE)
from c7n_azure.function_package import FunctionPackage
from c7n_azure.functionapp_utils import FunctionAppUtilities
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.storage_utils import StorageUtilities
from c7n_azure.utils import ResourceIdParser, StringUtils

from c7n import utils
from c7n.actions import EventAction
from c7n.exceptions import PolicyValidationError, PolicyExecutionError
from c7n.mu import generate_requirements
from c7n.policy import PullMode, ServerlessExecutionMode, execution
from c7n.utils import local_session, jmespath_search


class AzureFunctionMode(ServerlessExecutionMode):
    """A policy that runs/executes in azure functions."""

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'provision-options': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'identity': {
                        'type': 'object',
                        'additionalProperties': False,
                        'properties': {
                            'type': {'enum': [AUTH_TYPE_MSI,
                                              AUTH_TYPE_UAI,
                                              AUTH_TYPE_EMBED]},
                            'id': {'type': 'string'},
                        },
                    },
                    'appInsights': {
                        'oneOf': [
                            {'type': 'string'},
                            {'type': 'object',
                             'additionalProperties': False,
                             'properties': {
                                 'name': {'type': 'string'},
                                 'location': {'type': 'string'},
                                 'resourceGroupName': {'type': 'string'}}}
                        ]
                    },
                    'storageAccount': {
                        'oneOf': [
                            {'type': 'string'},
                            {'type': 'object',
                             'additionalProperties': False,
                             'properties': {
                                 'name': {'type': 'string'},
                                 'location': {'type': 'string'},
                                 'resourceGroupName': {'type': 'string'}}}
                        ]
                    },
                    'servicePlan': {
                        'oneOf': [
                            {'type': 'string'},
                            {'type': 'object',
                             'additionalProperties': False,
                             'properties': {
                                 'name': {'type': 'string'},
                                 'location': {'type': 'string'},
                                 'resourceGroupName': {'type': 'string'},
                                 'skuTier': {'type': 'string'},
                                 'skuName': {'type': 'string'},
                                 'autoScale': {
                                     'type': 'object',
                                     'additionalProperties': False,
                                     'properties': {
                                         'enabled': {'type': 'boolean'},
                                         'minCapacity': {'type': 'string'},
                                         'maxCapacity': {'type': 'string'},
                                         'defaultCapacity': {'type': 'string'}
                                     }
                                 }
                             }}
                        ]
                    },
                },
            },
            'execution-options': {'type': 'object'}
        },
    }

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    default_storage_name = "custodian"

    log = logging.getLogger('custodian.azure.policy.AzureFunctionMode')

    def __init__(self, policy):
        self.policy = policy
        self.policy_name = self.policy.data['name'].replace(' ', '-').lower()
        self.function_params = None
        self.function_app = None
        self.target_subscription_ids = []

    def validate(self):
        super().validate()
        identity = jmespath_search(
            'mode."provision-options".identity', self.policy.data)
        if (identity and identity['type'] == AUTH_TYPE_UAI and
                'id' not in identity):
            raise PolicyValidationError(
                "policy:%s user assigned identity requires specifying id" % (
                    self.policy.name))
        if not identity or identity['type'] == AUTH_TYPE_EMBED:
            self.log.error((
                'policy:%s function policies should use UserAssigned Identities '
                'see https://cloudcustodian.io/docs/azure/configuration/functionshosting.html#authentication-options'), # noqa
                self.policy.name)

    def get_function_app_params(self):
        session = local_session(self.policy.session_factory)
        provision_options = self.policy.data['mode'].get('provision-options', {})

        # Service plan is parsed first, location might be shared with storage & insights
        service_plan = AzureFunctionMode.extract_properties(
            provision_options,
            'servicePlan',
            {
                'name': 'cloud-custodian',
                'location': 'eastus',
                'resource_group_name': 'cloud-custodian',
                'sku_tier': 'Dynamic',  # consumption plan
                'sku_name': 'Y1',
                'auto_scale': {
                    'enabled': False,
                    'min_capacity': 1,
                    'max_capacity': 2,
                    'default_capacity': 1
                }
            })

        # Metadata used for automatic naming
        location = service_plan.get('location', 'eastus')
        rg_name = service_plan['resource_group_name']
        sub_id = session.get_subscription_id()

        target_sub_name = session.get_function_target_subscription_name()
        function_suffix = StringUtils.naming_hash(rg_name + target_sub_name)

        storage_suffix = StringUtils.naming_hash(rg_name + sub_id)

        storage_account = AzureFunctionMode.extract_properties(
            provision_options,
            'storageAccount',
            {
                'name': self.default_storage_name + storage_suffix,
                'location': location,
                'resource_group_name': rg_name
            })

        app_insights = AzureFunctionMode.extract_properties(
            provision_options,
            'appInsights',
            {
                'name': service_plan['name'],
                'location': location,
                'resource_group_name': rg_name
            })

        function_app_name = FunctionAppUtilities.get_function_name(self.policy_name,
            function_suffix)

        FunctionAppUtilities.validate_function_name(function_app_name)
        params = FunctionAppUtilities.FunctionAppInfrastructureParameters(
            app_insights=app_insights,
            service_plan=service_plan,
            storage_account=storage_account,
            function_app={
                'name': function_app_name,
                'resource_group_name': service_plan['resource_group_name'],
                'identity': self._get_identity(session)})
        return params

    def _get_identity(self, session):
        identity = jmespath_search(
            'mode."provision-options".identity', self.policy.data) or {
                'type': AUTH_TYPE_EMBED}
        if identity['type'] != AUTH_TYPE_UAI:
            return identity

        # We need to resolve the client id of the uai, as the metadata
        # service in functions is old and doesn't support newer
        # metadata api versions where this would be extraneous
        # (ie. versions 2018-02-01 or 2019-08-01). notably the
        # official docs here are wrong
        # https://docs.microsoft.com/en-us/azure/app-service/overview-managed-identity

        # TODO: switch out to using uai resource manager so we get some cache
        # benefits across policies using the same uai.
        id_client = session.client('azure.mgmt.msi.ManagedServiceIdentityClient')

        found = None
        for uai in id_client.user_assigned_identities.list_by_subscription():
            if uai.id == identity['id'] or uai.name == identity['id']:
                found = uai
                break
        if not found:
            raise PolicyExecutionError(
                "policy:%s Could not find the user assigned identity %s" % (
                    self.policy.name, identity['id']))
        identity['id'] = found.id
        identity['client_id'] = found.client_id
        return identity

    @staticmethod
    def extract_properties(options, name, properties):
        settings = options.get(name, {})
        result = {}
        # str type implies settings is a resource id
        if isinstance(settings, str):
            result['id'] = settings
            result['name'] = ResourceIdParser.get_resource_name(settings)
            result['resource_group_name'] = ResourceIdParser.get_resource_group(settings)
        else:
            # get nested keys
            for key in properties.keys():
                value = settings.get(StringUtils.snake_to_camel(key), properties[key])
                if isinstance(value, dict):
                    result[key] = \
                        AzureFunctionMode.extract_properties({'v': value}, 'v', properties[key])
                else:
                    result[key] = value

        return result

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        # Make sure we have auth data for function provisioning
        session = local_session(self.policy.session_factory)
        if jmespath_search(
                'mode."provision-options".identity.type',
                self.policy.data) in (AUTH_TYPE_EMBED, None):
            session.get_functions_auth_string("")

        self.target_subscription_ids = session.get_function_target_subscription_ids()

        self.function_params = self.get_function_app_params()
        self.function_app = FunctionAppUtilities.deploy_function_app(self.function_params)

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("subclass responsibility")

    def build_functions_package(self, queue_name=None, target_subscription_ids=None):
        self.log.info(
            "Building function package for %s",
            self.function_params.function_app['name'])

        requirements = generate_requirements('c7n-azure',
                                             ignore=['pywin32'],
                                             exclude='c7n')
        package = FunctionPackage(self.policy_name, target_sub_ids=target_subscription_ids)
        package.build(self.policy.data,
                      modules=['c7n', 'c7n-azure'],
                      requirements=requirements,
                      queue_name=queue_name)
        package.close()

        self.log.info("Function package built, size is %dKB" % (package.pkg.size / 1024))
        return package


class AzureModeCommon:
    """ Utility methods shared across a variety of modes """

    @staticmethod
    def extract_resource_id(policy, event):
        """
        Searches for a resource id in the events resource id
        that will match the policy resource type.
        """
        expected_type = policy.resource_manager.resource_type.resource_type

        if expected_type == 'armresource':
            return event['subject']
        elif expected_type == RESOURCE_GROUPS_TYPE:
            extract_regex = '/subscriptions/[^/]+/resourceGroups/[^/]+'
        else:
            types = expected_type.split('/')

            types_regex = '/'.join([t + '/[^/]+' for t in types[1:]])
            extract_regex = '/subscriptions/[^/]+/resourceGroups/[^/]+/providers/{0}/{1}'\
                .format(types[0], types_regex)

        return re.search(extract_regex, event['subject'], re.IGNORECASE).group()

    @staticmethod
    def run_for_event(policy, event=None):
        s = time.time()

        resources = policy.resource_manager.get_resources(
            [AzureModeCommon.extract_resource_id(policy, event)]
        )

        resources = policy.resource_manager.filter_resources(resources, event)

        if not resources:
            policy.log.info(
                "policy: %s resources: %s no resources found" % (policy.name, policy.resource_type)
            )
            return

        with policy.ctx as ctx:
            rt = time.time() - s

            ctx.metrics.put_metric("ResourceCount", len(resources), "Count", Scope="Policy")
            ctx.metrics.put_metric("ResourceTime", rt, "Seconds", Scope="Policy")
            ctx.output.write_file("resources.json", utils.dumps(resources, indent=2))

            at = time.time()
            for action in policy.resource_manager.actions:
                policy.log.info(
                    "policy: %s invoking action: %s resources: %d",
                    policy.name,
                    action.name,
                    len(resources),
                )
                with ctx.tracer.subsegment('action:%s' % action.type):
                    if isinstance(action, EventAction):
                        results = action.process(resources, event)
                    else:
                        results = action.process(resources)
                try:
                    ctx.output.write_file("action-%s" % action.name, utils.dumps(results))
                except (TypeError, OverflowError):
                    pass

            ctx.metrics.put_metric("ActionTime", time.time() - at, "Seconds", Scope="Policy")
            return resources


@execution.register(FUNCTION_TIME_TRIGGER_MODE)
class AzurePeriodicMode(AzureFunctionMode, PullMode):
    """A policy that runs/executes in azure functions at specified
    time intervals."""
    # Based on NCRONTAB used by Azure Functions:
    # https://docs.microsoft.com/en-us/azure/azure-functions/functions-bindings-timer
    schedule_regex = (r'^\s?([0-5]?[0-9]|\,|(\*\/)|\-)+ '
                      r'(\*|[0-5]?[0-9]|\,|\/|\-)+ '
                      r'(\*|[0-9]|(1[0-9])|(2[0-3])|\,|\/|\-)+ '
                      r'(\*|[1-9]|([1-2][0-9])|(3[0-1])|\,|\*\/|\-)+ '
                      r'([Jj](an|anuary)|[Ff](eb|ebruary)|[Mm](ar|arch)|[Aa](pr|pril)|[Mm]ay|'
                      r'[Jj](un|une)|[Jj](ul|uly)|[Aa](ug|ugust)|[Ss](ep|eptember)|[Oo](ct'
                      r'|ctober)|[Nn](ov|ovember)|[Dd](ec|ecember)|\,|\*\/|[1-9]|(1[0-2])|\*)+ '
                      r'([Mm](on|onday)|[Tt](u|ue|ues|uesday)|[Ww](ed|ednesday)|[Tt](hu|hursday)|'
                      r'[Ff](ri|riday)|[Ss](at|aturday)|[Ss](un|unday)|[0-6]|\,|\*|\-)+\s?$')
    schema = utils.type_schema(FUNCTION_TIME_TRIGGER_MODE,
                               schedule={'type': 'string', 'pattern': schedule_regex},
                               rinherit=AzureFunctionMode.schema)

    def provision(self):
        super(AzurePeriodicMode, self).provision()
        package = self.build_functions_package(target_subscription_ids=self.target_subscription_ids)
        FunctionAppUtilities.publish_functions_package(self.function_params, package)

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        return PullMode.run(self)

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")


@execution.register(FUNCTION_EVENT_TRIGGER_MODE)
class AzureEventGridMode(AzureFunctionMode):
    """A policy that runs/executes in azure functions from an
    azure event."""

    schema = utils.type_schema(FUNCTION_EVENT_TRIGGER_MODE,
                               events={'type': 'array',
                                    'maxItems': 5,
                                    'items': {
                                        'oneOf': [
                                            {'type': 'string'},
                                            {'type': 'object',
                                                'required': ['resourceProvider', 'event'],
                                                'properties': {
                                                    'resourceProvider': {'type': 'string'},
                                                    'event': {'type': 'string'}}}]}},
                               required=['events'],
                               rinherit=AzureFunctionMode.schema)

    def __init__(self, policy):
        super(AzureEventGridMode, self).__init__(policy)
        self.subscribed_events = AzureEvents.get_event_operations(
            self.policy.data['mode'].get('events', ()))

    def validate(self):
        super(AzureEventGridMode, self).validate()
        self._validate_is_arm_resource()
        self._validate_event_matches_resource()

    def _validate_is_arm_resource(self):
        if not isinstance(self.policy.resource_manager, ArmResourceManager):
            raise PolicyValidationError(
                'The policy resource, {}, is not supported in event grid mode.'.format(
                    self.policy.data['resource']))

    def _validate_event_matches_resource(self):
        resource_type = self.policy.resource_manager.resource_type.resource_type
        if resource_type != 'armresource':
            for event in self.subscribed_events:
                if resource_type.lower() not in event.lower():
                    raise PolicyValidationError(
                        'The policy resource, {}, can not be triggered by the event, {}.'.format(
                            resource_type, event))

    def provision(self):
        super(AzureEventGridMode, self).provision()
        session = local_session(self.policy.session_factory)

        # queue name is restricted to lowercase letters, numbers, and single hyphens
        queue_name = re.sub(r'(-{2,})+', '-', self.function_params.function_app['name'].lower())
        storage_account = self._create_storage_queue(queue_name, session)
        self._create_event_subscription(storage_account, queue_name, session)
        package = self.build_functions_package(queue_name=queue_name)
        FunctionAppUtilities.publish_functions_package(self.function_params, package)

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        return AzureModeCommon.run_for_event(self.policy, event)

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")

    def _create_storage_queue(self, queue_name, session):
        self.log.info("Creating storage queue")
        storage_client = session.client('azure.mgmt.storage.StorageManagementClient')
        storage_account = storage_client.storage_accounts.get_properties(
            self.function_params.storage_account['resource_group_name'],
            self.function_params.storage_account['name'])

        try:
            StorageUtilities.create_queue_from_storage_account(storage_account, queue_name, session)
            self.log.info("Storage queue creation succeeded")
            return storage_account
        except Exception:
            self.log.exception('Queue creation failed')
            raise SystemExit

    def _create_event_subscription(self, storage_account, queue_name, session):
        self.log.info('Creating event grid subscription')
        destination = StorageQueueEventSubscriptionDestination(resource_id=storage_account.id,
                                                               queue_name=queue_name)

        # filter specific events
        advance_filter = StringInAdvancedFilter(key='Data.OperationName',
                                                values=self.subscribed_events)
        event_filter = EventSubscriptionFilter(advanced_filters=[advance_filter])

        for subscription_id in self.target_subscription_ids:
            try:
                AzureEventSubscription.create(destination, queue_name,
                                              subscription_id, session, event_filter)
                self.log.info('Event grid subscription creation succeeded: subscription_id=%s' %
                              subscription_id)
            except Exception:
                self.log.exception('Event Subscription creation failed')
                raise SystemExit
