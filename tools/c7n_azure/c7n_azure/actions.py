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
"""
Actions to perform on Azure resources
"""
import datetime
from azure.mgmt.resource.resources.models import GenericResource, ResourceGroupPatchable
from msrestazure.azure_exceptions import CloudError
from c7n import utils
from c7n.actions import BaseAction
from c7n_azure.provider import resources
from c7n.filters import FilterValidationError


def utcnow():
    """The datetime object for the current time in UTC
    """
    return datetime.datetime.utcnow()


class Tag(BaseAction):
    """Adds tags to Azure resources

        .. code-block:: yaml

          policies:
            - name: azure-tag-resourcegroups
              resource: azure.resourcegroup
              description: |
                Tag all existing resource groups with a value such as Environment
              actions:
               - type: tag
                 tag: Environment
                 value: Test
    """

    schema = utils.type_schema(
        'tag',
        **{
            'tag': {'type': 'string'},
            'value': {'type': 'string'},
            'tags': {'type': 'object'}
        }
    )

    def validate(self):
        if not self.data.get('tags') and not (self.data.get('tag') and self.data.get('value')):
            raise FilterValidationError(
                "Must specify either tags or a tag and value")

        if self.data.get('tags') and self.data.get('tag'):
            raise FilterValidationError(
                "Can't specify both tags and tag, choose one")

        return self

    def process(self, resources):
        session = utils.local_session(self.manager.session_factory)
        client = self.manager.get_client('azure.mgmt.resource.ResourceManagementClient')

        for resource in resources:
            # get existing tags
            tags = resource.get('tags', {})

            # add or update tags
            new_tags = self.data.get('tags') or {self.data.get('tag'): self.data.get('value')}
            for key in new_tags:
                tags[key] = new_tags[key]

            # resource group type
            if self.manager.type == 'resourcegroup':
                params_patch = ResourceGroupPatchable(
                    tags=tags
                )
                client.resource_groups.update(
                    resource['name'],
                    params_patch,
                )
            # other Azure resources
            else:
                az_resource = GenericResource.deserialize(resource)
                api_version = session.resource_api_version(az_resource.id)
                az_resource.tags = tags

                client.resources.create_or_update_by_id(resource['id'], api_version, az_resource)


class AutoTagUser(BaseAction):
    """Attempts to tag a resource with the first user who created/modified it.

    .. code-block:: yaml

      policies:
        - name: azure-auto-tag-creator
          resource: azure.resourcegroup
          description: |
            Tag all existing resource groups with the 'CreatorEmail' tag
          actions:
           - type: auto-tag-user
             tag: CreatorEmail

    This action searches from the earliest 'write' operation's caller
    in the activity logs for a particular resource.

    Note: activity logs are only held for the last 90 days.

    """
    default_user = "Unknown"
    query_select = "eventTimestamp, operationName, caller"
    max_query_days = 90

    schema = utils.type_schema(
        'auto-tag-user',
        required=['tag'],
        **{'update': {'type': 'boolean'},
           'tag': {'type': 'string'},
           'days': {'type': 'integer'}})

    def __init__(self, data=None, manager=None, log_dir=None):
        super(AutoTagUser, self).__init__(data, manager, log_dir)
        delta_days = self.data.get('days', self.max_query_days)
        self.start_time = utcnow() - datetime.timedelta(days=delta_days)

    def validate(self):
        if self.manager.action_registry.get('tag') is None:
            raise FilterValidationError("Resource does not support tagging")

        if (self.data.get('days') is not None and
                (self.data.get('days') < 1 or self.data.get('days') > 90)):
            raise FilterValidationError("Days must be between 1 and 90")

        return self

    def process(self, resources):
        client = self.manager.get_client('azure.mgmt.monitor.MonitorManagementClient')
        tag_action = self.manager.action_registry.get('tag')
        tag_key = self.data['tag']
        should_update = self.data.get('update', False)

        for resource in resources:
            # if the auto-tag-user policy set update to False (or it's unset) then we
            # will skip writing their UserName tag and not overwrite pre-existing values
            if not should_update and resource.get('tags', {}).get(tag_key, None):
                continue

            user = self.default_user

            # resource group type
            if self.manager.type == 'resourcegroup':
                resource_type = "Microsoft.Resources/subscriptions/resourcegroups"
                query_filter = " and ".join([
                    "eventTimestamp ge '%s'" % self.start_time,
                    "resourceGroupName eq '%s'" % resource['name'],
                    "eventChannels eq 'Operation'"
                ])
            # other Azure resources
            else:
                resource_type = resource['type']
                query_filter = " and ".join([
                    "eventTimestamp ge '%s'" % self.start_time,
                    "resourceUri eq '%s'" % resource['id'],
                    "eventChannels eq 'Operation'"
                ])

            # fetch activity logs
            logs = client.activity_logs.list(
                filter=query_filter,
                select=self.query_select
            )

            # get the user who issued the first operation
            operation_name = "%s/write" % resource_type
            first_op = self.get_first_operation(logs, operation_name)
            if first_op is not None:
                user = first_op.caller

            # issue tag action to label user
            try:
                tag_action({'tag': tag_key, 'value': user}, self.manager).process([resource])
            except CloudError as e:
                # resources can be locked
                if e.inner_exception.error == 'ScopeLocked':
                    pass

    @staticmethod
    def get_first_operation(logs, operation_name):
        first_operation = None
        for l in logs:
            if l.operation_name.value == operation_name:
                first_operation = l

        return first_operation

    @staticmethod
    def add_auto_tag_user(registry, _):
        for resource in registry.keys():
            klass = registry.get(resource)
            if klass.action_registry.get('tag') and not klass.action_registry.get('auto-tag-user'):
                klass.action_registry.register('auto-tag-user', AutoTagUser)


# Add the AutoTagUser action to all resources that support tagging
resources.subscribe(resources.EVENT_FINAL, AutoTagUser.add_auto_tag_user)
