# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
"""
Generic Resource Tag / Filters and Actions wrapper

These work for the whole family of resources associated
to ec2 (subnets, vpc, security-groups, volumes, instances,
snapshots) and resources that support Amazon's Resource Groups Tagging API

"""
from collections import Counter
from concurrent.futures import as_completed

from datetime import datetime, timedelta
from dateutil import tz as tzutil
from dateutil.parser import parse

import time

from c7n.manager import resources as aws_resources
from c7n.actions import BaseAction as Action, AutoTagUser
from c7n.exceptions import PolicyValidationError, PolicyExecutionError
from c7n.resources import load_resources
from c7n.filters import Filter, OPERATORS
from c7n.filters.offhours import Time
from c7n import deprecated, utils

DEFAULT_TAG = "maid_status"


def register_ec2_tags(filters, actions):
    filters.register('marked-for-op', TagActionFilter)
    filters.register('tag-count', TagCountFilter)

    actions.register('auto-tag-user', AutoTagUser)
    actions.register('mark-for-op', TagDelayedAction)
    actions.register('tag-trim', TagTrim)

    actions.register('mark', Tag)
    actions.register('tag', Tag)

    actions.register('unmark', RemoveTag)
    actions.register('untag', RemoveTag)
    actions.register('remove-tag', RemoveTag)
    actions.register('rename-tag', RenameTag)
    actions.register('normalize-tag', NormalizeTag)


def register_universal_tags(filters, actions, compatibility=True):
    filters.register('marked-for-op', TagActionFilter)

    if compatibility:
        filters.register('tag-count', TagCountFilter)
        actions.register('mark', UniversalTag)

    actions.register('tag', UniversalTag)
    actions.register('auto-tag-user', AutoTagUser)
    actions.register('mark-for-op', UniversalTagDelayedAction)

    if compatibility:
        actions.register('unmark', UniversalUntag)
        actions.register('untag', UniversalUntag)

    actions.register('remove-tag', UniversalUntag)
    actions.register('rename-tag', UniversalTagRename)


def universal_augment(self, resources):
    # Resource Tagging API Support
    # https://docs.aws.amazon.com/awsconsolehelpdocs/latest/gsg/supported-resources.html
    # Bail on empty set
    if not resources:
        return resources

    region = utils.get_resource_tagging_region(self.resource_type, self.region)
    self.log.debug("Using region %s for resource tagging" % region)
    client = utils.local_session(
        self.session_factory).client('resourcegroupstaggingapi', region_name=region)

    # Lazy for non circular :-(
    from c7n.query import RetryPageIterator
    paginator = client.get_paginator('get_resources')
    paginator.PAGE_ITERATOR_CLS = RetryPageIterator

    rfetch = [r for r in resources if 'Tags' not in r]

    for arn_resource_set in utils.chunks(
            zip(self.get_arns(rfetch), rfetch), 100):
        arn_resource_map = dict(arn_resource_set)
        resource_tag_results = client.get_resources(
            ResourceARNList=list(arn_resource_map.keys())).get(
                'ResourceTagMappingList', ())
        resource_tag_map = {
            r['ResourceARN']: r['Tags'] for r in resource_tag_results}
        for arn, r in arn_resource_map.items():
            r['Tags'] = resource_tag_map.get(arn, [])

    return resources


def _common_tag_processer(executor_factory, batch_size, concurrency, client,
                          process_resource_set, id_key, resources, tags,
                          log):

    error = None
    with executor_factory(max_workers=concurrency) as w:
        futures = []
        for resource_set in utils.chunks(resources, size=batch_size):
            futures.append(
                w.submit(process_resource_set, client, resource_set, tags))

        for f in as_completed(futures):
            if f.exception():
                error = f.exception()
                log.error(
                    "Exception with tags: %s  %s", tags, f.exception())

    if error:
        raise error


class TagTrim(Action):
    """Automatically remove tags from an ec2 resource.

    EC2 Resources have a limit of 50 tags, in order to make
    additional tags space on a set of resources, this action can
    be used to remove enough tags to make the desired amount of
    space while preserving a given set of tags.

    .. code-block :: yaml

       policies:
         - name: ec2-tag-trim
           comment: |
             Any instances with 48 or more tags get tags removed until
             they match the target tag count, in this case 47 so we
             that we free up a tag slot for another usage.
           resource: ec2
           filters:
                 # Filter down to resources which already have 8 tags
                 # as we need space for 3 more, this also ensures that
                 # metrics reporting is correct for the policy.
               - type: value
                 key: "length(Tags)"
                 op: ge
                 value: 48
           actions:
              - type: tag-trim
                space: 3
                preserve:
                  - OwnerContact
                  - ASV
                  - CMDBEnvironment
                  - downtime
                  - custodian_status
    """
    max_tag_count = 50

    schema = utils.type_schema(
        'tag-trim',
        space={'type': 'integer'},
        preserve={'type': 'array', 'items': {'type': 'string'}})
    schema_alias = True

    permissions = ('ec2:DeleteTags',)

    def process(self, resources):
        self.id_key = self.manager.get_model().id

        self.preserve = set(self.data.get('preserve'))
        self.space = self.data.get('space', 3)

        client = utils.local_session(
            self.manager.session_factory).client(self.manager.resource_type.service)

        futures = {}
        mid = self.manager.get_model().id

        with self.executor_factory(max_workers=2) as w:
            for r in resources:
                futures[w.submit(self.process_resource, client, r)] = r
            for f in as_completed(futures):
                if f.exception():
                    self.log.warning(
                        "Error processing tag-trim on resource:%s",
                        futures[f][mid])

    def process_resource(self, client, i):
        # Can't really go in batch parallel without some heuristics
        # without some more complex matching wrt to grouping resources
        # by common tags populations.
        tag_map = {
            t['Key']: t['Value'] for t in i.get('Tags', [])
            if not t['Key'].startswith('aws:')}

        # Space == 0 means remove all but specified
        if self.space and len(tag_map) + self.space <= self.max_tag_count:
            return

        keys = set(tag_map)
        preserve = self.preserve.intersection(keys)
        candidates = keys - self.preserve

        if self.space:
            # Free up slots to fit
            remove = len(candidates) - (
                self.max_tag_count - (self.space + len(preserve)))
            candidates = list(sorted(candidates))[:remove]

        if not candidates:
            self.log.warning(
                "Could not find any candidates to trim %s" % i[self.id_key])
            return

        self.process_tag_removal(i, candidates)

    def process_tag_removal(self, client, resource, tags):
        self.manager.retry(
            client.delete_tags,
            Tags=[{'Key': c} for c in tags],
            Resources=[resource[self.id_key]],
            DryRun=self.manager.config.dryrun)


class TagActionFilter(Filter):
    """Filter resources for tag specified future action

    Filters resources by a 'maid_status' tag which specifies a future
    date for an action.

    The filter parses the tag values looking for an 'op@date'
    string. The date is parsed and compared to do today's date, the
    filter succeeds if today's date is gte to the target date.

    The optional 'skew' parameter provides for incrementing today's
    date a number of days into the future. An example use case might
    be sending a final notice email a few days before terminating an
    instance, or snapshotting a volume prior to deletion.

    The optional 'skew_hours' parameter provides for incrementing the current
    time a number of hours into the future.

    Optionally, the 'tz' parameter can get used to specify the timezone
    in which to interpret the clock (default value is 'utc')

    .. code-block :: yaml

      policies:
        - name: ec2-stop-marked
          resource: ec2
          filters:
            - type: marked-for-op
              # The default tag used is maid_status
              # but that is configurable
              tag: custodian_status
              op: stop
              # Another optional tag is skew
              tz: utc
          actions:
            - type: stop

    """
    schema = utils.type_schema(
        'marked-for-op',
        tag={'type': 'string'},
        tz={'type': 'string'},
        skew={'type': 'number', 'minimum': 0},
        skew_hours={'type': 'number', 'minimum': 0},
        op={'type': 'string'},
        custom={'type': 'boolean'})
    schema_alias = True

    def validate(self):
        if not self.data.get('custom'):
            op = self.data.get('op')
            if self.manager and op not in self.manager.action_registry.keys():
                raise PolicyValidationError(
                    "Invalid marked-for-op op:%s in %s" % (op, self.manager.data))

        tz = tzutil.gettz(Time.TZ_ALIASES.get(self.data.get('tz', 'utc')))
        if not tz:
            raise PolicyValidationError(
                "Invalid timezone specified '%s' in %s" % (
                    self.data.get('tz'), self.manager.data))
        return self

    def __call__(self, i):
        tag = self.data.get('tag', DEFAULT_TAG)
        op = self.data.get('op', 'stop')
        skew = self.data.get('skew', 0)
        skew_hours = self.data.get('skew_hours', 0)
        tz = tzutil.gettz(Time.TZ_ALIASES.get(self.data.get('tz', 'utc')))

        v = None
        for n in i.get('Tags', ()):
            if n['Key'] == tag:
                v = n['Value']
                break

        if v is None:
            return False
        if ':' not in v or '@' not in v:
            return False

        _, tgt = v.rsplit(':', 1)
        action, action_date_str = tgt.strip().split('@', 1)

        if action != op:
            return False

        try:
            action_date = parse(action_date_str)
        except Exception:
            self.log.warning("could not parse tag:%s value:%s on %s" % (
                tag, v, i['InstanceId']))
            return False

        if action_date.tzinfo:
            # if action_date is timezone aware, set to timezone provided
            action_date = action_date.astimezone(tz)
            current_date = datetime.now(tz=tz)
        else:
            current_date = datetime.now()

        return current_date >= (
            action_date - timedelta(days=skew, hours=skew_hours))


class TagCountFilter(Filter):
    """Simplify tag counting..

    ie. these two blocks are equivalent

    .. code-block :: yaml

       - filters:
           - type: value
             op: gte
             count: 8

       - filters:
           - type: tag-count
             count: 8
    """
    schema = utils.type_schema(
        'tag-count',
        count={'type': 'integer', 'minimum': 0},
        op={'enum': list(OPERATORS.keys())})
    schema_alias = True

    def __call__(self, i):
        count = self.data.get('count', 10)
        op_name = self.data.get('op', 'gte')
        op = OPERATORS.get(op_name)
        tag_count = len([
            t['Key'] for t in i.get('Tags', [])
            if not t['Key'].startswith('aws:')])
        return op(tag_count, count)


class Tag(Action):
    """Tag an ec2 resource.
    """

    batch_size = 25
    concurrency = 2

    deprecations = (
        deprecated.alias('mark'),
    )

    schema = utils.type_schema(
        'tag', aliases=('mark',),
        tags={'type': 'object'},
        key={'type': 'string'},
        value={'type': 'string'},
        tag={'type': 'string'},
    )
    schema_alias = True
    permissions = ('ec2:CreateTags',)
    id_key = None

    def validate(self):
        if self.data.get('key') and self.data.get('tag'):
            raise PolicyValidationError(
                "Can't specify both key and tag, choose one in %s" % (
                    self.manager.data,))
        return self

    def process(self, resources):
        # Legacy
        msg = self.data.get('msg')
        msg = self.data.get('value') or msg

        tag = self.data.get('tag', DEFAULT_TAG)
        tag = self.data.get('key') or tag

        # Support setting multiple tags in a single go with a mapping
        tags = self.data.get('tags')

        if tags is None:
            tags = []
        else:
            tags = [{'Key': k, 'Value': v} for k, v in tags.items()]

        if msg:
            tags.append({'Key': tag, 'Value': msg})

        self.interpolate_values(tags)

        batch_size = self.data.get('batch_size', self.batch_size)

        client = self.get_client()
        _common_tag_processer(
            self.executor_factory, batch_size, self.concurrency, client,
            self.process_resource_set, self.id_key, resources, tags, self.log)

    def process_resource_set(self, client, resource_set, tags):
        mid = self.manager.get_model().id
        self.manager.retry(
            client.create_tags,
            Resources=[v[mid] for v in resource_set],
            Tags=tags,
            DryRun=self.manager.config.dryrun)

    def interpolate_single_value(self, tag):
        """Interpolate in a single tag value.
        """
        params = {
            'account_id': self.manager.config.account_id,
            'now': utils.FormatDate.utcnow(),
            'region': self.manager.config.region}
        return str(tag).format(**params)

    def interpolate_values(self, tags):
        """Interpolate in a list of tags - 'old' ec2 format
        """
        for t in tags:
            t['Value'] = self.interpolate_single_value(t['Value'])

    def get_client(self):
        return utils.local_session(self.manager.session_factory).client(
            self.manager.resource_type.service)


class RemoveTag(Action):
    """Remove tags from ec2 resources.
    """

    deprecations = (
        deprecated.alias('unmark'),
        deprecated.alias('untag'),
    )

    batch_size = 100
    concurrency = 2

    schema = utils.type_schema(
        'remove-tag', aliases=('unmark', 'untag', 'remove-tag'),
        tags={'type': 'array', 'items': {'type': 'string'}})
    schema_alias = True
    permissions = ('ec2:DeleteTags',)

    def process(self, resources):
        self.id_key = self.manager.get_model().id

        tags = self.data.get('tags', [DEFAULT_TAG])
        batch_size = self.data.get('batch_size', self.batch_size)

        client = self.get_client()
        _common_tag_processer(
            self.executor_factory, batch_size, self.concurrency, client,
            self.process_resource_set, self.id_key, resources, tags, self.log)

    def process_resource_set(self, client, resource_set, tag_keys):
        return self.manager.retry(
            client.delete_tags,
            Resources=[v[self.id_key] for v in resource_set],
            Tags=[{'Key': k} for k in tag_keys],
            DryRun=self.manager.config.dryrun)

    def get_client(self):
        return utils.local_session(self.manager.session_factory).client(
            self.manager.resource_type.service)


class RenameTag(Action):
    """ Create a new tag with identical value & remove old tag
    """

    schema = utils.type_schema(
        'rename-tag',
        old_key={'type': 'string'},
        new_key={'type': 'string'})
    schema_alias = True

    permissions = ('ec2:CreateTags', 'ec2:DeleteTags')

    tag_count_max = 50

    def delete_tag(self, client, ids, key, value):
        client.delete_tags(
            Resources=ids,
            Tags=[{'Key': key, 'Value': value}])

    def create_tag(self, client, ids, key, value):
        client.create_tags(
            Resources=ids,
            Tags=[{'Key': key, 'Value': value}])

    def process_rename(self, client, tag_value, resource_set):
        """
        Move source tag value to destination tag value

        - Collect value from old tag
        - Delete old tag
        - Create new tag & assign stored value
        """
        self.log.info("Renaming tag on %s instances" % (len(resource_set)))
        old_key = self.data.get('old_key')
        new_key = self.data.get('new_key')

        # We have a preference to creating the new tag when possible first
        resource_ids = [r[self.id_key] for r in resource_set if len(
            r.get('Tags', [])) < self.tag_count_max]
        if resource_ids:
            self.create_tag(client, resource_ids, new_key, tag_value)

        self.delete_tag(
            client, [r[self.id_key] for r in resource_set], old_key, tag_value)

        # For resources with 50 tags, we need to delete first and then create.
        resource_ids = [r[self.id_key] for r in resource_set if len(
            r.get('Tags', [])) > self.tag_count_max - 1]
        if resource_ids:
            self.create_tag(client, resource_ids, new_key, tag_value)

    def create_set(self, instances):
        old_key = self.data.get('old_key', None)
        resource_set = {}
        for r in instances:
            tags = {t['Key']: t['Value'] for t in r.get('Tags', [])}
            if tags[old_key] not in resource_set:
                resource_set[tags[old_key]] = []
            resource_set[tags[old_key]].append(r)
        return resource_set

    def filter_resources(self, resources):
        old_key = self.data.get('old_key', None)
        filtered_resources = [
            r for r in resources
            if old_key in (t['Key'] for t in r.get('Tags', []))
        ]
        return filtered_resources

    def process(self, resources):
        count = len(resources)
        resources = self.filter_resources(resources)
        self.log.info(
            "Filtered from %s resources to %s" % (count, len(resources)))
        self.id_key = self.manager.get_model().id
        resource_set = self.create_set(resources)

        client = self.get_client()
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for r in resource_set:
                futures.append(
                    w.submit(self.process_rename, client, r, resource_set[r]))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception renaming tag set \n %s" % (
                            f.exception()))
        return resources

    def get_client(self):
        return utils.local_session(self.manager.session_factory).client(
            self.manager.resource_type.service)


class TagDelayedAction(Action):
    """Tag resources for future action.

    The optional 'tz' parameter can be used to adjust the clock to align
    with a given timezone. The default value is 'utc'.

    If neither 'days' nor 'hours' is specified, Cloud Custodian will default
    to marking the resource for action 4 days in the future.

    .. code-block :: yaml

      policies:
        - name: ec2-mark-for-stop-in-future
          resource: ec2
          filters:
            - type: value
              key: Name
              value: instance-to-stop-in-four-days
          actions:
            - type: mark-for-op
              op: stop
    """
    deprecations = (
        deprecated.optional_fields(('hours', 'days')),
    )

    schema = utils.type_schema(
        'mark-for-op',
        tag={'type': 'string'},
        msg={'type': 'string'},
        days={'type': 'number', 'minimum': 0},
        hours={'type': 'number', 'minimum': 0},
        tz={'type': 'string'},
        op={'type': 'string'},
        custom={'type': 'boolean'})
    schema_alias = True

    batch_size = 200
    concurrency = 2

    default_template = 'Resource does not meet policy: {op}@{action_date}'

    def get_permissions(self):
        return self.manager.action_registry['tag'].permissions

    def validate(self):
        if not self.data.get('custom'):
            op = self.data.get('op')
            if self.manager and op not in self.manager.action_registry.keys():
                raise PolicyValidationError(
                    "mark-for-op specifies invalid op:%s in %s" % (
                        op, self.manager.data))

        self.tz = tzutil.gettz(
            Time.TZ_ALIASES.get(self.data.get('tz', 'utc')))
        if not self.tz:
            raise PolicyValidationError(
                "Invalid timezone specified %s in %s" % (
                    self.tz, self.manager.data))
        return self

    def generate_timestamp(self, days, hours):
        n = datetime.now(tz=self.tz)
        if days is None or hours is None:
            # maintains default value of days being 4 if nothing is provided
            days = 4
        action_date = (n + timedelta(days=days, hours=hours))
        if hours > 0:
            action_date_string = action_date.strftime('%Y/%m/%d %H%M %Z')
        else:
            action_date_string = action_date.strftime('%Y/%m/%d')

        return action_date_string

    def get_config_values(self):
        d = {
            'op': self.data.get('op', 'stop'),
            'tag': self.data.get('tag', DEFAULT_TAG),
            'msg': self.data.get('msg', self.default_template),
            'tz': self.data.get('tz', 'utc'),
            'days': self.data.get('days', 0),
            'hours': self.data.get('hours', 0)}
        d['action_date'] = self.generate_timestamp(
            d['days'], d['hours'])
        return d

    def process(self, resources):
        cfg = self.get_config_values()
        self.tz = tzutil.gettz(Time.TZ_ALIASES.get(cfg['tz']))
        self.id_key = self.manager.get_model().id

        msg = cfg['msg'].format(
            op=cfg['op'], action_date=cfg['action_date'])

        self.log.info("Tagging %d resources for %s on %s" % (
            len(resources), cfg['op'], cfg['action_date']))

        tags = [{'Key': cfg['tag'], 'Value': msg}]

        # if the tag implementation has a specified batch size, it's typically
        # due to some restraint on the api so we defer to that.
        batch_size = getattr(
            self.manager.action_registry.get('tag'), 'batch_size', self.batch_size)

        client = self.get_client()
        _common_tag_processer(
            self.executor_factory, batch_size, self.concurrency, client,
            self.process_resource_set, self.id_key, resources, tags, self.log)

    def process_resource_set(self, client, resource_set, tags):
        tagger = self.manager.action_registry['tag']({}, self.manager)
        tagger.process_resource_set(client, resource_set, tags)

    def get_client(self):
        return utils.local_session(
            self.manager.session_factory).client(
                self.manager.resource_type.service)


class NormalizeTag(Action):
    """Transform the value of a tag.

    Set the tag value to uppercase, title, lowercase, or strip text
    from a tag key.

    .. code-block :: yaml

        policies:
          - name: ec2-service-transform-lower
            resource: ec2
            comment: |
              ec2-service-tag-value-to-lower
            query:
              - instance-state-name: running
            filters:
              - "tag:testing8882": present
            actions:
              - type: normalize-tag
                key: lower_key
                action: lower

          - name: ec2-service-strip
            resource: ec2
            comment: |
              ec2-service-tag-strip-blah
            query:
              - instance-state-name: running
            filters:
              - "tag:testing8882": present
            actions:
              - type: normalize-tag
                key: strip_key
                action: strip
                value: blah

    """

    schema_alias = True
    schema = utils.type_schema(
        'normalize-tag',
        key={'type': 'string'},
        action={'type': 'string',
                'items': {
                    'enum': ['upper', 'lower', 'title' 'strip', 'replace']}},
        value={'type': 'string'})

    permissions = ('ec2:CreateTags',)

    def create_tag(self, client, ids, key, value):

        self.manager.retry(
            client.create_tags,
            Resources=ids,
            Tags=[{'Key': key, 'Value': value}])

    def process_transform(self, tag_value, resource_set):
        """
        Transform tag value

        - Collect value from tag
        - Transform Tag value
        - Assign new value for key
        """
        self.log.info("Transforming tag value on %s instances" % (
            len(resource_set)))
        key = self.data.get('key')

        c = utils.local_session(self.manager.session_factory).client('ec2')

        self.create_tag(
            c,
            [r[self.id_key] for r in resource_set if len(
                r.get('Tags', [])) < 50],
            key, tag_value)

    def create_set(self, instances):
        key = self.data.get('key', None)
        resource_set = {}
        for r in instances:
            tags = {t['Key']: t['Value'] for t in r.get('Tags', [])}
            if tags[key] not in resource_set:
                resource_set[tags[key]] = []
            resource_set[tags[key]].append(r)
        return resource_set

    def filter_resources(self, resources):
        key = self.data.get('key', None)
        filtered_resources = [
            r for r in resources
            if key in (t['Key'] for t in r.get('Tags', []))
        ]
        return filtered_resources

    def process(self, resources):
        count = len(resources)
        resources = self.filter_resources(resources)
        self.log.info(
            "Filtered from %s resources to %s" % (count, len(resources)))
        self.id_key = self.manager.get_model().id
        resource_set = self.create_set(resources)
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for r in resource_set:
                action = self.data.get('action')
                value = self.data.get('value')
                new_value = False
                if action == 'lower' and not r.islower():
                    new_value = r.lower()
                elif action == 'upper' and not r.isupper():
                    new_value = r.upper()
                elif action == 'title' and not r.istitle():
                    new_value = r.title()
                elif action == 'strip' and value and value in r:
                    new_value = r.strip(value)
                if new_value:
                    futures.append(
                        w.submit(self.process_transform, new_value, resource_set[r]))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception renaming tag set \n %s" % (
                            f.exception()))
        return resources


class UniversalTag(Tag):
    """Applies one or more tags to the specified resources.

    :example:

        .. code-block :: yaml

            policies:
            - name: multiple-tags-example
              comment: |
                Tags any secrets missing either the Environment or ResourceOwner tag
              resource: aws.secrets-manager
              filters:
                - or:
                  - "tag:Environment": absent
                  - "tag:ResourceOwner": absent
              actions:
                - type: tag
                  tags:
                    Environment: Staging
                    ResourceOwner: Avengers
    """

    batch_size = 20
    concurrency = 1
    permissions = ('tag:TagResources',)

    def process(self, resources):
        self.id_key = self.manager.get_model().id

        # Legacy
        msg = self.data.get('msg')
        msg = self.data.get('value') or msg

        tag = self.data.get('tag', DEFAULT_TAG)
        tag = self.data.get('key') or tag

        # Support setting multiple tags in a single go with a mapping
        tags = self.data.get('tags', {})

        if msg:
            tags[tag] = msg

        self.interpolate_values(tags)

        batch_size = self.data.get('batch_size', self.batch_size)
        client = self.get_client()

        _common_tag_processer(
            self.executor_factory, batch_size, self.concurrency, client,
            self.process_resource_set, self.id_key, resources, tags, self.log)

    def process_resource_set(self, client, resource_set, tags):
        arns = self.manager.get_arns(resource_set)
        return universal_retry(
            client.tag_resources, ResourceARNList=arns, Tags=tags)

    def interpolate_values(self, tags):
        """Interpolate in a list of tags - 'new' resourcegroupstaggingapi format
        """
        for key in list(tags.keys()):
            tags[key] = self.interpolate_single_value(tags[key])

    def get_client(self):
        # For global resources, manage tags from us-east-1
        region = (getattr(self.manager.resource_type, 'global_resource', None)
            and 'us-east-1' or self.manager.region)
        return utils.local_session(self.manager.session_factory).client(
            'resourcegroupstaggingapi', region_name=region)


class UniversalUntag(RemoveTag):
    """Removes the specified tags from the specified resources.
    """

    batch_size = 20
    concurrency = 1
    permissions = ('tag:UntagResources',)

    def get_client(self):
        # For global resources, manage tags from us-east-1
        region = (getattr(self.manager.resource_type, 'global_resource', None)
            and 'us-east-1' or self.manager.region)
        return utils.local_session(self.manager.session_factory).client(
            'resourcegroupstaggingapi', region_name=region)

    def process_resource_set(self, client, resource_set, tag_keys):
        arns = self.manager.get_arns(resource_set)
        return universal_retry(
            client.untag_resources, ResourceARNList=arns, TagKeys=tag_keys)


class UniversalTagRename(Action):
    """Rename an existing tag key to a new value.

    :example:

    rename Application, and Bap to App, if a resource has both of the old keys
    then we'll use the value specified by Application, which is based on the
    order of values of old_keys.

        .. code-block :: yaml

            policies:
            - name: rename-tags-example
              resource: aws.log-group
              filters:
                - or:
                  - "tag:Bap": present
                  - "tag:Application": present
              actions:
                - type: rename-tag
                  old_keys: [Application, Bap]
                  new_key: App
    """
    schema = utils.type_schema(
        'rename-tag',
        old_keys={'type': 'array', 'items': {'type': 'string'}},
        old_key={'type': 'string'},
        new_key={'type': 'string'},
    )

    permissions = UniversalTag.permissions + UniversalUntag.permissions

    def validate(self):
        if 'old_keys' not in self.data and 'old_key' not in self.data:
            raise PolicyValidationError(
                f"{self.manager.ctx.policy.name}:{self.type} 'old_keys' or 'old_key' required")

    def process(self, resources):
        old_keys = set(self.data.get('old_keys', ()))
        if 'old_key' in self.data:
            old_keys.add(self.data['old_key'])

        # Collect by distinct tag value, and old_key value to minimize api calls
        # via bulk api usage on add and remove.
        old_key_resources = {}
        values_resources = {}

        # sort tags using ordering of old_keys
        def key_func(a):
            if a['Key'] in old_keys:
                return self.data['old_keys'].index(a['Key'])
            return 50

        for r in resources:
            found = False
            for t in sorted(r.get('Tags', ()), key=key_func):
                if t['Key'] in old_keys:
                    old_key_resources.setdefault(t['Key'], []).append(r)
                    if not found:
                        values_resources.setdefault(t['Value'], []).append(r)
                        found = True

        new_key = self.data['new_key']

        for value, rpopulation in values_resources.items():
            tagger = UniversalTag({'key': new_key, 'value': value}, self.manager)
            tagger.process(rpopulation)
        for old_key, rpopulation in old_key_resources.items():
            cleaner = UniversalUntag({'tags': [old_key]}, self.manager)
            cleaner.process(rpopulation)


class UniversalTagDelayedAction(TagDelayedAction):
    """Tag resources for future action.

    :example:

        .. code-block :: yaml

            policies:
            - name: ec2-mark-stop
              resource: ec2
              filters:
                - type: image-age
                  op: ge
                  days: 90
              actions:
                - type: mark-for-op
                  tag: custodian_cleanup
                  op: terminate
                  days: 4
    """

    batch_size = 20
    concurrency = 1

    def process(self, resources):
        self.tz = tzutil.gettz(
            Time.TZ_ALIASES.get(self.data.get('tz', 'utc')))
        self.id_key = self.manager.get_model().id

        # Move this to policy? / no resources bypasses actions?
        if not len(resources):
            return

        msg_tmpl = self.data.get('msg', self.default_template)

        op = self.data.get('op', 'stop')
        tag = self.data.get('tag', DEFAULT_TAG)
        days = self.data.get('days', 0)
        hours = self.data.get('hours', 0)
        action_date = self.generate_timestamp(days, hours)

        msg = msg_tmpl.format(
            op=op, action_date=action_date)

        self.log.info("Tagging %d resources for %s on %s" % (
            len(resources), op, action_date))

        tags = {tag: msg}

        batch_size = self.data.get('batch_size', self.batch_size)
        client = self.get_client()

        _common_tag_processer(
            self.executor_factory, batch_size, self.concurrency, client,
            self.process_resource_set, self.id_key, resources, tags, self.log)

    def process_resource_set(self, client, resource_set, tags):
        arns = self.manager.get_arns(resource_set)
        return universal_retry(
            client.tag_resources, ResourceARNList=arns, Tags=tags)

    def get_client(self):
        # For global resources, manage tags from us-east-1
        region = (getattr(self.manager.resource_type, 'global_resource', None)
            and 'us-east-1' or self.manager.region)
        return utils.local_session(self.manager.session_factory).client(
            'resourcegroupstaggingapi', region_name=region)


class CopyRelatedResourceTag(Tag):
    """
    Copy a related resource tag to its associated resource

    In some scenarios, resource tags from a related resource should be applied
    to its child resource. For example, EBS Volume tags propogating to their
    snapshots. To use this action, specify the resource type that contains the
    tags that are to be copied, which can be found by using the
    `custodian schema` command.

    Then, specify the key on the resource that references the related resource.
    In the case of ebs-snapshot, the VolumeId attribute would be the key that
    identifies the related resource, ebs.

    Finally, specify a list of tag keys to copy from the related resource onto
    the original resource. The special character "*" can be used to signify that
    all tags from the related resource should be copied to the original resource.

    To raise an error when related resources cannot be found, use the
    `skip_missing` option. By default, this is set to True.

    :example:

    .. code-block:: yaml

            policies:
                - name: copy-tags-from-ebs-volume-to-snapshot
                  resource: ebs-snapshot
                  actions:
                    - type: copy-related-tag
                      resource: ebs
                      skip_missing: True
                      key: VolumeId
                      tags: '*'

    In the event that the resource type is not supported in Cloud Custodian but
    is supported in the resources groups tagging api, use the resourcegroupstaggingapi
    resource type to reference the resource. The value should be an ARN for the
    related resource.

    :example:

    .. code-block:: yaml

            policies:
                - name: copy-tags-from-unsupported-resource
                  resource: ebs-snapshot
                  actions:
                    - type: copy-related-tag
                      resource: resourcegroupstaggingapi
                      key: tag:a-resource-tag
                      tags: '*'

    """

    schema = utils.type_schema(
        'copy-related-tag',
        resource={'type': 'string'},
        skip_missing={'type': 'boolean'},
        key={'type': 'string'},
        tags={'oneOf': [
            {'enum': ['*']},
            {'type': 'array'}
        ]},
        required=['tags', 'key', 'resource']
    )
    schema_alias = True

    def get_permissions(self):
        return self.manager.action_registry.get('tag').permissions

    def validate(self):
        related_resource = self.data['resource']
        if '.' in self.data['resource']:
            related_resource = self.data['resource'].split('.')[-1]
        load_resources((f'aws.{related_resource}', ))
        if (
            related_resource not in aws_resources.keys() and
            related_resource != "resourcegroupstaggingapi"
        ):
            raise PolicyValidationError(
                "Error: Invalid resource type selected: %s" % related_resource
            )
        # ideally should never raise here since we shouldn't be applying this
        # action to a resource if it doesn't have a tag action implemented
        if self.manager.action_registry.get('tag') is None:
            raise PolicyValidationError(
                "Error: Tag action missing on resource"
            )
        return self

    def process(self, resources):
        related_resources = []
        if self.data['key'].startswith('tag:'):
            tag_key = self.data['key'].split(':', 1)[-1]

            search_path = "[].[Tags[?Key=='%s'].Value | [0]]" % tag_key
        else:
            search_path = "[].[%s]" % self.data['key']

        for rrid, r in zip(utils.jmespath_search(search_path, resources),
                           resources):
            related_resources.append((rrid.pop(), r))

        related_ids = {r[0] for r in related_resources}
        missing = False
        if None in related_ids:
            missing = True
            related_ids.discard(None)
        related_tag_map = {}
        if self.data['resource'] == 'resourcegroupstaggingapi':
            related_tag_map = self.get_resource_tag_map_universal(related_ids)
        else:
            related_tag_map = self.get_resource_tag_map(self.data['resource'], related_ids)

        missing_related_tags = related_ids.difference(related_tag_map.keys())
        if not self.data.get('skip_missing', True) and (missing_related_tags or missing):
            raise PolicyExecutionError(
                "Unable to find all %d %s related resources tags %d missing" % (
                    len(related_ids), self.data['resource'],
                    len(missing_related_tags) + int(missing)))

        # rely on resource manager tag action implementation as it can differ between resources
        tag_action = self.manager.action_registry.get('tag')({}, self.manager)
        tag_action.id_key = tag_action.manager.get_model().id
        client = tag_action.get_client()

        stats = Counter()

        for related, r in related_resources:
            if (related is None or
                related in missing_related_tags or
                    not related_tag_map[related]):
                stats['missing'] += 1
            elif self.process_resource(
                    client, r, related_tag_map[related], self.data['tags'], tag_action):
                stats['tagged'] += 1
            else:
                stats['unchanged'] += 1

        self.log.info(
            'Tagged %d resources from related, missing-skipped %d unchanged %d',
            stats['tagged'], stats['missing'], stats['unchanged'])

    def process_resource(self, client, r, related_tags, tag_keys, tag_action):
        tags = {}
        resource_tags = {
            t['Key']: t['Value'] for t in r.get('Tags', []) if not t['Key'].startswith('aws:')}

        if tag_keys == '*':
            tags = {k: v for k, v in related_tags.items()
                    if resource_tags.get(k) != v and not k.startswith('aws:')}
        else:
            tags = {k: v for k, v in related_tags.items()
                    if k in tag_keys and resource_tags.get(k) != v}
        if not tags:
            return
        if not isinstance(tag_action, UniversalTag):
            tags = [{'Key': k, 'Value': v} for k, v in tags.items()]
        tag_action.process_resource_set(client, [r], tags)
        return True

    def get_resource_tag_map(self, r_type, ids):
        """
        Returns a mapping of {resource_id: {tagkey: tagvalue}}
        """
        manager = self.manager.get_resource_manager(r_type)
        r_id = manager.resource_type.id

        return {
            r[r_id]: {t['Key']: t['Value'] for t in r.get('Tags', [])}
            for r in manager.get_resources(list(ids))
        }

    def get_resource_tag_map_universal(self, ids):
        related_region = None
        ids = list(ids)
        if ids:
            if ids[0].startswith('arn:aws:iam'):
                related_region = 'us-east-1'
        client = utils.local_session(
            self.manager.session_factory).client(
                'resourcegroupstaggingapi', region_name=related_region)
        from c7n.query import RetryPageIterator
        paginator = client.get_paginator('get_resources')
        paginator.PAGE_ITERATOR_CLS = RetryPageIterator

        resource_tag_results = client.get_resources(
            ResourceARNList=list(ids))['ResourceTagMappingList']
        resource_tag_map = {
            r['ResourceARN']: {r['Key']: r['Value'] for r in r['Tags']}
            for r in resource_tag_results}
        return resource_tag_map

    @classmethod
    def register_resources(klass, registry, resource_class):
        if not resource_class.action_registry.get('tag'):
            return
        resource_class.action_registry.register('copy-related-tag', klass)


aws_resources.subscribe(CopyRelatedResourceTag.register_resources)


def universal_retry(method, ResourceARNList, **kw):
    """Retry support for resourcegroup tagging apis.

    The resource group tagging api typically returns a 200 status code
    with embedded resource specific errors. To enable resource specific
    retry on throttles, we extract those, perform backoff w/ jitter and
    continue. Other errors are immediately raised.

    We do not aggregate unified resource responses across retries, only the
    last successful response is returned for a subset of the resources if
    a retry is performed.
    """
    max_attempts = 6

    for idx, delay in enumerate(
            utils.backoff_delays(1.5, 2 ** 8, jitter=True)):
        response = method(ResourceARNList=ResourceARNList, **kw)
        failures = response.get('FailedResourcesMap', {})
        if not failures:
            return response

        errors = {}
        throttles = set()

        for f_arn in failures:
            error_code = failures[f_arn]['ErrorCode']
            if error_code == 'ThrottlingException':
                throttles.add(f_arn)
            elif error_code == 'ResourceNotFoundException':
                continue
            else:
                errors[f_arn] = error_code

        if errors:
            raise Exception("Resource Tag Errors %s" % (errors))

        if idx == max_attempts - 1:
            raise Exception("Resource Tag Throttled %s" % (", ".join(throttles)))

        time.sleep(delay)
        ResourceARNList = list(throttles)


def coalesce_copy_user_tags(resource, copy_tags, user_tags):
    """
    Returns a list of tags from resource and user supplied in
    the format: [{'Key': 'key', 'Value': 'value'}]

    Due to drift on implementation on copy-tags/tags used throughout
    the code base, the following options are supported:

        copy_tags (Tags to copy from the resource):
          - list of str, e.g. ['key1', 'key2', '*']
          - bool

        user_tags (User supplied tags to apply):
          - dict of key-value pairs, e.g. {Key: Value, Key2: Value}
          - list of dict e.g. [{'Key': k, 'Value': v}]

    In the case that there is a conflict in a user supplied tag
    and an existing tag on the resource, the user supplied tags will
    take priority.

    Additionally, a value of '*' in copy_tags can be used to signify
    to copy all tags from the resource.
    """

    assert isinstance(copy_tags, bool) or isinstance(copy_tags, list)
    assert isinstance(user_tags, dict) or isinstance(user_tags, list)

    r_tags = resource.get('Tags', [])

    if isinstance(copy_tags, list):
        if '*' in copy_tags:
            copy_keys = {t['Key'] for t in r_tags if not t['Key'].startswith('aws:')}
        else:
            copy_keys = set(copy_tags)

    if isinstance(copy_tags, bool):
        if copy_tags is True:
            copy_keys = {t['Key'] for t in r_tags if not t['Key'].startswith('aws:')}
        else:
            copy_keys = set()

    if isinstance(user_tags, dict):
        user_tags = [{'Key': k, 'Value': v} for k, v in user_tags.items()]

    user_keys = {t['Key'] for t in user_tags}
    tags_diff = list(copy_keys.difference(user_keys))
    resource_tags_to_copy = [t for t in r_tags if t['Key'] in tags_diff]
    user_tags.extend(resource_tags_to_copy)
    return user_tags
