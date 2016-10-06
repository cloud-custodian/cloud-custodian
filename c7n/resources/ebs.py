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
import logging

from botocore.exceptions import ClientError
from concurrent.futures import as_completed

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import (
    Filter, FilterRegistry, AgeFilter, ValueFilter, ANNOTATION_KEY,
    FilterValidationError, OPERATORS)

from c7n.manager import resources
from c7n.resources.kms import ResourceKmsKeyAlias
from c7n.query import QueryResourceManager, ResourceQuery
from c7n.utils import (
    local_session, set_annotation, query_instances, chunks, type_schema)
from c7n.resources.ami import AMI

log = logging.getLogger('custodian.ebs')

filters = FilterRegistry('ebs.filters')
actions = ActionRegistry('ebs.actions')


@resources.register('ebs-snapshot')
class Snapshot(QueryResourceManager):

    resource_type = "aws.ec2.snapshot"
    filter_registry = FilterRegistry('ebs-snapshot.filters')
    action_registry = ActionRegistry('ebs-snapshot.actions')


@Snapshot.filter_registry.register('age')
class SnapshotAge(AgeFilter):

    schema = type_schema(
        'age',
        days={'type': 'number'},
        op={'type': 'string', 'enum': OPERATORS.keys()})
    date_attribute = 'StartTime'
    

def _filter_ami_snapshots(self, snapshots):
    if not self.data.get('value', True):
        return snapshots
    #try using cache first to get a listing of all AMI snapshots and compares resources to the list
    #This will populate the cache.
    ami_manager = AMI(self.manager.ctx, {})
    amis = ami_manager.resources()
    ami_snaps = []
    for i in amis:
        for dev in i.get('BlockDeviceMappings'):
            if 'Ebs' in dev and 'SnapshotId' in dev['Ebs']:
                ami_snaps.append(dev['Ebs']['SnapshotId'])            
    matches = []
    for snap in snapshots:
        if snap['SnapshotId'] not in ami_snaps:
            matches.append(snap)
    return matches
        

@Snapshot.filter_registry.register('skip-ami-snapshots')
class SnapshotSkipAmiSnapshots(Filter):
    
    schema = type_schema('skip-ami-snapshots', value={'type': 'boolean'})
    
    def validate(self):
        if self.data.get('skip-ami-snapshots', not True or False):
            raise FilterValidationError(
                "invalid config: expected boolean value")
        return self
    
    def process(self, snapshots, event=None):
        resources = _filter_ami_snapshots(self, snapshots)
        return resources
    
    
@Snapshot.action_registry.register('delete')
class SnapshotDelete(BaseAction):

    schema = type_schema(
        'delete', **{'skip-ami-snapshots': {'type': 'boolean'}})

    def process(self, snapshots):
        self.image_snapshots = snaps = set()
         # Be careful re image snapshots, we do this by default
        # to keep things safe by default, albeit we'd get an error
        # if we did try to delete something associated to an image.
        pre = len(snapshots)
        snapshots = filter(None, _filter_ami_snapshots(self, snapshots))
        post = len(snapshots)
        log.info("Deleting %d snapshots, auto-filtered %d ami-snapshots" %(post, pre-post))
        
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for snapshot_set in chunks(reversed(snapshots), size=50):
                futures.append(
                    w.submit(self.process_snapshot_set, snapshot_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting snapshot set \n %s" % (
                            f.exception()))
        return snapshots

    def process_snapshot_set(self, snapshots_set):
        c = local_session(self.manager.session_factory).client('ec2')
        for s in snapshots_set:
            if s['SnapshotId'] in self.image_snapshots:
                continue
            try:
                c.delete_snapshot(
                    SnapshotId=s['SnapshotId'],
                    DryRun=self.manager.config.dryrun)
            except ClientError as e:
                if e.response['Error']['Code'] == "InvalidSnapshot.NotFound":
                    continue
                raise


@Snapshot.action_registry.register('copy')
class CopySnapshot(BaseAction):
    """Copy a snapshot across regions

    http://goo.gl/CP3dq
    """

    schema = type_schema(
        'copy',
        target_region={'type': 'string'},
        target_key={'type': 'string'},
        encrypted={'type': 'boolean'},
    )

    def validate(self):
        if self.data.get('encrypted', True):
            key = self.data.get('target_key')
            if not key:
                raise FilterValidationError(
                    "Encrypted snapshot copy requires kms key")
        return self

    def process(self, resources):
        if self.data['target_region'] == self.manager.config.region:
            self.log.info(
                "Source and destination region are the same, skipping")
            return

        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_resource_set, chunks(resources, 20)))

    def process_resource_set(self, resource_set):
        client = self.manager.session_factory(
            region=self.data['target_region']).client('ec2')

        if self.data['target_region'] != self.manager.config.region:
            cross_region = True

        params = {}
        params['Encrypted'] = self.data.get('encrypted', True)
        if params['Encrypted']:
            params['KmsKeyId'] = self.data['target_key']

        for snapshot_set in chunks(resource_set, 5):
            for r in snapshot_set:
                snapshot_id = client.copy_snapshot(
                    SourceRegion=self.manager.config.region,
                    SourceSnapshotId=r['SnapshotId'],
                    Description=r.get('Description', ''),
                    **params)['SnapshotId']
                client.create_tags(
                    Resources=[snapshot_id],
                    Tags=r['Tags'])
                r['CopiedSnapshot'] = snapshot_id

            if not cross_region or len(snapshot_set) < 5:
                continue

            copy_ids = [r['CopiedSnapshot'] for r in snapshot_set]
            self.log.debug(
                "Waiting on cross-region snapshot copy %s", ",".join(copy_ids))
            waiter = client.get_waiter('snapshot_completed')
            waiter.config.delay = 60
            waiter.config.max_attempts = 60
            waiter.wait(SnapshotIds=copy_ids)
            self.log.debug(
                "Cross region copy complete %s", ",".join(copy_ids))


@resources.register('ebs')
class EBS(QueryResourceManager):

    class resource_type(ResourceQuery.resolve("aws.ec2.volume")):
        default_namespace = 'AWS/EBS'
        config_type = "AWS::EC::Volume"

    filter_registry = filters
    action_registry = actions


@filters.register('instance')
class AttachedInstanceFilter(ValueFilter):
    """Filter volumes based on filtering on their attached instance"""

    schema = type_schema('instance', rinherit=ValueFilter.schema)

    def process(self, resources, event=None):
        original_count = len(resources)
        resources = [r for r in resources if r.get('Attachments')]
        self.log.debug('Filtered from %d volumes to %d attached volumes' % (
            original_count, len(resources)))
        self.instance_map = self.get_instance_mapping(resources)
        return filter(self, resources)

    def __call__(self, r):
        instance = self.instance_map[r['Attachments'][0]['InstanceId']]
        if self.match(instance):
            r['Instance'] = instance
            set_annotation(r, ANNOTATION_KEY, "instance-%s" % self.k)
            return True

    def get_instance_mapping(self, resources):
        instance_ids = [r['Attachments'][0]['InstanceId'] for r in resources]
        instances = query_instances(
            local_session(self.manager.session_factory),
            InstanceIds=instance_ids)
        self.log.debug("Queried %d instances for %d volumes" % (
            len(instances), len(resources)))
        return {i['InstanceId']: i for i in instances}


@filters.register('kms-alias')
class KmsKeyAlias(ResourceKmsKeyAlias):

    def process(self, resources, event=None):
        return self.get_matching_aliases(resources)


@actions.register('copy-instance-tags')
class CopyInstanceTags(BaseAction):
    """Copy instance tags to its attached volume.

    Useful for cost allocation to ebs volumes and tracking usage
    info for volumes.

    Mostly useful for volumes not set to delete on termination, which
    are otherwise candidates for garbage collection, copying the
    instance tags gives us more semantic information to determine if
    their useful, as well letting us know the last time the volume
    was actually used.
    """

    schema = type_schema(
        'copy-instance-tags',
        tags={'type': 'array', 'items': {'type': 'string'}})

    def process(self, volumes):
        volumes = [v for v in volumes if v['Attachments']]
        with self.executor_factory(max_workers=10) as w:
            futures = []
            for volume_set in chunks(reversed(volumes), size=100):
                futures.append(
                    w.submit(self.process_volume_set, volume_set))

            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception copying instance tags \n %s" % (
                            f.exception()))

    def process_volume_set(self, volume_set):
        instance_vol_map = {}
        for v in volume_set:
            instance_vol_map.setdefault(
                v['Attachments'][0]['InstanceId'], []).append(v)

        instance_map = {i['InstanceId']: i for i in query_instances(
            local_session(self.manager.session_factory),
            InstanceIds=instance_vol_map.keys())}

        for i in instance_vol_map:
            try:
                self.process_instance_volumes(
                    instance_map[i], instance_vol_map[i])
            except Exception as e:
                self.log.exception(
                    "Error copying instance tags to volumes \n %s" % e)

    def process_instance_volumes(self, instance, volumes):
        client = local_session(self.manager.session_factory).client('ec2')

        for v in volumes:
            copy_tags = self.get_volume_tags(v, instance, v['Attachments'][0])
            if not copy_tags:
                continue
            # Can't add more tags than the resource supports could try
            # to delete extant ones inline, else trim-tags action.
            if len(copy_tags) > 40:
                log.warning(
                    "action:%s volume:%s instance:%s too many tags to copy" % (
                        self.__class__.__name__.lower(),
                        v['VolumeId'], instance['InstanceId']))
                continue

            try:
                self.manager.retry(
                    client.create_tags,
                    Resources=[v['VolumeId']],
                    Tags=copy_tags,
                    DryRun=self.manager.config.dryrun)
            except ClientError as e:
                if e.response['Error']['Code'] == "InvalidVolume.NotFound":
                    continue
                raise

    def get_volume_tags(self, volume, instance, attachment):
        only_tags = self.data.get('tags', [])  # specify which tags to copy
        copy_tags = []
        extant_tags = dict([
            (t['Key'], t['Value']) for t in volume.get('Tags', [])])

        for t in instance.get('Tags', ()):
            if only_tags and not t['Key'] in only_tags:
                continue
            if t['Key'] in extant_tags and t['Value'] == extant_tags[t['Key']]:
                continue
            if t['Key'].startswith('aws:'):
                continue
            copy_tags.append(t)

        # Don't add attachment tags if we're already current
        if 'LastAttachInstance' in extant_tags \
           and extant_tags['LastAttachInstance'] == attachment['InstanceId']:
            return copy_tags

        copy_tags.append(
            {'Key': 'LastAttachTime',
             'Value': attachment['AttachTime'].isoformat()})
        copy_tags.append(
            {'Key': 'LastAttachInstance', 'Value': attachment['InstanceId']})
        return copy_tags


@actions.register('encrypt-instance-volumes')
class EncryptInstanceVolumes(BaseAction):
    """Encrypt extant volumes attached to an instance

    - Requires instance restart
    - Not suitable for autoscale groups.

    Multistep process
    -----------------

    - Stop instance (if running)
    - For each volume
       - Create snapshot
       - Wait on snapshot creation
       - Copy Snapshot to create encrypted snapshot
       - Wait on snapshot creation
       - Create encrypted volume from snapshot
       - Wait on volume creation
       - Delete transient snapshots
       - Detach Unencrypted Volume
       - Attach Encrypted Volume
    - For each volume
       - Delete unencrypted volume
    - Start Instance (if originally running)

    """

    schema = type_schema(
        'encrypt-instance-volumes',
        required=['key'],
        key={'type': 'string'},
        delay={'type': 'number'},
        verbose={'type': 'boolean'})

    def validate(self):
        key = self.data.get('key')
        if not key:
            raise ValueError(
                "action:encrypt-instance-volume "
                "requires kms keyid/alias specified")
        self.verbose = self.data.get('verbose', False)
        return self

    def process(self, volumes):
        original_count = len(volumes)
        volumes = [v for v in volumes
                   if not v['Encrypted'] or not v['Attachments']]
        log.debug(
            "EncryptVolumes filtered from %d to %d "
            " unencrypted attached volumes" % (
                original_count, len(volumes)))

        # Group volumes by instance id
        instance_vol_map = {}
        for v in volumes:
            instance_id = v['Attachments'][0]['InstanceId']
            instance_vol_map.setdefault(instance_id, []).append(v)

        # Query instances to find current instance state
        self.instance_map = {
            i['InstanceId']: i for i in query_instances(
                local_session(self.manager.session_factory),
                InstanceIds=instance_vol_map.keys())}

        with self.executor_factory(max_workers=10) as w:
            futures = {}
            for instance_id, vol_set in instance_vol_map.items():
                futures[w.submit(
                    self.process_volume, instance_id, vol_set)] = instance_id

            for f in as_completed(futures):
                if f.exception():
                    instance_id = futures[f]
                    log.error(
                        "Exception processing instance:%s volset: %s \n %s" % (
                            instance_id, instance_vol_map[instance_id],
                            f.exception()))

    def process_volume(self, instance_id, vol_set):
        """Encrypt attached unencrypted ebs volumes

        vol_set corresponds to all the unencrypted volumes on a given instance.
        """
        key_id = self.get_encryption_key()
        if self.verbose:
            self.log.debug("Using encryption key: %s" % key_id)

        client = local_session(self.manager.session_factory).client('ec2')

        # Only stop and start the instance if it was running.
        instance_running = self.stop_instance(instance_id)
        if instance_running is None:
            return

        # Create all the volumes before patching the instance.
        paired = []
        for v in vol_set:
            vol_id = self.create_encrypted_volume(v, key_id, instance_id)
            paired.append((v, vol_id))

        # Next detach and reattach
        for v, vol_id in paired:
            client.detach_volume(
                InstanceId=instance_id, VolumeId=v['VolumeId'])
            # 5/8/2016 The detach isn't immediately consistent
            self.data.get('delay', 15)
            client.attach_volume(
                InstanceId=instance_id, VolumeId=vol_id,
                Device=v['Attachments'][0]['Device'])

        if instance_running:
            client.start_instances(InstanceIds=[instance_id])

        if self.verbose:
            self.log.debug(
                "Deleting unencrypted volumes for: %s" % instance_id)

        for v in vol_set:
            client.delete_volume(VolumeId=v['VolumeId'])

    def stop_instance(self, instance_id):
        client = local_session(self.manager.session_factory).client('ec2')
        instance_state = self.instance_map[instance_id]['State']['Name']
        if instance_state in ('shutting-down', 'terminated'):
            self.log.debug('Skipping terminating instance: %s' % instance_id)
            return
        elif instance_state in ('running',):
            client.stop_instances(InstanceIds=[instance_id])
            self.wait_on_resource(client, instance_id=instance_id)
            return True
        return False

    def create_encrypted_volume(self, v, key_id, instance_id):
        # Create a current snapshot
        ec2 = local_session(self.manager.session_factory).client('ec2')
        results = ec2.create_snapshot(
            VolumeId=v['VolumeId'],
            Description="maid transient snapshot for encryption",)
        transient_snapshots = [results['SnapshotId']]
        ec2.create_tags(
            Resources=[results['SnapshotId']],
            Tags=[
                {'Key': 'maid-crypto-remediation', 'Value': 'true'}])
        self.wait_on_resource(ec2, snapshot_id=results['SnapshotId'])

        # Create encrypted snapshot from current
        results = ec2.copy_snapshot(
            SourceSnapshotId=results['SnapshotId'],
            SourceRegion=v['AvailabilityZone'][:-1],
            Description='maid transient snapshot for encryption',
            Encrypted=True,
            KmsKeyId=key_id)
        transient_snapshots.append(results['SnapshotId'])
        ec2.create_tags(
            Resources=[results['SnapshotId']],
            Tags=[
                {'Key': 'maid-crypto-remediation', 'Value': 'true'}
            ])
        self.wait_on_resource(ec2, snapshot_id=results['SnapshotId'])

        # Create encrypted volume, also tag so we can recover
        results = ec2.create_volume(
            Size=v['Size'],
            VolumeType=v['VolumeType'],
            SnapshotId=results['SnapshotId'],
            AvailabilityZone=v['AvailabilityZone'],
            Encrypted=True)
        ec2.create_tags(
            Resources=[results['VolumeId']],
            Tags=[
                {'Key': 'maid-crypt-remediation', 'Value': instance_id},
                {'Key': 'maid-origin-volume', 'Value': v['VolumeId']},
                {'Key': 'maid-instance-device',
                 'Value': v['Attachments'][0]['Device']}])

        # Wait on encrypted volume creation
        self.wait_on_resource(ec2, volume_id=results['VolumeId'])

        # Delete transient snapshots
        for sid in transient_snapshots:
            ec2.delete_snapshot(SnapshotId=sid)
        return results['VolumeId']

    def get_encryption_key(self):
        kms = local_session(self.manager.session_factory).client('kms')
        key_alias = self.data.get('key')
        result = kms.describe_key(KeyId=key_alias)
        key_id = result['KeyMetadata']['KeyId']
        return key_id

    def wait_on_resource(self, *args, **kw):
        # Sigh this is dirty, but failure in the middle of our workflow
        # due to overly long resource creation is complex to unwind,
        # with multi-volume instances. Wait up to three times (actual
        # wait time is a per resource type configuration.

        # Note we wait for all resource creation before attempting to
        # patch an instance, so even on resource creation failure, the
        # instance is not modified
        try:
            return self._wait_on_resource(*args, **kw)
        except Exception:
            try:
                return self._wait_on_resource(*args, **kw)
            except Exception:
                return self._wait_on_resource(*args, **kw)

    def _wait_on_resource(
            self, client, snapshot_id=None, volume_id=None, instance_id=None):
        # boto client waiters poll every 15 seconds up to a max 600s (5m)
        if snapshot_id:
            if self.verbose:
                self.log.debug(
                    "Waiting on snapshot completion %s" % snapshot_id)
            waiter = client.get_waiter('snapshot_completed')
            waiter.wait(SnapshotIds=[snapshot_id])
            if self.verbose:
                self.log.debug("Snapshot: %s completed" % snapshot_id)
        elif volume_id:
            if self.verbose:
                self.log.debug("Waiting on volume creation %s" % volume_id)
            waiter = client.get_waiter('volume_available')
            waiter.wait(VolumeIds=[volume_id])
            if self.verbose:
                self.log.debug("Volume: %s created" % volume_id)
        elif instance_id:
            if self.verbose:
                self.log.debug("Waiting on instance stop")
            waiter = client.get_waiter('instance_stopped')
            waiter.wait(InstanceIds=[instance_id])
            if self.verbose:
                self.log.debug("Instance: %s stopped" % instance_id)


@actions.register('delete')
class Delete(BaseAction):

    schema = type_schema('delete')

    def process(self, volumes):
        with self.executor_factory(max_workers=3) as w:
            list(w.map(self.process_volume, volumes))

    def process_volume(self, volume):
        client = local_session(self.manager.session_factory).client('ec2')
        try:
            self._run_api(
                client.delete_volume,
                VolumeId=volume['VolumeId'],
                DryRun=self.manager.config.dryrun)
        except ClientError as e:
            if e.response['Error']['Code'] == "InvalidVolume.NotFound":
                return
            raise
