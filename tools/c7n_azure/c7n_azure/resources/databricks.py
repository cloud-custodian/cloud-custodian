# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n.filters import ValueFilter, ListItemFilter
from c7n.utils import type_schema


@resources.register('databricks')
class Databricks(ArmResourceManager):
    """Databricks Resource

    :example:

    Returns all databricks named my-test-databricks

    .. code-block:: yaml

        policies:
          - name: get-databricks
            resource: azure.databricks
            filters:
              - type: value
                key: name
                op: eq
                value: my-test-databricks

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['AI + Machine Learning']

        service = 'azure.mgmt.databricks'
        client = 'DatabricksClient'
        enum_spec = ('workspaces', 'list_by_subscription', None)
        default_report_fields = ('name', 'location', 'resourceGroup', 'sku.name')
        resource_type = 'Microsoft.Databricks/workspaces'


@Databricks.filter_registry.register('vnet')
class DatabricksNSGFilter(ValueFilter):
    """
    Databricks Vnet filter. Allows to filter Databricks resources based on their associated
    Virtual Network.
    """

    schema = type_schema('vnet', rinherit=ValueFilter.schema)
    annotation_key = 'c7n:Vnet'
    FetchThreshold = 5

    def process(self, resources, event=None):
        if not resources:
            return resources

        ids = set()
        for r in resources:
            if self.annotation_key in r:
                continue
            vid = (
                r['properties'].get('parameters', {}).get('customVirtualNetworkId', {}).get('value')
            )
            if vid:
                ids.add(vid)
        if not ids:
            return resources

        vnet = self.manager.get_resource_manager('azure.vnet')
        if len(ids) < self.FetchThreshold:
            mapping = {v['id']: v for v in vnet.get_resources(ids)}
        else:
            mapping = {v['id']: v for v in vnet.resources() if v['id'] in ids}

        for r in resources:
            if self.annotation_key in r:
                continue
            vid = (
                r['properties'].get('parameters', {}).get('customVirtualNetworkId', {}).get('value')
            )
            if vid and vid in mapping:
                r[self.annotation_key] = mapping[vid]
            else:
                r[self.annotation_key] = None

        return super().process(resources, event)

    def __call__(self, i):
        return super().__call__(i[self.annotation_key])


@Databricks.filter_registry.register('subnets')
class DatabricksSubnetsFilter(ListItemFilter):
    schema = type_schema(
        "subnets",
        attrs={"$ref": "#/definitions/filters_common/list_item_attrs"},
        count={"type": "number"},
        count_op={"$ref": "#/definitions/filters_common/comparison_operators"},
    )
    annotation_key = "c7n:Subnets"
    FetchThreshold = 5

    def process(self, resources, event=None):
        """
        Seems like each Databricks resource can have one public and one private subnet
        """
        if not resources:
            return resources
        names = set()

        for r in resources:
            if self.annotation_key in r:
                continue
            pub = (
                r['properties'].get('parameters', {}).get('customPublicSubnetName', {}).get('value')
            )
            if pub:
                names.add(pub)
            pr = (
                r['properties']
                .get('parameters', {})
                .get('customPrivateSubnetName', {})
                .get('value')
            )
            if pr:
                names.add(pr)
        if not names:
            return resources
        subnets = self.manager.get_resource_manager('azure.subnet')

        # TODO: use get_resources when number of names is small. For that we need to
        #  build ID from name; maybe add some generic function that tries its best
        #  to build valid resource id from name given resource type
        mapping = {
            subnet['name']: subnet for subnet in subnets.resources() if subnet['name'] in names
        }
        for r in resources:
            if self.annotation_key in r:
                continue
            pub = (
                r['properties'].get('parameters', {}).get('customPublicSubnetName', {}).get('value')
            )
            pr = (
                r['properties']
                .get('parameters', {})
                .get('customPrivateSubnetName', {})
                .get('value')
            )
            s = []
            if pub and pub in mapping:
                s.append(mapping[pub])
            if pr and pr in mapping:
                s.append(mapping[pr])
            r[self.annotation_key] = s
        return super().process(resources, event)

    def get_item_values(self, resource):
        return resource[self.annotation_key]
