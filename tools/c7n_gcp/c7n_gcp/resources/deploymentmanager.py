# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re

from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo

from c7n.utils import type_schema


@resources.register('dm-deployment')
class DMDeployment(QueryResourceManager):
    """GCP resource: https://cloud.google.com/deployment-manager/docs/reference/latest/deployments
    """
    class resource_type(TypeInfo):
        service = 'deploymentmanager'
        version = 'v2'
        component = 'deployments'
        enum_spec = ('list', 'deployments[]', None)
        name = id = 'name'

        default_report_fields = ['name', 'description', 'insertTime', 'updateTime']

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project_id'],
                        'deployment': resource_info['name']})


@DMDeployment.action_registry.register('delete')
class DeleteInstanceGroupManager(MethodAction):
    """Deletes a deployment

    :Example:

    .. code-block:: yaml

        policies:
          - name: delete-deployments
            description: Delete all deployments
            resource: gcp.dm-deployment
            filters:
              - type: value
                key: name
                op: eq
                value: test-deployment
            actions:
              - delete

    https://cloud.google.com/deployment-manager/docs/reference/latest/deployments/delete
    """

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    path_param_re = re.compile('.*?/projects/(.*?)/global/deployments/(.*)')

    def get_resource_params(self, m, r):
        project, name = self.path_param_re.match(r['selfLink']).groups()
        return {'project': project, 'deployment': name}
