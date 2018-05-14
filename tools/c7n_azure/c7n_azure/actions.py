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
from c7n.filters import FilterValidationError


def utcnow():
    """The datetime object for the current time in UTC
    """
    return datetime.datetime.utcnow()


def update_resource_tags(self, session, client, resource, tags):
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

            update_resource_tags(self, session, client, resource, tags)


class RemoveTag(BaseAction):
    """Removes tags from Azure resources

        .. code-block:: yaml

          policies:
            - name: azure-remove-tag-resourcegroups
              resource: azure.resourcegroup
              description: |
                Remove tag for all existing resource groups with a key such as Environment
              actions:
               - type: untag
                 tags: ['Environment']
    """
    schema = utils.type_schema(
        'untag',
        tags={'type': 'array', 'items': {'type': 'string'}})

    def validate(self):
        if not self.data.get('tags'):
            raise FilterValidationError("Must specify tags")
        return self

    def process(self, resources):
        session = utils.local_session(self.manager.session_factory)
        client = self.manager.get_client('azure.mgmt.resource.ResourceManagementClient')

        for resource in resources:
            # get existing tags
            tags = resource.get('tags', {})

            # delete tag
            tags_to_delete = self.data.get('tags')
            resource_tags = {key: tags[key] for key in tags if key not in tags_to_delete}

            update_resource_tags(self, session, client, resource, resource_tags)


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


class TagTrim(BaseAction):
    """Automatically remove tags from an azure resource.

    Azure Resources and Resource Groups have a limit of 15 tags.
    In order to make additional tag space on a set of resources,
    this action can be used to remove enough tags to make the
    desired amount of space while preserving a given set of tags.
    Setting the space value to 0 removes all tags but those
    listed to preserve.

    .. code-block :: yaml

      - policies:
         - name: azure-tag-trim
           comment: |
             Any instances with 14 or more tags get tags removed until
             they match the target tag count, in this case 13, so
             that we free up tag slots for another usage.
           resource: azure.resourcegroup
           filters:
               # Filter down to resources that do not have the space
               # to add additional required tags. For example, if an
               # additional 2 tags need to be added to a resource, with
               # 15 tags as the limit, then filter down to resources that
               # have 14 or more tags since they will need to have tags
               # removed for the 2 extra. This also ensures that metrics
               # reporting is correct for the policy.
               type: value
               key: "[length(Tags)][0]"
               op: ge
               value: 14
           actions:
             - type: tag-trim
               space: 2
               preserve:
                - OwnerContact
                - Environment
                - downtime
                - custodian_status
    """
    max_tag_count = 15

    schema = utils.type_schema(
        'tag-trim',
        space={'type': 'integer'},
        preserve={'type': 'array', 'items': {'type': 'string'}})

    def validate(self):
        if self.data.get('space') < 0 or self.data.get('space') > 15:
            raise FilterValidationError("Space must be between 0 and 15")

        return self

    def process(self, resources):
        preserve = set(self.data.get('preserve', {}))
        space = self.data.get('space')
        untag_action = self.manager.action_registry.get('untag')

        for resource in resources:
            # get existing tags
            tags = resource.get('tags', {})

            if space and len(tags) + space <= self.max_tag_count:
                continue

            # delete tags
            keys = set(tags)
            tags_to_preserve = preserve.intersection(keys)
            candidates = keys - tags_to_preserve

            if space:
                # Free up slots to fit
                remove = len(candidates) - (
                    self.max_tag_count - (space + len(tags_to_preserve)))
                candidates = list(sorted(candidates))[:remove]

            if not candidates:
                self.log.warning(
                    "Could not find any candidates to trim %s" % resource['id'])
                continue

            untag_action({'tags': candidates}, self.manager).process([resource])
