# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re

from googleapiclient.errors import HttpError

from c7n.exceptions import PolicyExecutionError
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
        metric_key = 'resource.labels.unique_id'
        urn_component = 'service-account'
        urn_id_path = 'email'

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', verb_arguments={
                    'name': 'projects/{}/serviceAccounts/{}'.format(
                        resource_info['project_id'],
                        resource_info['email_id'])})

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
            'projects/(.*?)/serviceAccounts/(.*?)/keys/.*',
            child_instance['name']).groups()
        return {'project_id': project_id,
                'email_id': sa}

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
        default_report_fields = ['name', 'privateKeyType', 'keyAlgorithm',
          'validAfterTime', 'validBeforeTime', 'keyOrigin', 'keyType']
        parent_spec = {
            'resource': 'service-account',
            'child_enum_params': [
                ('name', 'name')
            ],
            'use_child_query': True
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
                '.*?/projects/(.*?)/serviceAccounts/(.*?)/keys/(.*)',
                resource_info['resourceName']).groups()
            return client.execute_query(
                'get', {
                    'name': 'projects/{}/serviceAccounts/{}/keys/{}'.format(
                        project, sa, key)})

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
            return client.execute_command(
                'get', {
                    'name': 'roles/{}'.format(
                        resource_info['name'])})


@Role.action_registry.register('delete')
class RoleDeleteAction(MethodAction):
    """Action to delete GCP custom roles

    Note: This action only works for custom roles. Predefined GCP roles are
    implicitly filtered out, as they cannot be deleted.

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

    # The `iam-role` resource is a blend of:
    #
    # * pre-defined roles (GCP-defined, not allowed to delete)
    # * organization-wide roles
    # * project-specific roles (also available via the `project-role` resource)
    #
    # Organization & project roles are deleted through different API components,
    # so the resources are split up by role type before processing.

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    permissions = ('iam.roles.delete',)
    role_components = {
        'organizations': 'organizations.roles',
        'projects': 'projects.roles',
    }

    def get_resource_params(self, model, resource):
        return {'name': resource['name']}

    def filter_resources(self, resources):
        """Drop predefined roles (`roles/...`), which can't be deleted."""
        rcount = len(resources)
        resources = [r for r in resources if r['name'].partition('/')[0] in self.role_components]
        if len(resources) != rcount:
            self.log.warning(
                "policy:%s action:%s implicitly filtered %d resources to %d "
                "(only custom organization & project roles can be deleted)",
                self.manager.ctx.policy.name,
                self.type,
                rcount,
                len(resources),
            )
        return resources

    def process(self, resources):
        resources = self.filter_resources(resources)
        model = self.manager.get_model()
        session = local_session(self.manager.session_factory)

        roles_by_type = {}
        for r in resources:
            roles_by_type.setdefault(r['name'].partition('/')[0], []).append(r)

        errors = []
        for role_type, component in self.role_components.items():
            if not roles_by_type.get(role_type):
                continue
            client = session.client('iam', 'v1', component)
            errors.extend(self.process_resource_set(client, model, roles_by_type[role_type]))

        if errors:
            raise PolicyExecutionError(
                "failed to delete %d role(s): %s" % (
                    len(errors), "; ".join("%s: %s" % err for err in errors)))

    def process_resource_set(self, client, model, resources):
        """Attempt every role, returning (name, error) pairs for any failures."""
        errors = []
        for resource in resources:
            try:
                super().process_resource_set(client, model, [resource])
            except HttpError as e:
                self.log.error("Failed to delete role %s: %s", resource['name'], e)
                errors.append((resource['name'], e))
        return errors


ProjectRole.action_registry.register('delete', RoleDeleteAction)


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

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'name': resource_info['resourceName']})


@ApiKey.action_registry.register('delete')
class ApiKeyDelete(MethodAction):
    """Delete a GCP API key.

    .. code-block:: yaml

        policies:
          - name: delete-unused-api-keys
            resource: gcp.api-key
            filters:
              - type: time-range
                value: 90
            actions:
              - delete
    """

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    permissions = ('apikeys.keys.delete',)

    def get_resource_params(self, m, r):
        return {'name': r['name']}


@ApiKey.action_registry.register('patch')
class ApiKeyPatch(MethodAction):
    """Patch mutable fields on a GCP API key.

    Supports updating any combination of ``displayName``, ``restrictions``,
    and ``annotations``.  At least one field must be provided.

    The ``restrictions`` object accepts an optional ``apiTargets`` list and
    exactly one of the following client restriction types:

    - ``browserKeyRestrictions`` – ``allowedReferrers[]``
    - ``serverKeyRestrictions`` – ``allowedIps[]``
    - ``androidKeyRestrictions`` – ``allowedApplications[]``
    - ``iosKeyRestrictions`` – ``allowedBundleIds[]``

    .. code-block:: yaml

        policies:
          - name: restrict-unrestricted-api-keys
            resource: gcp.api-key
            filters:
              - type: value
                key: restrictions
                value: absent
            actions:
              - type: patch
                restrictions:
                  serverKeyRestrictions:
                    allowedIps:
                      - 192.0.2.0/24
                  apiTargets:
                    - service: translate.googleapis.com
                annotations:
                  custodian-remediated: "true"
    """

    MUTABLE_FIELDS = ('displayName', 'restrictions', 'annotations')

    schema = type_schema(
        'patch',
        displayName={'type': 'string'},
        restrictions={'type': 'object'},
        annotations={'type': 'object'},
    )
    method_spec = {'op': 'patch'}
    method_perm = 'update'
    permissions = ('apikeys.keys.update',)

    def validate(self):
        if not set(self.MUTABLE_FIELDS).intersection(self.data):
            raise ValueError(
                "patch action requires at least one of: {}".format(
                    ', '.join(self.MUTABLE_FIELDS)))
        return super().validate()

    def get_resource_params(self, m, r):
        body = {f: self.data[f] for f in self.MUTABLE_FIELDS if f in self.data}
        return {
            'name': r['name'],
            'updateMask': ','.join(body.keys()),
            'body': body,
        }


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
    permissions = ('apikeys.keys.list', )
