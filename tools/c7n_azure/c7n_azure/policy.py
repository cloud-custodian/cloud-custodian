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

import logging
import re

import six
from azure.mgmt.eventgrid.models import StorageQueueEventSubscriptionDestination
from c7n_azure.azure_events import AzureEventSubscription
from c7n_azure.azure_events import AzureEvents
from c7n_azure.constants import (FUNCTION_EVENT_TRIGGER_MODE, FUNCTION_TIME_TRIGGER_MODE)
from c7n_azure.function_package import FunctionPackage
from c7n_azure.functionapp_utils import FunctionAppUtilities
from c7n_azure.storage_utils import StorageUtilities
from c7n_azure.utils import ResourceIdParser, StringUtils

from c7n import utils
from c7n.actions import EventAction
from c7n.policy import ServerlessExecutionMode, PullMode, execution
from c7n.utils import local_session


class AzureFunctionMode(ServerlessExecutionMode):
    """A policy that runs/executes in azure functions."""

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'provision-options': {
                'type': 'object',
                'appInsights': {
                    'type': 'object',
                    'oneOf': [
                        {'type': 'string'},
                        {'type': 'object',
                         'properties': {
                             'name': 'string',
                             'location': 'string',
                             'resourceGroupName': 'string'}
                         }
                    ]
                },
                'storageAccount': {
                    'type': 'object',
                    'oneOf': [
                        {'type': 'string'},
                        {'type': 'object',
                         'properties': {
                             'name': 'string',
                             'location': 'string',
                             'resourceGroupName': 'string'}
                         }
                    ]
                },
                'servicePlan': {
                    'type': 'object',
                    'oneOf': [
                        {'type': 'string'},
                        {'type': 'object',
                         'properties': {
                             'name': 'string',
                             'location': 'string',
                             'resourceGroupName': 'string',
                             'skuTier': 'string',
                             'skuName': 'string'}
                         }
                    ]
                },
            },
            'execution-options': {'type': 'object'}
        }
    }

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    default_storage_name = "custodian"

    def __init__(self, policy):

        self.policy = policy
        self.log = logging.getLogger('custodian.azure.AzureFunctionMode')
        self.policy_name = self.policy.data['name'].replace(' ', '-').lower()
        self.function_app_name = None

    def get_function_app_params(self):
        session = local_session(self.policy.session_factory)

        provision_options = self.policy.data['mode'].get('provision-options', {})

        # Service plan is parsed first, location might be shared with storage & insights
        service_plan = AzureFunctionMode.extract_properties(
            provision_options,
            'servicePlan',
            {
                'name': 'cloud-custodian',
                'location': 'westus2',
                'resource_group_name': 'cloud-custodian',
                'sku_name': 'B1',
                'sku_tier': 'Basic'
            })

        # Metadata used for automatic naming
        location = service_plan.get('location', 'westus2')
        rg_name = service_plan['resource_group_name']
        sub_id = session.get_subscription_id()
        target_sub_id = session.get_function_target_subscription_id()
        function_suffix = StringUtils.naming_hash(rg_name + target_sub_id)
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

        self.function_app_name = self.policy_name + '-' + function_suffix

        params = FunctionAppUtilities.FunctionAppInfrastructureParameters(
            app_insights=app_insights,
            service_plan=service_plan,
            storage_account=storage_account,
            functionapp_name=self.function_app_name)

        return params

    @staticmethod
    def extract_properties(options, name, properties):
        settings = options.get(name, {})
        result = {}
        # str type implies settings is a resource id
        if isinstance(settings, six.string_types):
            result['id'] = settings
            result['name'] = ResourceIdParser.get_resource_name(settings)
            result['resource_group_name'] = ResourceIdParser.get_resource_group(settings)
        else:
            for key in properties.keys():
                result[key] = settings.get(StringUtils.snake_to_camel(key), properties[key])

        return result

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        params = self.get_function_app_params()
        FunctionAppUtilities().deploy_dedicated_function_app(params)

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("subclass responsibility")

    def validate(self):
        """Validate configuration settings for execution mode."""

    def _publish_functions_package(self, queue_name=None):
        self.log.info("Building function package for %s" % self.function_app_name)

        archive = FunctionPackage(self.policy_name)
        archive.build(self.policy.data, queue_name=queue_name)
        archive.close()

        self.log.info("Function package built, size is %dMB" % (archive.pkg.size / (1024 * 1024)))

        if archive.wait_for_status(self.function_app_name):
            archive.publish(self.function_app_name)
        else:
            self.log.error("Aborted deployment, ensure Application Service is healthy.")


@execution.register(FUNCTION_TIME_TRIGGER_MODE)
class AzurePeriodicMode(AzureFunctionMode, PullMode):
    """A policy that runs/executes in azure functions at specified
    time intervals."""
    schema = utils.type_schema(FUNCTION_TIME_TRIGGER_MODE,
                               schedule={'type': 'string'},
                               rinherit=AzureFunctionMode.schema)

    def provision(self):
        super(AzurePeriodicMode, self).provision()
        self._publish_functions_package()

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
                               events={'type': 'array', 'items': {
                                   'oneOf': [
                                       {'type': 'string'},
                                       {'type': 'object',
                                        'required': ['resourceProvider', 'event'],
                                        'properties': {
                                            'resourceProvider': {'type': 'string'},
                                            'event': {'type': 'string'}}}]
                               }},
                               required=['events'],
                               rinherit=AzureFunctionMode.schema)

    def provision(self):
        super(AzureEventGridMode, self).provision()
        session = local_session(self.policy.session_factory)

        # queue name is restricted to lowercase letters, numbers, and single hyphens
        queue_name = re.sub(r'(-{2,})+', '-', self.functionapp_name.lower())
        storage_account = self._create_storage_queue(queue_name, session)
        self._create_event_subscription(storage_account, queue_name, session)
        self._publish_functions_package(queue_name)

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        subscribed_events = AzureEvents.get_event_operations(
            self.policy.data['mode'].get('events'))

        resource_ids = list(set(
            [e['subject'] for e in event if self._is_subscribed_to_event(e, subscribed_events)]))

        resources = self.policy.resource_manager.get_resources(resource_ids)

        if not resources:
            self.policy.log.info(
                "policy: %s resources: %s no resources found" % (
                    self.policy.name, self.policy.resource_type))
            return

        with self.policy.ctx:
            self.policy.ctx.metrics.put_metric(
                'ResourceCount', len(resources), 'Count', Scope="Policy",
                buffer=False)

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

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")

    def _is_subscribed_to_event(self, event, subscribed_events):
        subscribed_events = [e.lower() for e in subscribed_events]
        if not event['data']['operationName'].lower() in subscribed_events:
            self.policy.log.info(
                "Event operation %s does not match subscribed events %s" % (
                    event['data']['operationName'], subscribed_events
                )
            )
            return False

        return True

    def _create_storage_queue(self, queue_name, session):
        self.log.info("Creating storage queue")
        storage_client = session.client('azure.mgmt.storage.StorageManagementClient')
        storage_account = storage_client.storage_accounts.get_properties(
            self.storage_account['resource_group_name'], self.storage_account['name'])

        try:
            StorageUtilities.create_queue_from_storage_account(storage_account, queue_name)
            self.log.info("Storage queue creation succeeded")
            return storage_account
        except Exception as e:
            self.log.error('Queue creation failed with error: %s' % e)
            raise SystemExit

    def _create_event_subscription(self, storage_account, queue_name, session):
        self.log.info('Creating event grid subscription')
        destination = StorageQueueEventSubscriptionDestination(resource_id=storage_account.id,
                                                               queue_name=queue_name)

        try:
            AzureEventSubscription.create(destination, queue_name, session)
            self.log.info('Event grid subscription creation succeeded')
        except Exception as e:
            self.log.error('Event Subscription creation failed with error: %s' % e)
            raise SystemExit
