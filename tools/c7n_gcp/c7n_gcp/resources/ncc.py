# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n.utils import type_schema


@resources.register('ncc-spoke')
class NCCSpoke(QueryResourceManager):
    """GCP Network Connectivity Center (NCC) Spoke

    https://cloud.google.com/network-connectivity/docs/reference/networkconnectivity/rest/v1/projects.locations.spokes
    """

    class resource_type(TypeInfo):
        service = 'networkconnectivity'
        version = 'v1'
        component = 'projects.locations.spokes'
        enum_spec = ('list', 'spokes[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = 'projects/{}/locations/-'
        name = id = 'name'
        default_report_fields = ['name', 'state', 'hub', 'uniqueId', 'createTime']
        asset_type = 'networkconnectivity.googleapis.com/Spoke'
        urn_component = 'ncc-spoke'
        permissions = ('networkconnectivity.spokes.list',)

        @staticmethod
        def get(client, resource_info):
            return client.execute_query('get', verb_arguments={'name': resource_info['name']})


@NCCSpoke.action_registry.register('delete')
class DeleteNCCSpoke(MethodAction):
    """Delete an NCC Spoke.

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-inactive-ncc-spokes
            resource: gcp.ncc-spoke
            filters:
              - type: value
                key: state
                value: INACTIVE
            actions:
              - type: delete
    """

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    permissions = ('networkconnectivity.spokes.delete',)

    def get_resource_params(self, model, resource):
        return {'name': resource['name']}
