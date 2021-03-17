# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('cdnprofile')
class CdnProfile(ArmResourceManager):
    """CDN Resource

    :example:

    Returns all CDNs with Standard_Verizon sku

    .. code-block:: yaml

        policies:
          - name: standard-verizon
            resource: azure.cdnprofile
            filters:
              - type: value
                key: sku
                op: in
                value_type: normalize
                value: Standard_Verizon

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Media']

        service = 'azure.mgmt.cdn'
        client = 'CdnManagementClient'
        enum_spec = ('profiles', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'sku.name'
        )
        resource_type = 'Microsoft.Cdn/profiles'
