# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager


@resources.register('cdn-endpoint')
class CdnEndpoint(ChildArmResourceManager):
    """CDN Endpoint Resource

    :example:

    Returns all CDN endpoints with Standard_Verizon sku

    .. code-block:: yaml

        policies:
          - name: standard-verizon
            resource: azure.cdn-endpoint
            filters:
              - type: value
                key: sku
                op: in
                value_type: normalize
                value: standard_verizon

    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Media']

        service = 'azure.mgmt.cdn'
        client = 'CdnManagementClient'
        enum_spec = ('endpoints', 'list_by_profile', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            '"c7n:parent-id"'
        )
        resource_type = 'Microsoft.Cdn/profiles/endpoints'
        parent_manager_name = 'cdnprofile'

        @classmethod
        def extra_args(cls, parent_resource):
            return {'resource_group_name': parent_resource['resourceGroup'],
                    'profile_name': parent_resource['name']}
