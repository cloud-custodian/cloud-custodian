# Copyright 2016-2017 Capital One Services, LLC
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
Generic EC2 Resource Tag / Filters and actions

These work for the whole family of resources associated
to ec2 (subnets, vpc, security-groups, volumes, instances,
snapshots).

"""
from __future__ import absolute_import, division, print_function, unicode_literals

from concurrent.futures import as_completed

from datetime import datetime, timedelta
from dateutil.parser import parse
from dateutil.tz import tzutc

import itertools

from c7n.actions import BaseAction as Action, AutoTagUser
from c7n.filters import Filter, OPERATORS, FilterValidationError
from c7n import utils

DEFAULT_TAG = "maid_status"

universal_tag_retry = utils.get_retry((
    'Throttled',
    'RequestLimitExceeded',
    'Client.RequestLimitExceeded'
))


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


def register_universal_tags(filters, actions):
    filters.register('marked-for-op', TagActionFilter)
    filters.register('tag-count', TagCountFilter)

    actions.register('mark', UniversalTag)
    actions.register('tag', UniversalTag)

    actions.register('auto-tag-user', AutoTagUser)
    actions.register('mark-for-op', UniversalTagDelayedAction)

    actions.register('unmark', UniversalUntag)
    actions.register('untag', UniversalUntag)
    actions.register('remove-tag', UniversalUntag)


def universal_augment(self, resources):
    # Resource Tagging API Support
    # https://goo.gl/uccKc9

    client = utils.local_session(
        self.session_factory).client('resourcegroupstaggingapi')

    paginator = client.get_paginator('get_resources')
    resource_type = getattr(self.get_model(), 'resource_type', None)

    if not resource_type:
        resource_type = self.get_model().service
        if self.get_model().type:
            resource_type += ":" + self.get_model().type

    resource_tag_map_list = list(itertools.chain(
        *[p['ResourceTagMappingList'] for p in paginator.paginate(
            ResourceTypeFilters=[resource_type])]))
    resource_tag_map = {
        r['ResourceARN']: r['Tags'] for r in resource_tag_map_list}
    for arn, r in zip(self.get_arns(resources), resources):
        if arn in resource_tag_map:
            r['Tags'] = resource_tag_map[arn]
    return resources


def _common_tag_processer(executor_factory, batch_size, concurrency,
                          process_resource_set, id_key, resources, tags,
                          log):

    with executor_factory(max_workers=concurrency) as w:
        futures = []
        for resource_set in utils.chunks(resources, size=batch_size):
            futures.append(
                w.submit(process_resource_set, resource_set, tags))

        for f in as_completed(futures):
            if f.exception():
                log.error(
                    "Exception with tags: %s on resources: %s \n %s" % (
                        tags,
                        ", ".join([r[id_key] for r in resource_set]),
                        f.exception()))


class TagTrim(Action):
    """Automatically remove tags from an ec2 resource.

    EC2 Resources have a limit of 10 tags, in order to make
    additional tags space on a set of resources, this action can
    be used to remove enough tags to make the desired amount of
    space while preserving a given set of tags.

    .. code-block :: yaml

      - policies:
         - name: ec2-tag-trim
           comment: |
             Any instances with 8 or more tags get tags removed until
             they match the target tag count, in this case 7 so we
             that we free up a tag slot for another usage.
           resource: ec2
           filters:
               # Filter down to resources which already have 8 tags
               # as we need space for 3 more, this also ensures that
               # metrics reporting is correct for the policy.
               type: value
               key: "[length(Tags)][0]"
               op: ge
               value: 8
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

    permissions = ('ec2:DeleteTags',)

    def process(self, resources):
        self.id_key = self.manager.get_model().id

        self.preserve = set(self.data.get('preserve'))
        self.space = self.data.get('space', 3)

        with self.executor_factory(max_workers=3) as w:
            list(w.map(self.process_resource, resources))

    def process_resource(self, i):
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

    def process_tag_removal(self, resource, tags):
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        self.manager.retry(
            client.delete_tags,
            Tags=[{'Key': c} for c in tags],
            Resources=[resource[self.id_key]],
            DryRun=self.manager.config.dryrun)


class TagActionFilter(Filter):
    """Filter resources for tag specified future action

    Filters resources by a 'custodian_status' tag which specifies a future
    date for an action.

    The filter parses the tag values looking for an 'op@date'
    string. The date is parsed and compared to do today's date, the
    filter succeeds if today's date is gte to the target date.

    The optional 'skew' parameter provides for incrementing today's
    date a number of days into the future. An example use case might
    be sending a final notice email a few days before terminating an
    instance, or snapshotting a volume prior to deletion.

    .. code-block :: yaml

      - policies:
        - name: ec2-stop-marked
          resource: ec2
          filters:
            - type: marked-for-op
              # The default tag used is custodian_status
              # but that is configurable
              tag: custodian_status
              op: stop
              # Another optional tag is skew
          actions:
            - stop

    """
    schema = utils.type_schema(
        'marked-for-op',
        tag={'type': 'string'},
        skew={'type': 'number', 'minimum': 0},
        op={'type': 'string'})

    current_date = None

    def validate(self):
        op = self.data.get('op')
        if self.manager and op not in self.manager.action_registry.keys():
            raise FilterValidationError("Invalid marked-for-op op:%s" % op)
        return self

    def __call__(self, i):
        tag = self.data.get('tag', DEFAULT_TAG)
        op = self.data.get('op', 'stop')
        skew = self.data.get('skew', 0)

        v = None
        for n in i.get('Tags', ()):
            if n['Key'] == tag:
                v = n['Value']
                break

        if v is None:
            return False
        if ':' not in v or '@' not in v:
            return False

        msg, tgt = v.rsplit(':', 1)
        action, action_date_str = tgt.strip().split('@', 1)

        if action != op:
            return False

        try:
            action_date = parse(action_date_str)
        except Exception:
            self.log.warning("could not parse tag:%s value:%s on %s" % (
                tag, v, i['InstanceId']))

        if self.current_date is None:
            self.current_date = datetime.now()

        return self.current_date >= (action_date - timedelta(skew))


class TagCountFilter(Filter):
    """Simplify tag counting..

    ie. these two blocks are equivalent

    .. code-block :: yaml

       - filters:
           - type: value
             key: "[length(Tags)][0]"
             op: gte
             value: 8

       - filters:
           - type: tag-count
             value: 8
    """
    schema = utils.type_schema(
        'tag-count',
        count={'type': 'integer', 'minimum': 0},
        op={'enum': list(OPERATORS.keys())})

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

    schema = utils.type_schema(
        'tag', aliases=('mark',),
        tags={'type': 'object'},
        key={'type': 'string'},
        value={'type': 'string'},
        tag={'type': 'string'},
    )

    permissions = ('ec2:CreateTags',)

    def validate(self):
        if self.data.get('key') and self.data.get('tag'):
            raise FilterValidationError(
                "Can't specify both key and tag, choose one")
        return self

    def process(self, resources):
        self.id_key = self.manager.get_model().id

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

        _common_tag_processer(
            self.executor_factory, batch_size, self.concurrency,
            self.process_resource_set, self.id_key, resources, tags, self.log)

    def process_resource_set(self, resource_set, tags):
        client = utils.local_session(
            self.manager.session_factory).client('ec2')

        self.manager.retry(
            client.create_tags,
            Resources=[v[self.id_key] for v in resource_set],
            Tags=tags,
            DryRun=self.manager.config.dryrun)

    def interpolate_values(self, tags):
        params = {
            'account_id': self.manager.config.account_id,
            'now': utils.FormatDate.utcnow(),
            'region': self.manager.config.region}
        interpolate_tag_values(tags, params)


def interpolate_tag_values(tags, params):
    for t in tags:
        t['Value'] = t['Value'].format(**params)


class RemoveTag(Action):
    """Remove tags from ec2 resources.
    """

    batch_size = 100
    concurrency = 2

    schema = utils.type_schema(
        'untag', aliases=('unmark', 'remove-tag'),
        tags={'type': 'array', 'items': {'type': 'string'}})

    permissions = ('ec2:DeleteTags',)

    def process(self, resources):
        self.id_key = self.manager.get_model().id

        tags = self.data.get('tags', [DEFAULT_TAG])
        batch_size = self.data.get('batch_size', self.batch_size)
        _common_tag_processer(
            self.executor_factory, batch_size, self.concurrency,
            self.process_resource_set, self.id_key, resources, tags, self.log)

    def process_resource_set(self, vol_set, tag_keys):
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        return self.manager.retry(
            client.delete_tags,
            Resources=[v[self.id_key] for v in vol_set],
            Tags=[{'Key': k} for k in tag_keys],
            DryRun=self.manager.config.dryrun)


class RenameTag(Action):
    """ Create a new tag with identical value & remove old tag
    """

    schema = utils.type_schema(
        'rename-tag',
        old_key={'type': 'string'},
        new_key={'type': 'string'})

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

    def process_rename(self, tag_value, resource_set):
        """
        Move source tag value to destination tag value

        - Collect value from old tag
        - Delete old tag
        - Create new tag & assign stored value
        """
        self.log.info("Renaming tag on %s instances" % (len(resource_set)))
        old_key = self.data.get('old_key')
        new_key = self.data.get('new_key')

        c = utils.local_session(self.manager.session_factory).client('ec2')

        # We have a preference to creating the new tag when possible first
        resource_ids = [r[self.id_key] for r in resource_set if len(
            r.get('Tags', [])) < self.tag_count_max]
        if resource_ids:
            self.create_tag(c, resource_ids, new_key, tag_value)

        self.delete_tag(
            c, [r[self.id_key] for r in resource_set], old_key, tag_value)

        # For resources with 50 tags, we need to delete first and then create.
        resource_ids = [r[self.id_key] for r in resource_set if len(
            r.get('Tags', [])) > self.tag_count_max - 1]
        if resource_ids:
            self.create_tag(c, resource_ids, new_key, tag_value)

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
        res = 0
        for r in resources:
            tags = {t['Key']: t['Value'] for t in r.get('Tags', [])}
            if old_key not in tags.keys():
                resources.pop(res)
            res += 1
        return resources

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
                futures.append(
                    w.submit(self.process_rename, r, resource_set[r]))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception renaming tag set \n %s" % (
                            f.exception()))
        return resources


class TagDelayedAction(Action):
    """Tag resources for future action.

    .. code-block :: yaml

      - policies:
        - name: ec2-stop-marked
          resource: ec2
          filters:
            - type: marked-for-op
              # The default tag used is custodian_status
              # but that is configurable
              tag: custodian_status
              op: stop
              # Another optional tag is skew
          actions:
            - stop
    """

    schema = utils.type_schema(
        'mark-for-op',
        tag={'type': 'string'},
        msg={'type': 'string'},
        days={'type': 'integer', 'minimum': 0, 'exclusiveMinimum': False},
        op={'type': 'string'})

    permissions = ('ec2:CreateTags',)

    batch_size = 200
    concurrency = 2

    default_template = 'Resource does not meet policy: {op}@{action_date}'

    def validate(self):
        op = self.data.get('op')
        if self.manager and op not in self.manager.action_registry.keys():
            raise FilterValidationError(
                "mark-for-op specifies invalid op:%s" % op)
        return self

    def process(self, resources):
        self.id_key = self.manager.get_model().id

        # Move this to policy? / no resources bypasses actions?
        if not len(resources):
            return

        msg_tmpl = self.data.get('msg', self.default_template)

        op = self.data.get('op', 'stop')
        tag = self.data.get('tag', DEFAULT_TAG)
        date = self.data.get('days', 4)

        n = datetime.now(tz=tzutc())
        action_date = n + timedelta(days=date)
        msg = msg_tmpl.format(
            op=op, action_date=action_date.strftime('%Y/%m/%d'))

        self.log.info("Tagging %d resources for %s on %s" % (
            len(resources), op, action_date.strftime('%Y/%m/%d')))

        tags = [{'Key': tag, 'Value': msg}]

        batch_size = self.data.get('batch_size', self.batch_size)

        _common_tag_processer(
            self.executor_factory, batch_size, self.concurrency,
            self.process_resource_set, self.id_key, resources, tags, self.log)

    def process_resource_set(self, resource_set, tags):
        client = utils.local_session(self.manager.session_factory).client('ec2')
        return self.manager.retry(
            client.create_tags,
            Resources=[v[self.id_key] for v in resource_set],
            Tags=tags,
            DryRun=self.manager.config.dryrun)


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
        res = 0
        for r in resources:
            tags = {t['Key']: t['Value'] for t in r.get('Tags', [])}
            if key not in tags.keys():
                resources.pop(res)
            res += 1
        return resources

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
                action    = self.data.get('action')
                value     = self.data.get('value')
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
    """

    batch_size = 20
    concurrency = 1
    permissions = ('resourcegroupstaggingapi:TagResources',)

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

        batch_size = self.data.get('batch_size', self.batch_size)

        _common_tag_processer(
            self.executor_factory, batch_size, self.concurrency,
            self.process_resource_set, self.id_key, resources, tags, self.log)

    def process_resource_set(self, resource_set, tags):
        client = utils.local_session(
            self.manager.session_factory).client('resourcegroupstaggingapi')

        arns = self.manager.get_arns(resource_set)

        response = universal_tag_retry(
            client.tag_resources,
            ResourceARNList=arns,
            Tags=tags)

        for f in response.get('FailedResourcesMap', ()):
            raise Exception("Resource:{} ".format(f) +
                            "ErrorCode:{} ".format(
                            response['FailedResourcesMap'][f]['ErrorCode']) +
                            "StatusCode:{} ".format(
                            response['FailedResourcesMap'][f]['StatusCode']) +
                            "ErrorMessage:{}".format(
                            response['FailedResourcesMap'][f]['ErrorMessage']))


class UniversalUntag(RemoveTag):
    """Removes the specified tags from the specified resources.
    """

    batch_size = 20
    concurrency = 1
    permissions = ('resourcegroupstaggingapi:UntagResources',)

    def process_resource_set(self, resource_set, tag_keys):
        client = utils.local_session(
            self.manager.session_factory).client('resourcegroupstaggingapi')

        arns = self.manager.get_arns(resource_set)

        response = universal_tag_retry(
            client.untag_resources,
            ResourceARNList=arns,
            TagKeys=tag_keys)

        for f in response.get('FailedResourcesMap', ()):
            raise Exception("Resource:{} ".format(f) +
                            "ErrorCode:{} ".format(
                            response['FailedResourcesMap'][f]['ErrorCode']) +
                            "StatusCode:{} ".format(
                            response['FailedResourcesMap'][f]['StatusCode']) +
                            "ErrorMessage:{}".format(
                            response['FailedResourcesMap'][f]['ErrorMessage']))


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
    concurrency = 2
    permissions = ('resourcegroupstaggingapi:TagResources',)

    def process(self, resources):
        self.id_key = self.manager.get_model().id

        # Move this to policy? / no resources bypasses actions?
        if not len(resources):
            return

        msg_tmpl = self.data.get('msg', self.default_template)

        op = self.data.get('op', 'stop')
        tag = self.data.get('tag', DEFAULT_TAG)
        date = self.data.get('days', 4)

        n = datetime.now(tz=tzutc())
        action_date = n + timedelta(days=date)
        msg = msg_tmpl.format(
            op=op, action_date=action_date.strftime('%Y/%m/%d'))

        self.log.info("Tagging %d resources for %s on %s" % (
            len(resources), op, action_date.strftime('%Y/%m/%d')))

        tags = {tag: msg}

        batch_size = self.data.get('batch_size', self.batch_size)

        _common_tag_processer(
            self.executor_factory, batch_size, self.concurrency,
            self.process_resource_set, self.id_key, resources, tags, self.log)

    def process_resource_set(self, resource_set, tags):
        client = utils.local_session(
            self.manager.session_factory).client('resourcegroupstaggingapi')

        arns = self.manager.get_arns(resource_set)

        response = universal_tag_retry(
            client.tag_resources,
            ResourceARNList=arns,
            Tags=tags)

        for f in response.get('FailedResourcesMap', ()):
            raise Exception("Resource:{} ".format(f) +
                            "ErrorCode:{} ".format(
                            response['FailedResourcesMap'][f]['ErrorCode']) +
                            "StatusCode:{} ".format(
                            response['FailedResourcesMap'][f]['StatusCode']) +
                            "ErrorMessage:{}".format(
                            response['FailedResourcesMap'][f]['ErrorMessage']))
