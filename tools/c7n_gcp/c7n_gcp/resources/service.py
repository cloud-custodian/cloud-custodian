# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo
from c7n.utils import type_schema, local_session


@resources.register('service')
class Service(QueryResourceManager):
    """GCP Service Management
    https://cloud.google.com/service-infrastructure/docs/service-management/reference/rest/v1/services
    """
    class resource_type(TypeInfo):
        service = 'servicemanagement'
        version = 'v1'
        component = 'services'
        enum_spec = ('list', 'services[]', None)
        scope = 'project'
        scope_key = 'consumerId'
        scope_template = 'project:{}'
        name = id = 'serviceName'
        default_report_fields = [name, "producerProjectId"]
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
           - serviceName: translate.googleapis.com
          actions:
           - disable
    """

    schema = type_schema('disable')
    method_spec = {'op': 'disable'}

    def get_resource_params(self, model, resource):
        session = local_session(self.manager.session_factory)
        return {'serviceName': resource['serviceName'],
                'body': {
                    'consumerId': 'project:{}'.format(
                        session.get_default_project())}}
