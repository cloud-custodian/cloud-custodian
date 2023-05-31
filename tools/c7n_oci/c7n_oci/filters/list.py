# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n.utils import type_schema
from c7n.filters.core import Filter
from c7n_oci.provider import resources

class QueryFilter(Filter):
    '''
    QueryFilter that queries the resources from the OCI. This query filter is applicable to all the OCI
    resources and it fetches the resources based on the params that are passed to this filter

    :example:

        Query filter that filter the Compute instance resources from the specified compartment

    .. code-block:: yaml

         policies:
            - name: tag-vm-policy
            description: |
                Adds a tag to a virtual machines
            resource: oci.compute
            filters:
                - type: query
                  params:
                     compartment_id: 'ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-Value'

    '''
    schema = type_schema('query',
                         params={'type': 'object', "additionalProperties": {'type': 'string'}},
                         required=['params'])

    def process(self, resources, event):
        return resources

    @classmethod
    def register_resources(cls, registry, resource_class):
        resource_class.filter_registry.register('query', QueryFilter)

resources.subscribe(QueryFilter.register_resources)