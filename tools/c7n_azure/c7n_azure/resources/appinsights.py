# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('app-insights')
class AzureAppInsights(ArmResourceManager):
    """Application Insights resource

    :example:

    This policy will list Applilcation Insights components.

    .. code-block:: yaml

        policies:
          - name: check-app-insights
            resource: azure.app-insights
            filters:
              - type: value
                key: name
                value: present

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute']

        service = 'azure.mgmt.applicationinsights'
        client = 'ApplicationInsightsManagementClient'
        enum_spec = ('components', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )
        resource_type = 'microsoft.insights/components'
