# Copyright 2015-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

from botocore.exceptions import ClientError

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.utils import local_session
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
from c7n.tags import Tag, RemoveTag


@resources.register('directory')
class Directory(QueryResourceManager):

    class resource_type(object):
        service = "ds"
        enum_spec = ("describe_directories", "DirectoryDescriptions", None)
        name = "Name"
        id = "DirectoryId"
        dimension = None
        filter_name = 'DirectoryIds'
        filter_type = 'list'

    permissions = ('ds:ListTagsForResource',)

    def augment(self, directories):
        def _add_tags(d):
            client = local_session(self.session_factory).client('ds')
            for t in client.list_tags_for_resource(
                    ResourceId=d['DirectoryId']).get('Tags', []):
                d.setdefault('Tags', []).append(
                    {'Key': t['Key'], 'Value': t['Value']})
            return d

        with self.executor_factory(max_workers=2) as w:
            return list(filter(None, w.map(_add_tags, directories)))


@Directory.filter_registry.register('subnet')
class DirectorySubnetFilter(SubnetFilter):

    RelatedIdsExpression = "VpcSettings.SubnetIds"


@Directory.filter_registry.register('security-group')
class DirectorySecurityGroupFilter(SecurityGroupFilter):

    RelatedIdsExpression = "VpcSettings.SecurityGroupId"


@Directory.action_registry.register('tag')
class DirectoryTag(Tag):
    """Add tags to a directory

    :example:

        .. code-block: yaml

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
    permissions = ('ds:AddTagToResource',)

    def process_resource_set(self, directories, tags):
        client = local_session(self.manager.session_factory).client('ds')
        tag_list = []
        for t in tags:
            tag_list.append({'Key': t['Key'], 'Value': t['Value']})
        for d in directories:
            try:
                client.add_tags_to_resource(
                    ResourceId=d['DirectoryId'], Tags=tag_list)
            except ClientError as e:
                self.log.exception(
                    'Exception tagging Directory %s: %s', d['DirectoryId'], e)
                continue


@Directory.action_registry.register('remove-tag')
class DirectoryRemoveTag(RemoveTag):
    """Remove tags from a directory

    :example:

        .. code-block: yaml

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

    def process_resource_set(self, directories, tags):
        client = local_session(self.manager.session_factory).client('ds')
        for d in directories:
            try:
                client.remove_tags_from_resource(
                    ResourceId=d['DirectoryId'], TagKeys=tags)
            except ClientError as e:
                self.log.exception(
                    'Exception removing tags from Directory %s: %s',
                    d['DirectoryId'], e)
                continue


@resources.register('cloud-directory')
class CloudDirectory(QueryResourceManager):

    class resource_type(object):
        service = "clouddirectory"
        enum_spec = ("list_directories", "Directories", None)
        id = "DirectoryArn"
        name = "Name"
        dimension = None
        filter_name = None
