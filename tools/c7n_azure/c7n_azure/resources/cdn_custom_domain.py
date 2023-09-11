# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ChildArmResourceManager
from c7n_azure.utils import ResourceIdParser
from c7n.filters.core import ValueFilter
from c7n.utils import type_schema


@resources.register('cdn-custom-domain')
class CdnCustomDomain(ChildArmResourceManager):
    """CDN Endpoint Resource

    :example:

    Returns all CDN endpoints without Https provisioning

    .. code-block:: yaml

        policies:
          - name: standard-verizon
            resource: azure.cdn-custom-domain
            filters:
              - type: value
                key: properties.customHttpsProvisioningState
                op: ne
                value: Enabled

    """

    class resource_type(ChildArmResourceManager.resource_type):
        doc_groups = ['Media']

        service = 'azure.mgmt.cdn'
        client = 'CdnManagementClient'
        enum_spec = ('custom_domains', 'list_by_endpoint', None)
        parent_manager_name = 'cdn-endpoint'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
            'properties.customHttpsProvisioningState',
            'properties.customHttpsProvisioningSubstate',
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


@CdnCustomDomain.filter_registry.register('tls-version')
class CdnManagedHttpsParametersFilter(ValueFilter):
    """
     Find all Cdn Endpoint Custom Domain with minimum Tls Version set to TLS12

    :example:

    .. code-block:: yaml

        policies:
          - name: cdn-endpoint-custom-domain-tls-version
            resource: azure.cdn-custom-domain
            filters:
               - and:
                  - type: value
                    key: properties.customHttpsProvisioningState
                    op: eq
                    value: Enabled
                  - type: tls-version
                    key: properties.customHttpsParameters.minimumTlsVersion
                    op: eq
                    value: "TLS12"

    """

    schema = type_schema(
          'tls-version',
          rinherit=ValueFilter.schema,
          value = {'type': 'string', 'enum':['None', 'TLS10', 'TLS12']})
    
    def process(self, resources, event=None):
        desired_version = self.data['value']
        for custom_domain in resources:
            properties = custom_domain.get('properties', {})
            if 'customHttpsParameters' not in properties:
                http_params = {
                      "certificateSource": "Cdn",
                      "protocolType": "ServerNameIndication",
                      "minimumTlsVersion": desired_version,
                      "certificateSource_parameters": {
                           "typeName": "CdnCertificateSourceParameters",
                            "certificateType": "Dedicated"
                      }
                }
                custom_domain['properties']['customHttpsParameters'] = http_params
        return super().process(resources)
