# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import inspect

from typing import get_args

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.utils import type_to_jsonschema, ResourceIdParser

from c7n.filters.core import ValueFilter, type_schema


@resources.register('webapp')
class WebApp(ArmResourceManager):
    """Web Applications Resource

    :example:

    This policy will find all web apps with 10 or less requests over the last 72 hours

    .. code-block:: yaml

        policies:
          - name: webapp-dropping-messages
            resource: azure.webapp
            filters:
              - type: metric
                metric: Requests
                op: le
                aggregation: total
                threshold: 10
                timeframe: 72
             actions:
              - type: mark-for-op
                op: delete
                days: 7

    :example:

    This policy will find all web apps with 1000 or more server errors over the last 72 hours

    .. code-block:: yaml

        policies:
          - name: webapp-high-error-count
            resource: azure.webapp
            filters:
              - type: metric
                metric: Http5xxx
                op: ge
                aggregation: total
                threshold: 1000
                timeframe: 72

    :example:

    This policy will find all web apps with minimum TLS encryption version not equal to 1.2

    .. code-block:: yaml

        policies:
          - name: webapp-min-tls-enforcement
            resource: azure.webapp
            filters:
              - type: configuration
                key: minTlsVersion
                value: '1.2'
                op: ne
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute', 'Web']

        service = 'azure.mgmt.web'
        client = 'WebSiteManagementClient'
        enum_spec = ('web_apps', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'kind',
            'properties.hostNames[0]'
        )
        resource_type = 'Microsoft.Web/sites'


@WebApp.filter_registry.register('configuration')
class ConfigurationFilter(ValueFilter):
    schema = type_schema('configuration', rinherit=ValueFilter.schema)

    def __call__(self, i):
        if 'c7n:configuration' not in i:
            client = self.manager.get_client().web_apps
            instance = (
                client.get_configuration(i['resourceGroup'], i['name'])
            )
            i['c7n:configuration'] = instance.serialize(keep_readonly=True)['properties']

        return super(ConfigurationFilter, self).__call__(i['c7n:configuration'])


@WebApp.filter_registry.register('authentication')
class AuthenticationFilter(ValueFilter):
    """Web Applications Authentication Filter

    :example:

    This policy will find all web apps without an authentication method enabled

    .. code-block:: yaml

        policies:
          - name: webapp-no-authentication
            resource: azure.webapp
            filters:
              - type: authentication
                key: enabled
                value: False
                op: eq
    """

    schema = type_schema('authentication', rinherit=ValueFilter.schema)

    def __call__(self, i):
        if 'c7n:authentication' not in i:
            client = self.manager.get_client().web_apps

            instance = (
                client.get_auth_settings(i['resourceGroup'], i['name'])
            )

            i['c7n:authentication'] = instance.serialize(keep_readonly=True)['properties']

        return super().__call__(i['c7n:authentication'])


@WebApp.action_registry.register("update-configuration")
class UpdateWebAppActionConfiguration(AzureBaseAction):
    """
    Updates a web app configuration
    """

    @staticmethod
    def generate_schema():
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.web import WebSiteManagementClient

        sub_id = "00000000-0000-0000-0000-000000000000"
        client = WebSiteManagementClient(credential=DefaultAzureCredential(), subscription_id=sub_id)
        site_config_model = client.models().SiteConfigResource
        model_signature = inspect.signature(site_config_model)

        schema_dict = {}
        required = []

        for name, v in model_signature.parameters.items():

            if name == "kwargs":
                continue

            schema_dict.setdefault(name, {})

            if hasattr(v, "annotation"):
                args = get_args(v.annotation)

                if type(None) not in args:
                    required.append(name)
                else:
                    args = list(args)
                    args.remove(type(None))

                if len(args) == 1:
                    schema_dict[name]['type'] = args[0]

                schema_dict[name] = type_to_jsonschema(args[0])

        return type_schema(
            "update-configuration",
            required=required,
            **{"configuration": {"type": "object", "properties": schema_dict}}
        )

    schema = generate_schema()

    def _process_resource(self, resource, event=None):

        client = self.manager.get_client().web_apps

        group_name = ResourceIdParser().get_resource_group(resource["id"])
        name = ResourceIdParser().get_resource_name(resource["id"])

        client.create_or_update_configuration(
            resource_group_name=group_name,
            name=name,
            site_config=self.data.get("configuration")
        )
