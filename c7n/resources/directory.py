# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.manager import resources
from c7n.query import QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema, chunks
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


@Directory.action_registry.register('tag')
class DirectoryTag(Tag):
    """Add tags to a directory

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

        for resource_set in chunks(resources, size=100):
            for r in resource_set:
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

    augment = universal_augment

@CloudDirectory.action_registry.register('delete')
class CloudDirectoryDelete(BaseAction):
    """Disable/Delete a cloud directory.
    
    The directory(s) will be disabled when this action is called.
    If force is True, the directory(s) will be permanently deleted
    
    :example:
    .. code-block:: yaml
            policies:
              - name: disable-cloud-directory
                resource: aws.cloud-directory
                filters:
                  - Name: test-cloud
                actions:
                  - type: delete

              - name: delete-cloud-directory
                resource: aws.cloud-directory
                filters:
                  - Name: test-cloud
                actions:
                  - type: delete
                    force: True
    """

    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = ('clouddirectory:DeleteDirectory',
                   'clouddirectory:DisableDirectory',)

    def process(self, resources):
        client = local_session(
            self.manager.session_factory).client('clouddirectory')
        force = self.data.get("force", False)
        for r in resources:
            if r["State"] == "DISABLED": 
                continue
            self.manager.retry(
                    client.disable_directory,
                    DirectoryArn=r['DirectoryArn'])
        
        if force:
            for r in resources:
                self.manager.retry(
                    client.delete_directory,
                    DirectoryArn=r['DirectoryArn'])
