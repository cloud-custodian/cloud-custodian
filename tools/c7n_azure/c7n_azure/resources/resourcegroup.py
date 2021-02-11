# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_azure.constants import RESOURCE_GROUPS_TYPE
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.utils import ResourceIdParser

from c7n.filters import Filter
from c7n.utils import type_schema


@resources.register('resourcegroup')
class ResourceGroup(ArmResourceManager):
    """Resource Group Resource

    :example:

    Finds all Resource Groups in the subscription.

    .. code-block:: yaml

        policies:
            - name: find-all-resource-groups
              resource: azure.resourcegroup

    :example:

    Find all Resource Groups that have no resources in the subscription.

    .. code-block:: yaml

        policies:
          - name: test - azure
            resource: azure.resourcegroup
            filters:
              - type: empty-group

    :example:

    Delete all Resource Groups in the subscription tagged with 'ShouldBeDeleted'.

    **Warning: Deleting a resource group will delete all resources inside the resource group.**

    .. code-block:: yaml

        policies:
          - name: test - azure
            resource: azure.resourcegroup
            filters:
                - tag:ShouldBeDeleted: present
            actions:
                - type: delete

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Resource Group', 'Subscription']

        service = 'azure.mgmt.resource'
        client = 'ResourceManagementClient'
        enum_spec = ('resource_groups', 'list', None)
        resource_type = RESOURCE_GROUPS_TYPE

        default_report_fields = (
            'name',
            'location'
        )

    def get_resources(self, resource_ids):
        resource_client = self.get_client('azure.mgmt.resource.ResourceManagementClient')
        data = [
            resource_client.resource_groups.get(ResourceIdParser.get_resource_group(rid))
            for rid in resource_ids
        ]
        for d in data:
            d.type = RESOURCE_GROUPS_TYPE
        return [r.serialize(True) for r in data]

    def augment(self, resources):
        for resource in resources:
            resource['type'] = RESOURCE_GROUPS_TYPE
        return resources


@ResourceGroup.filter_registry.register('empty-group')
class EmptyGroup(Filter):
    schema = type_schema('empty-group')

    def __call__(self, group):
        resources_iterator = (
            self.manager
                .get_client()
                .resources
                .list_by_resource_group(group['name'])
        )
        return not any(True for _ in resources_iterator)
