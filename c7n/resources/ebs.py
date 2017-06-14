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
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import itertools
import json
import time

from botocore.exceptions import ClientError
from concurrent.futures import as_completed

from c7n.actions import ActionRegistry, BaseAction
from c7n.filters import (
    CrossAccountAccessFilter, Filter, FilterRegistry, AgeFilter, ValueFilter,
    ANNOTATION_KEY, FilterValidationError, OPERATORS)
from c7n.filters.health import HealthEventFilter

from c7n.manager import resources
from c7n.resources.kms import ResourceKmsKeyAlias
from c7n.query import QueryResourceManager
from c7n.utils import (
    camelResource,
    chunks,
    get_retry,
    local_session,
    set_annotation,
    type_schema,
    worker,
)
from c7n.resources.ami import AMI

log = logging.getLogger('custodian.ebs')

filters = FilterRegistry('ebs.filters')
actions = ActionRegistry('ebs.actions')


@resources.register('ebs-snapshot')
class Snapshot(QueryResourceManager):

    class resource_type(object):
        service = 'ec2'
        type = 'snapshot'
        enum_spec = (
            'describe_snapshots', 'Snapshots', {'OwnerIds': ['self']})
        detail_spec = None
        id = 'SnapshotId'
        filter_name = 'SnapshotIds'
        filter_type = 'list'
        name = 'SnapshotId'
        date = 'StartTime'
        dimension = None

        default_report_fields = (
            'SnapshotId',
            'VolumeId',
            'tag:InstanceId',
            'VolumeSize',
            'StartTime',
            'State',
        )

    filter_registry = FilterRegistry('ebs-snapshot.filters')
    action_registry = ActionRegistry('ebs-snapshot.actions')


@Snapshot.filter_registry.register('age')
class SnapshotAge(AgeFilter):
    """EBS Snapshot Age Filter

    Filters an EBS snapshot based on the age of the snapshot (in days)

    :example:

        .. code-block: yaml

            policies:
              - name: ebs-snapshots-week-old
                resource: ebs-snapshot
                filters:
                  - type: age
                    days: 7
                    op: ge
    """

    schema = type_schema(
        'age',
        days={'type': 'number'},
        op={'type': 'string', 'enum': OPERATORS.keys()})
    date_attribute = 'StartTime'


def _filter_ami_snapshots(self, snapshots):
    if not self.data.get('value', True):
        return snapshots
    # try using cache first to get a listing of all AMI snapshots and compares resources to the list
    # This will populate the cache.
    amis = self.manager.get_resource_manager('ami').resources()
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


@Snapshot.filter_registry.register('cross-account')
class SnapshotCrossAccountAccess(CrossAccountAccessFilter):

    permissions = ('ec2:DescribeSnapshotAttribute',)

    def process(self, resources, event=None):
        self.accounts = self.get_accounts()
        results = []
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for resource_set in chunks(resources, 50):
                futures.append(w.submit(
                    self.process_resource_set, resource_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception checking cross account access \n %s" % (
                            f.exception()))
                    continue
                results.extend(f.result())
        return results

    def process_resource_set(self, resource_set):
        client = local_session(self.manager.session_factory).client('ec2')
        results = []
        for r in resource_set:
            attrs = self.manager.retry(
                client.describe_snapshot_attribute,
                SnapshotId=r['SnapshotId'],
                Attribute='createVolumePermission')['CreateVolumePermissions']
            shared_accounts = {
                g.get('Group') or g.get('UserId') for g in attrs}
            delta_accounts = shared_accounts.difference(self.accounts)
            if delta_accounts:
                r['c7n:CrossAccountViolations'] = list(delta_accounts)
                results.append(r)
        return results


@Snapshot.filter_registry.register('skip-ami-snapshots')
class SnapshotSkipAmiSnapshots(Filter):
    """
    Filter to remove snapshots of AMIs from results

    This filter is 'true' by default.

    :example:

        .. implicit with no parameters, 'true' by default
        .. code-block: yaml

            policies:
              - name: delete-stale-snapshots
                resource: ebs-snapshot
                filters:
                  - type: age
                    days: 28
                    op: ge
                  - skip-ami-snapshots

    :example:

        .. explicit with parameter
        .. code-block: yaml

            policies:
              - name: delete-snapshots
                resource: ebs-snapshot
                filters:
                  - type: age
                    days: 28
                    op: ge
                  - type: skip-ami-snapshots
                    value: false
    """

    schema = type_schema('skip-ami-snapshots', value={'type': 'boolean'})

    def get_permissions(self):
        return AMI(self.manager.ctx, {}).get_permissions()

    def validate(self):
        if not isinstance(self.data.get('value', True), bool):
            raise FilterValidationError(
                "invalid config: expected boolean value")
        return self

    def process(self, snapshots, event=None):
        resources = _filter_ami_snapshots(self, snapshots)
        return resources


@Snapshot.action_registry.register('delete')
class SnapshotDelete(BaseAction):
    """Deletes EBS snapshots

    :example:

        .. code-block: yaml

            policies:
              - name: delete-stale-snapshots
                resource: ebs-snapshots
                filters:
                  - type: age
                    days: 28
                    op: ge
                actions:
                  - delete
    """

    schema = type_schema(
        'delete', **{'skip-ami-snapshots': {'type': 'boolean'}})
    permissions = ('ec2.DeleteSnapshot',)

    def process(self, snapshots):
        self.image_snapshots = set()
        # Be careful re image snapshots, we do this by default
        # to keep things safe by default, albeit we'd get an error
        # if we did try to delete something associated to an image.
        pre = len(snapshots)
        snapshots = filter(None, _filter_ami_snapshots(self, snapshots))
        post = len(snapshots)
        log.info("Deleting %d snapshots, auto-filtered %d ami-snapshots",
                 post, pre - post)

        with self.executor_factory(max_workers=2) as w:
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

    @worker
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

    :example:

        .. code-block: yaml

            policies:
              - name: copy-snapshot-east-west
                resource: ebs-snapshot
                filters:
                  - type: age
                    days: 7
                    op: le
                actions:
                  - type: copy
                    target_region: us-west-2
                    target_key: *target_kms_key*
                    encrypted: true
    """

    schema = type_schema(
        'copy',
        target_region={'type': 'string'},
        target_key={'type': 'string'},
        encrypted={'type': 'boolean'},
    )
    permissions = (
        'ec2:CreateTags', 'ec2:CopySnapshot', 'ec2:DescribeSnapshots')

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

    @worker
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
                if r.get('Tags'):
                    client.create_tags(
                        Resources=[snapshot_id], Tags=r['Tags'])
                r['c7n:CopiedSnapshot'] = snapshot_id

            if not cross_region or len(snapshot_set) < 5:
                continue

            copy_ids = [r['c7n:CopiedSnapshot'] for r in snapshot_set]
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

    class resource_type(object):
        service = 'ec2'
        type = 'volume'
        enum_spec = ('describe_volumes', 'Volumes', None)
        name = id = 'VolumeId'
        filter_name = 'VolumeIds'
        filter_type = 'list'
        date = 'createTime'
        dimension = 'VolumeId'
        metrics_namespace = 'AWS/EBS'
        config_type = "AWS::EC2::Volume"
        default_report_fields = (
            'VolumeId',
            'Attachments[0].InstanceId',
            'Size',
            'VolumeType',
            'KmsKeyId'
        )

    filter_registry = filters
    action_registry = actions


@filters.register('instance')
class AttachedInstanceFilter(ValueFilter):
    """Filter volumes based on filtering on their attached instance

    :example:

        .. code-block: yaml

            policies:
              - name: instance-ebs-volumes
                resource: ebs
                filters:
                  - instance
    """

    schema = type_schema('instance', rinherit=ValueFilter.schema)

    def get_permissions(self):
        return self.manager.get_resource_manager('ec2').get_permissions()

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
        instances = self.manager.get_resource_manager(
            'ec2').get_resources(instance_ids)
        self.log.debug("Queried %d instances for %d volumes" % (
            len(instances), len(resources)))
        return {i['InstanceId']: i for i in instances}


@filters.register('kms-alias')
class KmsKeyAlias(ResourceKmsKeyAlias):

    def process(self, resources, event=None):
        return self.get_matching_aliases(resources)


@filters.register('fault-tolerant')
class FaultTolerantSnapshots(Filter):
    """
    This filter will return any EBS volume that does/does not have a
    snapshot within the last 7 days. 'Fault-Tolerance' in this instance
    means that, in the event of a failure, the volume can be restored
    from a snapshot with (reasonable) data loss

    - name: ebs-volume-tolerance
    - resource: ebs
    - filters: [{
        'type': 'fault-tolerant',
        'tolerant': True}]
    """
    schema = type_schema('fault-tolerant', tolerant={'type': 'boolean'})
    check_id = 'H7IgTzjTYb'
    permissions = ('support:RefreshTrustedAdvisorCheck',
                   'support:DescribeTrustedAdvisorCheckResult')

    def pull_check_results(self):
        result = set()
        client = local_session(self.manager.session_factory).client('support')
        client.refresh_trusted_advisor_check(checkId=self.check_id)
        results = client.describe_trusted_advisor_check_result(
            checkId=self.check_id, language='en')['result']
        for r in results['flaggedResources']:
            result.update([r['metadata'][1]])
        return result

    def process(self, resources, event=None):
        flagged = self.pull_check_results()
        if self.data.get('tolerant', True):
            return [r for r in resources if r['VolumeId'] not in flagged]
        return [r for r in resources if r['VolumeId'] in flagged]


@filters.register('health-event')
class HealthFilter(HealthEventFilter):

    schema = type_schema(
        'health-event',
        types={'type': 'array', 'items': {
            'type': 'string',
            'enum': ['AWS_EBS_DEGRADED_EBS_VOLUME_PERFORMANCE',
                     'AWS_EBS_VOLUME_LOST']}},
        statuses={'type': 'array', 'items': {
            'type': 'string',
            'enum': ['open', 'upcoming', 'closed']
        }})

    permissions = HealthEventFilter.permissions + (
        'config:GetResourceConfigHistory',)

    def process(self, resources, event=None):
        if 'AWS_EBS_VOLUME_LOST' not in self.data['types']:
            return super(HealthFilter, self).process(resources, event)
        if not resources:
            return resources

        client = local_session(self.manager.session_factory).client(
            'health', region_name='us-east-1')
        f = self.get_filter_parameters()
        resource_map = {}

        paginator = client.get_paginator('describe_events')
        events = list(itertools.chain(
            *[p['events']for p in paginator.paginate(filter=f)]))
        entities = self.process_event(events)

        event_map = {e['arn']: e for e in events}
        for e in entities:
            rid = e['entityValue']
            if not resource_map.get(rid):
                resource_map[rid] = self.load_resource(rid)
            resource_map[rid].setdefault(
                'c7n:HealthEvent', []).append(event_map[e['eventArn']])
        return resource_map.values()

    def load_resource(self, rid):
        config = local_session(self.manager.session_factory).client('config')
        resources_histories = config.get_resource_config_history(
            resourceType='AWS::EC2::Volume',
            resourceId=rid,
            limit=2)['configurationItems']
        for r in resources_histories:
            if r['configurationItemStatus'] != u'ResourceDeleted':
                return camelResource(json.loads(r['configuration']))
        return {"VolumeId": rid}


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

    :example:

        .. code-block: yaml

            policies:
              - name: ebs-copy-instance-tags
                resource: ebs
                filters:
                  - type: value
                    key: "Attachments[0].Device"
                    value: not-null
                actions:
                  - type: copy-instance-tags
                    tags:
                      - Name
    """

    schema = type_schema(
        'copy-instance-tags',
        tags={'type': 'array', 'items': {'type': 'string'}})

    def get_permissions(self):
        perms = self.manager.get_resource_manager('ec2').get_permissions()
        perms.append('ec2:CreateTags')
        return perms

    def process(self, volumes):
        vol_count = len(volumes)
        volumes = [v for v in volumes if v['Attachments']]
        if len(volumes) != vol_count:
            self.log.warning(
                "ebs copy tags action implicitly filtered from %d to %d",
                vol_count, len(volumes))
        self.initialize(volumes)
        with self.executor_factory(max_workers=10) as w:
            futures = []
            for instance_set in chunks(reversed(
                    self.instance_map.keys()), size=100):
                futures.append(
                    w.submit(self.process_instance_set, instance_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception copying instance tags \n %s" % (
                            f.exception()))

    def initialize(self, volumes):
        instance_vol_map = {}
        for v in volumes:
            instance_vol_map.setdefault(
                v['Attachments'][0]['InstanceId'], []).append(v)
        instance_map = {
            i['InstanceId']: i for i in
            self.manager.get_resource_manager('ec2').get_resources(
                instance_vol_map.keys())}
        self.instance_vol_map = instance_vol_map
        self.instance_map = instance_map

    def process_instance_set(self, instance_ids):
        client = local_session(self.manager.session_factory).client('ec2')
        for i in instance_ids:
            try:
                self.process_instance_volumes(
                    client,
                    self.instance_map[i],
                    self.instance_vol_map[i])
            except Exception as e:
                self.log.exception(
                    "Error copy instance:%s tags to volumes: %s \n %s",
                    i, ",".join([v['VolumeId'] for v in self.instance_vol_map[i]]),
                    e)

    def process_instance_volumes(self, client, instance, volumes):
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

    Multistep process:

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
       - Set DeleteOnTermination instance attribute equal to source volume
    - For each volume
       - Delete unencrypted volume
    - Start Instance (if originally running)
    - For each newly encrypted volume
       - Delete transient tags

    :example:

        .. code-block:: yaml

            policies:
              - name: encrypt-unencrypted-ebs
                resource: ebs
                filters:
                  - Encrypted: false
                actions:
                  - type: encrypt-instance-volumes
                    key: alias/encrypted
    """

    schema = type_schema(
        'encrypt-instance-volumes',
        required=['key'],
        key={'type': 'string'},
        delay={'type': 'number'},
        verbose={'type': 'boolean'})

    permissions = (
        'ec2:CopySnapshot',
        'ec2:CreateSnapshot',
        'ec2:CreateVolume',
        'ec2:DescribeInstances',
        'ec2:DescribeSnapshots',
        'ec2:DescribeVolumes',
        'ec2:StopInstances',
        'ec2:StartInstances',
        'ec2:ModifyInstanceAttribute',
        'ec2:DeleteTags')

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
            i['InstanceId']: i for i in
            self.manager.get_resource_manager('ec2').get_resources(
                instance_vol_map.keys(), cache=False)}

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
            time.sleep(self.data.get('delay', 15))
            client.attach_volume(
                InstanceId=instance_id, VolumeId=vol_id,
                Device=v['Attachments'][0]['Device'])

            # Set DeleteOnTermination attribute the same as source volume
            if v['Attachments'][0]['DeleteOnTermination']:
                client.modify_instance_attribute(
                    InstanceId=instance_id,
                    BlockDeviceMappings=[
                        {
                            'DeviceName': v['Attachments'][0]['Device'],
                            'Ebs': {
                                'VolumeId': vol_id,
                                'DeleteOnTermination': True
                            }
                        }
                    ]
                )

        if instance_running:
            client.start_instances(InstanceIds=[instance_id])

        if self.verbose:
            self.log.debug(
                "Deleting unencrypted volumes for: %s" % instance_id)

        for v in vol_set:
            client.delete_volume(VolumeId=v['VolumeId'])

        # Clean-up transient tags on newly created encrypted volume.
        for v, vol_id in paired:
            client.delete_tags(
                Resources=[vol_id],
                Tags=[
                    {'Key': 'maid-crypt-remediation'},
                    {'Key': 'maid-origin-volume'},
                    {'Key': 'maid-instance-device'}
                ]
            )

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


@actions.register('snapshot')
class CreateSnapshot(BaseAction):
    """Snapshot an EBS volume

    :example:

        .. code-block: yaml

            policies:
              - name: snapshot-volumes
                resource: ebs
                filters:
                  - Attachments: []
                  - State: available
                actions:
                  - snapshot
    """
    permissions = ('ec2:CreateSnapshot',)
    schema = type_schema('snapshot')

    def process(self, volumes):
        client = local_session(self.manager.session_factory).client('ec2')
        retry = get_retry(['Throttled'], max_attempts=5)
        for vol in volumes:
            vol_id = vol['VolumeId']
            retry(client.create_snapshot, VolumeId=vol_id)


@actions.register('delete')
class Delete(BaseAction):
    """Delete an ebs volume.

    If the force boolean is true, we will detach an attached volume
    from an instance. Note this cannot be done for running instance
    root volumes.

    :example:

        .. code-block: yaml

            policies:
              - name: delete-unattached-volumes
                resource: ebs
                filters:
                  - Attachments: []
                  - State: available
                actions:
                  - delete
    """
    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = (
        'ec2:DetachVolume', 'ec2:DeleteVolume', 'ec2:DescribeVolumes')

    def process(self, volumes):
        with self.executor_factory(max_workers=3) as w:
            list(w.map(self.process_volume, volumes))

    def process_volume(self, volume):
        client = local_session(self.manager.session_factory).client('ec2')
        try:
            if self.data.get('force') and len(volume['Attachments']):
                client.detach_volume(VolumeId=volume['VolumeId'], Force=True)
                waiter = client.get_waiter('volume_available')
                waiter.wait(VolumeIds=[volume['VolumeId']])
            self.manager.retry(
                client.delete_volume, VolumeId=volume['VolumeId'])
        except ClientError as e:
            if e.response['Error']['Code'] == "InvalidVolume.NotFound":
                return
            raise
