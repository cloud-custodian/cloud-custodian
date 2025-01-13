# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager


@resources.register('afd-custom-domain')
class AfdCustomDomain(ChildArmResourceManager):
    """AFD custom domain resource

    :example:

    Returns all AFD custom domains where minimum tls version is not TLS12

    .. code-block:: yaml

        policies:
          - name: standard-verizon
            resource: azure.afd-custom-domain
            filters:
              - type: value
                key: properties.tlsSettings.minimumTlsVersion
                op: ne
                value: TLS12

    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Media']

        service = 'azure.mgmt.cdn'
        client = 'CdnManagementClient'
        enum_spec = ('afd_custom_domains', 'list_by_profile', None)
        parent_manager_name = 'cdnprofile'
        default_report_fields = (
            'name',
            'resourceGroup',
            'properties.hostName',
            '"c7n:parent-id"'
        )
        resource_type = 'Microsoft.Cdn/profiles/customdomains'

        @classmethod
        def extra_args(cls, parent_resource):
            return {
                'resource_group_name': parent_resource['resourceGroup'],
                'profile_name': parent_resource['name']
            }
