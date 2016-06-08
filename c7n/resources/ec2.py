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
import itertools
import operator

from dateutil.parser import parse
from concurrent.futures import as_completed

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import (
    FilterRegistry, AgeFilter, ValueFilter, Filter
)

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.offhours import OffHour, OnHour
from c7n import tags, utils
from c7n.utils import type_schema


filters = FilterRegistry('ec2.filters')
actions = ActionRegistry('ec2.actions')

tags.register_tags(filters, actions, 'InstanceId')


@resources.register('ec2')
class EC2(QueryResourceManager):

    resource_type = "aws.ec2.instance"
    filter_registry = filters
    action_registry = actions

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


class StateTransitionFilter(object):
    """Filter instances by state.

    Try to simplify construction for policy authors by automatically
    filtering elements (filters or actions) to the instances states
    they are valid for.

    For more details see http://goo.gl/TZH9Q5

    """
    valid_origin_states = ()

    def filter_instance_state(self, instances):
        orig_length = len(instances)
        results = [i for i in instances
                   if i['State']['Name'] in self.valid_origin_states]
        self.log.info("%s %d of %d instances" % (
            self.__class__.__name__, len(results), orig_length))
        return results


@filters.register('ebs')
class AttachedVolume(ValueFilter):

    schema = type_schema(
        'ebs', rinherit=ValueFilter.schema,
        **{'operator': {'enum': ['and', 'or']},
           'skip-devices': {'type': 'array', 'items': {'type': 'string'}}})

    def process(self, resources, event=None):
        self.volume_map = self.get_volume_mapping(resources)
        self.skip = self.data.get('skip-devices', [])
        self.operator = self.data.get(
            'operator', 'or') == 'or' and any or all
        return filter(self, resources)

    def get_volume_mapping(self, resources):
        volume_map = {}
        ec2 = utils.local_session(self.manager.session_factory).client('ec2')
        for instance_set in utils.chunks(
                [i['InstanceId'] for i in resources], 200):
            self.log.debug("Processing %d instance of %d" % (
                len(instance_set), len(resources)))
            results = ec2.describe_volumes(
                Filters=[
                    {'Name': 'attachment.instance-id',
                     'Values': instance_set}])
            for v in results['Volumes']:
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


class InstanceImageBase(object):

    def get_image_mapping(self, resources):
        ec2 = utils.local_session(self.manager.session_factory).client('ec2')
        image_ids = set([i['ImageId'] for i in resources])
        results = ec2.describe_images(ImageIds=list(image_ids))
        return {i['ImageId']: i for i in results['Images']}


@filters.register('image-age')
class ImageAge(AgeFilter, InstanceImageBase):

    date_attribute = "CreationDate"

    schema = type_schema('image-age', days={'type': 'number'})

    def process(self, resources, event=None):
        self.image_map = self.get_image_mapping(resources)
        return super(ImageAge, self).process(resources, event)

    def get_resource_date(self, i):
        if i['ImageId'] not in self.image_map:
            # our image is no longer available
            return parse("2000-01-01T01:01:01.000Z")
        image = self.image_map[i['ImageId']]
        return parse(image['CreationDate'])


@filters.register('image')
class InstanceImage(ValueFilter, InstanceImageBase):

    schema = type_schema('image', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):
        self.image_map = self.get_image_mapping(resources)
        return map(self, resources)

    def __call__(self, i):
        image = self.image_map.get(i['InstanceId'])
        if not image:
            self.log.warning(
                "Could not locate image for instance:%s ami:%s" % (
                    i['InstanceId'], i["ImageId"]))
            # Match instead on empty skeleton?
            return False
        return self.match(image)


@filters.register('offhour')
class InstanceOffHour(OffHour, StateTransitionFilter):

    valid_origin_states = ('running',)
    schema = type_schema('offhour', inherits=['#/definitions/filters/time'])

    def process(self, resources, event=None):
        return super(InstanceOffHour, self).process(
            self.filter_instance_state(resources))


@filters.register('onhour')
class InstanceOnHour(OnHour, StateTransitionFilter):

    valid_origin_states = ('stopped',)

    schema = type_schema('onhour', inherits=['#/definitions/filters/time'])

    def process(self, resources, event=None):
        return super(InstanceOnHour, self).process(
            self.filter_instance_state(resources))


@filters.register('ephemeral')
class EphemeralInstanceFilter(Filter):

    schema = type_schema('ephemeral')

    def __call__(self, i):
        return self.is_ephemeral(i)

    @staticmethod
    def is_ephemeral(i):
        for bd in i.get('BlockDeviceMappings', []):
            if bd['DeviceName'] in ('/dev/sda1', '/dev/xvda'):
                if 'Ebs' in bd:
                    return False
                return True
        return True


@filters.register('instance-uptime')
class UpTimeFilter(AgeFilter):

    date_attribute = "LaunchTime"

    schema = type_schema('instance-uptime', days={'type': 'number'})


@filters.register('instance-age')
class InstanceAgeFilter(AgeFilter):

    date_attribute = "LaunchTime"
    ebs_key_func = operator.itemgetter('AttachTime')

    schema = type_schema('instance-age', days={'type': 'number'})

    def get_resource_date(self, i):
        # LaunchTime is basically how long has the instance
        # been on, use the oldest ebs vol attach time
        found = False
        ebs_vols = [
            block['Ebs'] for block in i['BlockDeviceMappings']
            if 'Ebs' in block]
        if not ebs_vols:
            # Fall back to using age attribute (ephemeral instances)
            return super(InstanceAgeFilter, self).get_resource_date(i)
        # Lexographical sort on date
        ebs_vols = sorted(ebs_vols, key=self.ebs_key_func)
        return ebs_vols[0]['AttachTime']


@actions.register('start')
class Start(BaseAction, StateTransitionFilter):

    valid_origin_states = ('stopped',)

    schema = type_schema('start')

    def process(self, instances):
        instances = self.filter_instance_state(instances)
        if not len(instances):
            return
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        self._run_api(
            client.start_instances,
            InstanceIds=[i['InstanceId'] for i in instances],
            DryRun=self.manager.config.dryrun)


@actions.register('stop')
class Stop(BaseAction, StateTransitionFilter):
    """Stop instances
    """
    valid_origin_states = ('running',)

    schema =  type_schema(
        'stop', **{'terminate-ephemeral': {'type': 'boolean'}})

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
            self._run_api(
                client.terminate_instances,
                InstanceIds=[i['InstanceId'] for i in ephemeral],
                DryRun=self.manager.config.dryrun)
        if persistent:
            self._run_api(
                client.stop_instances,
                InstanceIds=[i['InstanceId'] for i in persistent],
                DryRun=self.manager.config.dryrun)


@actions.register('terminate')
class Terminate(BaseAction, StateTransitionFilter):
    """ Terminate a set of instances.

    While ec2 offers a bulk delete api, any given instance can be configured
    with api deletion termination protection, so we can't use the bulk call
    reliabily, we need to process the instances individually. Additionally
    If we're configured with 'force' then we'll turn off instance termination
    protection.
    """

    valid_origin_states = ('running', 'stopped', 'pending', 'stopping')

    schema = type_schema('terminate', force={'type': 'boolean'})

    def process(self, instances):
        instances = self.filter_instance_state(instances)
        if not len(instances):
            return
        if self.data.get('force'):
            self.log.info("Disabling termination protection on instances")
            self.disable_deletion_protection(instances)
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        # limit batch sizes to avoid api limits
        for batch in utils.chunks(instances, 100):
            self._run_api(
                client.terminate_instances,
                InstanceIds=[i['InstanceId'] for i in instances],
                DryRun=self.manager.config.dryrun)

    def disable_deletion_protection(self, instances):
        def process_instance(i):
            client = utils.local_session(
                self.manager.session_factory).client('ec2')
            self._run_api(
                client.modify_instance_attribute,
                InstanceId=i['InstanceId'],
                Attribute='disableApiTermination',
                Value='false',
                DryRun=self.manager.config.dryrun)

        with self.executor_factory(max_workers=2) as w:
            list(w.map(process_instance, instances))


@actions.register('snapshot')
class Snapshot(BaseAction):

    schema = type_schema(
        'snapshot',
        **{'copy-tags': {'type': 'array', 'items': {'type': 'string'}}})

    def process(self, resources):
        for resource in resources:
            with self.executor_factory(max_workers=3) as w:
                futures = []
                futures.append(w.submit(self.process_volume_set, resource))
                for f in as_completed(futures):
                    if f.exception():
                        self.log.error(
                            "Exception creating snapshot set \n %s" % (
                                f.exception()))

    def process_volume_set(self, resource):
        c = utils.local_session(self.manager.session_factory).client('ec2')
        for block_device in resource['BlockDeviceMappings']:
            if 'Ebs' not in block_device:
                continue
            description = "Automated,Backup,%s,%s" % (
                resource['InstanceId'],
                block_device['Ebs']['VolumeId'])
            response = c.create_snapshot(
                DryRun=self.manager.config.dryrun,
                VolumeId=block_device['Ebs']['VolumeId'],
                Description=description)

            tags = [
                {'Key': 'Name', 'Value': block_device['Ebs']['VolumeId']},
                {'Key': 'InstanceId', 'Value': resource['InstanceId']},
                {'Key': 'DeviceName', 'Value': block_device['DeviceName']}
            ]

            copy_keys = self.data.get('copy-tags', [])
            copy_tags = []
            if copy_keys:
                for t in resource.get('Tags', []):
                    if t['Key'] in copy_keys:
                        copy_tags.append(t)

            if len(copy_tags) + len(tags) > 10:
                log.warning(
                    "action:%s volume:%s too many tags to copy" % (
                        self.__class__.__name__.lower(),
                        block_device['Ebs']['VolumeId']))
                copy_tags = []

            tags.extend(copy_tags)

            c.create_tags(
                DryRun=self.manager.config.dryrun,
                Resources=[
                    response['SnapshotId']],
                Tags=tags)


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
        if not len(self.data.keys()) == 1:
            raise ValueError(
                "EC2 Query Filter Invalid %s" % self.data)
        self.key = self.data.keys()[0]
        self.value = self.data.values()[0]

        if self.key not in EC2_VALID_FILTERS and not self.key.startswith(
                'tag:'):
            raise ValueError(
                "EC2 Query Filter invalid filter name %s" % (self.data))

        if self.value is None:
            raise ValueError(
                "EC2 Query Filters must have a value, use tag-key"
                " w/ tag name as value for tag present checks"
                " %s" % self.data)
        return self

    def query(self):
        value = self.value
        if isinstance(self.value, basestring):
            value = [self.value]

        return {'Name': self.key, 'Values': value}
