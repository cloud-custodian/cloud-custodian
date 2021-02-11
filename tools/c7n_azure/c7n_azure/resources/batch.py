# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('batch')
class Batch(ArmResourceManager):
    """Batch Resource

    :example:

    This set of policies will find all Azure Batch services that have more than 100 cores
    as the limit for the dedicated core quota.

    .. code-block:: yaml

        policies:
          - name: find-batch-with-high-dedicated-cores
            resource: azure.batch
            filters:
              - type: value
                key: properties.dedicatedCoreQuota
                op: gt
                value: 100

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Compute']

        service = 'azure.mgmt.batch'
        client = 'BatchManagementClient'
        enum_spec = ('batch_account', 'list', None)
        resource_type = 'Microsoft.Batch/batchAccounts'
