# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import datetime
import logging
from abc import abstractmethod
from email.utils import parseaddr

from c7n_azure import constants
from c7n_azure.actions.base import AzureBaseAction, AzureEventAction
from c7n_azure.tags import TagHelper
from c7n_azure.utils import StringUtils
from dateutil import tz as tzutils
from msrest import Deserializer

from c7n import utils
from c7n.exceptions import PolicyValidationError
from c7n.filters import FilterValidationError
from c7n.filters.offhours import Time
from c7n.utils import type_schema, jmespath_compile
from c7n.lookup import Lookup


class Tag(AzureBaseAction):
    """Adds tags to Azure resources

    :example:

    This policy will tag all existing resource groups with a value such as Environment

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
            'value': Lookup.lookup_type({'type': 'string'}),
            'tag': Lookup.lookup_type({'type': 'string'}),
            'tags': {'type': 'object'}
        }
    )
    schema_alias = True
    log = logging.getLogger('custodian.azure.tagging.Tag')

    def __init__(self, data=None, manager=None, log_dir=None):
        super(Tag, self).__init__(data, manager, log_dir)

    def validate(self):
        if not self.data.get('tags') and not (self.data.get('tag') and self.data.get('value')):
            raise FilterValidationError(
                "Must specify either tags or a tag and value")

        if self.data.get('tags') and self.data.get('tag'):
            raise FilterValidationError(
                "Can't specify both tags and tag, choose one")

        return self

    def _process_resource(self, resource):
        new_tags = self._get_tags(resource)
        return TagHelper.add_tags(self, resource, new_tags)

    def _get_tags(self, resource):
        return self.data.get('tags') or {Lookup.extract(
            self.data.get('tag'), resource): Lookup.extract(self.data.get('value'), resource)}


class RemoveTag(AzureBaseAction):
    """Removes tags from Azure resources

    :example:

    This policy will remove tag for all existing resource groups with a key such as Environment

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
    schema_alias = True

    def __init__(self, data=None, manager=None, log_dir=None):
        super(RemoveTag, self).__init__(data, manager, log_dir)

    def validate(self):
        if not self.data.get('tags'):
            raise FilterValidationError("Must specify tags")
        return self

    def _prepare_processing(self,):
        self.tags_to_delete = self.data.get('tags')

    def _process_resource(self, resource):
        return TagHelper.remove_tags(self, resource, self.tags_to_delete)


class AutoTagBase(AzureEventAction):

    default_value = "Unknown"
    query_select = "eventTimestamp, operationName"
    max_query_days = 90

    schema = utils.type_schema(
        'auto-tag-base',
        required=['tag'],
        **{'update': {'type': 'boolean'},
           'tag': {'type': 'string'},
           'days': {'type': 'integer'}})
    schema_alias = True

    def __init__(self, data=None, manager=None, log_dir=None):
        super(AutoTagBase, self).__init__(data, manager, log_dir)

    @abstractmethod
    def _get_tag_value_from_event(self, event):
        raise NotImplementedError()

    @abstractmethod
    def _get_tag_value_from_resource(self, resource):
        raise NotImplementedError()

    def validate(self):

        if self.manager.data.get('mode', {}).get('type') == 'azure-event-grid' \
                and self.data.get('days') is not None:
            raise PolicyValidationError(
                "Auto tag actions in event mode does not use days.")

        if (self.data.get('days') is not None and
                (self.data.get('days') < 1 or self.data.get('days') > 90)):
            raise FilterValidationError("Days must be between 1 and 90")

        return self

    def _prepare_processing(self):
        self.session = self.manager.get_session()
        self.client = self.manager.get_client('azure.mgmt.monitor.MonitorManagementClient')
        self.tag_key = self.data['tag']
        self.should_update = self.data.get('update', False)

    def _process_resource(self, resource, event):
        # if the auto-tag-user policy set update to False (or it's unset) then we
        # will skip writing their UserName tag and not overwrite pre-existing values
        if not self.should_update and resource.get('tags', {}).get(self.tag_key, None):
            return

        tag_value = self.default_value
        if event:
            tag_value = self._get_tag_value_from_event(event) or tag_value
        else:
            tag_value = self._get_tag_value_from_resource(resource) or tag_value

        return TagHelper.add_tags(self, resource, {self.tag_key: tag_value})

    def _get_first_event(self, resource):

        if 'c7n:first_iam_event' in resource:
            return resource['c7n:first_iam_event']

        # Makes patching this easier
        from c7n_azure.utils import utcnow

        # Calculate start time
        delta_days = self.data.get('days', self.max_query_days)
        start_time = utcnow() - datetime.timedelta(days=delta_days)

        # resource group type
        if self.manager.type == 'resourcegroup':
            resource_type = "Microsoft.Resources/subscriptions/resourcegroups"
            query_filter = " and ".join([
                "eventTimestamp ge '%s'" % start_time,
                "resourceGroupName eq '%s'" % resource['name'],
                "eventChannels eq 'Operation'",
                "resourceType eq '%s'" % resource_type
            ])
        # other Azure resources
        else:
            resource_type = resource['type']
            query_filter = " and ".join([
                "eventTimestamp ge '%s'" % start_time,
                "resourceUri eq '%s'" % resource['id'],
                "eventChannels eq 'Operation'",
                "resourceType eq '%s'" % resource_type
            ])

        # fetch activity logs
        logs = self.client.activity_logs.list(
            filter=query_filter,
            select=self.query_select
        )

        # get the user who issued the first operation
        operation_name = "%s/write" % resource_type
        first_event = None
        for l in logs:
            if l.operation_name.value and l.operation_name.value.lower() == operation_name.lower():
                first_event = l

        resource['c7n:first_iam_event'] = first_event
        return first_event


class AutoTagUser(AutoTagBase):
    """Attempts to tag a resource with the first user who created/modified it.

    :example:

    This policy will tag all existing resource groups with the 'CreatorEmail' tag

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

    schema = type_schema('auto-tag-user',
                         rinherit=AutoTagBase.schema,
                         **{
                             'default-claim': {'enum': ['upn', 'name']}
                         })
    log = logging.getLogger('custodian.azure.tagging.AutoTagUser')

    # compiled JMES paths
    service_admin_jmes_path = jmespath_compile(constants.EVENT_GRID_SERVICE_ADMIN_JMES_PATH)
    sp_jmes_path = jmespath_compile(constants.EVENT_GRID_SP_NAME_JMES_PATH)
    upn_jmes_path = jmespath_compile(constants.EVENT_GRID_UPN_CLAIM_JMES_PATH)
    name_jmes_path = jmespath_compile(constants.EVENT_GRID_NAME_CLAIM_JMES_PATH)
    principal_role_jmes_path = jmespath_compile(constants.EVENT_GRID_PRINCIPAL_ROLE_JMES_PATH)
    principal_type_jmes_path = jmespath_compile(constants.EVENT_GRID_PRINCIPAL_TYPE_JMES_PATH)

    def __init__(self, data=None, manager=None, log_dir=None):
        super(AutoTagUser, self).__init__(data, manager, log_dir)
        self.query_select = "eventTimestamp, operationName, caller, claims"
        self.default_claim = self.data.get('default-claim', 'upn')

    def _get_tag_value_from_event(self, event):
        principal_role = self.principal_role_jmes_path.search(event)
        principal_type = self.principal_type_jmes_path.search(event)
        user = None
        # The Subscription Admins role does not have a principal type
        if StringUtils.equal(principal_role, 'Subscription Admin'):
            user = self.service_admin_jmes_path.search(event)
        # ServicePrincipal type
        elif StringUtils.equal(principal_type, 'ServicePrincipal'):
            user = self.sp_jmes_path.search(event)

        if not user:
            known_claims = {'upn': self.upn_jmes_path.search(event),
                            'name': self.name_jmes_path.search(event)}
            if known_claims[self.default_claim]:
                user = known_claims[self.default_claim]
            elif self.default_claim == 'upn' and known_claims['name']:
                user = known_claims['name']
            elif self.default_claim == 'name' and known_claims['upn']:
                user = known_claims['upn']

        # Last effort search for an email address in the claims
        if not user:
            claims = event['data'].get('claims', [])
            for c in claims:
                value = claims[c]
                if self._is_email(value):
                    user = value
                    break

        if not user:
            self.log.error('Principal could not be determined.')
        return user

    def _is_email(self, target):
        if target is None:
            return False
        elif parseaddr(target)[1] and '@' in target and '.' in target:
            return True
        else:
            return False

    def _get_tag_value_from_resource(self, resource):
        first_op = self._get_first_event(resource)

        if not first_op:
            return None

        return self._get_tag_value_from_event({'data': first_op.serialize(True)})


class AutoTagDate(AutoTagBase):
    """
    Attempts to tag a resource with the date when resource was created.

    This action searches from the earliest 'write' operation's caller
    in the activity logs for a particular resource.

    Note: activity logs are only held for the last 90 days.

    :example:

    This policy will tag all existing resource groups with the 'CreatedDate' tag

    .. code-block:: yaml

        policies:
          - name: azure-auto-tag-created-date
            resource: azure.resourcegroup
            description: |
              Tag all existing resource groups with the 'CreatedDate' tag
            actions:
              - type: auto-tag-date
                tag: CreatedDate
                format: "%m-%d-%Y"

    """

    schema = type_schema('auto-tag-date', rinherit=AutoTagBase.schema,
                         **{'format': {'type': 'string'}})

    event_time_path = jmespath_compile(constants.EVENT_GRID_EVENT_TIME_PATH)
    log = logging.getLogger('custodian.azure.tagging.AutoTagDate')

    def __init__(self, data=None, manager=None, log_dir=None):
        super(AutoTagDate, self).__init__(data, manager, log_dir)
        self.format = self.data.get('format', '%m.%d.%Y')

    def validate(self):
        super(AutoTagDate, self).validate()
        try:
            datetime.datetime.now().strftime(self.format)
        except Exception:
            raise FilterValidationError("'%s' string has invalid datetime format." % self.format)

    def _get_tag_value_from_event(self, event):
        event_time = Deserializer.deserialize_iso(self.event_time_path.search(event))
        return event_time.strftime(self.format)

    def _get_tag_value_from_resource(self, resource):
        first_op = self._get_first_event(resource)

        if not first_op:
            return None

        return first_op.event_timestamp.strftime(self.format)


class TagTrim(AzureBaseAction):
    """Automatically remove tags from an azure resource.
    Azure Resources and Resource Groups have a limit of 50 tags.
    In order to make additional tag space on a set of resources,
    this action can be used to remove enough tags to make the
    desired amount of space while preserving a given set of tags.
    Setting the space value to 0 removes all tags but those
    listed to preserve.

    :example:

    .. code-block :: yaml

       policies:
         - name: azure-tag-trim
           comment: |
             Any instances with 49 or more tags get tags removed until
             they match the target tag count, in this case 48, so
             that we free up tag slots for another usage.
           resource: azure.resourcegroup
           filters:
               # Filter down to resources that do not have the space
               # to add additional required tags. For example, if an
               # additional 2 tags need to be added to a resource, with
               # 50 tags as the limit, then filter down to resources that
               # have 49 or more tags since they will need to have tags
               # removed for the 2 extra. This also ensures that metrics
               # reporting is correct for the policy.
              - type: value
                key: "length(Tags)"
                op: ge
                value: 49
           actions:
              - type: tag-trim
                space: 2
                preserve:
                 - OwnerContact
                 - Environment
                 - downtime
                 - custodian_status

    """
    max_tag_count = 50

    schema = utils.type_schema(
        'tag-trim',
        space={'type': 'integer'},
        preserve={'type': 'array', 'items': {'type': 'string'}})
    schema_alias = True
    log = logging.getLogger('custodian.azure.tagging.TagTrim')

    def __init__(self, data=None, manager=None, log_dir=None):
        super(TagTrim, self).__init__(data, manager, log_dir)
        self.preserve = set(self.data.get('preserve', {}))
        self.space = self.data.get('space', 1)

    def validate(self):
        if self.space < 0 or self.space > self.max_tag_count:
            raise FilterValidationError("Space must be between 0 and %i" % self.max_tag_count)
        return self

    def _process_resource(self, resource):
        tags = resource.get('tags', {})

        if self.space and len(tags) + self.space <= self.max_tag_count:
            return

        # delete tags
        keys = set(tags)
        tags_to_preserve = self.preserve.intersection(keys)
        candidates = keys - tags_to_preserve

        if self.space:
            # Free up slots to fit
            remove = (len(candidates) -
                      (self.max_tag_count - (self.space + len(tags_to_preserve))))
            candidates = list(sorted(candidates))[:remove]

        if not candidates:
            self.log.warning(
                "Could not find any candidates to trim %s" % resource['id'])
            return

        return TagHelper.remove_tags(self, resource, candidates)


DEFAULT_TAG = "custodian_status"


class TagDelayedAction(AzureBaseAction):
    """Tag resources for future action.

    The optional 'tz' parameter can be used to adjust the clock to align
    with a given timezone. The default value is 'utc'.

    If neither 'days' nor 'hours' is specified, Cloud Custodian will default
    to marking the resource for action 4 days in the future.

    :example:

    .. code-block :: yaml

       policies:
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
        days={'type': 'number', 'minimum': 0, 'exclusiveMinimum': False},
        hours={'type': 'number', 'minimum': 0, 'exclusiveMinimum': False},
        tz={'type': 'string'},
        op={'type': 'string'})
    schema_alias = True
    log = logging.getLogger('custodian.azure.tagging.TagDelayed')

    default_template = 'Resource does not meet policy: {op}@{action_date}'

    def __init__(self, data=None, manager=None, log_dir=None):
        super(TagDelayedAction, self).__init__(data, manager, log_dir)
        self.tz = tzutils.gettz(
            Time.TZ_ALIASES.get(self.data.get('tz', 'utc')))

        msg_tmpl = self.data.get('msg', self.default_template)

        op = self.data.get('op', 'stop')
        days = self.data.get('days', 0)
        hours = self.data.get('hours', 0)
        action_date = self.generate_timestamp(days, hours)

        self.tag = self.data.get('tag', DEFAULT_TAG)
        self.msg = msg_tmpl.format(
            op=op, action_date=action_date)

    def validate(self):
        op = self.data.get('op')
        if self.manager and op not in self.manager.action_registry.keys():
            raise FilterValidationError(
                "mark-for-op specifies invalid op:%s in %s" % (
                    op, self.manager.data))

        self.tz = tzutils.gettz(
            Time.TZ_ALIASES.get(self.data.get('tz', 'utc')))
        if not self.tz:
            raise FilterValidationError(
                "Invalid timezone specified %s in %s" % (
                    self.tz, self.manager.data))
        return self

    def generate_timestamp(self, days, hours):
        from c7n_azure.utils import now
        n = now(tz=self.tz)
        if days is None or hours is None:
            # maintains default value of days being 4 if nothing is provided
            days = 4
        action_date = (n + datetime.timedelta(days=days, hours=hours))
        if hours > 0:
            action_date_string = action_date.strftime('%Y/%m/%d %H%M %Z')
        else:
            action_date_string = action_date.strftime('%Y/%m/%d')

        return action_date_string

    def _process_resource(self, resource):
        tags = resource.get('tags', {})

        # add new tag
        tags[self.tag] = self.msg

        TagHelper.update_resource_tags(self, resource, tags)
        return {self.tag: self.msg}
