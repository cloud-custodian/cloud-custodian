# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('databricks')
class Databricks(ArmResourceManager):
    """Databricks Resource

    :example:

    Returns all databricks named my-test-databricks

    .. code-block:: yaml

        policies:
          - name: get-databricks
            resource: azure.databricks
            filters:
              - type: value
                key: name
                op: eq
                value: my-test-databricks

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']

        service = 'azure.mgmt.databricks.databricks_client'
        client = 'DatabricksClient'
        enum_spec = ('workspaces', 'list_by_subscription', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.name'
        )
        resource_type = 'Microsoft.Databricks/workspaces'
