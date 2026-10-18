# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging

from botocore.exceptions import ClientError

from c7n.actions import Action, BaseAction
from c7n.exceptions import PolicyExecutionError, PolicyValidationError
from c7n.filters import ValueFilter, Filter
from c7n.manager import resources
from c7n.tags import universal_augment
from c7n.query import ConfigSource, DescribeSource, QueryResourceManager, TypeInfo
from c7n.utils import local_session, type_schema

from .aws import shape_validate, Arn

log = logging.getLogger('c7n.resources.cloudtrail')


class DescribeTrail(DescribeSource):

    def augment(self, resources):
        return universal_augment(self.manager, resources)


def get_trail_groups(session_factory, trails):
    # returns a dictionary -> key: region value: (client, trails)
    grouped = {}
    for t in trails:
        region = Arn.parse(t['TrailARN']).region
        client, trails = grouped.setdefault(region, (None, []))
        trails.append(t)
        if client is None:
            client = local_session(session_factory).client(
                'cloudtrail', region_name=region)
        grouped[region] = client, trails
    return grouped


@resources.register('cloudtrail')
class CloudTrail(QueryResourceManager):
    class resource_type(TypeInfo):
        service = 'cloudtrail'
        enum_spec = ('describe_trails', 'trailList', None)
        filter_name = 'trailNameList'
        filter_type = 'list'
        arn_type = 'trail'
        arn = id = 'TrailARN'
        name = 'Name'
        cfn_type = config_type = "AWS::CloudTrail::Trail"
        universal_taggable = object()

    source_mapping = {
        'describe': DescribeTrail,
        'config': ConfigSource
    }


@CloudTrail.filter_registry.register('is-shadow')
class IsShadow(Filter):
    """Identify shadow trails (secondary copies), shadow trails
    can't be modified directly, the origin trail needs to be modified.

    Shadow trails are created for multi-region trails as well for
    organizational trails.
    """
    schema = type_schema('is-shadow', state={'type': 'boolean'})
    permissions = ('cloudtrail:DescribeTrails',)
    embedded = False

    def process(self, resources, event=None):
        rcount = len(resources)
        trails = [t for t in resources if (self.is_shadow(t) == self.data.get('state', True))]
        if len(trails) != rcount and self.embedded:
            self.log.info("implicitly filtering shadow trails %d -> %d",
                          rcount, len(trails))
        return trails

    def is_shadow(self, t):
        if t.get('IsOrganizationTrail') and self.manager.config.account_id not in t['TrailARN']:
            return True
        if t.get('IsMultiRegionTrail') and t['HomeRegion'] != self.manager.config.region:
            return True
        return False


@CloudTrail.filter_registry.register('status')
class Status(ValueFilter):
    """Filter a cloudtrail by its status.

    :Example:

    .. code-block:: yaml

        policies:
          - name: cloudtrail-check-status
            resource: aws.cloudtrail
            filters:
            - type: status
              key: IsLogging
              value: False
    """

    schema = type_schema('status', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('cloudtrail:GetTrailStatus',)
    annotation_key = 'c7n:TrailStatus'

    def process(self, resources, event=None):
        grouped_trails = get_trail_groups(self.manager.session_factory, resources)
        for region, (client, trails) in grouped_trails.items():
            for t in trails:
                if self.annotation_key in t:
                    continue
                status = client.get_trail_status(Name=t['TrailARN'])
                status.pop('ResponseMetadata')
                t[self.annotation_key] = status
        return super(Status, self).process(resources)

    def __call__(self, r):
        return self.match(r[self.annotation_key])


@CloudTrail.filter_registry.register('event-selectors')
class EventSelectors(ValueFilter):
    """Filter a cloudtrail by its related Event Selectors.

    :example:

    .. code-block:: yaml

      policies:
        - name: cloudtrail-event-selectors
          resource: aws.cloudtrail
          filters:
          - type: event-selectors
            key: EventSelectors[].IncludeManagementEvents
            op: contains
            value: True
    """

    schema = type_schema('event-selectors', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('cloudtrail:GetEventSelectors',)
    annotation_key = 'c7n:TrailEventSelectors'

    def process(self, resources, event=None):
        grouped_trails = get_trail_groups(self.manager.session_factory, resources)
        for region, (client, trails) in grouped_trails.items():
            for t in trails:
                if self.annotation_key in t:
                    continue
                selectors = client.get_event_selectors(TrailName=t['TrailARN'])
                selectors.pop('ResponseMetadata')
                t[self.annotation_key] = selectors
        return super(EventSelectors, self).process(resources)

    def __call__(self, r):
        return self.match(r[self.annotation_key])


@CloudTrail.action_registry.register('update-trail')
class UpdateTrail(Action):
    """Update trail attributes.

    :Example:

    .. code-block:: yaml

       policies:
         - name: cloudtrail-set-log
           resource: aws.cloudtrail
           filters:
            - or:
              - KmsKeyId: empty
              - LogFileValidationEnabled: false
           actions:
            - type: update-trail
              attributes:
                KmsKeyId: arn:aws:kms:us-west-2:111122223333:key/1234abcd-12ab-34cd-56ef
                EnableLogFileValidation: true
    """
    schema = type_schema(
        'update-trail',
        attributes={'type': 'object'},
        required=('attributes',))
    shape = 'UpdateTrailRequest'
    permissions = ('cloudtrail:UpdateTrail',)

    def validate(self):
        attrs = dict(self.data['attributes'])
        if 'Name' in attrs:
            raise PolicyValidationError(
                "Can't include Name in update-trail action")
        attrs['Name'] = 'PolicyValidation'
        return shape_validate(
            attrs,
            self.shape,
            self.manager.resource_type.service)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('cloudtrail')
        shadow_check = IsShadow({'state': False}, self.manager)
        shadow_check.embedded = True
        resources = shadow_check.process(resources)

        for r in resources:
            client.update_trail(
                Name=r['Name'],
                **self.data['attributes'])


@CloudTrail.action_registry.register('set-event-selectors')
class SetEventSelectors(Action):
    """Set the event selectors of a trail.

    Specify either ``event-selectors`` (basic) or
    ``advanced-event-selectors``, not both.

    This replaces all of the trail's existing selectors, of either type,
    so include every selector the trail should keep. When pairing this
    action with the ``event-selectors`` filter, filter on the same
    selector type the action writes; otherwise the filter keeps matching
    and the policy re-applies the change on every run.

    See the `PutEventSelectors API reference
    <https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_PutEventSelectors.html>`__
    for the syntax of both selector types, and `Logging data events
    <https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html>`__
    for a detailed comparison and examples.

    :Example:

    .. code-block:: yaml

      policies:
        - name: cloudtrail-log-s3-writes
          resource: aws.cloudtrail
          filters:
           - type: is-shadow
             state: false
           - type: event-selectors
             key: AdvancedEventSelectors
             value: empty
          actions:
           - type: set-event-selectors
             advanced-event-selectors:
              - Name: Log all management events
                FieldSelectors:
                  - Field: eventCategory
                    Equals: [Management]
              - Name: Log S3 object writes
                FieldSelectors:
                  - Field: eventCategory
                    Equals: [Data]
                  - Field: resources.type
                    Equals: [AWS::S3::Object]
                  - Field: readOnly
                    Equals: ["false"]
    """
    schema = type_schema(
        'set-event-selectors',
        **{
            'event-selectors': {
                'type': 'array', 'items': {'type': 'object'}, 'minItems': 1},
            'advanced-event-selectors': {
                'type': 'array', 'items': {'type': 'object'}, 'minItems': 1},
        })
    schema['oneOf'] = [
        {'required': ['event-selectors']},
        {'required': ['advanced-event-selectors']},
    ]
    shape = 'PutEventSelectorsRequest'
    permissions = ('cloudtrail:PutEventSelectors',)

    def get_params(self):
        params = {}
        if 'event-selectors' in self.data:
            params['EventSelectors'] = self.data['event-selectors']
        if 'advanced-event-selectors' in self.data:
            params['AdvancedEventSelectors'] = self.data['advanced-event-selectors']
        return params

    def validate(self):
        # mirrors the schema's oneOf/minItems, which only applies when
        # schema validation is enabled
        params = self.get_params()
        if len(params) != 1 or not all(params.values()):
            raise PolicyValidationError(
                "set-event-selectors requires exactly one non-empty list of "
                "event-selectors or advanced-event-selectors on %s" % (
                    self.manager.data,))
        params['TrailName'] = 'PolicyValidation'
        return shape_validate(
            params,
            self.shape,
            self.manager.resource_type.service)

    def process(self, resources):
        shadow_check = IsShadow({'state': False}, self.manager)
        shadow_check.embedded = True
        resources = shadow_check.process(resources)
        params = self.get_params()

        errors = []
        grouped_trails = get_trail_groups(self.manager.session_factory, resources)
        for region, (client, trails) in grouped_trails.items():
            for t in trails:
                try:
                    self.manager.retry(
                        client.put_event_selectors, TrailName=t['TrailARN'], **params)
                except client.exceptions.TrailNotFoundException:
                    self.log.warning(
                        "trail %s no longer exists, skipping", t['TrailARN'])
                    continue
                except ClientError as e:
                    self.log.error(
                        "failed to set event selectors on %s: %s", t['TrailARN'], e)
                    errors.append(t['TrailARN'])
                    continue
                # drop any stale filter annotation
                t.pop(EventSelectors.annotation_key, None)
        if errors:
            raise PolicyExecutionError(
                "set-event-selectors failed on %d trail(s): %s" % (
                    len(errors), ", ".join(errors)))


@CloudTrail.action_registry.register('set-logging')
class SetLogging(Action):
    """Set the logging state of a trail

    :Example:

    .. code-block:: yaml

      policies:
        - name: cloudtrail-set-active
          resource: aws.cloudtrail
          filters:
           - type: status
             key: IsLogging
             value: False
          actions:
           - type: set-logging
             enabled: True
    """
    schema = type_schema(
        'set-logging', enabled={'type': 'boolean'})

    def get_permissions(self):
        enable = self.data.get('enabled', True)
        if enable is True:
            return ('cloudtrail:StartLogging',)
        else:
            return ('cloudtrail:StopLogging',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('cloudtrail')
        shadow_check = IsShadow({'state': False}, self.manager)
        shadow_check.embedded = True
        resources = shadow_check.process(resources)
        enable = self.data.get('enabled', True)

        for r in resources:
            if enable:
                client.start_logging(Name=r['Name'])
            else:
                client.stop_logging(Name=r['Name'])


@CloudTrail.action_registry.register('delete')
class DeleteTrail(BaseAction):
    """ Delete a cloud trail

    :example:

    .. code-block:: yaml

      policies:
        - name: delete-cloudtrail
          resource: aws.cloudtrail
          filters:
           - type: value
             key: Name
             value: delete-me
             op: eq
          actions:
           - type: delete
    """

    schema = type_schema('delete')
    permissions = ('cloudtrail:DeleteTrail',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('cloudtrail')
        shadow_check = IsShadow({'state': False}, self.manager)
        shadow_check.embedded = True
        resources = shadow_check.process(resources)
        for r in resources:
            try:
                client.delete_trail(Name=r['Name'])
            except client.exceptions.TrailNotFoundException:
                continue
