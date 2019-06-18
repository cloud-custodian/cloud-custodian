# Copyright 2019 Capital One Services, LLC
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
from c7n.exceptions import PolicyValidationError
from c7n.utils import type_schema
from c7n_gcp.actions import MethodAction
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildTypeInfo, ChildResourceManager


@resources.register('spanner-instance')
class SpannerInstance(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'spanner'
        version = 'v1'
        component = 'projects.instances'
        enum_spec = ('list', 'instances[]', None)
        scope_key = 'parent'
        scope_template = 'projects/{}'
        id = 'name'

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'name': resource_info['resourceName']}
            )


class SpannerInstanceAction(MethodAction):

    def get_resource_params(self, model, resource):
        return {'name': resource['name']}


@SpannerInstance.action_registry.register('delete')
class SpannerInstanceDelete(SpannerInstanceAction):
    """The action is used for spanner instances delete.
    GCP resource is https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances.
    GCP action is https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances/delete

    Example:

    .. code-block:: yaml
        policies:
        - name: gcp-spanner-instances-delete
          resource: gcp.spanner-instance
          filters:
          - type: value
            key: nodeCount
            op: gte
            value: 2
          actions:
          - type: delete
    """
    schema = type_schema('delete')
    method_spec = {'op': 'delete'}


@SpannerInstance.action_registry.register('patch')
class SpannerInstancePatch(SpannerInstanceAction):
    """The action is used for spanner instances patch. Values from following fields can be updated
    - config,
    - displayName,
    - nodeCount,
    - labels.

    GCP resource is https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances.
    GCP action is https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances/patch

    Example:

    .. code-block:: yaml
        policies:
        - name: gcp-spanner-instances-patch
          resource: gcp.spanner-instance
          filters:
            - type: value
              key: nodeCount
              op: gte
              value: 2
          actions:
          - type: patch
            nodeCount: 1
    """
    schema = type_schema('patch', required=['nodeCount'],
                         **{'nodeCount': 'number'})
    method_spec = {'op': 'patch'}

    FIELDS_TO_UPDATE = ['config', 'displayName', 'nodeCount', 'labels']

    def validate(self):
        valid = False
        for field in self.data.keys():
            if field in self.FIELDS_TO_UPDATE:
                valid = True
                break

        if not valid:
            raise PolicyValidationError("Nothing to update")

    def get_resource_params(self, model, resource):
        result = super(SpannerInstancePatch, self).get_resource_params(model, resource)
        field_mask = []
        result['body'] = {}
        result['body']['instance'] = {}
        for field in self.data.keys():
            if field in self.FIELDS_TO_UPDATE:
                field_mask.append(field)
                result['body']['instance'][field] = self.data[field]

        result['body']['field_mask'] = ', '.join([x for x in field_mask])
        return result


@SpannerInstance.action_registry.register('set-iam-policy')
class SpannerInstanceSetIamPolicy(SpannerInstanceAction):
    """Sets IAM policy. It works with bindings only.

    GCP resource is https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances.
    GCP action is
    https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances/setIamPolicy.

    Example:

    .. code-block:: yaml

        policies:
        - name: gcp-spanner-instances-set-iam-policy
          resource: gcp.spanner-instance
          actions:
          - type: set-iam-policy
            bindings:
            - members:
              - user:user1@test.com
              - user2@test.com
              role:roles/owner
            - members:
              - user:user3@gmail.com
              role:roles/viewer
    """
    schema = type_schema('setIamPolicy',
        required=['bindings'],
        **{
            'bindings': {
                'type': 'array',
                'items': {'role': {'type': 'string'}, 'members': {'type': 'array'}}
            }
        })
    method_spec = {'op': 'setIamPolicy'}

    MEMBER_TYPES = ['user', 'group', 'domain', 'serviceAccount']

    def get_resource_params(self, model, resource):
        result = {'resource': resource['name'],
                  'body': {
                      'policy': {
                          'bindings': []
                      }}
                  }
        bindings = result['body']['policy']['bindings']

        if self.data['bindings'] is not None:
            for binding in self.data['bindings']:
                if binding['role'] and binding['members']:
                    members = []
                    for member in binding['members']:
                        requires_update = True
                        for member_type in self.MEMBER_TYPES:
                            if member.startswith(member_type + ':'):
                                requires_update = False
                                break
                        if requires_update:
                            member = 'user:' + member
                        members.append(member)
                    bindings.append({'role': binding['role'], 'members': members})

        return result


@resources.register('spanner-database-instance')
class SpannerDatabaseInstance(ChildResourceManager):
    """GCP resource:
    https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances.databases
    """
    def _get_parent_resource_info(self, child_instance):
        resource_name = None
        if child_instance['name'] is not None:
            resource_names = child_instance['name'].split('/databases')
            if len(resource_names) > 0:
                resource_name = resource_names[0]
        return {
            'resourceName': resource_name
        }

    class resource_type(ChildTypeInfo):
        service = 'spanner'
        version = 'v1'
        component = 'projects.instances.databases'
        enum_spec = ('list', 'databases[]', None)
        id = 'name'
        scope = None
        parent_spec = {
            'resource': 'spanner-instance',
            'child_enum_params': [
                ('name', 'parent')
            ]
        }

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {
                    'name': resource_info['resourceName']}
            )


@SpannerDatabaseInstance.action_registry.register('set-iam-policy')
class SpannerDatabaseInstanceSetIamPolicy(SpannerInstanceAction):
    """Sets IAM policy. It works with bindings only.

    GCP resource is
    https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances.databases.
    GCP action is
https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances.databases/setIamPolicy.

    Example:

    .. code-block:: yaml

        policies:
        - name: gcp-spanner-database-instances-set-iam-policy
          resource: gcp.spanner-database-instance
          actions:
          - type: set-iam-policy
            bindings:
            - members:
              - user:user1@test.com
              - user2@test.com
              role:roles/owner
            - members:
              - user:user3@gmail.com
              role:roles/viewer
    """

    schema = type_schema('setIamPolicy',
                         required=['bindings'],
                         **{
                             'bindings': {
                                 'type': 'array',
                                 'items': {'role': {'type': 'string'}, 'members': {'type': 'array'}}
                             }
                         }
                         )
    method_spec = {'op': 'setIamPolicy'}

    MEMBER_TYPES = ['user', 'group', 'domain', 'serviceAccount']

    def get_resource_params(self, model, resource):
        result = {'resource': resource['name'],
                  'body': {
                      'policy': {
                          'bindings': []
                      }}
                  }
        bindings = result['body']['policy']['bindings']

        if self.data['bindings'] is not None:
            for binding in self.data['bindings']:
                if binding['role'] and binding['members']:
                    members = []
                    for member in binding['members']:
                        requires_update = True
                        for member_type in self.MEMBER_TYPES:
                            if member.startswith(member_type + ':'):
                                requires_update = False
                                break
                        if requires_update:
                            member = 'user:' + member
                        members.append(member)
                    bindings.append({'role': binding['role'], 'members': members})
        return result


@SpannerDatabaseInstance.action_registry.register('delete')
class SpannerDatabaseInstanceDropDatabase(SpannerInstanceAction):
    """The action is used for databases deleting.
    GCP resource is
    https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances.databases.
    GCP action is
https://cloud.google.com/spanner/docs/reference/rest/v1/projects.instances.databases/dropDatabase.

    Example:

    .. code-block:: yaml

        policies:
        - name: gcp-spanner-instance-databases-delete
          resource: gcp.spanner-database-instance
          filters:
            - type: value
              key: name
              op: contains
              value: dev
          actions:
          - type: delete
    """
    schema = type_schema('dropDatabase')
    method_spec = {'op': 'dropDatabase'}

    def get_resource_params(self, model, resource):
        return {'database': resource['name']}
