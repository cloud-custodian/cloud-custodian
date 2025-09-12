# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager

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
                metric: Http5xx
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
