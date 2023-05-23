# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('recovery-services')
class RecoveryServices(ArmResourceManager):

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
