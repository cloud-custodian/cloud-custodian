# Copyright 2018-2019 Capital One Services, LLC
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

from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('project-role')
class ProjectRole(QueryResourceManager):
    """GCP Project Role
    https://cloud.google.com/iam/docs/reference/rest/v1/organizations.roles#Role
    """
    class resource_type(TypeInfo):
        service = 'iam'
        version = 'v1'
        component = 'projects.roles'
        enum_spec = ('list', 'roles[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = 'projects/{}'
        name = id = "name"
        default_report_fields = ['name', 'title', 'description', 'stage', 'deleted']
        asset_type = "iam.googleapis.com/Role"

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', verb_arguments={
                    'name': 'projects/{}/roles/{}'.format(
                        resource_info['project_id'],
                        resource_info['role_name'].rsplit('/', 1)[-1])})


@resources.register('service-account')
class ServiceAccount(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'iam'
        version = 'v1'
        component = 'projects.serviceAccounts'
        enum_spec = ('list', 'accounts[]', [])
        scope = 'project'
        scope_key = 'name'
        scope_template = 'projects/{}'
        id = "name"
        name = 'email'
        default_report_fields = ['name', 'displayName', 'email', 'description', 'disabled']
        asset_type = "iam.googleapis.com/ServiceAccount"

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', verb_arguments={
                    'name': 'projects/{}/serviceAccounts/{}'.format(
                        resource_info['project_id'],
                        resource_info['email_id'])})


@resources.register('iam-role')
class Role(QueryResourceManager):
    """GCP Organization Role
    https://cloud.google.com/iam/docs/reference/rest/v1/organizations.roles#Role
    """
    class resource_type(TypeInfo):
        service = 'iam'
        version = 'v1'
        component = 'roles'
        enum_spec = ('list', 'roles[]', None)
        scope = "global"
        name = id = "name"
        default_report_fields = ['name', 'title', 'description', 'stage', 'deleted']
        asset_type = "iam.googleapis.com/Role"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {
                    'name': 'roles/{}'.format(
                        resource_info['name'])})
