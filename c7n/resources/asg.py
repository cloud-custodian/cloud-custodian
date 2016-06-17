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
from botocore.client import ClientError

from collections import Counter
from concurrent.futures import as_completed

from datetime import datetime, timedelta
from dateutil.parser import parse
from dateutil.tz import tzutc

import logging
import itertools
import time

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import (
    FilterRegistry, ValueFilter, AgeFilter, Filter, FilterValidationError)

from c7n.manager import resources
from c7n.query import QueryResourceManager
from c7n.offhours import Time, OffHour, OnHour
from c7n.tags import TagActionFilter, DEFAULT_TAG, TagCountFilter
from c7n.utils import local_session, query_instances, type_schema, chunks

log = logging.getLogger('custodian.asg')

filters = FilterRegistry('asg.filters')
actions = ActionRegistry('asg.actions')


filters.register('time', Time)
filters.register('offhour', OffHour)
filters.register('onhour', OnHour)
filters.register('tag-count', TagCountFilter)
filters.register('marked-for-op', TagActionFilter)


@resources.register('asg')
class ASG(QueryResourceManager):

    resource_type = "aws.autoscaling.autoScalingGroup"
    filter_registry = filters
    action_registry = actions


class LaunchConfigFilterBase(object):
    """Mixin base class for querying asg launch configs."""

    def initialize(self, asgs):
        """Get launch configs for the set of asgs"""
        config_names = set()
        skip = []

        for a in asgs:
            # Per https://github.com/capitalone/cloud-custodian/issues/143
            if 'LaunchConfigurationName' not in a:
                skip.append(a)
                continue
            config_names.add(a['LaunchConfigurationName'])

        for a in skip:
            asgs.remove(a)

        session = local_session(self.manager.session_factory)
        client = session.client('autoscaling')

        self.configs = {}

        self.log.debug(
            "Querying launch configs for filter %s",
            self.__class__.__name__)
        config_manager = LaunchConfig(self.manager.ctx, {})
        if len(asgs) < 20:
            configs = config_manager.get_resources(
                [asg['LaunchConfigurationName'] for asg in asgs])
        else:
            configs = config_manager.resources()
        self.configs = {
            cfg['LaunchConfigurationName']: cfg for cfg in configs}

    def __call__(self, config):
        return config['LaunchConfigurationName'] not in self.used
            

@filters.register('launch-config')
class LaunchConfigFilter(ValueFilter, LaunchConfigFilterBase):
    """Filter asg by launch config attributes."""
    schema = type_schema(
        'launch-config', rinherit=ValueFilter.schema)

    config = None

    def process(self, asgs, event=None):
        self.initialize(asgs)
        return super(LaunchConfigFilter, self).process(asgs, event)

    def __call__(self, asg):
        # Active launch configs can be deleted..
        cfg = self.configs.get(asg['LaunchConfigurationName'])
        return self.match(cfg)


@filters.register('invalid')
class InvalidConfigFilter(Filter, LaunchConfigFilterBase):
    """
    Filter autoscale groups to find those that are structurally invalid.

    Structurally invalid means that the auto scale group will not be able
    to launch an instance succesfully as the instance.

    - invalid subnets
    - invalid launch config snapshots
    - invalid amis
    - invalid health check elb (slower)

    Internally this tries to reuse other resource managers to get
    their cache effiency.
    """
    schema = type_schema('invalid')
    
    def validate(self):
        if self.manager.data.get('mode'):
            raise FilterValidationError(
                "invalid-config makes too many queries to be run efficiently in lambda")
        return self

    def initialize(self, asgs):
        super(InvalidConfigFilter, self).initialize(asgs)
        import pdb; pdb.set_trace()
        session = local_session(self.manager.session_factory)
        self.subnets = self.get_subnets()
        self.elbs = self.get_elbs()
        self.images = self.get_images()
        self.snapshots = self.get_snapshots()
    
    def get_subnets(self):
        from c7n.resources.vpc import Subnet
        manager = Subnet(self.manager.ctx, {})
        return set([s['SubnetId'] for s in manager.resources()])
    
    def get_elbs(self):
        from c7n.resources.elb import ELB
        manager = ELB(self.manager.ctx, {})
        return set([e['LoadBalancerName'] for e in manager.resources()])
    
    def get_images(self):
        from c7n.resources.ami import AMI
        manager = AMI(self.manager.ctx, {})
        return set([i['ImageId'] for i in manager.resources()])

    def get_snapshots(self):
        from c7n.resources.ebs import Snapshot
        manager = Snapshot(self.manager.ctx, {})
        return set([s['SnapshotId'] for s in manager.resources()])

    def process(self, asgs, event=None):
        self.initialize(asgs)
        return super(InvalidConfigFilter, self).process(asgs, event)
    
    def __call__(self, asg):
        errors = []        
        subnets = asg.get('VPCZoneIdentifier', '').split(',')

        for s in subnets:
            if not s in self.subnets:
                errors.append(('invalid-subnet', s))

        for elb in asg['LoadBalancerNames']:
            if elb not in self.elbs:
                errors.append(('invalid-elb', elb))
                    
        cfg_id = asg.get('LaunchConfigurationName', asg['AutoScalingGroupName'])
        
        cfg = self.configs.get(cfg_id)
        if cfg is None:
            errors.append(('invalid-config', cfg_id))
            self.log.debug(
                "asg:%s no launch config found" % asg['AutoScalingGroupName'])
            asg['Invalid'] = errors
            return True

        if cfg['ImageId'] not in self.images:
            errors.append(('invaid-image', cfg['ImageId']))

        for bd in cfg['BlockDeviceMappings']:
            if 'SnapshotId' not in bd:
                continue
            if bd['SnapshotId'] not in self.snapshots:
                errors.append(('invalid-snapshot', cfg['SnapshotId']))
        if errors:
            asg['Invalid'] = errors
            return True

        
@filters.register('not-encrypted')
class NotEncryptedFilter(Filter, LaunchConfigFilterBase):
    """Check if an asg is configured to have unencrypted volumes.

    Checks both the ami snapshots and the launch configuration.
    """
    schema = type_schema('encrypted', exclude_image={'type': 'boolean'})
    images = unencrypted_configs = unencrypted_images = None

    def process(self, asgs, event=None):
        self.initialize(asgs)
        return super(NotEncryptedFilter, self).process(asgs, event)

    def __call__(self, asg):
        cfg = self.configs.get(asg['LaunchConfigurationName'])
        if not cfg:
            self.log.warning(
                "ASG %s instances: %d has missing config: %s",
                asg['AutoScalingGroupName'], len(asg['Instances']),
                asg['LaunchConfigurationName'])
            return False
        unencrypted = []
        if (not self.data.get('exclude_image')
               and cfg['ImageId'] in self.unencrypted_images):
            unencrypted.append('Image')
        if cfg['LaunchConfigurationName'] in self.unencrypted_configs:
            unencrypted.append('LaunchConfig')
        if unencrypted:
            asg['Unencrypted'] = unencrypted
        return bool(unencrypted)

    def initialize(self, asgs):
        super(NotEncryptedFilter, self).initialize(asgs)
        ec2 = local_session(self.manager.session_factory).client('ec2')
        self.unencrypted_images = self.get_unencrypted_images(ec2)
        self.unencrypted_configs = self.get_unencrypted_configs(ec2)

    def _fetch_images(self, ec2, image_ids):
        while True:
            try:
                return ec2.describe_images(ImageIds=list(image_ids))
            except ClientError as e:
                if e.response['Error']['Code'] == 'InvalidAMIID.NotFound':
                    msg = e.response['Error']['Message']
                    e_ami_id = msg[msg.find("'[")+2:msg.rfind("']")]
                    self.log.warning(
                        "asg:not-encrypted filter image not found %s",
                        e_ami_id)
                    image_ids.remove(e_ami_id)
                    continue
                raise

    def get_unencrypted_images(self, ec2):
        """retrieve images which have unencrypted snapshots referenced."""
        image_ids = set()
        for cfg in self.configs.values():
            image_ids.add(cfg['ImageId'])

        self.log.debug("querying %d images", len(image_ids))
        results = self._fetch_images(ec2, image_ids)
        self.images = {i['ImageId']: i for i in results['Images']}

        unencrypted_images = set()
        for i in self.images.values():
            for bd in i['BlockDeviceMappings']:
                if 'Ebs' in bd and not bd['Ebs'].get('Encrypted'):
                    unencrypted_images.add(i['ImageId'])
                    break
        return unencrypted_images

    def get_unencrypted_configs(self, ec2):
        """retrieve configs that have unencrypted ebs voluems referenced."""
        unencrypted_configs = set()
        snaps = {}
        for cid, c in self.configs.items():
            image = self.images.get(c['ImageId'])
            # image deregistered/unavailable
            if image is not None:
                image_block_devs = {
                    bd['DeviceName']: bd['Ebs']
                    for bd in image['BlockDeviceMappings'] if 'Ebs' in bd}
            else:
                image_block_devs = {}
            for bd in c['BlockDeviceMappings']:
                if 'Ebs' not in bd:
                    continue
                # Launch configs can shadow image devices, images have
                # precedence.
                if bd['DeviceName'] in image_block_devs:
                    continue
                if 'SnapshotId' in bd['Ebs']:
                    snaps.setdefault(
                        bd['Ebs']['SnapshotId'].strip(), []).append(cid)
                elif not bd['Ebs'].get('Encrypted'):
                    unencrypted_configs.add(cid)
        if not snaps:
            return unencrypted_configs

        self.log.debug("querying %d snapshots", len(snaps))
        for s in self.get_snapshots(ec2, snaps.keys()):
            if not s.get('Encrypted'):
                unencrypted_configs.update(snaps[s['SnapshotId']])
        return unencrypted_configs

    def get_snapshots(self, ec2, snap_ids):
        """get snapshots corresponding to id, but tolerant of missing."""
        while True:
            try:
                result = ec2.describe_snapshots(SnapshotIds=snap_ids)
            except ClientError as e:
                if e.response['Error']['Code'] == 'InvalidSnapshot.NotFound':
                    msg = e.response['Error']['Message']
                    e_snap_id = msg[msg.find("'")+1:msg.rfind("'")]
                    self.log.warning("Snapshot not found %s" % e_snap_id)
                    snap_ids.remove(e_snap_id)
                    continue
                raise
            else:
                return result.get('Snapshots', ())


@filters.register('image-age')
class ImageAgeFilter(AgeFilter, LaunchConfigFilterBase):
    """Filter asg by image age."""

    date_attribute = "CreationDate"
    schema = type_schema('image-age', days={'type': 'number'})

    def process(self, asgs, event=None):
        self.initialize(asgs)
        return super(ImageAgeFilter, self).process(asgs, event)

    def initialize(self, asgs):
        super(ImageAgeFilter, self).initialize(asgs)
        image_ids = set()
        for cfg in self.configs.values():
            image_ids.add(cfg['ImageId'])
        ec2 = local_session(self.manager.session_factory).client('ec2')
        results = ec2.describe_images(ImageIds=list(image_ids))
        self.images = {i['ImageId']: i for i in results['Images']}

    def get_resource_date(self, i):
        cfg = self.configs[i['LaunchConfigurationName']]
        ami = self.images[cfg['ImageId']]
        return parse(ami[self.date_attribute])


@filters.register('vpc-id')
class VpcIdFilter(ValueFilter):

    schema = type_schema(
        'vpc-id', rinherit=ValueFilter.schema)
    schema['properties'].pop('key')

    def __init__(self, data, manager=None):
        super(VpcIdFilter, self).__init__(data, manager)
        self.data['key'] = 'VpcId'

    def process(self, asgs, event=None):
        subnets = {}
        for a in asgs:
            subnet_ids = a.get('VPCZoneIdentifier', '')
            if not subnet_ids:
                continue
            subnets.setdefault(subnet_ids.split(',')[0], []).append(a)

        session = local_session(self.manager.session_factory)
        ec2 = session.client('ec2')

        # Invalid subnets on asgs happen, so query all
        all_subnets = {s['SubnetId']: s for s in ec2.describe_subnets()[
            'Subnets']}

        for s, s_asgs in subnets.items():
            if s not in all_subnets:
                self.log.warning(
                    "invalid subnet %s for asgs: %s",
                    s, [a['AutoScalingGroupName'] for a in s_asgs])
                continue
            for a in s_asgs:
                a['VpcId'] = all_subnets[s]['VpcId']
        return super(VpcIdFilter, self).process(asgs)


@actions.register('remove-tag')
@actions.register('untag')
@actions.register('unmark')
class RemoveTag(BaseAction):

    schema = type_schema(
        'remove-tag',
        aliases=('untag', 'unmark'),
        key={'type': 'string'})

    def process(self, asgs):
        error = False
        key = self.data.get('key', DEFAULT_TAG)
        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for asg_set in chunks(asgs, 20):
                futures[w.submit(self.process_asg_set, asg_set, key)] = asg_set
            for f in as_completed(futures):
                asg_set = futures[f]
                if f.exception():
                    error = f.exception()
                    self.log.exception(
                        "Exception untagging asg:%s tag:%s error:%s" % (
                            ", ".join([a['AutoScalingGroupName']
                                       for a in asg_set]),
                            self.data.get('key', DEFAULT_TAG),
                            f.exception()))
        if error:
            raise error

    def process_asg_set(self, asgs, key):
        session = local_session(self.manager.session_factory)
        client = session.client('autoscaling')
        tags= [dict(Key=key, ResourceType='auto-scaling-group',
                    ResourceId=a['AutoScalingGroupName']) for a in asgs]
        client.delete_tags(Tags=tags)


@actions.register('tag')
@actions.register('mark')
class Tag(BaseAction):

    schema = type_schema(
        'tag',
        key={'type': 'string'},
        value={'type': 'string'},
        # Backwards compatibility
        tag={'type': 'string'},
        msg={'type': 'string'},
        propagate={'type': 'boolean'})

    def process(self, asgs):
        error = False
        key = self.data.get('key', self.data.get('tag', DEFAULT_TAG))
        value = self.data.get(
            'value', self.data.get(
                'msg', 'AutoScaleGroup does not meet policy guidelines'))
        return self.tag(asgs, key, value)

    def tag(self, asgs, key, value):
        error = None
        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for asg_set in chunks(asgs, 20):
                futures[w.submit(
                    self.process_asg_set, asg_set, key, value)] = asg_set
            for f in as_completed(futures):
                asg_set = futures[f]
                if f.exception():
                    error = f.exception()
                    self.log.exception(
                        "Exception untagging tag:%s error:%s asg:%s" % (
                            self.data.get('key', DEFAULT_TAG),
                            f.exception(),
                            ", ".join([a['AutoScalingGroupName']
                                       for a in asg_set])))
        if error:
            raise error

    def process_asg_set(self, asgs, key, value):
        session = local_session(self.manager.session_factory)
        client = session.client('autoscaling')
        propagate = self.data.get('propagate_launch', True)
        tags= [dict(Key=key, ResourceType='auto-scaling-group', Value=value,
                    PropagateAtLaunch=propagate,
                    ResourceId=a['AutoScalingGroupName']) for a in asgs]
        client.create_or_update_tags(Tags=tags)


@actions.register('propagate-tags')
class PropagateTags(BaseAction):
    """Propagate tags to an asg instances.

    In AWS changing an asg tag does not propagate to instances.

    This action exists to do that, and can also trim older tags
    not present on the asg anymore that are present on instances.
    """

    schema = type_schema(
        'propagate-tags',
        tags={'type': 'array', 'items': {'type': 'string'}},
        trim={'type': 'boolean'})

    def validate(self):
        if not isinstance(self.data.get('tags', []), (list, tuple)):
            raise ValueError("No tags specified")
        return self

    def process(self, asgs):
        if not asgs:
            return
        if self.data.get('trim', False):
            self.instance_map = self.get_instance_map(asgs)
        with self.executor_factory(max_workers=10) as w:
            instance_count = sum(list(w.map(self.process_asg, asgs)))
            self.log.info("Applied tags to %d instances" % instance_count)

    def process_asg(self, asg):
        client = local_session(self.manager.session_factory).client('ec2')
        instance_ids = [i['InstanceId'] for i in asg['Instances']]
        tag_map = {t['Key']: t['Value'] for t in asg.get('Tags', [])
                   if t['PropagateAtLaunch']
                   and not t['Key'].startswith('aws:')}

        if self.data.get('tags'):
            tag_map = {
                k: v for k, v in tag_map.items()
                if k in self.data['tags']}

        tag_set = set(tag_map)
        if self.data.get('trim', False):
            instances = [self.instance_map[i] for i in instance_ids]
            self.prune_instance_tags(client, asg, tag_set, instances)
        if not self.manager.config.dryrun:
            client.create_tags(
                Resources=instance_ids,
                Tags=[{'Key': k, 'Value': v} for k, v in tag_map.items()])
        return len(instance_ids)

    def prune_instance_tags(self, client, asg, tag_set, instances):
        """Remove tags present on all asg instances which are not present
        on the asg.
        """
        instance_tags = Counter()
        instance_count = len(instances)

        remove_tags = []
        extra_tags = []

        for i in instances:
            instance_tags.update([
                t['Key'] for t in i['Tags']
                if not t['Key'].startswith('aws:')])
        for k, v in instance_tags.items():
            if not v >= instance_count:
                extra_tags.append(k)
                continue
            if k not in tag_set:
                remove_tags.append(k)

        if remove_tags:
            log.debug("Pruning asg:%s instances:%d of old tags: %s" % (
                asg['AutoScalingGroupName'], instance_count, remove_tags))
        if extra_tags:
            log.debug("Asg: %s has uneven tags population: %s" % (
                asg['AutoScalingGroupName'], instance_tags))
        # Remove orphan tags
        remove_tags.extend(extra_tags)

        if not self.manager.config.dryrun:
            client.delete_tags(
                Resources=[i['InstanceId'] for i in instances],
                Tags=[{'Key': t} for t in remove_tags])

    def get_instance_map(self, asgs):
        instance_ids = [
            i['InstanceId'] for i in
            list(itertools.chain(*[
                g['Instances']
                for g in asgs if g['Instances']]))]
        if not instance_ids:
            return {}
        instances = query_instances(
            local_session(self.manager.session_factory),
            InstanceIds=instance_ids)
        return {i['InstanceId']: i for i in instances}


@actions.register('rename-tag')
class RenameTag(BaseAction):
    """Rename a tag on an AutoScaleGroup.
    """

    schema = type_schema(
        'rename-tag', required=['source', 'dest'],
        propagate={'type': 'boolean'},
        source={'type': 'string'},
        dest={'type': 'string'})

    def process(self, asgs):
        source = self.data.get('source')
        dest = self.data.get('dest')
        count = len(asgs)

        filtered = []
        for a in asgs:
            for t in a.get('Tags'):
                if t['Key'] == source:
                    filtered.append(a)
                    break
        asgs = filtered
        self.log.info("Filtered from %d asgs to %d" % (
            count, len(asgs)))
        self.log.info("Renaming %s to %s on %d asgs" % (
            source, dest, len(filtered)))

        with self.executor_factory(max_workers=3) as w:
            list(w.map(self.process_asg, asgs))

    def process_asg(self, asg):
        """Move source tag to destination tag.

        Check tag count on asg
        Create new tag tag
        Delete old tag
        Check tag count on instance
        Create new tag
        Delete old tag
        """
        source_tag = self.data.get('source')
        tag_map = {t['Key']: t for t in asg.get('Tags', [])}
        source = tag_map[source_tag]
        destination_tag = self.data.get('dest')
        propagate = self.data.get('propagate', True)
        client = local_session(
            self.manager.session_factory).client('autoscaling')
        # technically safer to create first, but running into
        # max tags constraints, otherwise.
        #
        # delete_first = len([t for t in tag_map if not t.startswith('aws:')])
        client.delete_tags(Tags=[
            {'ResourceId': asg['AutoScalingGroupName'],
             'ResourceType': 'auto-scaling-group',
             'Key': source_tag,
             'Value': source['Value']}])
        client.create_or_update_tags(Tags=[
            {'ResourceId': asg['AutoScalingGroupName'],
             'ResourceType': 'auto-scaling-group',
             'PropagateAtLaunch': propagate,
             'Key': destination_tag,
             'Value': source['Value']}])
        self.propogate_instance_tag(source, destination_tag, asg)

    def propogate_instance_tag(self, source, destination_tag, asg):
        client = local_session(self.manager.session_factory).client('ec2')
        client.delete_tags(
            Resources=[i['InstanceId'] for i in asg['Instances']],
            Tags=[{"Key": source['Key']}])
        client.create_tags(
            Resources=[i['InstanceId'] for i in asg['Instances']],
            Tags=[{'Key': source['Key'], 'Value': source['Value']}])


@actions.register('mark-for-op')
class MarkForOp(Tag):

    schema = type_schema(
        'mark-for-op',
        op={'enum': ['suspend', 'resume', 'delete']},
        key={'type': 'string'},
        days={'type': 'number', 'minimum': 0})

    def process(self, asgs):
        msg_tmpl = self.data.get(
            'msg',
            'AutoScaleGroup does not meet org tag policy: {op}@{stop_date}')

        op = self.data.get('op', 'suspend')
        date = self.data.get('days', 4)

        n = datetime.now(tz=tzutc())
        stop_date = n + timedelta(days=date)
        msg = msg_tmpl.format(
            op=op, stop_date=stop_date.strftime('%Y/%m/%d'))

        self.log.info("Tagging %d asgs for %s on %s" % (
            len(asgs), op, stop_date.strftime('%Y/%m/%d')))
        self.tag(asgs, self.data['key'], msg)


@actions.register('suspend')
class Suspend(BaseAction):

    schema = type_schema('suspend')

    def process(self, asgs):
        original_count = len(asgs)
        asgs = [a for a in asgs if a['Instances']]
        self.log.debug("Filtered from %d to %d asgs with instances" % (
            original_count, len(asgs)))
        with self.executor_factory(max_workers=3) as w:
            list(w.map(self.process_asg, asgs))

    def process_asg(self, asg):
        """Multistep process to stop an asg aprori of setup

        - suspend processes
        - note load balancer in tag
        - detach load balancer
        - stop instances
        """
        session = local_session(self.manager.session_factory)
        asg_client = session.client('autoscaling')
        asg_client.suspend_processes(
            AutoScalingGroupName=asg['AutoScalingGroupName'])
        ec2_client = session.client('ec2')
        try:
            ec2_client.stop_instances(
                InstanceIds=[i['InstanceId'] for i in asg['Instances']])
        except ClientError as e:
            if e.response['Error']['Code'] in (
                    'InvalidInstanceID.NotFound',
                    'IncorrectInstanceState'):
                log.warning("Erroring stopping asg instances %s %s" % (
                    asg['AutoScalingGroupName'], e))
                return
            raise


@actions.register('resume')
class Resume(BaseAction):
    """Resume a suspended autoscale group and its instances
    """
    schema = type_schema('resume', delay={'type': 'integer'})

    def process(self, asgs):
        original_count = len(asgs)
        asgs = [a for a in asgs if a['SuspendedProcesses']]
        self.delay = self.data.get('delay', 30)
        self.log.debug("Filtered from %d to %d suspended asgs" % (
            original_count, len(asgs)))

        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for a in asgs:
                futures[w.submit(self.resume_asg_instances, a)] = a
            for f in as_completed(futures):
                if f.exception():
                    log.error("Traceback resume asg:%s instances error:%s" % (
                        futures[f]['AutoScalingGroupName'],
                        f.exception()))
                    continue

        log.debug("Sleeping for asg health check grace")
        time.sleep(self.delay)

        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for a in asgs:
                futures[w.submit(self.resume_asg, a)] = a
            for f in as_completed(futures):
                if f.exception():
                    log.error("Traceback resume asg:%s error:%s" % (
                        futures[f]['AutoScalingGroupName'],
                        f.exception()))

    def resume_asg_instances(self, asg):
        """Resume asg instances.
        """
        session = local_session(self.manager.session_factory)
        ec2_client = session.client('ec2')
        ec2_client.start_instances(
            InstanceIds=[i['InstanceId'] for i in asg['Instances']])

    def resume_asg(self, asg):
        """Resume asg processes.
        """
        session = local_session(self.manager.session_factory)
        asg_client = session.client('autoscaling')
        asg_client.resume_processes(
            AutoScalingGroupName=asg['AutoScalingGroupName'])


@actions.register('delete')
class Delete(BaseAction):

    schema = type_schema('delete', force={'type': 'boolean'})

    def process(self, asgs):
        with self.executor_factory(max_workers=5) as w:
            list(w.map(self.process_asg, asgs))

    def process_asg(self, asg):
        force_delete = self.data.get('force', False)
        if force_delete:
            log.info('Forcing deletion of Auto Scaling group %s' % (
                asg['AutoScalingGroupName']))
        session = local_session(self.manager.session_factory)
        asg_client = session.client('autoscaling')
        asg_client.delete_auto_scaling_group(
                AutoScalingGroupName=asg['AutoScalingGroupName'],
                ForceDelete=force_delete)


@resources.register('launch-config')
class LaunchConfig(QueryResourceManager):

    resource_type = "aws.autoscaling.launchConfigurationName"

    
@LaunchConfig.filter_registry.register('age')
class LaunchConfigAge(AgeFilter):

    date_attribute = "CreatedTime"
    schema = type_schema('age', days={'type': 'number'})


@LaunchConfig.filter_registry.register('unused')
class UnusedLaunchConfig(Filter):

    schema = type_schema('unused')

    def process(self, configs, event=None):
        asgs = self.manager._cache.get(
            {'region': self.manager.config.region,
             'resource': 'asg'})
        if asgs is None:
            self.log.debug(
                "Querying asgs to determine unused launch configs")
            asg_manager = ASG(self.manager.ctx, {})
            asgs = asg_manager.resources()
        self.used = set([a['LaunchConfigurationName'] for a in asgs])
        return super(UnusedLaunchConfig, self).process(configs)

    def __call__(self, config):
        return config['LaunchConfigurationName'] not in self.used


@LaunchConfig.action_registry.register('delete')
class LaunchConfigDelete(BaseAction):

    schema = type_schema('delete')

    def process(self, configs):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_config, configs))

    def process_config(self, config):
        session = local_session(self.manager.session_factory)
        client = session.client('autoscaling')
        try:
            client.delete_launch_configuration(
                LaunchConfigurationName=config[
                    'LaunchConfigurationName'])
        except ClientError as e:
            # Catch already deleted
            if e.response['Error']['Code'] == 'ValidationError':
                return

        
