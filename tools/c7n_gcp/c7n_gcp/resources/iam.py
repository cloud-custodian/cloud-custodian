# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re

from googleapiclient.errors import HttpError

from c7n.utils import local_session, type_schema
from c7n_gcp.filters.iampolicy import IamPolicyFilter
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo, ChildResourceManager, ChildTypeInfo
from c7n_gcp.actions import MethodAction
from c7n_gcp.filters.timerange import TimeRangeFilter


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
        urn_component = "project-role"
        urn_id_segments = (-1,)  # Just use the last segment of the id in the URN

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get',
                verb_arguments={
                    'name': 'projects/{}/roles/{}'.format(
                        resource_info['project_id'], resource_info['role_name'].rsplit('/', 1)[-1]
                    )
                },
            )


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
        metric_key = 'resource.labels.unique_id'
        urn_component = 'service-account'
        urn_id_path = 'email'

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get',
                verb_arguments={
                    'name': 'projects/{}/serviceAccounts/{}'.format(
                        resource_info['project_id'], resource_info['email_id']
                    )
                },
            )

        @staticmethod
        def get_metric_resource_name(resource, metric_key=None):
            return resource["uniqueId"]


@ServiceAccount.action_registry.register('delete')
class DeleteServiceAccount(MethodAction):
    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    permissions = ("iam.serviceAccounts.delete",)

    def get_resource_params(self, m, r):
        return {'name': r['name']}


@ServiceAccount.action_registry.register('enable')
class EnableServiceAccount(MethodAction):
    schema = type_schema('enable')
    method_spec = {'op': 'enable'}
    permissions = ("iam.serviceAccounts.enable",)

    def get_resource_params(self, m, r):
        return {'name': r['name']}


@ServiceAccount.action_registry.register('disable')
class DisableServiceAccount(MethodAction):
    schema = type_schema('disable')
    method_spec = {'op': 'disable'}
    permissions = ("iam.serviceAccounts.disable",)

    def get_resource_params(self, m, r):
        return {'name': r['name']}


@ServiceAccount.filter_registry.register('iam-policy')
class ServiceAccountIamPolicyFilter(IamPolicyFilter):
    """
    Overrides the base implementation to process service account resources correctly.
    """

    permissions = ('resourcemanager.projects.getIamPolicy',)


@resources.register('service-account-key')
class ServiceAccountKey(ChildResourceManager):
    """GCP Resource
    https://cloud.google.com/iam/docs/reference/rest/v1/projects.serviceAccounts.keys
    """

    def _get_parent_resource_info(self, child_instance):
        project_id, sa = re.match(
            'projects/(.*?)/serviceAccounts/(.*?)/keys/.*', child_instance['name']
        ).groups()
        return {'project_id': project_id, 'email_id': sa}

    def get_resource_query(self):
        """Does nothing as self does not need query values unlike its parent
        which receives them with the use_child_query flag."""
        pass

    class resource_type(ChildTypeInfo):
        service = 'iam'
        version = 'v1'
        component = 'projects.serviceAccounts.keys'
        enum_spec = ('list', 'keys[]', [])
        scope = None
        scope_key = 'name'
        name = id = 'name'
        default_report_fields = [
            'name',
            'privateKeyType',
            'keyAlgorithm',
            'validAfterTime',
            'validBeforeTime',
            'keyOrigin',
            'keyType',
        ]
        parent_spec = {
            'resource': 'service-account',
            'child_enum_params': [('name', 'name')],
            'use_child_query': True,
        }
        asset_type = "iam.googleapis.com/ServiceAccountKey"
        scc_type = "google.iam.ServiceAccountKey"
        permissions = ("iam.serviceAccounts.list",)
        metric_key = 'metric.labels.key_id'
        urn_component = "service-account-key"
        urn_id_segments = (3, 5)

        @staticmethod
        def get(client, resource_info):
            project, sa, key = re.match(
                '.*?/projects/(.*?)/serviceAccounts/(.*?)/keys/(.*)', resource_info['resourceName']
            ).groups()
            return client.execute_query(
                'get', {'name': 'projects/{}/serviceAccounts/{}/keys/{}'.format(project, sa, key)}
            )

        @staticmethod
        def get_metric_resource_name(resource, metric_key=None):
            return resource["name"].split('/')[-1]


@ServiceAccountKey.action_registry.register('delete')
class DeleteServiceAccountKey(MethodAction):
    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    permissions = ("iam.serviceAccountKeys.delete",)

    def get_resource_params(self, m, r):
        return {'name': r['name']}


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
        urn_component = "role"
        # Don't show the project ID in the URN.
        urn_has_project = False
        urn_id_segments = (-1,)  # Just use the last segment of the id in the URN

        @staticmethod
        def get(client, resource_info):
            return client.execute_command('get', {'name': 'roles/{}'.format(resource_info['name'])})


@Role.action_registry.register('delete')
class RoleDeleteAction(MethodAction):
    """Action to delete GCP custom roles

    Note: This action only works for custom roles. Predefined GCP roles cannot be deleted.

    It is recommended to use a filter to avoid unwanted deletion of IAM roles

    :example:

    .. code-block:: yaml

            policies:
              - name: gcp-delete-testing-org-roles
                resource: gcp.iam-role
                filters:
                  - type: value
                    key: name
                    op: regex
                    value: 'organizations/.*/roles/.*test.*'
                actions:
                  - type: delete
    """
    # Preface: The `roles` resources is a mutt. It returns a blend of:
    #
    # * pre-defined roles (GCP-defined, not allowed to delete)
    # * organization-wide roles
    # * project-specific roles (Already present in the `ProjectRole` resource above)
    #
    # In order to support deletes WITHOUT breaking the backward-compatibility
    # of this resource, we need to do detection of the roles that allow deletes.

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    permissions = ('iam.roles.delete',)

    def get_resource_params(self, m, r):
        return {'name': r['name']}

    def handle_resource_error(self, client, model, resource, op_name, params, error):
        self.log.error(f"Failed to call {op_name} with params: %s", params)
        self.log.exception(error)

    def is_organizational_role(self, role):
        return role.startswith("organizations/")

    def get_organizational_role_name(self, role):
        # Extract org ID: organizations/123456/roles/customRole
        match = re.match(r'organizations/([^/]+)/roles/(.+)', role)
        if not match:
            self.log.error(f"Invalid organization role name format: {role}")
            return None

        return match.groups()[1]

    def is_project_role(self, role):
        return role.startswith("projects/")

    def get_project_role_name(self, role):
        # Extract project ID: projects/my-project/roles/customRole
        match = re.match(r'projects/([^/]+)/roles/(.+)', role)
        if not match:
            self.log.error(f"Invalid project role name format: {role}")
            return None

        return match.groups()[1]

    def handle_role_delete(self, override_client, model, resource, role_name):
        """
        Deletes an individual role.
        """
        op_name = self.get_operation_name(model, resource)
        params = self.get_resource_params(model, resource)

        try:
            self.invoke_api(override_client, op_name, params)
            self.log.info(f"Deleted role: {role_name}")
        except HttpError as e:
            self.handle_resource_error(
                override_client, model, resource, op_name, params, e
            )

    def process_resource_set(self, client, model, resources):
        """Override to handle different role types with appropriate API components"""
        session = local_session(self.manager.session_factory)

        for resource in resources:
            full_role = resource['name']

            # Detect role type and get appropriate client
            if self.is_organizational_role(full_role):
                role_name = self.get_organizational_role_name(full_role)
                # Create client for organizations.roles component
                override_client = session.client('iam', 'v1', 'organizations.roles')
            elif self.is_project_role(full_role):
                role_name = self.get_project_role_name(full_role)
                # Create client for projects.roles component
                override_client = session.client('iam', 'v1', 'projects.roles')
            else:
                # Predefined role (roles/viewer, roles/editor, etc.)
                self.log.error(
                    f"Cannot delete predefined role: {full_role}. "
                    "Only organization and project custom roles can be deleted."
                )
                continue

            self.handle_role_delete(override_client, model, resource, role_name)


@resources.register('api-key')
class ApiKey(QueryResourceManager):
    """GCP API Key
    https://cloud.google.com/api-keys/docs/reference/rest/v2/projects.locations.keys#Key
    """

    class resource_type(TypeInfo):
        service = 'apikeys'
        version = 'v2'
        component = 'projects.locations.keys'
        enum_spec = ('list', 'keys[]', None)
        scope = 'project'
        scope_key = 'parent'
        scope_template = 'projects/{}/locations/global'
        name = id = "name"
        default_report_fields = ['name', 'displayName', 'createTime', 'updateTime']
        asset_type = "apikeys.googleapis.com/projects.locations.keys"


@ApiKey.filter_registry.register('time-range')
class ApiKeyTimeRangeFilter(TimeRangeFilter):
    """Filters api keys that have been changed during a specific time range.

    .. code-block:: yaml

        policies:
          - name: api_keys_not_rotated_more_than_90_days
            resource: gcp.api-key
            filters:
              - not:
                  - type: time-range
                    value: 90
    """

    create_time_field_name = 'createTime'
    expire_time_field_name = 'updateTime'
    permissions = ('apikeys.keys.list',)
