# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('search')
class SearchService(ArmResourceManager):
    """Azure Search Service Resource

    :example:

    Returns all Search services on the Basic SKU

    .. code-block:: yaml

        policies:
          - name: basic-search
            resource: azure.search
            filters:
              - type: value
                key: sku.name
                op: equal
                value: Basic

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']

        service = 'azure.mgmt.search'
        client = 'SearchManagementClient'
        enum_spec = ('services', 'list_by_subscription', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.name'
        )
        resource_type = 'Microsoft.Search/searchServices'
