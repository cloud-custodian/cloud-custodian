# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n_azure.utils import ResourceIdParser


@resources.register('cdncustomdomain')
class CdnCustomDomain(ChildArmResourceManager):
    """CDN Endpoint Resource

    :example:

    Returns all CDN endpoints with Https provisioning stated not-equal Enabled

    .. code-block:: yaml

        policies:
          - name: standard-verizon
            resource: azure.cdncustomDomain
            filters:
              - type: value
                key: properties.customHttpsProvisioingState
                op: ne
                value_: Enabled


    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Media']

        service = 'azure.mgmt.cdn'
        client = 'CdnManagementClient'
        enum_spec = ('custom_domains', 'list_by_endpoints', None)
        parent_manager_name = 'cdnendpoint'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.customDomainName',
            'properties.customHttpsProvisioningState',
            'properties.customHttpaProvisioningSubstate',
            'properties.customDomainHttpsParameters'
            '"c7n:parent-id"'
        )
        resource_type = 'Microsoft.Cdn/profiles/endpoints/customDomains'

        @classmethod
        def extra_args(cls, parent_resource):
            endpoint_name = parent_resource['name']
            resource_group_name = parent_resource['resourceGroup']
            profile_id = parent_resource['c7n:parent-id']
            profile_name = ResourceIdParser.get_resource_name(profile_id)

            return {
                'resource_group_name': resource_group_name,
                'endpoint_name': endpoint_name,
                'profile_name': profile_name
            }
