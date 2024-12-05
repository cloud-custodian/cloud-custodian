# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('recovery-services')
class RecoveryServices(ArmResourceManager):
    """Azure Recovery Services Vault

    :example:

    Return all Recovery Services Vault on the Standcard SKU

    .. code-block:: yaml

        policies:
          - name: recovery-services-vault
            resource: azure.recovery-services
            filters: value
            key: sku.name
            op: equal
            value: Standard

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Backup and Recovery']

        service = 'azure.mgmt.recoveryservices'
        client = 'RecoveryServicesClient'
        enum_spec = ('vaults', 'list_by_subscription_id', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.name'
        )

        resource_type = 'Microsoft.RecoveryServices/vaults'
