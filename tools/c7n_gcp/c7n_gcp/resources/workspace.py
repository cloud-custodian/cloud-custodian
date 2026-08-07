# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

# The relationship between GCP and Google Workspace is genuinely confusing.
# See:
#
# docs/source/gcp/examples/workspace-user-mfa.rst

from c7n_gcp.client import get_workspace_customer
from c7n_gcp.provider import resources
from c7n_gcp.query import QueryResourceManager, TypeInfo


@resources.register('workspace-user')
class WorkspaceUser(QueryResourceManager):
    """Google Workspace user.

    Users live in Cloud Identity / Google Workspace rather than in GCP, so
    reading them needs its own setup: see :ref:`gcp_workspace_users` for what
    to configure and why.

    https://developers.google.com/admin-sdk/directory/reference/rest/v1/users/list

    :example:

    Users that have not enrolled in 2 step verification, Google's term for
    MFA (CIS-B-GCPF-4.0.0-1.2). Suspended users can't sign in, so they are
    excluded.

    .. code-block:: yaml

        policies:
          - name: gcp-workspace-users-without-mfa
            resource: gcp.workspace-user
            filters:
              - type: value
                key: isEnrolledIn2Sv
                value: false
              - type: value
                key: suspended
                value: false
    """

    def get_resource_query(self):
        return {'customer': get_workspace_customer()}

    class resource_type(TypeInfo):
        service = 'admin'
        version = 'directory_v1'
        component = 'users'
        enum_spec = ('list', 'users[]', None)
        # Customer scoped, so no project is injected into the query.
        scope = None
        scopes = (
            'https://www.googleapis.com/auth/admin.directory.user.readonly',)
        id = 'id'
        name = 'primaryEmail'
        default_report_fields = [
            'primaryEmail', 'isAdmin', 'isEnrolledIn2Sv', 'isEnforcedIn2Sv',
            'suspended', 'orgUnitPath', 'lastLoginTime']
        urn_component = 'workspace-user'
        # Workspace users do not live under a GCP project.
        urn_has_project = False
