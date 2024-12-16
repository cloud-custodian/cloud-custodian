# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.filters.core import Filter, ValueFilter
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema, QueryParser
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter, VpcFilter
from c7n.tags import Tag, RemoveTag, universal_augment, TagDelayedAction, TagActionFilter
from c7n.actions import BaseAction


@resources.register('directory')
class Directory(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "ds"
        enum_spec = ("describe_directories", "DirectoryDescriptions", None)
        name = "Name"
        id = "DirectoryId"
        filter_name = 'DirectoryIds'
        filter_type = 'list'
        arn_type = "directory"
        permission_augment = ('ds:ListTagsForResource',)

    def augment(self, directories):
        client = local_session(self.session_factory).client('ds')

        def _add_tags(d):
            d['Tags'] = client.list_tags_for_resource(
                ResourceId=d['DirectoryId']).get('Tags', [])
            return d

        return list(map(_add_tags, directories))


@Directory.filter_registry.register('subnet')
class DirectorySubnetFilter(SubnetFilter):

    RelatedIdsExpression = "VpcSettings.SubnetIds"


@Directory.filter_registry.register('security-group')
class DirectorySecurityGroupFilter(SecurityGroupFilter):

    RelatedIdsExpression = "VpcSettings.SecurityGroupId"


@Directory.filter_registry.register('vpc')
class DirectoryVpcFilter(VpcFilter):

    RelatedIdsExpression = "VpcSettings.VpcId"


@Directory.filter_registry.register('is-log-forwarding')
class DirectoryLogSubscriptionFilter(Filter):

    annotation_key = "c7n:LogSubscriptions"
    permissions = ("ds:ListLogSubscriptions",)
    schema = type_schema('is-log-forwarding')

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ds')
        results = []
        for r in resources:
            subs = self.manager.retry(
                client.list_log_subscriptions,
                DirectoryId=r["DirectoryId"]
            )["LogSubscriptions"]
            if subs:
                r[self.annotation_key] = subs
                results.append(r)

        return results


@Directory.filter_registry.register('ldap')
class DirectoryLDAPFilter(Filter):
    """Filter directories based on their LDAP status

    :example:

        .. code-block:: yaml

            policies:
              - name: ldap-enabled-directories
                resource: directory
                filters:
                  - type: ldap
                    status: Disabled
    """
    schema = type_schema(
        'ldap',
        status={'type': 'string', 'enum': ['Enabled', 'Disabled']},
        required=['status']
    )

    permissions = ('ds:DescribeLDAPSSettings',)
    annotation_key = 'c7n:LDAPSSettings'
    # Only MicrosoftAD and ADConnector directories have LDAP settings
    # the other types will throw an UnsupportedOperationException
    valid_directory_types = ['MicrosoftAD', "ADConnector"]

    def process(self, resources, event=None):
        resources = self.filter_resources(resources, 'Type', self.valid_directory_types)
        client = local_session(self.manager.session_factory).client('ds')
        status = self.data.get('status', 'Enabled')
        matches = []
        for r in resources:
            if self.annotation_key not in r:
                ldap_settings = client.describe_ldaps_settings(
                    DirectoryId=r['DirectoryId'])['LDAPSSettingsInfo']
                r[self.annotation_key] = ldap_settings
            if status == "Disabled" and len(r[self.annotation_key]) == 0:
                matches.append(r)
            else:
                for setting in r[self.annotation_key]:
                    if setting['LDAPSStatus'] == status:
                        matches.append(r)
                        break
        return matches


@Directory.filter_registry.register('settings')
class DirectorySettingsFilter(Filter):
    """Filter directories based on their settings

    :example:

        .. code-block:: yaml

            policies:
              - name: settings-enabled-directories
                resource: directory
                filters:
                  - type: settings
                    key: TLS_1_0
                    value: Enable
    """
    schema = type_schema(
        'settings', rinherit=ValueFilter.schema)

    permissions = ('ds:DescribeSettings',)
    annotation_key = 'c7n:Settings'
    # Only MicrosoftAD directories have settings
    # Other types will throw an InvalidParameterException
    valid_directory_types = ['MicrosoftAD']

    def process(self, resources, event=None):
        resources = self.filter_resources(resources, 'Type', self.valid_directory_types)
        client = local_session(self.manager.session_factory).client('ds')
        key = self.data.get('key')
        value = self.data.get('value')
        matches = []
        for r in resources:
            if self.annotation_key not in r:
                settings = client.describe_settings(
                    DirectoryId=r['DirectoryId'])['SettingEntries']
                r[self.annotation_key] = settings
            for setting in r[self.annotation_key]:
                if setting['Name'] == key and setting['AppliedValue'] == value:
                    matches.append(r)
                    break
        return matches


@Directory.filter_registry.register('trust')
class DirectoryTrustFilter(ValueFilter):
    """Filter directories based on their trust relationships

    :example:

        .. code-block:: yaml

            policies:
              - name: trust-enabled-directories
                resource: directory
                filters:
                  - type: trust
                    key: TrustState
                    value: Verified
              - name: trust-remote-domain
                resource: directory
                filters:
                  - type: trust
                    key: RemoteDomainName
                    value: example.com
    """
    schema = type_schema(
        'trust', rinherit=ValueFilter.schema)

    permissions = ('ds:DescribeTrusts',)
    annotation_key = 'c7n:Trusts'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ds')
        trusts = client.describe_trusts()['Trusts']
        for r in resources:
            r[self.annotation_key] = [
                t for t in trusts if t['DirectoryId'] == r['DirectoryId']]
        matched = []
        for r in resources:
            if any((self.match(trust) for trust in r[self.annotation_key])):
                matched.append(r)
        return matched


@Directory.action_registry.register('tag')
class DirectoryTag(Tag):
    """Add tags to a directory
-
    :example:

        .. code-block:: yaml

            policies:
              - name: tag-directory
                resource: directory
                filters:
                  - "tag:desired-tag": absent
                actions:
                  - type: tag
                    key: desired-tag
                    value: desired-value
    """
    permissions = ('ds:AddTagsToResource',)

    def process_resource_set(self, client, directories, tags):
        for d in directories:
            try:
                client.add_tags_to_resource(
                    ResourceId=d['DirectoryId'], Tags=tags)
            except client.exceptions.EntityDoesNotExistException:
                continue


@Directory.action_registry.register('remove-tag')
class DirectoryRemoveTag(RemoveTag):
    """Remove tags from a directory

    :example:

        .. code-block:: yaml

            policies:
              - name: remove-directory-tag
                resource: directory
                filters:
                  - "tag:desired-tag": present
                actions:
                  - type: remove-tag
                    tags: ["desired-tag"]
    """
    permissions = ('ds:RemoveTagsFromResource',)

    def process_resource_set(self, client, directories, tags):
        for d in directories:
            try:
                client.remove_tags_from_resource(
                    ResourceId=d['DirectoryId'], TagKeys=tags)
            except client.exceptions.EntityDoesNotExistException:
                continue


Directory.filter_registry.register('marked-for-op', TagActionFilter)
Directory.action_registry.register('mark-for-op', TagDelayedAction)


@Directory.action_registry.register('delete')
class DirectoryDelete(BaseAction):
    """Delete a directory.

    :example:

    .. code-block:: yaml

            policies:
              - name: delete-directory
                resource: aws.directory
                filters:
                    - Name: test.example.com
                actions:
                  - delete
    """
    schema = type_schema('delete')
    permissions = ('ds:DeleteDirectory',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('ds')

        for r in resources:
            self.manager.retry(
                client.delete_directory,
                DirectoryId=r['DirectoryId'])


@resources.register('cloud-directory')
class CloudDirectory(QueryResourceManager):

    class resource_type(TypeInfo):
        service = "clouddirectory"
        enum_spec = ("list_directories", "Directories", {'state': 'ENABLED'})
        arn = id = "DirectoryArn"
        name = "Name"
        arn_type = "directory"
        universal_taggable = object()
        permissions_augment = ("clouddirectory:ListTagsForResource",)

    augment = universal_augment

    def resources(self, query=None):
        query_filters = CloudDirectoryQueryParser.parse(self.data.get('query', []))
        query = query or {}
        if query_filters:
            query['Filters'] = query_filters
        return super(CloudDirectory, self).resources(query=query)


@CloudDirectory.action_registry.register('delete')
class CloudDirectoryDelete(BaseAction):
    """Delete a cloud directory.

    .. code-block:: yaml

       policies:
         - name: delete-cloud-directory
           resource: aws.cloud-directory
           filters:
             - Name: test-cloud
           actions:
             - type: delete
    """
    schema = type_schema('delete')
    permissions = ('clouddirectory:DeleteDirectory',
                   'clouddirectory:DisableDirectory',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('clouddirectory')
        for r in resources:
            self.manager.retry(
                    client.disable_directory,
                    DirectoryArn=r['DirectoryArn'])

        for r in resources:
            self.manager.retry(
                client.delete_directory,
                DirectoryArn=r['DirectoryArn'])


@CloudDirectory.action_registry.register('disable')
class CloudDirectoryDisable(BaseAction):
    """Disable a cloud directory.

    .. code-block:: yaml

       policies:
         - name: disable-cloud-directory
           resource: aws.cloud-directory
           filters:
             - Name: test-cloud
           actions:
             - type: disable
    """
    schema = type_schema('disable')
    permissions = ('clouddirectory:DisableDirectory',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('clouddirectory')
        for r in resources:
            self.manager.retry(
                    client.disable_directory,
                    DirectoryArn=r['DirectoryArn'])


class CloudDirectoryQueryParser(QueryParser):
    QuerySchema = {
        'name': str,
        'directoryArn': str,
        'state': str,
    }

    type_name = 'CloudDirectory'
