import datetime
import logging
from email.utils import parseaddr

import jmespath
from c7n_azure import constants
from c7n_azure.tags import TagHelper
from c7n_azure.utils import StringUtils
from dateutil import tz as tzutils
from c7n_azure.actions.base import AzureBaseAction, AzureEventAction

from c7n import utils
from c7n.exceptions import PolicyValidationError
from c7n.filters import FilterValidationError
from c7n.filters.offhours import Time


class Tag(AzureBaseAction):
    """Adds tags to Azure resources

    :example: This policy will tag all existing resource groups with a value such as Environment

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
    schema_alias = True

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

    def _prepare_processing(self,):
        self.new_tags = self.data.get('tags') or {self.data.get('tag'): self.data.get('value')}

    def _process_resource(self, resource):
        TagHelper.add_tags(self, resource, self.new_tags)


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
        TagHelper.remove_tags(self, resource, self.tags_to_delete)


class AutoTagUser(AzureEventAction):
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
    default_user = "Unknown"
    query_select = "eventTimestamp, operationName, caller"
    max_query_days = 90

    # compiled JMES paths
    service_admin_jmes_path = jmespath.compile(constants.EVENT_GRID_SERVICE_ADMIN_JMES_PATH)
    sp_jmes_path = jmespath.compile(constants.EVENT_GRID_SP_NAME_JMES_PATH)
    upn_jmes_path = jmespath.compile(constants.EVENT_GRID_UPN_CLAIM_JMES_PATH)
    principal_role_jmes_path = jmespath.compile(constants.EVENT_GRID_PRINCIPAL_ROLE_JMES_PATH)
    principal_type_jmes_path = jmespath.compile(constants.EVENT_GRID_PRINCIPAL_TYPE_JMES_PATH)

    schema = utils.type_schema(
        'auto-tag-user',
        required=['tag'],
        **{'update': {'type': 'boolean'},
           'tag': {'type': 'string'},
           'days': {'type': 'integer'}})
    schema_alias = True

    def __init__(self, data=None, manager=None, log_dir=None):
        super(AutoTagUser, self).__init__(data, manager, log_dir)
        self.log = logging.getLogger('custodian.azure.actions.auto-tag-user')

    def validate(self):

        if self.manager.action_registry.get('tag') is None:
            raise FilterValidationError("Resource does not support tagging")

        if self.manager.data.get('mode', {}).get('type') == 'azure-event-grid' \
                and self.data.get('days') is not None:
            raise PolicyValidationError(
                "Auto tag user in event mode does not use days.")

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

        user = self.default_user
        if event:
            user = self._get_user_from_event(event) or user
        else:
            user = self._get_user_from_resource_logs(resource) or user

        # issue tag action to label user
        TagHelper.add_tags(self, resource, {self.tag_key: user})

    def _get_user_from_event(self, event):
        principal_role = self.principal_role_jmes_path.search(event)
        principal_type = self.principal_type_jmes_path.search(event)
        user = None
        # The Subscription Admins role does not have a principal type
        if StringUtils.equal(principal_role, 'Subscription Admin'):
            user = self.service_admin_jmes_path.search(event)
        # ServicePrincipal type
        elif StringUtils.equal(principal_type, 'ServicePrincipal'):
            user = self.sp_jmes_path.search(event)

        # Other types and main fallback (e.g. User, Office 365 Groups, and Security Groups)
        if not user and self.upn_jmes_path.search(event):
            user = self.upn_jmes_path.search(event)

        # Last effort search for an email address in the claims
        if not user:
            claims = event['data']['claims']
            for c in claims:
                value = claims[c]
                if self._is_email(value):
                    user = value

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

    def _get_user_from_resource_logs(self, resource):
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
                "eventChannels eq 'Operation'"
            ])
        # other Azure resources
        else:
            resource_type = resource['type']
            query_filter = " and ".join([
                "eventTimestamp ge '%s'" % start_time,
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
        return first_op.caller if first_op else None

    @staticmethod
    def get_first_operation(logs, operation_name):
        first_operation = None
        for l in logs:
            if l.operation_name.value and l.operation_name.value.lower() == operation_name.lower():
                first_operation = l

        return first_operation


class TagTrim(AzureBaseAction):
    """Automatically remove tags from an azure resource.
    Azure Resources and Resource Groups have a limit of 15 tags.
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
              - type: value
                key: "length(Tags)"
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
    schema_alias = True

    def __init__(self, data=None, manager=None, log_dir=None):
        super(TagTrim, self).__init__(data, manager, log_dir)
        self.preserve = set(self.data.get('preserve', {}))
        self.space = self.data.get('space', 1)

    def validate(self):
        if self.space < 0 or self.space > 15:
            raise FilterValidationError("Space must be between 0 and 15")
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

        TagHelper.remove_tags(self, resource, candidates)


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
        days={'type': 'integer', 'minimum': 0, 'exclusiveMinimum': False},
        hours={'type': 'integer', 'minimum': 0, 'exclusiveMinimum': False},
        tz={'type': 'string'},
        op={'type': 'string'})
    schema_alias = True

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
            raise PolicyValidationError(
                "mark-for-op specifies invalid op:%s in %s" % (
                    op, self.manager.data))

        self.tz = tzutils.gettz(
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
