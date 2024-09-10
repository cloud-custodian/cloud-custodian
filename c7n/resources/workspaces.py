# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import functools
import itertools

from c7n.actions import BaseAction
from c7n.filters import ValueFilter
from c7n.filters.kms import KmsRelatedFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, ConfigSource
from c7n.tags import universal_augment, Tag, RemoveTag
from c7n.exceptions import PolicyValidationError, PolicyExecutionError
from c7n.utils import get_retry, local_session, type_schema, chunks, jmespath_search
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.resolver import ValuesFrom
import c7n.filters.vpc as net_filters
import json


class DescribeWorkspace(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, resources)


@resources.register('workspaces')
class Workspace(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'workspaces'
        enum_spec = ('describe_workspaces', 'Workspaces', None)
        arn_type = 'workspace'
        name = id = dimension = 'WorkspaceId'
        universal_taggable = True
        cfn_type = config_type = 'AWS::WorkSpaces::Workspace'
        permissions_augment = ("workspaces:DescribeTags",)

    source_mapping = {
        'describe': DescribeWorkspace,
        'config': ConfigSource
    }


@Workspace.filter_registry.register('connection-status')
class WorkspaceConnectionStatusFilter(ValueFilter):
    """Filter Workspaces based on user connection information

    :example:

    .. code-block:: yaml

            policies:

              - name: workspaces-abandoned
                resource: workspaces
                filters:
                  - type: connection-status
                    value_type: age
                    key: LastKnownUserConnectionTimestamp
                    op: ge
                    value: 90

              - name: workspaces-expensive-zombies
                resource: workspaces
                filters:
                  - "WorkspaceProperties.RunningMode": ALWAYS_ON
                  - type: connection-status
                    value_type: age
                    key: LastKnownUserConnectionTimestamp
                    op: ge
                    value: 30
    """

    schema = type_schema('connection-status', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('workspaces:DescribeWorkspacesConnectionStatus',)
    annotation_key = 'c7n:ConnectionStatus'

    def get_connection_status(self, client, workspace_ids):
        connection_status_chunk = self.manager.retry(
            client.describe_workspaces_connection_status,
            WorkspaceIds=workspace_ids
        )['WorkspacesConnectionStatus']

        return connection_status_chunk

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('workspaces')
        unannotated = {r['WorkspaceId']: r for r in resources if self.annotation_key not in r}
        status_map = {}
        with self.executor_factory(max_workers=2) as w:
            self.log.debug(
                'Querying connection status for %d workspaces' % len(unannotated))
            for status in itertools.chain(*w.map(
                functools.partial(self.get_connection_status, client),
                chunks(unannotated.keys(), 25)
            )):
                status_map[status['WorkspaceId']] = status

        # Note: In some cases (e.g. workspaces that just launched or reached ERROR state during
        # initialization) there will be no connection status information. Here we'll make
        # sure that every workspace gets _some_ status annotation, even if it's empty.
        for ws_id, r in unannotated.items():
            r[self.annotation_key] = status_map.get(ws_id, {})

        return list(filter(self, resources))

    def get_resource_value(self, k, i):
        return super(WorkspaceConnectionStatusFilter, self).get_resource_value(
            k, i[self.annotation_key])


@Workspace.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):

    RelatedIdsExpression = 'VolumeEncryptionKey'


@Workspace.action_registry.register('terminate')
class TerminateWorkspace(BaseAction):
    """
    Terminates a Workspace

    :example:

    .. code-block:: yaml

      policies:
        - name: delete-workspace
          resource: workspaces
          filters:
            - "tag:DeleteMe": present
          actions:
            - terminate
    """

    schema = type_schema('terminate')
    permissions = ('workspaces:TerminateWorkspaces',)
    valid_origin_states = (
        'PENDING',
        'AVAILABLE',
        'IMPAIRED',
        'UNHEALTHY',
        'REBOOTING',
        'STARTING',
        'REBUILDING',
        'RESTORING',
        'MAINTENANCE',
        'ADMIN_MAINTENANCE',
        'UPDATING',
        'STOPPING',
        'STOPPED',
        'ERROR'
    )

    def process(self, resources):

        resources = self.filter_resources(resources, 'State', self.valid_origin_states)
        client = local_session(self.manager.session_factory).client('workspaces')

        for resource_set in chunks(resources, size=25):
            ids = [{'WorkspaceId': w['WorkspaceId']} for w in resource_set]
            client.terminate_workspaces(TerminateWorkspaceRequests=ids)


@resources.register('workspaces-image')
class WorkspaceImage(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'workspaces'
        enum_spec = ('describe_workspace_images', 'Images', None)
        arn_type = 'workspaceimage'
        name = id = 'ImageId'
        universal_taggable = True
        permissions_augment = ("workspaces:DescribeTags",)

    augment = universal_augment


@WorkspaceImage.filter_registry.register('cross-account')
class WorkspaceImageCrossAccount(CrossAccountAccessFilter):

    schema = type_schema(
        'cross-account',
        # white list accounts
        whitelist_from=ValuesFrom.schema,
        whitelist={'type': 'array', 'items': {'type': 'string'}})

    permissions = ('workspaces:DescribeWorkspaceImagePermissions',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('workspaces')
        allowed_accounts = set(self.get_accounts())
        results = []
        for r in resources:
            found = False
            try:
                accts = client.describe_workspace_image_permissions(
                    ImageId=r['ImageId']).get('ImagePermissions')
                for a in accts:
                    account_id = a['SharedAccountId']
                    if (account_id not in allowed_accounts):
                        r.setdefault('c7n:CrossAccountViolations', []).append(account_id)
                        found = True
                if found:
                    results.append(r)
            except client.exceptions.ResourceNotFoundException:
                continue

        return results


@WorkspaceImage.action_registry.register('delete')
class DeleteWorkspaceImage(BaseAction):
    """
    Deletes a Workspace Image

    :example:

    .. code-block:: yaml

      policies:
        - name: delete-workspace-img
          resource: workspaces-image
          filters:
            - "tag:DeleteMe": present
          actions:
            - delete
    """

    schema = type_schema('delete')
    permissions = ('workspaces:DeleteWorkspaceImage',)
    valid_origin_states = ('AVAILABLE', 'ERROR',)

    def process(self, resources):

        resources = self.filter_resources(resources, 'State', self.valid_origin_states)
        client = local_session(self.manager.session_factory).client('workspaces')
        for r in resources:
            try:
                client.delete_workspace_image(ImageId=r['ImageId'])
            except client.exceptions.InvalidResourceStateException as e:
                self.log.error(f"Error deleting workspace image: {r['ImageId']} error: {e}")
                continue
            except client.exceptions.ResourceAssociatedException as e:
                self.log.error(f"Error deleting workspace image: {r['ImageId']} error: {e}")
                continue
            except client.exceptions.ResourceNotFoundException:
                continue


@resources.register('workspaces-directory')
class WorkspaceDirectory(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'workspaces'
        enum_spec = ('describe_workspace_directories', 'Directories', None)
        arn_type = 'directory'
        id = 'DirectoryId'
        name = 'DirectoryName'
        universal_taggable = True

    augment = universal_augment


@WorkspaceDirectory.filter_registry.register('security-group')
class WorkspacesDirectorySG(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = ""
    expressions = ("WorkspaceSecurityGroupId", "WorkspaceCreationProperties.CustomSecurityGroupId")

    def get_related_ids(self, resources):
        sg_ids = set()
        for r in resources:
            for exp in self.expressions:
                id = jmespath_search(exp, r)
                if id:
                    sg_ids.add(id)
        return list(sg_ids)


@WorkspaceDirectory.filter_registry.register('subnet')
class WorkSpacesDirectorySg(net_filters.SubnetFilter):

    RelatedIdsExpression = "SubnetIds[]"


@WorkspaceDirectory.filter_registry.register('connection-aliases')
class WorkspacesDirectoryConnectionAliases(ValueFilter):
    """Filter workspace directories based on connection aliases

    :example:

    .. code-block:: yaml

       policies:
         - name: workspace-connection-alias
           resource: aws.workspaces-directory
           filters:
            - type: connection-aliases
              key: 'ConnectionAliases'
              value: 'empty'

    """

    permissions = ('workspaces:DescribeConnectionAliases',)

    schema = type_schema('connection-aliases', rinherit=ValueFilter.schema)
    annotation_key = 'c7n:ConnectionAliases'

    def process(self, directories, event=None):
        client = local_session(self.manager.session_factory).client('workspaces')
        results = []

        for directory in directories:
            if self.annotation_key not in directory:
                connection_aliases = client.describe_connection_aliases(
                    ResourceId=directory['DirectoryId'])
                directory[self.annotation_key] = connection_aliases

            if self.match(directory[self.annotation_key]):
                results.append(directory)

        return results


@WorkspaceDirectory.filter_registry.register('client-properties')
class WorkspacesDirectoryClientProperties(ValueFilter):
    """Filter workspace directories based off workspace client properties.

    :example:

    .. code-block:: yaml

       policies:
         - name: workspace-client-credentials
           resource: aws.workspaces-directory
           filters:
            - type: client-properties
              key: ReconnectEnabled
              value: ENABLED

    """
    permissions = ('workspaces:DescribeClientProperties',)

    schema = type_schema('client-properties', rinherit=ValueFilter.schema)
    annotation_key = 'c7n:client-properties'

    def process(self, directories, event=None):
        client = local_session(self.manager.session_factory).client('workspaces')
        results = []
        for directory in directories:
            if self.annotation_key not in directory:
                try:
                    client_properties = client.describe_client_properties(
                        ResourceIds=[directory['DirectoryId']]).get(
                            'ClientPropertiesList')[0].get('ClientProperties')
                except client.exceptions.ResourceNotFoundException:
                    continue
                directory[self.annotation_key] = client_properties

            if self.match(directory[self.annotation_key]):
                results.append(directory)
        return results


@WorkspaceDirectory.action_registry.register('modify-client-properties')
class ModifyClientProperties(BaseAction):
    """Action to enable/disable credential caching for Workspaces client.

    :example:

    .. code-block:: yaml

            policies:
              - name: workspace-directories-credentials-cache
                resource: aws.workspaces-directory
                filters:
                  - type: client-properties
                    key: ReconnectEnabled
                    value: ENABLED
                actions:
                  - type: modify-client-properties
                    attributes:
                      ClientProperties:
                        ReconnectEnabled: DISABLED

    """
    schema = type_schema(
        'modify-client-properties',
        required=['attributes'],
        attributes={
            'type': 'object',
            'additionalProperties': False,
            'properties': {
                'ClientProperties': {
                    'type': 'object',
                    'additionalProperties': False,
                    'required': ['ReconnectEnabled'],
                    'properties': {
                        'ReconnectEnabled': {'enum': ['DISABLED', 'ENABLED']}
                    }
                }
            }})

    permissions = ('workspaces:ModifyClientProperties',)

    def validate(self):
        for f in self.manager.iter_filters():
            if isinstance(f, WorkspacesDirectoryClientProperties):
                return self
        raise PolicyValidationError(
            '`modify-client-properties` may only be used in '
            'conjunction with `client-properties` filter on %s' % (self.manager.data,))

    def process(self, directories):
        client = local_session(self.manager.session_factory).client('workspaces')
        for directory in directories:
            try:
                client.modify_client_properties(
                    ResourceId=directory['DirectoryId'], **self.data['attributes'])
            except client.exceptions.ResourceNotFoundException:
                continue


@WorkspaceDirectory.action_registry.register('deregister')
class DeregisterWorkspaceDirectory(BaseAction):
    """
    Deregisters a workspace

    :example:

    .. code-block:: yaml

      policies:
        - name: deregister-workspace
          resource: aws.workspaces-directory
          filters:
            - "tag:Deregister": present
          actions:
            - deregister
    """

    schema = type_schema('deregister')
    permissions = ('workspaces:DeregisterWorkspaceDirectory',)

    def process(self, directories):
        exceptions = []
        retry = get_retry(('InvalidResourceStateException',))
        client = local_session(self.manager.session_factory).client('workspaces')
        for d in directories:
            try:
                retry(client.deregister_workspace_directory, DirectoryId=d['DirectoryId'],
                    ignore_err_codes=('ResourceNotFoundException',))
            except client.exceptions.OperationNotSupportedException as e:
                self.log.error(f"Error deregistering workspace: {d['DirectoryId']} error: {e}")
                exceptions.append(d['DirectoryId'])

        if exceptions:
            raise PolicyExecutionError(
                'The following directories must be removed from WorkSpaces'
                'and cannot be deregistered: %s ' % ''.join(map(str, exceptions))
            )


@resources.register('workspaces-web')
class WorkspacesWeb(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'workspaces-web'
        enum_spec = ('list_portals', 'portals', None)
        arn_type = 'portal'
        name = 'displayName'
        arn = id = "portalArn"

    augment = universal_augment


@WorkspacesWeb.filter_registry.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):
    """Filters Workspaces Secure Browsers based on their associated subnet

    :example:

    .. code-block:: yaml

            policies:
              - name: workspaces-web-in-subnet-x
                resource: workspaces-web
                filters:
                  - type: subnet
                    key: SubnetId
                    value: subnet-068dfbf3f275a6ae8
    """
    RelatedIdsExpression = ""

    def get_permissions(self):
        perms = super().get_permissions()
        perms.append('workspaces-web:GetNetworkSettings')
        return perms

    def get_related_ids(self, resources):
        subnetIds = set()

        for r in resources:
            if 'networkSettings' in r:
                for s in r['networkSettings']['subnetIds']:
                    subnetIds.add(s)
        return subnetIds

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('workspaces-web')

        for r in resources:
            if 'networkSettingsArn' in r:
                r['networkSettings'] = client.get_network_settings(
                    networkSettingsArn=r['networkSettingsArn']
                    ).get('networkSettings', {}
                )
        return super().process(resources, event)


@WorkspacesWeb.filter_registry.register('browser-policy')
class BrowerPolicyFilter(ValueFilter):
    """
    Applies value type filter on the browser policy of a workspaces secured browser.
    :example:

    .. code-block:: yaml

            policies:
              - name: browser-policy-match
                resource: workspaces-web
                filters:
                  - type: browser-policy
                    key: chromePolicies.AllowDeletingBrowserHistory.value
                    op: eq
                    value: false
    """

    schema = type_schema('browser-policy', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('workspaces-web:GetBrowserSettings',)
    matched_policy_annotation = 'c7n:BrowerPolicyMatches'
    policy_annotation = "c7n:BrowserPolicy"

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('workspaces-web')
        results = []
        for r in resources:
            if self.policy_annotation not in r:
                browserSettings = self.manager.retry(
                    client.get_browser_settings,
                    browserSettingsArn=r['browserSettingsArn']).get('browserSettings')
                browserPolicy = json.loads(browserSettings['browserPolicy'])
                r[self.policy_annotation] = browserPolicy
            if self.match(r[self.policy_annotation]):
                if self.matched_policy_annotation not in r:
                    r[self.matched_policy_annotation] = [self.data.get('key')]
                else:
                    r[self.matched_policy_annotation].append(self.data.get('key'))
                results.append(r)
        return results


@WorkspacesWeb.filter_registry.register('user-settings')
class UserSettingsFilter(ValueFilter):
    """
    Filters workspaces secured browsers based on their user settings.
    :example:

    .. code-block:: yaml

            policies:
              - name: user-settings-match
                resource: workspaces-web
                filters:
                  - type: user-settings
                    key: copyAllowed
                    value: Disabled
    """

    schema = type_schema('user-settings', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('workspaces-web:GetUserSettings',)
    policy_annotation = "c7n:UserSettings"

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('workspaces-web')
        for r in resources:
            if (self.policy_annotation not in r) and ('userSettingsArn' in r):
                r[self.policy_annotation] = self.manager.retry(
                    client.get_user_settings,
                    userSettingsArn=r['userSettingsArn']).get(
                        'userSettings', {})
        return super().process(resources, event)

    def __call__(self, r):
        return super().__call__(r.get(self.policy_annotation, {}))


@WorkspacesWeb.filter_registry.register('user-access-logging')
class UserAccessLoggingFilter(ValueFilter):
    """
    Filters workspaces secured browsers based on their user access logging settings.
    :example:

    .. code-block:: yaml

            policies:
              - name: user-access-logging-match
                resource: workspaces-web
                filters:
                  - type: user-access-logging
                    key: kinesisStreamArn
                    value: present
    """

    schema = type_schema('user-access-logging', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('workspaces-web:GetUserAccessLoggingSettings',)
    policy_annotation = "c7n:UserAccessLogging"

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('workspaces-web')
        for r in resources:
            if (self.policy_annotation not in r) and (
                'userAccessLoggingSettingsArn' in r):
                r[self.policy_annotation] = self.manager.retry(
                    client.get_user_access_logging_settings,
                    userAccessLoggingSettingsArn=r['userAccessLoggingSettingsArn']).get(
                        'userAccessLoggingSettings', {})
        return super().process(resources, event)

    def __call__(self, r):
        return super().__call__(r.get(self.policy_annotation, {}))


@WorkspacesWeb.action_registry.register('tag')
class TagWorkspacesWebResource(Tag):
    """Create tags on a Workspaces Web portal

    :example:

    .. code-block:: yaml

        policies:
            - name: tag-workspaces-web
              resource: workspaces-web
              actions:
                - type: tag
                  key: test-key
                  value: test-value
    """
    permissions = ('workspaces-web:TagResource',)

    def process_resource_set(self, client, resources, new_tags):
        for r in resources:
            client.tag_resource(resourceArn=r["portalArn"], tags=new_tags)


@WorkspacesWeb.action_registry.register('remove-tag')
class RemoveTagWorkspacesWebResource(RemoveTag):
    """Remove tags from a Workspaces Web portal

    :example:

    .. code-block:: yaml

        policies:
            - name: remove-tag-workspaces-web
              resource: workspaces-web
              actions:
                - type: remove-tag
                  tags: ["tag-key"]
    """
    permissions = ('workspaces-web:UntagResource',)

    def process_resource_set(self, client, resources, tags):
        for r in resources:
            client.untag_resource(resourceArn=r['portalArn'], tagKeys=tags)


@WorkspacesWeb.action_registry.register('delete')
class DeleteWorkspacesWeb(BaseAction):
    """Delete a WorkSpaces Web portal

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-workspaces-web
            resource: workspaces-web
            actions:
              - type: delete
    """
    schema = type_schema('delete')
    permissions = (
        'workspaces-web:DeletePortal',
        'workspaces-web:DisassociateNetworkSettings',
        'workspaces-web:DisassociateBrowserSettings',
        'workspaces-web:DisassociateUserSettings'
    )

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('workspaces-web')
        for r in resources:
            self.disassociate_settings(client, r, 'networkSettingsArn',
                                       'disassociate_network_settings')
            self.disassociate_settings(client, r, 'browserSettingsArn',
                                       'disassociate_browser_settings')
            self.disassociate_settings(client, r, 'userSettingsArn',
                                       'disassociate_user_settings')
            self.delete_portal(client, r)

    def disassociate_settings(self, client, resource, setting_arn_key, disassociate_method_name):
        setting_arn = resource.get(setting_arn_key)
        if setting_arn:
            disassociate_method = getattr(client, disassociate_method_name)
            try:
                disassociate_method(portalArn=resource["portalArn"])
            except client.exceptions.ResourceNotFoundException:
                pass
            except Exception as e:
                self.log.error(
                    "Failed to disassociate %s for portal %s: %s",
                    setting_arn_key, resource['portalArn'], str(e)
                )

    def delete_portal(self, client, resource):
        client.delete_portal(portalArn=resource['portalArn'])


@resources.register('workspaces-bundle')
class WorkspacesBundle(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'workspaces'
        enum_spec = ('describe_workspace_bundles', 'Bundles', None)
        arn_type = 'workspacebundle'
        name = id = 'BundleId'
        universal_taggable = True


@WorkspacesBundle.action_registry.register('delete')
class DeleteWorkspaceBundle(BaseAction):
    """
    Deletes a WorkSpaces Bundle

    :example:

    .. code-block:: yaml

        policies:
          - name: delete-workspaces-bundle
            resource: aws.workspaces-bundle
            actions:
              - delete
    """

    schema = type_schema('delete')
    permissions = ('workspaces:DeleteWorkspaceBundle',)

    def process(self, bundles):
        client = local_session(self.manager.session_factory).client('workspaces')
        for bundle in bundles:
            try:
                client.delete_workspace_bundle(BundleId=bundle['BundleId'])
            except client.exceptions.ResourceNotFoundException:
                self.log.warning("Bundle not found: %s" % bundle['BundleId'])
