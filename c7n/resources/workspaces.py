# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import functools
import itertools

from c7n.actions import BaseAction
from c7n.filters import ValueFilter
from c7n.filters.kms import KmsRelatedFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo, DescribeSource, ConfigSource
from c7n.tags import universal_augment
from c7n.exceptions import PolicyValidationError, PolicyExecutionError
from c7n.utils import get_retry, local_session, type_schema, chunks, jmespath_search
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.resolver import ValuesFrom
import c7n.filters.vpc as net_filters


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
