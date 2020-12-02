# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n.utils import type_schema


@resources.register('service')
class Service(QueryResourceManager):
    """GCP Service Usage Management

    https://cloud.google.com/service-usage/docs/reference/rest
    https://cloud.google.com/service-infrastructure/docs/service-management/reference/rest/v1/services
    """
    class resource_type(TypeInfo):
        service = 'serviceusage'
        version = 'v1'
        component = 'services'
        enum_spec = ('list', 'services[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = 'projects/{}'
        name = id = 'name'
        default_report_fields = [name, "state"]
        asset_type = 'serviceusage.googleapis.com/Service'

        @staticmethod
        def get(client, resource_info):
            serviceName = resource_info['resourceName'].rsplit('/', 1)[-1][1:-1]
            return {'serviceName': serviceName}


@Service.action_registry.register('disable')
class Disable(MethodAction):
    """Disable a service for the current project

    Example::

      policies:
        - name: disable-disallowed-services
          resource: gcp.service
          mode:
            type: gcp-audit
            methods:
             - google.api.servicemanagement.v1.ServiceManagerV1.ActivateServices
          filters:
           - config.name: translate.googleapis.com
          actions:
           - disable
    """

    schema = type_schema(
        'disable',
        dependents={'type': 'boolean', 'default': False},
        usage={'enum': ['SKIP', 'CHECK']})

    method_spec = {'op': 'disable'}
    method_perm = 'update'

    def get_resource_params(self, model, resource):
        return {'name': resource['name'],
                'body': {
                    'disableDependentServices': self.data.get('dependents', False),
                    'checkIfServiceHasUsage': self.data.get(
                        'usage', 'CHECK_IF_SERVICE_HAS_USAGE_UNSPECIFIED')}}
