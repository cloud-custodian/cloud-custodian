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

import requests
import logging
import json
import time

from c7n_azure.function_package import FunctionPackage
from msrestazure.azure_exceptions import CloudError
from c7n_azure.functionapp_utils import FunctionAppUtilities
from c7n_azure.template_utils import TemplateUtilities
from c7n_azure.azure_events import AzureEvents
from c7n_azure.constants import (CONST_DOCKER_VERSION, CONST_FUNCTIONS_EXT_VERSION,
                                 CONST_AZURE_EVENT_TRIGGER_MODE, CONST_AZURE_TIME_TRIGGER_MODE,
                                 CONST_AZURE_FUNCTION_KEY_URL)

from c7n import utils
from c7n.actions import EventAction
from c7n.policy import ServerlessExecutionMode, PullMode, execution
from c7n.utils import local_session

from azure.mgmt.eventgrid.models import (EventSubscription, EventSubscriptionFilter,
                                         WebHookEventSubscriptionDestination)


class AzureFunctionMode(ServerlessExecutionMode):
    """A policy that runs/executes in azure functions."""

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'provision-options': {
                'type': 'object',
                'location': 'string',
                'appInsightsLocation': 'string',
                'servicePlanName': 'string',
                'sku': 'string',
                'workerSize': 'number',
                'skuCode': 'string'
            },
            'execution-options': {'type': 'object'}
        }
    }

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    def __init__(self, policy):
        self.policy = policy
        self.log = logging.getLogger('custodian.azure.AzureFunctionMode')
        self.session = local_session(self.policy.session_factory)
        self.client = self.session.client('azure.mgmt.web.WebSiteManagementClient')

        self.template_util = TemplateUtilities()
        self.parameters = self._get_parameters(self.template_util)
        self.group_name = self.parameters['servicePlanName']['value']
        self.webapp_name = self.parameters['name']['value']
        self.policy_name = self.policy.data['name'].replace(' ', '-').lower()

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        """Provision any resources needed for the policy."""
        existing_service_plan = self.client.app_service_plans.get(
            self.group_name, self.parameters['servicePlanName']['value'])

        if not existing_service_plan:
            self.template_util.create_resource_group(
                self.group_name, {'location': self.parameters['location']['value']})

            self.template_util.deploy_resource_template(
                self.group_name, 'dedicated_functionapp.json', self.parameters).wait()

        else:
            existing_webapp = self.client.web_apps.get(self.group_name, self.webapp_name)
            if not existing_webapp:
                functionapp_util = FunctionAppUtilities()
                functionapp_util.deploy_webapp(self.webapp_name,
                                               self.group_name, existing_service_plan,
                                               self.parameters['storageName']['value'])
            else:
                self.log.info("Found existing App %s (%s) in group %s" %
                              (self.webapp_name, existing_webapp.location, self.group_name))

        self.log.info("Building function package for %s" % self.webapp_name)

        archive = FunctionPackage(self.policy_name)
        archive.build(self.policy.data)
        archive.close()

        if archive.wait_for_status(self.webapp_name):
            archive.publish(self.webapp_name)
        else:
            self.log.error("Aborted deployment, ensure Application Service is healthy.")

    def _get_parameters(self, template_util):
        parameters = template_util.get_default_parameters(
            'dedicated_functionapp.parameters.json')

        data = self.policy.data

        updated_parameters = {
            'dockerVersion': CONST_DOCKER_VERSION,
            'functionsExtVersion': CONST_FUNCTIONS_EXT_VERSION
        }

        if 'mode' in data:
            if 'provision-options' in data['mode']:
                updated_parameters.update(data['mode']['provision-options'])
                if 'servicePlanName' in data['mode']['provision-options']:
                    updated_parameters['name'] = (
                        data['mode']['provision-options']['servicePlanName'] +
                        '-' + data['name']
                    ).replace(' ', '-').lower()

                    updated_parameters['storageName'] = (
                        data['mode']['provision-options']['servicePlanName']
                    ).replace('-', '').lower()

        parameters = template_util.update_parameters(parameters, updated_parameters)

        return parameters

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("subclass responsibility")

    def validate(self):
        """Validate configuration settings for execution mode."""


@execution.register(CONST_AZURE_TIME_TRIGGER_MODE)
class AzurePeriodicMode(AzureFunctionMode, PullMode):
    """A policy that runs/executes in azure functions at specified
    time intervals."""
    schema = utils.type_schema(CONST_AZURE_TIME_TRIGGER_MODE,
                               schedule={'type': 'string'},
                               rinherit=AzureFunctionMode.schema)

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        return PullMode.run(self)

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")


@execution.register(CONST_AZURE_EVENT_TRIGGER_MODE)
class AzureEventGridMode(AzureFunctionMode):
    """A policy that runs/executes in azure functions from an
    azure event."""

    schema = utils.type_schema(CONST_AZURE_EVENT_TRIGGER_MODE,
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
        key = self._get_webhook_key()
        webhook_url = 'https://%s.azurewebsites.net/api/%s?code=%s' % (self.webapp_name,
                                                                       self.policy_name, key)
        destination = WebHookEventSubscriptionDestination(
            endpoint_url=webhook_url
        )
        event_filter = EventSubscriptionFilter()
        event_info = EventSubscription(destination=destination, filter=event_filter)
        scope = '/subscriptions/%s' % self.session.subscription_id

        #: :type: azure.mgmt.eventgrid.EventGridManagementClient
        eventgrid_client = self.session.client('azure.mgmt.eventgrid.EventGridManagementClient')

        status_success = False
        while not status_success:
            try:
                event_subscription = eventgrid_client.event_subscriptions.create_or_update(
                    scope, self.webapp_name, event_info)

                event_subscription.result()
                self.log.info('Event subscription creation succeeded')
                status_success = True
            except CloudError as e:
                self.log.info(e)
                self.log.info('Retrying in 30 seconds')
                time.sleep(30)

    def _get_webhook_key(self):
        token_headers = {
            'Authorization': 'Bearer %s' % self.session.get_bearer_token()
        }

        key_url = (
            'https://management.azure.com'
            '/subscriptions/{0}/resourceGroups/{1}/'
            'providers/Microsoft.Web/sites/{2}/{3}').format(
                self.session.subscription_id,
                self.group_name,
                self.webapp_name,
                CONST_AZURE_FUNCTION_KEY_URL)

        retrieved_key = False

        while not retrieved_key:
            response = requests.get(key_url, headers=token_headers)
            if response.status_code == 200:
                key = json.loads(response.content)
                return key['value']
            else:
                self.log.info('Function app key unavailable, will retry in 30 seconds')
                time.sleep(30)

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
