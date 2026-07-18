# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager


@resources.register('afd-endpoint')
class AfdEndpoint(ChildArmResourceManager):
    """Lists exising Azure Front Door endpoints

    :example:

    Returns all enabled Front Door endpoints

    .. code-block:: yaml

        policies:
          - name: enabled-front-door-endpoints
            resource: azure.afd-endpoint
            filters:
              - type: value
                key: properties.enabledState
                value: Enabled

    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Media']

        service = 'azure.mgmt.cdn'
        client = 'CdnManagementClient'
        enum_spec = ('afd_endpoints', 'list_by_profile', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            '"c7n:parent-id"'
        )
        resource_type = 'Microsoft.Cdn/profiles/afdendpoints'
        # seems like cdn profile and afd profile are the same
        parent_manager_name = 'cdnprofile'

        @classmethod
        def extra_args(cls, parent_resource):
            return {'resource_group_name': parent_resource['resourceGroup'],
                    'profile_name': parent_resource['name']}
