# Copyright 2016 Capital One Services, LLC
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
from concurrent.futures import as_completed

from datetime import datetime, timedelta
from dateutil.parser import parse
from dateutil.tz import tzutc

from c7n.actions import BaseAction as Action
from c7n.filters import Filter, OPERATORS, FilterValidationError
from c7n import utils

DEFAULT_TAG = "maid_status"


def register_tags(filters, actions):
    filters.register('marked-for-op', TagActionFilter)
    filters.register('tag-count', TagCountFilter)

    actions.register('mark-for-op', TagDelayedAction)
    actions.register('tag-trim', TagTrim)

    actions.register('mark', Tag)
    actions.register('tag', Tag)

    actions.register('unmark', RemoveTag)
    actions.register('untag', RemoveTag)
    actions.register('remove-tag', RemoveTag)


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
            t['Key']:t['Value'] for t in i.get('Tags', [])
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
        except:
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
        op={'enum': OPERATORS.keys()})

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

    batch_size = 150
    concurrency = 2

    schema = utils.type_schema(
        'tag', aliases=('mark',),
        tags={'type': 'object'},
        key={'type': 'string'},
        value={'type': 'string'},
        )

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

        batch_size = self.data.get('batch_size', self.batch_size)

        with self.executor_factory(max_workers=self.concurrency) as w:
            futures = {}
            for resource_set in utils.chunks(resources, size=batch_size):
                futures[
                    w.submit(
                        self.process_resource_set, resource_set, tags)
                ] = resource_set

            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception removing tags: %s on resources:%s \n %s" % (
                            tags,
                            ", ".join([r[self.id_key] for r in resource_set]),
                            f.exception()))

    def process_resource_set(self, resource_set, tags):
        client = utils.local_session(
            self.manager.session_factory).client('ec2')

        self.manager.retry(
            client.create_tags,
            Resources=[v[self.id_key] for v in resource_set],
            Tags=tags,
            DryRun=self.manager.config.dryrun)


class RemoveTag(Action):
    """Remove tags from ec2 resources.
    """

    batch_size = 100
    concurrency = 2

    schema = utils.type_schema(
        'untag', aliases=('unmark', 'remove-tag'),
        tags={'type': 'array', 'items': {'type': 'string'}})

    def process(self, resources):
        self.id_key = self.manager.get_model().id

        tags = self.data.get('tags', [DEFAULT_TAG])
        batch_size = self.data.get('batch_size', self.batch_size)

        with self.executor_factory(max_workers=self.concurrency) as w:
            futures = {}
            for resource_set in utils.chunks(resources, size=batch_size):
                futures[
                    w.submit(
                        self.process_resource_set, resource_set, tags)
                ] = resource_set

            for f in as_completed(futures):
                if f.exception():
                    resource_set = futures[f]
                    self.log.error(
                        "Exception removing tags: %s on resources:%s \n %s" % (
                            tags,
                            ", ".join([r[self.id_key] for r in resource_set]),
                            f.exception()))

    def process_resource_set(self, vol_set, tag_keys):
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        return self.manager.retry(
            client.delete_tags,
            Resources=[v[self.id_key] for v in vol_set],
            Tags=[{'Key': k for k in tag_keys}],
            DryRun=self.manager.config.dryrun)


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
        days={'type': 'number', 'minimum': 0, 'exclusiveMinimum': True},
        op={'type': 'string'})

    batch_size = 200

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

        with self.executor_factory(max_workers=2) as w:
            futures = []
            for resource_set in utils.chunks(resources, size=self.batch_size):
                futures.append(
                    w.submit(self.process_resource_set, resource_set, tags))

            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception tagging resource set: %s  \n %s" % (
                            tags, f.exception()))

    def process_resource_set(self, resource_set, tags):
        client = utils.local_session(self.manager.session_factory).client('ec2')
        return self.manager.retry(
            client.create_tags,
            Resources=[v[self.id_key] for v in resource_set],
            Tags=tags,
            DryRun=self.manager.config.dryrun)
