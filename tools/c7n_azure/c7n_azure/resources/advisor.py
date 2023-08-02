# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('advisor-recommendation')
class AdvisorRecommendation(ArmResourceManager):
    """Azure Advisor Resource

    :example:

    Returns all azure advisor recommendations of type Security

    .. code-block:: yaml

        policies:
        - name: list-advisor-security-recommendations
          resource: azure.advisor-recommendation
          filters:
            - type: value
              key: properties.category
              op: equal
              value_type: normalize
              value: security

        - name: azure-advisor-recommendations-with-query
          description: Query recommendations by category
          query:
            - filter: "Category eq 'Cost'"
          resource: azure.advisor-recommendation
    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Security']

        service = 'azure.mgmt.advisor'
        client = 'AdvisorManagementClient'
        enum_spec = ('recommendations', 'list', None)
        default_report_fields = (
            'name',
            'resourceGroup',
            'properties.category',
            'properties.impact',
            'properties.impactedField',
            'properties.impactedValue',
            'properties.shortDescription.problem',
            'properties.lastUpdated'
        )
        resource_type = 'Microsoft.Advisor/recommendations'
