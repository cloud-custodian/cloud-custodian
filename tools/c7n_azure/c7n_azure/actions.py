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
from datetime import timedelta

from azure.mgmt.resource.resources.models import GenericResource, ResourceGroupPatchable
from c7n_azure.storage_utils import StorageUtilities
from c7n_azure.utils import utcnow
from dateutil import zoneinfo
from msrestazure.azure_exceptions import CloudError

from c7n import utils
from c7n.actions import BaseAction, BaseNotify
from c7n.filters import FilterValidationError
from c7n.filters.core import PolicyValidationError
from c7n.filters.offhours import Time
from c7n.resolver import ValuesFrom
from c7n.utils import local_session, type_schema


def update_resource_tags(self, resource, tags):

    # resource group type
    if self.manager.type == 'resourcegroup':
        params_patch = ResourceGroupPatchable(
            tags=tags
        )
        self.client.resource_groups.update(
            resource['name'],
            params_patch,
        )
    # other Azure resources
    else:
        if self.manager.type == 'armresource':
            raise NotImplementedError('Cannot tag generic ARM resources.')

        az_resource = GenericResource.deserialize(resource)
        api_version = self.session.resource_api_version(az_resource.id)
        az_resource.tags = tags

        self.client.resources.create_or_update_by_id(resource['id'], api_version, az_resource)


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

    def __init__(self, data=None, manager=None, log_dir=None):
        super(Tag, self).__init__(data, manager, log_dir)
        self.session = utils.local_session(self.manager.session_factory)
        self.client = self.manager.get_client('azure.mgmt.resource.ResourceManagementClient')

    def validate(self):
        if not self.data.get('tags') and not (self.data.get('tag') and self.data.get('value')):
            raise FilterValidationError(
                "Must specify either tags or a tag and value")

        if self.data.get('tags') and self.data.get('tag'):
            raise FilterValidationError(
                "Can't specify both tags and tag, choose one")

        return self

    def process(self, resources):
        with self.executor_factory(max_workers=3) as w:
            list(w.map(self.process_resource, resources))

    def process_resource(self, resource):
        # get existing tags
        tags = resource.get('tags', {})

        # add or update tags
        new_tags = self.data.get('tags') or {self.data.get('tag'): self.data.get('value')}
        for key in new_tags:
            tags[key] = new_tags[key]

        update_resource_tags(self, resource, tags)


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

    def __init__(self, data=None, manager=None, log_dir=None):
        super(RemoveTag, self).__init__(data, manager, log_dir)
        self.session = utils.local_session(self.manager.session_factory)
        self.client = self.manager.get_client('azure.mgmt.resource.ResourceManagementClient')

    def validate(self):
        if not self.data.get('tags'):
            raise FilterValidationError("Must specify tags")
        return self

    def process(self, resources):
        with self.executor_factory(max_workers=3) as w:
            list(w.map(self.process_resource, resources))

    def process_resource(self, resource):
        # get existing tags
        tags = resource.get('tags', {})

        # delete tag
        tags_to_delete = self.data.get('tags')
        resource_tags = {key: tags[key] for key in tags if key not in tags_to_delete}

        update_resource_tags(self, resource, resource_tags)


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
        self.client = self.manager.get_client('azure.mgmt.monitor.MonitorManagementClient')
        self.tag_action = self.manager.action_registry.get('tag')

    def validate(self):
        if self.manager.action_registry.get('tag') is None:
            raise FilterValidationError("Resource does not support tagging")

        if (self.data.get('days') is not None and
                (self.data.get('days') < 1 or self.data.get('days') > 90)):
            raise FilterValidationError("Days must be between 1 and 90")

        return self

    def process(self, resources):
        self.tag_key = self.data['tag']
        self.should_update = self.data.get('update', False)
        with self.executor_factory(max_workers=3) as w:
            list(w.map(self.process_resource, resources))

    def process_resource(self, resource):
        # if the auto-tag-user policy set update to False (or it's unset) then we
        # will skip writing their UserName tag and not overwrite pre-existing values
        if not self.should_update and resource.get('tags', {}).get(self.tag_key, None):
            return

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
        logs = self.client.activity_logs.list(
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
            self.tag_action({'tag': self.tag_key, 'value': user}, self.manager).process([resource])
        except CloudError as e:
            # resources can be locked
            if e.inner_exception.error == 'ScopeLocked':
                pass

    @staticmethod
    def get_first_operation(logs, operation_name):
        first_operation = None
        for l in logs:
            if l.operation_name.value.lower() == operation_name.lower():
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

    def __init__(self, data=None, manager=None, log_dir=None):
        super(TagTrim, self).__init__(data, manager, log_dir)
        self.untag_action = self.manager.action_registry.get('untag')

    def validate(self):
        if self.data.get('space') < 0 or self.data.get('space') > 15:
            raise FilterValidationError("Space must be between 0 and 15")

        return self

    def process(self, resources):
        self.preserve = set(self.data.get('preserve', {}))
        self.space = self.data.get('space', 1)

        with self.executor_factory(max_workers=3) as w:
            list(w.map(self.process_resource, resources))

    def process_resource(self, resource):
        # get existing tags
        tags = resource.get('tags', {})

        if self.space and len(tags) + self.space <= self.max_tag_count:
            return

        # delete tags
        keys = set(tags)
        tags_to_preserve = self.preserve.intersection(keys)
        candidates = keys - tags_to_preserve

        if self.space:
            # Free up slots to fit
            remove = len(candidates) - (
                self.max_tag_count - (self.space + len(tags_to_preserve)))
            candidates = list(sorted(candidates))[:remove]

        if not candidates:
            self.log.warning(
                "Could not find any candidates to trim %s" % resource['id'])
            return

        self.untag_action({'tags': candidates}, self.manager).process([resource])


class Notify(BaseNotify):

    batch_size = 50

    schema = {
        'type': 'object',
        'anyOf': [
            {'required': ['type', 'transport', 'to']},
            {'required': ['type', 'transport', 'to_from']}],
        'properties': {
            'type': {'enum': ['notify']},
            'to': {'type': 'array', 'items': {'type': 'string'}},
            'owner_absent_contact': {'type': 'array', 'items': {'type': 'string'}},
            'to_from': ValuesFrom.schema,
            'cc': {'type': 'array', 'items': {'type': 'string'}},
            'cc_from': ValuesFrom.schema,
            'cc_manager': {'type': 'boolean'},
            'from': {'type': 'string'},
            'subject': {'type': 'string'},
            'template': {'type': 'string'},
            'transport': {
                'oneOf': [
                    {'type': 'object',
                     'required': ['type', 'queue'],
                     'properties': {
                         'queue': {'type': 'string'},
                         'type': {'enum': ['asq']}
                     }}],
            },
        }
    }

    def __init__(self, data=None, manager=None, log_dir=None):
        super(Notify, self).__init__(data, manager, log_dir)

    def process(self, resources, event=None):
        session = utils.local_session(self.manager.session_factory)
        message = {
            'event': event,
            'account_id': session.subscription_id,
            'account': session.subscription_id,
            'region': 'all',
            'policy': self.manager.data}

        message['action'] = self.expand_variables(message)

        for batch in utils.chunks(resources, self.batch_size):
            message['resources'] = batch
            receipt = self.send_data_message(message)
            self.log.info("sent message:%s policy:%s template:%s count:%s" % (
                receipt, self.manager.data['name'],
                self.data.get('template', 'default'), len(batch)))

    def send_data_message(self, message):
        if self.data['transport']['type'] == 'asq':
            queue_uri = self.data['transport']['queue']
            return self.send_to_azure_queue(queue_uri, message)

    def send_to_azure_queue(self, queue_uri, message):
        queue_service, queue_name = StorageUtilities.get_queue_client_by_uri(queue_uri)
        return StorageUtilities.put_queue_message(queue_service, queue_name, self.pack(message)).id


DEFAULT_TAG = "custodian_status"


class TagDelayedAction(BaseAction):
    """Tag resources for future action.

    The optional 'tz' parameter can be used to adjust the clock to align
    with a given timezone. The default value is 'utc'.

    If neither 'days' nor 'hours' is specified, Cloud Custodian will default
    to marking the resource for action 4 days in the future.

    .. code-block :: yaml

      - policies:
        - name: vm-mark-for-stop
          resource: azure.vm
          filters:
            - type: value
              key: Name
              value: instance-to-stop-in-four-days
          actions:
            - type: mark-for-op
              op: stop
    """

    schema = utils.type_schema(
        'mark-for-op',
        tag={'type': 'string'},
        msg={'type': 'string'},
        days={'type': 'integer', 'minimum': 0, 'exclusiveMinimum': False},
        hours={'type': 'integer', 'minimum': 0, 'exclusiveMinimum': False},
        tz={'type': 'string'},
        op={'type': 'string'})

    default_template = 'Resource does not meet policy: {op}@{action_date}'

    def __init__(self, data=None, manager=None, log_dir=None):
        super(TagDelayedAction, self).__init__(data, manager, log_dir)
        self.session = utils.local_session(self.manager.session_factory)
        self.client = self.manager.get_client('azure.mgmt.resource.ResourceManagementClient')

    def validate(self):
        op = self.data.get('op')
        if self.manager and op not in self.manager.action_registry.keys():
            raise PolicyValidationError(
                "mark-for-op specifies invalid op:%s in %s" % (
                    op, self.manager.data))

        self.tz = zoneinfo.gettz(
            Time.TZ_ALIASES.get(self.data.get('tz', 'utc')))
        if not self.tz:
            raise PolicyValidationError(
                "Invalid timezone specified %s in %s" % (
                    self.tz, self.manager.data))
        return self

    def generate_timestamp(self, days, hours):
        from c7n_azure.utils import now
        n = now(tz=self.tz)
        if days is None or hours is None:
            # maintains default value of days being 4 if nothing is provided
            days = 4
        action_date = (n + timedelta(days=days, hours=hours))
        if hours > 0:
            action_date_string = action_date.strftime('%Y/%m/%d %H%M %Z')
        else:
            action_date_string = action_date.strftime('%Y/%m/%d')

        return action_date_string

    def process(self, resources):
        self.tz = zoneinfo.gettz(
            Time.TZ_ALIASES.get(self.data.get('tz', 'utc')))

        msg_tmpl = self.data.get('msg', self.default_template)

        op = self.data.get('op', 'stop')
        days = self.data.get('days', 0)
        hours = self.data.get('hours', 0)
        action_date = self.generate_timestamp(days, hours)

        self.tag = self.data.get('tag', DEFAULT_TAG)

        self.msg = msg_tmpl.format(
            op=op, action_date=action_date)

        self.log.info("Tagging %d resources for %s on %s" % (
            len(resources), op, action_date))

        with self.executor_factory(max_workers=1) as w:
            list(w.map(self.process_resource, resources))

    def process_resource(self, resource):
        # get existing tags
        tags = resource.get('tags', {})

        # add new tag
        tags[self.tag] = self.msg

        update_resource_tags(self, resource, tags)


class DeleteAction(BaseAction):

    schema = type_schema('delete')

    def process(self, resources):
        session = local_session(self.manager.session_factory)
        #: :type: azure.mgmt.resource.ResourceManagementClient
        client = self.manager.get_client('azure.mgmt.resource.ResourceManagementClient')
        for resource in resources:
            client.resources.delete_by_id(resource['id'],
                session.resource_api_version(resource['id']))
