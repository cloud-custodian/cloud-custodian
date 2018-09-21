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

import base64
import itertools
import operator
import random
import re
import zlib

import six
from botocore.exceptions import ClientError
from dateutil.parser import parse
from concurrent.futures import as_completed

from c7n.actions import (
    ActionRegistry, BaseAction, ModifyVpcSecurityGroupsAction
)
from c7n.exceptions import PolicyValidationError
from c7n.filters import (
    FilterRegistry, AgeFilter, ValueFilter, Filter, OPERATORS, DefaultVpcBase
)
from c7n.filters.offhours import OffHour, OnHour
from c7n.filters.health import HealthEventFilter
import c7n.filters.vpc as net_filters

from c7n.manager import resources
from c7n import query

from c7n import utils
from c7n.utils import type_schema


filters = FilterRegistry('ec2.filters')
actions = ActionRegistry('ec2.actions')

filters.register('health-event', HealthEventFilter)


@resources.register('ec2')
class EC2(query.QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'instance'
        enum_spec = ('describe_instances', 'Reservations[].Instances[]', None)
        detail_spec = None
        id = 'InstanceId'
        filter_name = 'InstanceIds'
        filter_type = 'list'
        name = 'PublicDnsName'
        date = 'LaunchTime'
        dimension = 'InstanceId'
        config_type = "AWS::EC2::Instance"
        shape = "Instance"

        default_report_fields = (
            'CustodianDate',
            'InstanceId',
            'tag:Name',
            'InstanceType',
            'LaunchTime',
            'VpcId',
            'PrivateIpAddress',
        )

    filter_registry = filters
    action_registry = actions

    # if we have to do a fallback scenario where tags don't come in describe
    permissions = ('ec2:DescribeTags',)

    def __init__(self, ctx, data):
        super(EC2, self).__init__(ctx, data)
        self.queries = QueryFilter.parse(self.data.get('query', []))

    def resources(self, query=None):
        q = self.resource_query()
        if q is not None:
            query = query or {}
            query['Filters'] = q
        return super(EC2, self).resources(query=query)

    def resource_query(self):
        qf = []
        qf_names = set()
        # allow same name to be specified multiple times and append the queries
        # under the same name
        for q in self.queries:
            qd = q.query()
            if qd['Name'] in qf_names:
                for qf in qf:
                    if qd['Name'] == qf['Name']:
                        qf['Values'].extend(qd['Values'])
            else:
                qf_names.add(qd['Name'])
                qf.append(qd)
        return qf

    def get_source(self, source_type):
        if source_type == 'describe':
            return DescribeEC2(self)
        elif source_type == 'config':
            return query.ConfigSource(self)
        raise ValueError('invalid source %s' % source_type)


class DescribeEC2(query.DescribeSource):

    def augment(self, resources):
        """EC2 API and AWOL Tags

        While ec2 api generally returns tags when doing describe_x on for
        various resources, it may also silently fail to do so unless a tag
        is used as a filter.

        See footnote on http://goo.gl/YozD9Q for official documentation.

        Apriori we may be using custodian to ensure tags (including
        name), so there isn't a good default to ensure that we will
        always get tags from describe_x calls.
        """
        # First if we're in event based lambda go ahead and skip this,
        # tags can't be trusted in ec2 instances immediately post creation.
        if not resources or self.manager.data.get(
                'mode', {}).get('type', '') in (
                    'cloudtrail', 'ec2-instance-state'):
            return resources

        # AWOL detector, so we don't make extraneous api calls.
        resource_count = len(resources)
        search_count = min(int(resource_count % 0.05) + 1, 5)
        if search_count > resource_count:
            search_count = resource_count
        found = False
        for r in random.sample(resources, search_count):
            if 'Tags' in r:
                found = True
                break

        if found:
            return resources

        # Okay go and do the tag lookup
        client = utils.local_session(self.manager.session_factory).client('ec2')
        tag_set = self.manager.retry(
            client.describe_tags,
            Filters=[{'Name': 'resource-type',
                      'Values': ['instance']}])['Tags']
        resource_tags = {}
        for t in tag_set:
            t.pop('ResourceType')
            rid = t.pop('ResourceId')
            resource_tags.setdefault(rid, []).append(t)

        m = self.manager.get_model()
        for r in resources:
            r['Tags'] = resource_tags.get(r[m.id], ())
        return resources


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "SecurityGroups[].GroupId"


@filters.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "SubnetId"


filters.register('network-location', net_filters.NetworkLocation)


@filters.register('state-age')
class StateTransitionAge(AgeFilter):
    """Age an instance has been in the given state.

    .. code-block:: yaml

        policies:
          - name: ec2-state-running-7-days
            resource: ec2
            filters:
              - type: state-age
                op: ge
                days: 7
    """
    RE_PARSE_AGE = re.compile("\(.*?\)")

    # this filter doesn't use date_attribute, but needs to define it
    # to pass AgeFilter's validate method
    date_attribute = "dummy"

    schema = type_schema(
        'state-age',
        op={'type': 'string', 'enum': list(OPERATORS.keys())},
        days={'type': 'number'})

    def get_resource_date(self, i):
        v = i.get('StateTransitionReason')
        if not v:
            return None
        dates = self.RE_PARSE_AGE.findall(v)
        if dates:
            return parse(dates[0][1:-1])
        return None


class StateTransitionFilter(object):
    """Filter instances by state.

    Try to simplify construction for policy authors by automatically
    filtering elements (filters or actions) to the instances states
    they are valid for.

    For more details see http://goo.gl/TZH9Q5
    """
    valid_origin_states = ()

    def filter_instance_state(self, instances, states=None):
        states = states or self.valid_origin_states
        orig_length = len(instances)
        results = [i for i in instances
                   if i['State']['Name'] in states]
        self.log.info("%s %d of %d instances" % (
            self.__class__.__name__, len(results), orig_length))
        return results


@filters.register('ebs')
class AttachedVolume(ValueFilter):
    """EC2 instances with EBS backed volume

    Filters EC2 instances with EBS backed storage devices (non ephemeral)

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-encrypted-ebs-volumes
            resource: ec2
            filters:
              - type: ebs
                key: Encrypted
                value: true
    """

    schema = type_schema(
        'ebs', rinherit=ValueFilter.schema,
        **{'operator': {'enum': ['and', 'or']},
           'skip-devices': {'type': 'array', 'items': {'type': 'string'}}})

    def get_permissions(self):
        return self.manager.get_resource_manager('ebs').get_permissions()

    def process(self, resources, event=None):
        self.volume_map = self.get_volume_mapping(resources)
        self.skip = self.data.get('skip-devices', [])
        self.operator = self.data.get(
            'operator', 'or') == 'or' and any or all
        return list(filter(self, resources))

    def get_volume_mapping(self, resources):
        volume_map = {}
        manager = self.manager.get_resource_manager('ebs')
        for instance_set in utils.chunks(resources, 200):
            volume_ids = []
            for i in instance_set:
                for bd in i.get('BlockDeviceMappings', ()):
                    if 'Ebs' not in bd:
                        continue
                    volume_ids.append(bd['Ebs']['VolumeId'])
            for v in manager.get_resources(volume_ids):
                if not v['Attachments']:
                    continue
                volume_map.setdefault(
                    v['Attachments'][0]['InstanceId'], []).append(v)
        return volume_map

    def __call__(self, i):
        volumes = self.volume_map.get(i['InstanceId'])
        if not volumes:
            return False
        if self.skip:
            for v in list(volumes):
                for a in v.get('Attachments', []):
                    if a['Device'] in self.skip:
                        volumes.remove(v)
        return self.operator(map(self.match, volumes))


@filters.register('termination-protected')
class DisableApiTermination(Filter):
    """EC2 instances with ``disableApiTermination`` attribute set

    Filters EC2 instances with ``disableApiTermination`` attribute set to true.

    :Example:

    .. code-block:: yaml

        policies:
          - name: termination-protection-enabled
            resource: ec2
            filters:
              - type: termination-protected

    :Example:

    .. code-block:: yaml

        policies:
          - name: termination-protection-NOT-enabled
            resource: ec2
            filters:
              - not:
                - type: termination-protected
    """

    schema = type_schema('termination-protected')
    permissions = ('ec2:DescribeInstanceAttribute',)

    def get_permissions(self):
        perms = list(self.permissions)
        perms.extend(self.manager.get_permissions())
        return perms

    def process(self, resources, event=None):
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        return [r for r in resources
                if self.is_termination_protection_enabled(client, r)]

    def is_termination_protection_enabled(self, client, inst):
        attr_val = self.manager.retry(
            client.describe_instance_attribute,
            Attribute='disableApiTermination',
            InstanceId=inst['InstanceId']
        )
        return attr_val['DisableApiTermination']['Value']


class InstanceImageBase(object):

    def prefetch_instance_images(self, instances):
        image_ids = [i['ImageId'] for i in instances if 'c7n:instance-image' not in i]
        self.image_map = self.get_local_image_mapping(image_ids)

    def get_base_image_mapping(self):
        return {i['ImageId']: i for i in
                self.manager.get_resource_manager('ami').resources()}

    def get_instance_image(self, instance):
        image = instance.get('c7n:instance-image', None)
        if not image:
            image = instance['c7n:instance-image'] = self.image_map.get(instance['ImageId'], None)
        return image

    def get_local_image_mapping(self, image_ids):
        base_image_map = self.get_base_image_mapping()
        resources = {i: base_image_map[i] for i in image_ids if i in base_image_map}
        missing = list(set(image_ids) - set(resources.keys()))
        if missing:
            loaded = self.manager.get_resource_manager('ami').get_resources(missing, False)
            resources.update({image['ImageId']: image for image in loaded})
        return resources


@filters.register('image-age')
class ImageAge(AgeFilter, InstanceImageBase):
    """EC2 AMI age filter

    Filters EC2 instances based on the age of their AMI image (in days)

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-ancient-ami
            resource: ec2
            filters:
              - type: image-age
                op: ge
                days: 90
    """

    date_attribute = "CreationDate"

    schema = type_schema(
        'image-age',
        op={'type': 'string', 'enum': list(OPERATORS.keys())},
        days={'type': 'number'})

    def get_permissions(self):
        return self.manager.get_resource_manager('ami').get_permissions()

    def process(self, resources, event=None):
        self.prefetch_instance_images(resources)
        return super(ImageAge, self).process(resources, event)

    def get_resource_date(self, i):
        image = self.get_instance_image(i)
        if image:
            return parse(image['CreationDate'])
        else:
            return parse("2000-01-01T01:01:01.000Z")


@filters.register('image')
class InstanceImage(ValueFilter, InstanceImageBase):

    schema = type_schema('image', rinherit=ValueFilter.schema)

    def get_permissions(self):
        return self.manager.get_resource_manager('ami').get_permissions()

    def process(self, resources, event=None):
        self.prefetch_instance_images(resources)
        return super(InstanceImage, self).process(resources, event)

    def __call__(self, i):
        image = self.get_instance_image(i)
        # Finally, if we have no image...
        if not image:
            self.log.warning(
                "Could not locate image for instance:%s ami:%s" % (
                    i['InstanceId'], i["ImageId"]))
            # Match instead on empty skeleton?
            return False
        return self.match(image)


@filters.register('offhour')
class InstanceOffHour(OffHour, StateTransitionFilter):
    """Custodian OffHour filter

    Filters running EC2 instances with the intent to stop at a given hour of
    the day. A list of days to excluded can be included as a list of strings
    with the format YYYY-MM-DD. Alternatively, the list (using the same syntax)
    can be taken from a specified url.

    :Example:

    .. code-block:: yaml

        policies:
          - name: offhour-evening-stop
            resource: ec2
            filters:
              - type: offhour
                tag: custodian_downtime
                default_tz: et
                offhour: 20
            actions:
              - stop

          - name: offhour-evening-stop-skip-holidays
            resource: ec2
            filters:
              - type: offhour
                tag: custodian_downtime
                default_tz: et
                offhour: 20
                skip-days: ['2017-12-25']
            actions:
              - stop

          - name: offhour-evening-stop-skip-holidays-from
            resource: ec2
            filters:
              - type: offhour
                tag: custodian_downtime
                default_tz: et
                offhour: 20
                skip-days-from:
                  expr: 0
                  format: csv
                  url: 's3://location/holidays.csv'
            actions:
              - stop
    """

    valid_origin_states = ('running',)

    def process(self, resources, event=None):
        return super(InstanceOffHour, self).process(
            self.filter_instance_state(resources))


@filters.register('onhour')
class InstanceOnHour(OnHour, StateTransitionFilter):
    """Custodian OnHour filter

    Filters stopped EC2 instances with the intent to start at a given hour of
    the day. A list of days to excluded can be included as a list of strings
    with the format YYYY-MM-DD. Alternatively, the list (using the same syntax)
    can be taken from a specified url.

    :Example:

    .. code-block:: yaml

        policies:
          - name: onhour-morning-start
            resource: ec2
            filters:
              - type: onhour
                tag: custodian_downtime
                default_tz: et
                onhour: 6
            actions:
              - start

          - name: onhour-morning-start-skip-holidays
            resource: ec2
            filters:
              - type: onhour
                tag: custodian_downtime
                default_tz: et
                onhour: 6
                skip-days: ['2017-12-25']
            actions:
              - start

          - name: onhour-morning-start-skip-holidays-from
            resource: ec2
            filters:
              - type: onhour
                tag: custodian_downtime
                default_tz: et
                onhour: 6
                skip-days-from:
                  expr: 0
                  format: csv
                  url: 's3://location/holidays.csv'
            actions:
              - start
    """

    valid_origin_states = ('stopped',)

    def process(self, resources, event=None):
        return super(InstanceOnHour, self).process(
            self.filter_instance_state(resources))


@filters.register('ephemeral')
class EphemeralInstanceFilter(Filter):
    """EC2 instances with ephemeral storage

    Filters EC2 instances that have ephemeral storage (an instance-store backed
    root device)

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-ephemeral-instances
            resource: ec2
            filters:
              - type: ephemeral

    http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/InstanceStorage.html
    """

    schema = type_schema('ephemeral')

    def __call__(self, i):
        return self.is_ephemeral(i)

    @staticmethod
    def is_ephemeral(i):
        for bd in i.get('BlockDeviceMappings', []):
            if bd['DeviceName'] in ('/dev/sda1', '/dev/xvda', 'xvda'):
                if 'Ebs' in bd:
                    return False
                return True
        return True


@filters.register('instance-uptime')
class UpTimeFilter(AgeFilter):

    date_attribute = "LaunchTime"

    schema = type_schema(
        'instance-uptime',
        op={'type': 'string', 'enum': list(OPERATORS.keys())},
        days={'type': 'number'})


@filters.register('instance-age')
class InstanceAgeFilter(AgeFilter):
    """Filters instances based on their age (in days)

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-30-days-plus
            resource: ec2
            filters:
              - type: instance-age
                op: ge
                days: 30
    """

    date_attribute = "LaunchTime"
    ebs_key_func = operator.itemgetter('AttachTime')

    schema = type_schema(
        'instance-age',
        op={'type': 'string', 'enum': list(OPERATORS.keys())},
        days={'type': 'number'},
        hours={'type': 'number'},
        minutes={'type': 'number'})

    def get_resource_date(self, i):
        # LaunchTime is basically how long has the instance
        # been on, use the oldest ebs vol attach time
        ebs_vols = [
            block['Ebs'] for block in i['BlockDeviceMappings']
            if 'Ebs' in block]
        if not ebs_vols:
            # Fall back to using age attribute (ephemeral instances)
            return super(InstanceAgeFilter, self).get_resource_date(i)
        # Lexographical sort on date
        ebs_vols = sorted(ebs_vols, key=self.ebs_key_func)
        return ebs_vols[0]['AttachTime']


@filters.register('default-vpc')
class DefaultVpc(DefaultVpcBase):
    """ Matches if an ec2 database is in the default vpc
    """

    schema = type_schema('default-vpc')

    def __call__(self, ec2):
        return ec2.get('VpcId') and self.match(ec2.get('VpcId')) or False


def deserialize_user_data(user_data):
    data = base64.b64decode(user_data)
    # try raw and compressed
    try:
        return data.decode('utf8')
    except UnicodeDecodeError:
        return zlib.decompress(data, 16).decode('utf8')


@filters.register('user-data')
class UserData(ValueFilter):
    """Filter on EC2 instances which have matching userdata.
    Note: It is highly recommended to use regexes with the ?sm flags, since Custodian
    uses re.match() and userdata spans multiple lines.

        :example:

        .. code-block:: yaml

            policies:
              - name: ec2_userdata_stop
                resource: ec2
                filters:
                  - type: user-data
                    op: regex
                    value: (?smi).*password=
                actions:
                  - stop
    """

    schema = type_schema('user-data', rinherit=ValueFilter.schema)
    batch_size = 50
    annotation = 'c7n:user-data'
    permissions = ('ec2:DescribeInstanceAttribute',)

    def process(self, resources, event=None):
        self.data['key'] = '"c7n:user-data"'
        client = utils.local_session(self.manager.session_factory).client('ec2')
        results = []
        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for instance_set in utils.chunks(resources, self.batch_size):
                futures[w.submit(
                    self.process_instance_set,
                    client, instance_set)] = instance_set

            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Error processing userdata on instance set %s", f.exception())
                results.extend(f.result())
        return results

    def process_instance_set(self, client, resources):
        results = []
        for r in resources:
            if self.annotation not in r:
                try:
                    result = client.describe_instance_attribute(
                        Attribute='userData',
                        InstanceId=r['InstanceId'])
                except ClientError as e:
                    if e.response['Error']['Code'] == 'InvalidInstanceId.NotFound':
                        continue
                if 'Value' not in result['UserData']:
                    r[self.annotation] = None
                else:
                    r[self.annotation] = deserialize_user_data(
                        result['UserData']['Value'])
            if self.match(r):
                results.append(r)
        return results


@filters.register('singleton')
class SingletonFilter(Filter, StateTransitionFilter):
    """EC2 instances without autoscaling or a recover alarm

    Filters EC2 instances that are not members of an autoscaling group
    and do not have Cloudwatch recover alarms.

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-recover-instances
            resource: ec2
            filters:
              - singleton
            actions:
              - type: tag
                key: problem
                value: instance is not resilient

    https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-recover.html
    """

    schema = type_schema('singleton')

    permissions = ('cloudwatch:DescribeAlarmsForMetric',)

    valid_origin_states = ('running', 'stopped', 'pending', 'stopping')

    in_asg = ValueFilter({
        'key': 'tag:aws:autoscaling:groupName',
        'value': 'not-null'}).validate()

    def process(self, instances, event=None):
        return super(SingletonFilter, self).process(
            self.filter_instance_state(instances))

    def __call__(self, i):
        if self.in_asg(i):
            return False
        else:
            return not self.has_recover_alarm(i)

    def has_recover_alarm(self, i):
        client = utils.local_session(self.manager.session_factory).client('cloudwatch')
        alarms = client.describe_alarms_for_metric(
            MetricName='StatusCheckFailed_System',
            Namespace='AWS/EC2',
            Dimensions=[
                {
                    'Name': 'InstanceId',
                    'Value': i['InstanceId']
                }
            ]
        )

        for i in alarms['MetricAlarms']:
            for a in i['AlarmActions']:
                if (
                    a.startswith('arn:aws:automate:') and
                    a.endswith(':ec2:recover')
                ):
                    return True

        return False


@actions.register('start')
class Start(BaseAction, StateTransitionFilter):
    """Starts a previously stopped EC2 instance.

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-start-stopped-instances
            resource: ec2
            query:
              - instance-state-name: stopped
            actions:
              - start

    http://docs.aws.amazon.com/cli/latest/reference/ec2/start-instances.html
    """

    valid_origin_states = ('stopped',)
    schema = type_schema('start')
    permissions = ('ec2:StartInstances',)
    batch_size = 10
    exception = None

    def _filter_ec2_with_volumes(self, instances):
        return [i for i in instances if len(i['BlockDeviceMappings']) > 0]

    def process(self, instances):
        instances = self._filter_ec2_with_volumes(
            self.filter_instance_state(instances))
        if not len(instances):
            return

        client = utils.local_session(self.manager.session_factory).client('ec2')
        failures = {}

        # Play nice around aws having insufficient capacity...
        for itype, t_instances in utils.group_by(
                instances, 'InstanceType').items():
            for izone, z_instances in utils.group_by(
                    t_instances, 'Placement.AvailabilityZone').items():
                for batch in utils.chunks(z_instances, self.batch_size):
                    fails = self.process_instance_set(client, batch, itype, izone)
                    if fails:
                        failures["%s %s" % (itype, izone)] = [i['InstanceId'] for i in batch]

        if failures:
            fail_count = sum(map(len, failures.values()))
            msg = "Could not start %d of %d instances %s" % (
                fail_count, len(instances),
                utils.dumps(failures))
            self.log.warning(msg)
            raise RuntimeError(msg)

    def process_instance_set(self, client, instances, itype, izone):
        # Setup retry with insufficient capacity as well
        retryable = ('InsufficientInstanceCapacity', 'RequestLimitExceeded',
                     'Client.RequestLimitExceeded'),
        retry = utils.get_retry(retryable, max_attempts=5)
        instance_ids = [i['InstanceId'] for i in instances]
        try:
            retry(client.start_instances, InstanceIds=instance_ids)
        except ClientError as e:
            if e.response['Error']['Code'] in retryable:
                return True
            raise


@actions.register('resize')
class Resize(BaseAction, StateTransitionFilter):
    """Change an instance's size.

    An instance can only be resized when its stopped, this action
    can optionally restart an instance if needed to effect the instance
    type change. Instances are always left in the run state they were
    found in.

    There are a few caveats to be aware of, instance resizing
    needs to maintain compatibility for architecture, virtualization type
    hvm/pv, and ebs optimization at minimum.

    http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-resize.html
    """

    schema = type_schema(
        'resize',
        **{'restart': {'type': 'boolean'},
           'type-map': {'type': 'object'},
           'default': {'type': 'string'}})

    valid_origin_states = ('running', 'stopped')

    def get_permissions(self):
        perms = ('ec2:DescribeInstances', 'ec2:ModifyInstanceAttribute')
        if self.data.get('restart', False):
            perms += ('ec2:StopInstances', 'ec2:StartInstances')
        return perms

    def process(self, resources):
        stopped_instances = self.filter_instance_state(
            resources, ('stopped',))
        running_instances = self.filter_instance_state(
            resources, ('running',))

        if self.data.get('restart') and running_instances:
            Stop({'terminate-ephemeral': False},
                 self.manager).process(running_instances)
            client = utils.local_session(
                self.manager.session_factory).client('ec2')
            waiter = client.get_waiter('instance_stopped')
            try:
                waiter.wait(
                    InstanceIds=[r['InstanceId'] for r in running_instances])
            except ClientError as e:
                self.log.exception(
                    "Exception stopping instances for resize:\n %s" % e)

        for instance_set in utils.chunks(itertools.chain(
                stopped_instances, running_instances), 20):
            self.process_resource_set(instance_set)

        if self.data.get('restart') and running_instances:
            client.start_instances(
                InstanceIds=[i['InstanceId'] for i in running_instances])
        return list(itertools.chain(stopped_instances, running_instances))

    def process_resource_set(self, instance_set):
        type_map = self.data.get('type-map')
        default_type = self.data.get('default')

        client = utils.local_session(
            self.manager.session_factory).client('ec2')

        for i in instance_set:
            self.log.debug(
                "resizing %s %s" % (i['InstanceId'], i['InstanceType']))
            new_type = type_map.get(i['InstanceType'], default_type)
            if new_type == i['InstanceType']:
                continue
            try:
                client.modify_instance_attribute(
                    InstanceId=i['InstanceId'],
                    InstanceType={'Value': new_type})
            except ClientError as e:
                self.log.exception(
                    "Exception resizing instance:%s new:%s old:%s \n %s" % (
                        i['InstanceId'], new_type, i['InstanceType'], e))


@actions.register('stop')
class Stop(BaseAction, StateTransitionFilter):
    """Stops a running EC2 instances

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-stop-running-instances
            resource: ec2
            query:
              - instance-state-name: running
            actions:
              - stop
    """
    valid_origin_states = ('running',)

    schema = type_schema('stop', **{'terminate-ephemeral': {'type': 'boolean'}})

    def get_permissions(self):
        perms = ('ec2:StopInstances',)
        if self.data.get('terminate-ephemeral', False):
            perms += ('ec2:TerminateInstances',)
        return perms

    def split_on_storage(self, instances):
        ephemeral = []
        persistent = []
        for i in instances:
            if EphemeralInstanceFilter.is_ephemeral(i):
                ephemeral.append(i)
            else:
                persistent.append(i)
        return ephemeral, persistent

    def process(self, instances):
        instances = self.filter_instance_state(instances)
        if not len(instances):
            return
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        # Ephemeral instance can't be stopped.
        ephemeral, persistent = self.split_on_storage(instances)
        if self.data.get('terminate-ephemeral', False) and ephemeral:
            self._run_instances_op(
                client.terminate_instances,
                [i['InstanceId'] for i in ephemeral])
        if persistent:
            self._run_instances_op(
                client.stop_instances,
                [i['InstanceId'] for i in persistent])
        return instances

    def _run_instances_op(self, op, instance_ids):
        while True:
            try:
                return self.manager.retry(op, InstanceIds=instance_ids)
            except ClientError as e:
                if e.response['Error']['Code'] == 'IncorrectInstanceState':
                    msg = e.response['Error']['Message']
                    e_instance_id = msg[msg.find("'") + 1:msg.rfind("'")]
                    instance_ids.remove(e_instance_id)
                    if not instance_ids:
                        return
                    continue
                raise


@actions.register('reboot')
class Reboot(BaseAction, StateTransitionFilter):
    """reboots a previously running EC2 instance.

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-reboot-instances
            resource: ec2
            query:
              - instance-state-name: running
            actions:
              - reboot

    http://docs.aws.amazon.com/cli/latest/reference/ec2/reboot-instances.html
    """

    valid_origin_states = ('running',)
    schema = type_schema('reboot')
    permissions = ('ec2:RebootInstances',)
    batch_size = 10
    exception = None

    def _filter_ec2_with_volumes(self, instances):
        return [i for i in instances if len(i['BlockDeviceMappings']) > 0]

    def process(self, instances):
        instances = self._filter_ec2_with_volumes(
            self.filter_instance_state(instances))
        if not len(instances):
            return

        client = utils.local_session(self.manager.session_factory).client('ec2')
        failures = {}

        for batch in utils.chunks(instances, self.batch_size):
            fails = self.process_instance_set(client, batch)
            if fails:
                failures = [i['InstanceId'] for i in batch]

        if failures:
            fail_count = sum(map(len, failures.values()))
            msg = "Could not reboot %d of %d instances %s" % (
                fail_count, len(instances),
                utils.dumps(failures))
            self.log.warning(msg)
            raise RuntimeError(msg)

    def process_instance_set(self, client, instances):
        # Setup retry with insufficient capacity as well
        retryable = ('InsufficientInstanceCapacity', 'RequestLimitExceeded',
                     'Client.RequestLimitExceeded'),
        retry = utils.get_retry(retryable, max_attempts=5)
        instance_ids = [i['InstanceId'] for i in instances]
        try:
            retry(client.reboot_instances, InstanceIds=instance_ids)
        except ClientError as e:
            if e.response['Error']['Code'] in retryable:
                return True
            raise


@actions.register('terminate')
class Terminate(BaseAction, StateTransitionFilter):
    """ Terminate a set of instances.

    While ec2 offers a bulk delete api, any given instance can be configured
    with api deletion termination protection, so we can't use the bulk call
    reliabily, we need to process the instances individually. Additionally
    If we're configured with 'force' then we'll turn off instance termination
    protection.

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-process-termination
            resource: ec2
            filters:
              - type: marked-for-op
                op: terminate
            actions:
              - terminate
    """

    valid_origin_states = ('running', 'stopped', 'pending', 'stopping')

    schema = type_schema('terminate', force={'type': 'boolean'})

    def get_permissions(self):
        permissions = ("ec2:TerminateInstances",)
        if self.data.get('force'):
            permissions += ('ec2:ModifyInstanceAttribute',)
        return permissions

    def process(self, instances):
        instances = self.filter_instance_state(instances)
        if not len(instances):
            return
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        if self.data.get('force'):
            self.log.info("Disabling termination protection on instances")
            self.disable_deletion_protection(
                client,
                [i for i in instances if i.get('InstanceLifecycle') != 'spot'])
        # limit batch sizes to avoid api limits
        for batch in utils.chunks(instances, 100):
            self.manager.retry(
                client.terminate_instances,
                InstanceIds=[i['InstanceId'] for i in instances])

    def disable_deletion_protection(self, client, instances):

        def process_instance(i):
            try:
                self.manager.retry(
                    client.modify_instance_attribute,
                    InstanceId=i['InstanceId'],
                    Attribute='disableApiTermination',
                    Value='false')
            except ClientError as e:
                if e.response['Error']['Code'] == 'IncorrectInstanceState':
                    return
                raise

        with self.executor_factory(max_workers=2) as w:
            list(w.map(process_instance, instances))


@actions.register('snapshot')
class Snapshot(BaseAction):
    """Snapshots volumes attached to an EC2 instance

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-snapshots
            resource: ec2
          actions:
            - type: snapshot
              copy-tags:
                - Name
    """

    schema = type_schema(
        'snapshot',
        **{'copy-tags': {'type': 'array', 'items': {'type': 'string'}}})
    permissions = ('ec2:CreateSnapshot', 'ec2:CreateTags',)

    def process(self, resources):
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for resource in resources:
                futures.append(w.submit(
                    self.process_volume_set, client, resource))
            for f in as_completed(futures):
                if f.exception():
                    raise f.exception()
                    self.log.error(
                        "Exception creating snapshot set \n %s" % (
                            f.exception()))

    def process_volume_set(self, client, resource):
        for block_device in resource['BlockDeviceMappings']:
            if 'Ebs' not in block_device:
                continue
            volume_id = block_device['Ebs']['VolumeId']
            description = "Automated,Backup,%s,%s" % (
                resource['InstanceId'], volume_id)
            tags = self.get_snapshot_tags(resource, block_device)
            try:
                self.manager.retry(
                    client.create_snapshot,
                    DryRun=self.manager.config.dryrun,
                    VolumeId=volume_id,
                    Description=description,
                    TagSpecifications=[{
                        'ResourceType': 'snapshot',
                        'Tags': tags}])
            except ClientError as e:
                if e.response['Error']['Code'] == 'IncorrectState':
                    self.log.warning(
                        "action:%s volume:%s is incorrect state" % (
                            self.__class__.__name__.lower(),
                            volume_id))
                    continue
                raise

    def get_snapshot_tags(self, resource, block_device):
        tags = [
            {'Key': 'Name', 'Value': block_device['Ebs']['VolumeId']},
            {'Key': 'InstanceId', 'Value': resource['InstanceId']},
            {'Key': 'DeviceName', 'Value': block_device['DeviceName']},
            {'Key': 'custodian_snapshot', 'Value': ''}]

        copy_keys = self.data.get('copy-tags', [])
        copy_tags = []
        if copy_keys:
            for t in resource.get('Tags', []):
                if t['Key'] in copy_keys:
                    copy_tags.append(t)

            if len(copy_tags) + len(tags) > 40:
                self.log.warning(
                    "action:%s volume:%s too many tags to copy" % (
                        self.__class__.__name__.lower(),
                        block_device['Ebs']['VolumeId']))
                copy_tags = []
            tags.extend(copy_tags)
        return tags


@actions.register('modify-security-groups')
class EC2ModifyVpcSecurityGroups(ModifyVpcSecurityGroupsAction):
    """Modify security groups on an instance."""

    permissions = ("ec2:ModifyNetworkInterfaceAttribute",)

    def process(self, instances):
        if not len(instances):
            return
        client = utils.local_session(
            self.manager.session_factory).client('ec2')

        # handle multiple ENIs
        interfaces = []
        for i in instances:
            for eni in i['NetworkInterfaces']:
                if i.get('c7n:matched-security-groups'):
                    eni['c7n:matched-security-groups'] = i[
                        'c7n:matched-security-groups']
                if i.get('c7n:NetworkLocation'):
                    eni['c7n:NetworkLocation'] = i[
                        'c7n:NetworkLocation']
                interfaces.append(eni)

        groups = super(EC2ModifyVpcSecurityGroups, self).get_groups(interfaces)

        for idx, i in enumerate(interfaces):
            client.modify_network_interface_attribute(
                NetworkInterfaceId=i['NetworkInterfaceId'],
                Groups=groups[idx])


@actions.register('autorecover-alarm')
class AutorecoverAlarm(BaseAction, StateTransitionFilter):
    """Adds a cloudwatch metric alarm to recover an EC2 instance.

    This action takes effect on instances that are NOT part
    of an ASG.

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-autorecover-alarm
            resource: ec2
            filters:
              - singleton
          actions:
            - autorecover-alarm

    https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-recover.html
    """

    schema = type_schema('autorecover-alarm')
    permissions = ('ec2:DescribeInstanceStatus',
                   'ec2:RecoverInstances',
                   'ec2:DescribeInstanceRecoveryAttribute')

    valid_origin_states = ('running', 'stopped', 'pending', 'stopping')
    filter_asg_membership = ValueFilter({
        'key': 'tag:aws:autoscaling:groupName',
        'value': 'empty'}).validate()

    def process(self, instances):
        instances = self.filter_asg_membership.process(
            self.filter_instance_state(instances))
        if not len(instances):
            return
        client = utils.local_session(
            self.manager.session_factory).client('cloudwatch')
        for i in instances:
            client.put_metric_alarm(
                AlarmName='recover-{}'.format(i['InstanceId']),
                AlarmDescription='Auto Recover {}'.format(i['InstanceId']),
                ActionsEnabled=True,
                AlarmActions=[
                    'arn:aws:automate:{}:ec2:recover'.format(
                        i['Placement']['AvailabilityZone'][:-1])
                ],
                MetricName='StatusCheckFailed_System',
                Namespace='AWS/EC2',
                Statistic='Minimum',
                Dimensions=[
                    {
                        'Name': 'InstanceId',
                        'Value': i['InstanceId']
                    }
                ],
                Period=60,
                EvaluationPeriods=2,
                Threshold=0,
                ComparisonOperator='GreaterThanThreshold'
            )


@actions.register('set-instance-profile')
class SetInstanceProfile(BaseAction, StateTransitionFilter):
    """Sets (add, modify, remove) the instance profile for a running EC2 instance.

    :Example:

    .. code-block:: yaml

        policies:
          - name: set-default-instance-profile
            resource: ec2
            filters:
              - IamInstanceProfile: absent
            actions:
              - type: set-instance-profile
                name: default

    https://docs.aws.amazon.com/cli/latest/reference/ec2/associate-iam-instance-profile.html
    https://docs.aws.amazon.com/cli/latest/reference/ec2/disassociate-iam-instance-profile.html
    """

    schema = type_schema(
        'set-instance-profile',
        **{'name': {'type': 'string'}})

    permissions = (
        'ec2:AssociateIamInstanceProfile',
        'ec2:DisassociateIamInstanceProfile',
        'iam:PassRole')

    valid_origin_states = ('running', 'pending', 'stopped', 'stopping')

    def process(self, instances):
        instances = self.filter_instance_state(instances)
        if not len(instances):
            return
        client = utils.local_session(self.manager.session_factory).client('ec2')
        profile_name = self.data.get('name')
        profile_instances = [i for i in instances if i.get('IamInstanceProfile')]

        associations = {
            a['InstanceId']: (a['AssociationId'], a['IamInstanceProfile']['Arn'])
            for a in client.describe_iam_instance_profile_associations(
                Filters=[
                    {'Name': 'instance-id',
                     'Values': [i['InstanceId'] for i in profile_instances]},
                    {'Name': 'state', 'Values': ['associating', 'associated']}]
            ).get('IamInstanceProfileAssociations', ())}

        for i in instances:
            if profile_name and i['InstanceId'] not in associations:
                client.associate_iam_instance_profile(
                    IamInstanceProfile={'Name': profile_name},
                    InstanceId=i['InstanceId'])
                continue
            # Removing profile and no profile on instance.
            elif profile_name is None and i['InstanceId'] not in associations:
                continue

            p_assoc_id, p_arn = associations[i['InstanceId']]

            # Already associated to target profile, skip
            if profile_name and p_arn.endswith('/%s' % profile_name):
                continue

            if profile_name is None:
                client.disassociate_iam_instance_profile(
                    AssociationId=p_assoc_id)
            else:
                client.replace_iam_instance_profile_association(
                    IamInstanceProfile={'Name': profile_name},
                    AssociationId=p_assoc_id)

        return instances


@actions.register('propagate-spot-tags')
class PropagateSpotTags(BaseAction):
    """Propagate Tags that are set at Spot Request level to EC2 instances.

    :Example:

    .. code-block: yaml

        policies:
          - name: ec2-spot-instances
            resource: ec2
          filters:
            - State.Name: pending
            - instanceLifecycle: spot
          actions:
            - type: propagate-spot-tags
              only_tags:
                - Name
                - BillingTag
    """

    schema = type_schema(
        'propagate-spot-tags',
        **{'only_tags': {'type': 'array', 'items': {'type': 'string'}}})

    permissions = (
        'ec2:DescribeInstances',
        'ec2:DescribeSpotInstanceRequests',
        'ec2:DescribeTags',
        'ec2:CreateTags')

    MAX_TAG_COUNT = 50

    def process(self, instances):
        instances = [
            i for i in instances if i['InstanceLifecycle'] == 'spot']
        if not len(instances):
            self.log.warning(
                "action:%s no spot instances found, implicit filter by action" % (
                    self.__class__.__name__.lower()))
            return

        client = utils.local_session(
            self.manager.session_factory).client('ec2')

        request_instance_map = {}
        for i in instances:
            request_instance_map.setdefault(
                i['SpotInstanceRequestId'], []).append(i)

        # ... and describe the corresponding spot requests ...
        requests = client.describe_spot_instance_requests(
            Filters=[{
                'Name': 'spot-instance-request-id',
                'Values': list(request_instance_map.keys())}]).get(
                    'SpotInstanceRequests', [])

        updated = []
        for r in requests:
            if not r.get('Tags'):
                continue
            updated.extend(
                self.process_request_instances(
                    client, r, request_instance_map[r['SpotInstanceRequestId']]))
        return updated

    def process_request_instances(self, client, request, instances):
        # Now we find the tags we can copy : either all, either those
        # indicated with 'only_tags' parameter.
        copy_keys = self.data.get('only_tags', [])
        request_tags = {t['Key']: t['Value'] for t in request['Tags']
                        if not t['Key'].startswith('aws:')}
        if copy_keys:
            for k in set(copy_keys).difference(request_tags):
                del request_tags[k]

        update_instances = []
        for i in instances:
            instance_tags = {t['Key']: t['Value'] for t in i.get('Tags', [])}
            # We may overwrite tags, but if the operation changes no tag,
            # we will not proceed.
            for k, v in request_tags.items():
                if k not in instance_tags or instance_tags[k] != v:
                    update_instances.append(i['InstanceId'])

            if len(set(instance_tags) | set(request_tags)) > self.MAX_TAG_COUNT:
                self.log.warning(
                    "action:%s instance:%s too many tags to copy (> 50)" % (
                        self.__class__.__name__.lower(),
                        i['InstanceId']))
                continue

        for iset in utils.chunks(update_instances, 20):
            client.create_tags(
                DryRun=self.manager.config.dryrun,
                Resources=iset,
                Tags=[{'Key': k, 'Value': v} for k, v in request_tags.items()])

        self.log.debug(
            "action:%s tags updated on instances:%r" % (
                self.__class__.__name__.lower(),
                update_instances))

        return update_instances


# Valid EC2 Query Filters
# http://docs.aws.amazon.com/AWSEC2/latest/CommandLineReference/ApiReference-cmd-DescribeInstances.html
EC2_VALID_FILTERS = {
    'architecture': ('i386', 'x86_64'),
    'availability-zone': str,
    'iam-instance-profile.arn': str,
    'image-id': str,
    'instance-id': str,
    'instance-lifecycle': ('spot',),
    'instance-state-name': (
        'pending',
        'terminated',
        'running',
        'shutting-down',
        'stopping',
        'stopped'),
    'instance.group-id': str,
    'instance.group-name': str,
    'tag-key': str,
    'tag-value': str,
    'tag:': str,
    'tenancy': ('dedicated', 'default', 'host'),
    'vpc-id': str}


class QueryFilter(object):

    @classmethod
    def parse(cls, data):
        results = []
        for d in data:
            if not isinstance(d, dict):
                raise ValueError(
                    "EC2 Query Filter Invalid structure %s" % d)
            results.append(cls(d).validate())
        return results

    def __init__(self, data):
        self.data = data
        self.key = None
        self.value = None

    def validate(self):
        if not len(list(self.data.keys())) == 1:
            raise PolicyValidationError(
                "EC2 Query Filter Invalid %s" % self.data)
        self.key = list(self.data.keys())[0]
        self.value = list(self.data.values())[0]

        if self.key not in EC2_VALID_FILTERS and not self.key.startswith(
                'tag:'):
            raise PolicyValidationError(
                "EC2 Query Filter invalid filter name %s" % (self.data))

        if self.value is None:
            raise PolicyValidationError(
                "EC2 Query Filters must have a value, use tag-key"
                " w/ tag name as value for tag present checks"
                " %s" % self.data)
        return self

    def query(self):
        value = self.value
        if isinstance(self.value, six.string_types):
            value = [self.value]

        return {'Name': self.key, 'Values': value}


@filters.register('instance-attribute')
class InstanceAttribute(ValueFilter):
    """EC2 Instance Value FIlter on a given instance attribute.

    Filters EC2 Instances with the given instance attribute

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-unoptimized-ebs
            resource: ec2
            filters:
              - type: instance-attribute
                attribute: ebsOptimized
                key: "Value"
                value: false
    """

    valid_attrs = (
        'instanceType',
        'kernel',
        'ramdisk',
        'userData',
        'disableApiTermination',
        'instanceInitiatedShutdownBehavior',
        'rootDeviceName',
        'blockDeviceMapping',
        'productCodes',
        'sourceDestCheck',
        'groupSet',
        'ebsOptimized',
        'sriovNetSupport',
        'enaSupport')

    schema = type_schema(
        'instance-attribute',
        rinherit=ValueFilter.schema,
        attribute={'enum': valid_attrs},
        required=('attribute',))

    def get_permissions(self):
        return ('ec2:DescribeInstanceAttribute',)

    def process(self, resources, event=None):
        attribute = self.data['attribute']
        self.get_instance_attribute(resources, attribute)
        return [resource for resource in resources
                if self.match(resource['c7n:attribute-%s' % attribute])]

    def get_instance_attribute(self, resources, attribute):
        client = utils.local_session(
            self.manager.session_factory).client('ec2')

        for resource in resources:
            instance_id = resource['InstanceId']
            fetched_attribute = self.manager.retry(
                client.describe_instance_attribute,
                Attribute=attribute,
                InstanceId=instance_id)
            keys = list(fetched_attribute.keys())
            keys.remove('ResponseMetadata')
            keys.remove('InstanceId')
            resource['c7n:attribute-%s' % attribute] = fetched_attribute[
                keys[0]]
