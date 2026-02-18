# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from collections import Counter
import logging
import itertools
import json
import time

from botocore.exceptions import ClientError
from concurrent.futures import as_completed
from dateutil.parser import parse as parse_date

from c7n.actions import BaseAction
from c7n.exceptions import PolicyValidationError
from c7n.filters import (
    CrossAccountAccessFilter, Filter, AgeFilter, ValueFilter,
    ANNOTATION_KEY, ListItemFilter)
from c7n.filters.health import HealthEventFilter
from c7n.filters.related import RelatedResourceFilter

from c7n.manager import resources
from c7n.resources.kms import ResourceKmsKeyAlias
from c7n.resources.securityhub import PostFinding
from c7n.query import QueryResourceManager, TypeInfo
from c7n.tags import Tag, coalesce_copy_user_tags
from c7n.utils import (
    camelResource,
    chunks,
    get_retry,
    local_session,
    select_keys,
    set_annotation,
    type_schema,
    QueryParser,
    get_support_region,
    group_by
)
from c7n.resources.ami import AMI

log = logging.getLogger('custodian.ebs')


@resources.register('ebs-snapshot')
class Snapshot(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'ec2'
        arn_type = 'snapshot'
        enum_spec = (
            'describe_snapshots', 'Snapshots', None)
        id = 'SnapshotId'
        id_prefix = 'snap-'
        filter_name = 'SnapshotIds'
        filter_type = 'list'
        name = 'SnapshotId'
        date = 'StartTime'

        default_report_fields = (
            'SnapshotId',
            'VolumeId',
            'tag:InstanceId',
            'VolumeSize',
            'StartTime',
            'State',
        )

    def resources(self, query=None):
        query = query or {}
        queries = SnapshotQueryParser.parse(self.data.get('query', []))
        for q in queries:
            query.update(q)
        if 'OwnerIds' not in query:
            query['OwnerIds'] = ['self']
        if 'MaxResults' not in query:
            query['MaxResults'] = 1000
        return super(Snapshot, self).resources(query=query)

    def get_resources(self, ids, cache=True, augment=True):
        if cache:
            resources = self._get_cached_resources(ids)
            if resources is not None:
                return resources
        while ids:
            try:
                return self.source.get_resources(ids)
            except ClientError as e:
                bad_snap = ErrorHandler.extract_bad_snapshot(e)
                if bad_snap:
                    ids.remove(bad_snap)
                    continue
                raise
        return []


class ErrorHandler:

    @staticmethod
    def remove_snapshot(rid, resource_set):
        found = None
        for r in resource_set:
            if r['SnapshotId'] == rid:
                found = r
                break
        if found:
            resource_set.remove(found)

    @staticmethod
    def extract_bad_snapshot(e):
        """Handle various client side errors when describing snapshots"""
        msg = e.response['Error']['Message']
        error = e.response['Error']['Code']
        e_snap_id = None
        if error == 'InvalidSnapshot.NotFound':
            e_snap_id = msg[msg.find("'") + 1:msg.rfind("'")]
            log.warning("Snapshot not found %s" % e_snap_id)
        elif error == 'InvalidSnapshotID.Malformed':
            e_snap_id = msg[msg.find('"') + 1:msg.rfind('"')]
            log.warning("Snapshot id malformed %s" % e_snap_id)
        return e_snap_id

    @staticmethod
    def extract_bad_volume(e):
        """Handle various client side errors when describing volumes"""
        msg = e.response['Error']['Message']
        error = e.response['Error']['Code']
        e_vol_id = None
        if error == 'InvalidVolume.NotFound':
            e_vol_id = msg[msg.find("'") + 1:msg.rfind("'")]
            log.warning("Volume not found %s" % e_vol_id)
        elif error == 'InvalidVolumeID.Malformed':
            e_vol_id = msg[msg.find('"') + 1:msg.rfind('"')]
            log.warning("Volume id malformed %s" % e_vol_id)
        return e_vol_id


class SnapshotQueryParser(QueryParser):

    QuerySchema = {
        'Filters': {
            'description': str,
            'owner-alias': ('amazon', 'amazon-marketplace', 'microsoft'),
            'owner-id': str,
            'progress': str,
            'snapshot-id': str,
            'start-time': str,
            'status': ('pending', 'completed', 'error'),
            'tag': str,
            'tag-key': str,
            'volume-id': str,
            'volume-size': str,
        },
        'OwnerIds': str,
        'RestorableByUserIds': str,
        'SnapshotIds': str,
        'MaxResults': int,
    }
    single_value_fields = ('MaxResults',)

    type_name = 'EBS Snapshot'


class VolumeQueryParser(QueryParser):

    # Valid EBS Volume Query Filters
    # https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeVolumes.html
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/describe_volumes.html
    QuerySchema = {
        'Filters': {
            'attachment.attach-time': str,
            'attachment.delete-on-termination': ('true', 'false'),
            'attachment.device': str,
            'attachment.instance-id': str,
            'attachment.status': ('attaching', 'attached', 'detaching'),
            'availability-zone': str,
            'create-time': str,
            'encrypted': ('true', 'false'),
            'multi-attach-enabled': ('true', 'false'),
            'size': int,
            'snapshot-id': str,
            'status': ('creating', 'available', 'in-use', 'deleting', 'deleted', 'error'),
            'tag': str,
            'tag-key': str,
            'volume-id': str,
            'volume-type': ('standard', 'io1', 'io2', 'gp2', 'gp3', 'sc1', 'st1'),
        },
        'MaxResults': int,
    }
    single_value_fields = ('MaxResults',)

    type_name = 'EBS Volume'


@Snapshot.action_registry.register('tag')
class SnapshotTag(Tag):

    permissions = ('ec2:CreateTags',)

    def process_resource_set(self, client, resource_set, tags):
        while resource_set:
            try:
                return super(SnapshotTag, self).process_resource_set(
                    client, resource_set, tags)
            except ClientError as e:
                bad_snap = ErrorHandler.extract_bad_snapshot(e)
                if bad_snap:
                    ErrorHandler.remove_snapshot(bad_snap, resource_set)
                    continue
                raise


@Snapshot.filter_registry.register('locked')
class SnapshotLocked(ValueFilter):

    schema = type_schema('locked', rinherit=ValueFilter.schema)

    lock_annotation = 'c7n:LockStatus'
    batch_size = 100

    def annotate_lock(self, client, resources):
        for resource_set in chunks(resources, self.batch_size):
            lock_status = {
                l['SnapshotId']: l for l in
                client.describe_locked_snapshots(resource_set)['Snapshots']}
            for r in resource_set:
                r[self.lock_annotation] = lock_status.get(r['SnapshotId'], {})

    def process(self, resources):
        self.annotate_lock(local_session(self.manager.session_factory).client('ec2'), resources)
        super().process(resources)

    def __call__(self, r):
        return super()(r[self.lock_annotation])


@Snapshot.filter_registry.register('age')
class SnapshotAge(AgeFilter):
    """EBS Snapshot Age Filter

    Filters an EBS snapshot based on the age of the snapshot (in days)

    :example:

    .. code-block:: yaml

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
        op={'$ref': '#/definitions/filters_common/comparison_operators'})
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
        client = local_session(self.manager.session_factory).client('ec2')
        with self.executor_factory(max_workers=3) as w:
            futures = []
            for resource_set in chunks(resources, 50):
                futures.append(w.submit(
                    self.process_resource_set, client, resource_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception checking cross account access \n %s" % (
                            f.exception()))
                    continue
                results.extend(f.result())
        return results

    def process_resource_set(self, client, resource_set):
        results = []
        everyone_only = self.data.get('everyone_only', False)
        for r in resource_set:
            attrs = self.manager.retry(
                client.describe_snapshot_attribute,
                SnapshotId=r['SnapshotId'],
                Attribute='createVolumePermission')['CreateVolumePermissions']
            shared_accounts = set()
            if everyone_only:
                for g in attrs:
                    if g.get('Group') == 'all':
                        shared_accounts = {g.get('Group')}
            else:
                shared_accounts = {
                g.get('Group') or g.get('UserId') for g in attrs}
            delta_accounts = shared_accounts.difference(self.accounts)
            if delta_accounts:
                r['c7n:CrossAccountViolations'] = list(delta_accounts)
                results.append(r)
        return results


@Snapshot.filter_registry.register('unused')
class SnapshotUnusedFilter(Filter):
    """Filters snapshots based on usage

    true: snapshot is not used by launch-template, launch-config, or ami.

    false: snapshot is being used by launch-template, launch-config, or ami.

    :example:

    .. code-block:: yaml

            policies:
              - name: snapshot-unused
                resource: ebs-snapshot
                filters:
                  - type: unused
                    value: true
    """

    schema = type_schema('unused', value={'type': 'boolean'})

    def get_permissions(self):
        return list(itertools.chain(*[
            self.manager.get_resource_manager(m).get_permissions()
            for m in ('asg', 'launch-config', 'ami')]))

    def _pull_asg_snapshots(self):
        asgs = self.manager.get_resource_manager('asg').resources()
        snap_ids = set()
        lcfgs = set(a['LaunchConfigurationName'] for a in asgs if 'LaunchConfigurationName' in a)
        lcfg_mgr = self.manager.get_resource_manager('launch-config')

        if lcfgs:
            for lc in lcfg_mgr.resources():
                for b in lc.get('BlockDeviceMappings'):
                    if 'Ebs' in b and 'SnapshotId' in b['Ebs']:
                        snap_ids.add(b['Ebs']['SnapshotId'])

        tmpl_mgr = self.manager.get_resource_manager('launch-template-version')
        for tversion in tmpl_mgr.get_resources(
                list(tmpl_mgr.get_asg_templates(asgs).keys())):
            for bd in tversion['LaunchTemplateData'].get('BlockDeviceMappings', ()):
                if 'Ebs' in bd and 'SnapshotId' in bd['Ebs']:
                    snap_ids.add(bd['Ebs']['SnapshotId'])
        return snap_ids

    def _pull_ami_snapshots(self):
        amis = self.manager.get_resource_manager('ami').resources()
        ami_snaps = set()
        for i in amis:
            for dev in i.get('BlockDeviceMappings'):
                if 'Ebs' in dev and 'SnapshotId' in dev['Ebs']:
                    ami_snaps.add(dev['Ebs']['SnapshotId'])
        return ami_snaps

    def process(self, resources, event=None):
        snaps = self._pull_asg_snapshots().union(self._pull_ami_snapshots())
        if self.data.get('value', True):
            return [r for r in resources if r['SnapshotId'] not in snaps]
        return [r for r in resources if r['SnapshotId'] in snaps]


@Snapshot.filter_registry.register('skip-ami-snapshots')
class SnapshotSkipAmiSnapshots(Filter):
    """
    Filter to remove snapshots of AMIs from results

    This filter is 'true' by default.

    :example:

    implicit with no parameters, 'true' by default

    .. code-block:: yaml

            policies:
              - name: delete-ebs-stale-snapshots
                resource: ebs-snapshot
                filters:
                  - type: age
                    days: 28
                    op: ge
                  - skip-ami-snapshots

    :example:

    explicit with parameter

    .. code-block:: yaml

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

    def process(self, snapshots, event=None):
        resources = _filter_ami_snapshots(self, snapshots)
        return resources


@Snapshot.filter_registry.register('volume')
class SnapshotVolumeFilter(RelatedResourceFilter):
    """
    Filter EBS snapshots by their volume attributes.

    .. code-block:: yaml

        policies:
          - name: snapshot-with-no-volume
            description: Find any snapshots that do not have a corresponding volume.
            resource: aws.ebs-snapshot
            filters:
              - type: volume
                key: VolumeId
                value: absent
          - name: find-snapshots-from-volume
            resource: aws.ebs-snapshot
            filters:
              - type: volume
                key: VolumeId
                value: vol-foobarbaz
    """

    RelatedResource = 'c7n.resources.ebs.EBS'
    RelatedIdsExpression = 'VolumeId'
    AnnotationKey = 'Volume'

    schema = type_schema(
        'volume', rinherit=ValueFilter.schema)


@Snapshot.action_registry.register('delete')
class SnapshotDelete(BaseAction):
    """Deletes EBS snapshots

    :example:

    .. code-block:: yaml

            policies:
              - name: delete-stale-snapshots
                resource: ebs-snapshot
                filters:
                  - type: age
                    days: 28
                    op: ge
                actions:
                  - delete
    """

    schema = type_schema(
        'delete', **{'skip-ami-snapshots': {'type': 'boolean'}})
    permissions = ('ec2:DeleteSnapshot',)

    def process(self, snapshots):
        self.image_snapshots = set()
        # Be careful re image snapshots, we do this by default
        # to keep things safe by default, albeit we'd get an error
        # if we did try to delete something associated to an image.
        pre = len(snapshots)
        snapshots = list(filter(None, _filter_ami_snapshots(self, snapshots)))
        post = len(snapshots)
        log.info("Deleting %d snapshots, auto-filtered %d ami-snapshots",
                 post, pre - post)

        client = local_session(self.manager.session_factory).client('ec2')
        deleted_snapshots = []
        with self.executor_factory(max_workers=2) as w:
            futures = []
            for snapshot_set in chunks(reversed(snapshots), size=50):
                futures.append(
                    w.submit(self.process_snapshot_set, client, snapshot_set, deleted_snapshots))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception deleting snapshot set \n %s" % (
                            f.exception()))
        return deleted_snapshots

    def process_snapshot_set(self, client, snapshots_set, deleted_snapshots):
        retry = get_retry((
            'RequestLimitExceeded', 'Client.RequestLimitExceeded'))

        for s in snapshots_set:
            if s['SnapshotId'] in self.image_snapshots:
                continue
            try:
                retry(client.delete_snapshot,
                      SnapshotId=s['SnapshotId'],
                      DryRun=self.manager.config.dryrun)
                deleted_snapshots.append(s)
            except ClientError as e:
                if e.response['Error']['Code'] == "InvalidSnapshot.NotFound":
                    continue
                raise


@Snapshot.action_registry.register('copy')
class CopySnapshot(BaseAction):
    """Copy a snapshot across regions

    https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ebs-copy-snapshot.html

    :example:

    .. code-block:: yaml

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
                    target_key: target_kms_key
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
                raise PolicyValidationError(
                    "Encrypted snapshot copy requires kms key on %s" % (
                        self.manager.data,))
        return self

    def process(self, resources):
        with self.executor_factory(max_workers=2) as w:
            list(w.map(self.process_resource_set, chunks(resources, 20)))

    def process_resource_set(self, resource_set):
        client = self.manager.session_factory(
            region=self.data['target_region']).client('ec2')

        cross_region = self.data['target_region'] != self.manager.config.region

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


@Snapshot.action_registry.register('set-permissions')
class SetPermissions(BaseAction):
    """Action to set permissions for creating volumes from a snapshot

    Use the 'add' and 'remove' parameters to control which accounts to
    add or remove respectively.  The default is to remove any create
    volume permissions granted to other AWS accounts.

    Combining this action with the 'cross-account' filter allows you
    greater control over which accounts will be removed, e.g. using a
    whitelist:

    :example:

    .. code-block:: yaml

            policies:
              - name: ebs-dont-share-cross-account
                resource: ebs-snapshot
                filters:
                  - type: cross-account
                    whitelist:
                    - '112233445566'
                actions:
                  - type: set-permissions
                    remove: matched
    """
    schema = type_schema(
        'set-permissions',
        remove={
            'oneOf': [
                {'enum': ['matched']},
                {'type': 'array', 'items': {
                    'type': 'string', 'minLength': 12, 'maxLength': 12}},
            ]},
        add={
            'type': 'array', 'items': {
                'type': 'string', 'minLength': 12, 'maxLength': 12}},
    )

    permissions = ('ec2:ModifySnapshotAttribute',)

    def validate(self):
        if self.data.get('remove') == 'matched':
            found = False
            for f in self.manager.iter_filters():
                if isinstance(f, SnapshotCrossAccountAccess):
                    found = True
                    break
            if not found:
                raise PolicyValidationError(
                    "policy:%s filter:%s with matched requires cross-account filter" % (
                        self.manager.ctx.policy.name, self.type))

    def process(self, snapshots):
        client = local_session(self.manager.session_factory).client('ec2')
        for i in snapshots:
            self.process_image(client, i)

    def process_image(self, client, snapshot):
        add_accounts = self.data.get('add', [])
        remove_accounts = self.data.get('remove', [])
        if not add_accounts and not remove_accounts:
            return client.reset_snapshot_attribute(
                SnapshotId=snapshot['SnapshotId'], Attribute="createVolumePermission")
        if remove_accounts == 'matched':
            remove_accounts = snapshot.get(
                'c7n:' + SnapshotCrossAccountAccess.annotation_key)

        remove = []
        remove.extend([{'UserId': a} for a in remove_accounts if a != 'all'])
        if 'all' in remove_accounts:
            remove.append({'Group': 'all'})
            remove_accounts.remove('all')

        add = [{'UserId': a} for a in add_accounts]

        if remove:
            client.modify_snapshot_attribute(
                SnapshotId=snapshot['SnapshotId'],
                CreateVolumePermission={'Remove': remove},
                OperationType='remove')
        if add:
            client.modify_snapshot_attribute(
                SnapshotId=snapshot['SnapshotId'],
                CreateVolumePermission={'Add': add},
                OperationType='add')


@resources.register('ebs')
class EBS(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'ec2'
        arn_type = 'volume'
        enum_spec = ('describe_volumes', 'Volumes', None)
        name = id = 'VolumeId'
        id_prefix = 'vol-'
        filter_name = 'VolumeIds'
        filter_type = 'list'
        date = 'createTime'
        dimension = 'VolumeId'
        metrics_namespace = 'AWS/EBS'
        cfn_type = config_type = "AWS::EC2::Volume"
        default_report_fields = (
            'VolumeId',
            'Attachments[0].InstanceId',
            'Size',
            'VolumeType',
            'KmsKeyId'
        )

    def resources(self, query=None):
        query = query or {}
        queries = VolumeQueryParser.parse(self.data.get('query', []))
        for q in queries:
            query.update(q)
        if 'MaxResults' not in query:
            query['MaxResults'] = 1000
        return super(EBS, self).resources(query=query)

    def get_resources(self, ids, cache=True, augment=True):
        if cache:
            resources = self._get_cached_resources(ids)
            if resources is not None:
                return resources
        while ids:
            try:
                return self.source.get_resources(ids)
            except ClientError as e:
                bad_vol = ErrorHandler.extract_bad_volume(e)
                if bad_vol:
                    ids.remove(bad_vol)
                    continue
                raise
        return []


@EBS.filter_registry.register('snapshots')
class EBSSnapshotsFilter(ListItemFilter):
    """
    Filter volumes by all their snapshots.

    :example:

    .. code-block:: yaml

        policies:
          - name: ebs-volumes
            resource: aws.ebs
            filters:
              - not:
                - type: snapshots
                  attrs:
                    - type: value
                      key: StartTime
                      value_type: age
                      value: 2
                      op: less-than
    """
    schema = type_schema(
        'snapshots',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'}
    )
    permissions = ('ec2:DescribeSnapshots', )
    item_annotation_key = 'c7n:Snapshots'
    annotate_items = True

    def _process_resources_set(self, client, resources):
        snapshots = client.describe_snapshots(
            Filters=[{
                'Name': 'volume-id',
                'Values': [r['VolumeId'] for r in resources]
            }]
        ).get('Snapshots') or []
        grouped = group_by(snapshots, 'VolumeId')
        for res in resources:
            res[self.item_annotation_key] = grouped.get(res['VolumeId']) or []

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ec2')
        with self.manager.executor_factory(max_workers=3) as w:
            futures = []
            # 200 max value for a single call
            for resources_set in chunks(resources, 30):
                futures.append(w.submit(self._process_resources_set, client,
                                        resources_set))
            for f in as_completed(futures):
                if f.exception():
                    self.log.error(
                        "Exception getting snapshots by volume ids \n %s" % (
                            f.exception())
                    )
                    continue
        return super().process(resources, event)

    def get_item_values(self, resource):
        if self.annotate_items:
            return resource[self.item_annotation_key]
        return resource.pop(self.item_annotation_key)


@EBS.action_registry.register('post-finding')
class EBSPostFinding(PostFinding):

    resource_type = 'AwsEc2Volume'

    def format_resource(self, r):
        envelope, payload = self.format_envelope(r)
        details = select_keys(
            r, ['KmsKeyId', 'Size', 'SnapshotId', 'Status', 'CreateTime', 'Encrypted'])
        details['CreateTime'] = details['CreateTime'].isoformat()
        self.filter_empty(details)
        for attach in r.get('Attachments', ()):
            details.setdefault('Attachments', []).append(
                self.filter_empty({
                    'AttachTime': attach['AttachTime'].isoformat(),
                    'InstanceId': attach.get('InstanceId'),
                    'DeleteOnTermination': attach['DeleteOnTermination'],
                    'Status': attach['State']}))
        payload.update(details)
        return envelope


@EBS.action_registry.register('detach')
class VolumeDetach(BaseAction):
    """
    Detach an EBS volume from an Instance.

    If 'Force' Param is True, then we'll do a forceful detach
    of the Volume. The default value for 'Force' is False.

     :example:

     .. code-block:: yaml

             policies:
               - name: detach-ebs-volumes
                 resource: ebs
                 filters:
                   - VolumeId :  volumeid
                 actions:
                   - detach


    """

    schema = type_schema('detach', force={'type': 'boolean'})
    permissions = ('ec2:DetachVolume',)

    def process(self, volumes, event=None):
        client = local_session(self.manager.session_factory).client('ec2')

        for vol in volumes:
            for attachment in vol.get('Attachments', []):
                client.detach_volume(InstanceId=attachment['InstanceId'],
                                VolumeId=attachment['VolumeId'],
                                Force=self.data.get('force', False))


@EBS.filter_registry.register('instance')
class AttachedInstanceFilter(ValueFilter):
    """Filter volumes based on filtering on their attached instance

    :example:

    .. code-block:: yaml

            policies:
              - name: instance-ebs-volumes
                resource: ebs
                filters:
                  - type: instance
                    key: tag:Name
                    value: OldManBySea
    """

    schema = type_schema('instance', rinherit=ValueFilter.schema)
    schema_alias = False

    def get_permissions(self):
        return self.manager.get_resource_manager('ec2').get_permissions()

    def process(self, resources, event=None):
        original_count = len(resources)
        resources = [r for r in resources if r.get('Attachments')]
        self.log.debug('Filtered from %d volumes to %d attached volumes' % (
            original_count, len(resources)))
        self.instance_map = self.get_instance_mapping(resources)
        return list(filter(self, resources))

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


@EBS.filter_registry.register('kms-alias')
class KmsKeyAlias(ResourceKmsKeyAlias):

    def process(self, resources, event=None):
        return self.get_matching_aliases(resources)


@EBS.filter_registry.register('fault-tolerant')
class FaultTolerantSnapshots(Filter):
    """
    This filter will return any EBS volume that does/does not have a
    snapshot within the last 7 days. 'Fault-Tolerance' in this instance
    means that, in the event of a failure, the volume can be restored
    from a snapshot with (reasonable) data loss

    .. code-block:: yaml

      policies:
       - name: ebs-volume-tolerance
         resource: ebs
         filters:
           - type: fault-tolerant
             tolerant: True
    """
    schema = type_schema('fault-tolerant', tolerant={'type': 'boolean'})
    check_id = 'H7IgTzjTYb'
    permissions = ('support:RefreshTrustedAdvisorCheck',
                   'support:DescribeTrustedAdvisorCheckResult')

    def pull_check_results(self):
        result = set()
        support_region = get_support_region(self.manager)
        client = local_session(self.manager.session_factory).client(
            'support', region_name=support_region)
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


@EBS.filter_registry.register('health-event')
class HealthFilter(HealthEventFilter):

    schema_alias = False
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
        entities = self.process_event(client, events)

        event_map = {e['arn']: e for e in events}
        config = local_session(self.manager.session_factory).client('config')
        for e in entities:
            rid = e['entityValue']
            if not resource_map.get(rid):
                resource_map[rid] = self.load_resource(config, rid)
            resource_map[rid].setdefault(
                'c7n:HealthEvent', []).append(event_map[e['eventArn']])
        return list(resource_map.values())

    def load_resource(self, config, rid):
        resources_histories = config.get_resource_config_history(
            resourceType='AWS::EC2::Volume',
            resourceId=rid,
            limit=2)['configurationItems']
        for r in resources_histories:
            if r['configurationItemStatus'] != u'ResourceDeleted':
                return camelResource(json.loads(r['configuration']))
        return {"VolumeId": rid}


@EBS.action_registry.register('copy-instance-tags')
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

    .. code-block:: yaml

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
        client = local_session(self.manager.session_factory).client('ec2')
        with self.executor_factory(max_workers=10) as w:
            futures = []
            for instance_set in chunks(sorted(
                    self.instance_map.keys(), reverse=True), size=100):
                futures.append(
                    w.submit(self.process_instance_set, client, instance_set))
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
                list(instance_vol_map.keys()))}
        self.instance_vol_map = instance_vol_map
        self.instance_map = instance_map

    def process_instance_set(self, client, instance_ids):
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
            if only_tags and t['Key'] not in only_tags:
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


@EBS.action_registry.register('encrypt-instance-volumes')
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
                list(instance_vol_map.keys()), cache=False)}

        client = local_session(self.manager.session_factory).client('ec2')

        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for instance_id, vol_set in instance_vol_map.items():
                futures[w.submit(
                    self.process_volume, client,
                    instance_id, vol_set)] = instance_id

            for f in as_completed(futures):
                if f.exception():
                    instance_id = futures[f]
                    log.error(
                        "Exception processing instance:%s volset: %s \n %s" % (
                            instance_id, instance_vol_map[instance_id],
                            f.exception()))

    def process_volume(self, client, instance_id, vol_set):
        """Encrypt attached unencrypted ebs volumes

        vol_set corresponds to all the unencrypted volumes on a given instance.
        """
        key_id = self.get_encryption_key()
        if self.verbose:
            self.log.debug("Using encryption key: %s" % key_id)

        # Only stop and start the instance if it was running.
        instance_running = self.stop_instance(client, instance_id)
        if instance_running is None:
            return

        # Create all the volumes before patching the instance.
        paired = []
        for v in vol_set:
            vol_id = self.create_encrypted_volume(client, v, key_id, instance_id)
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

    def stop_instance(self, client, instance_id):
        instance_state = self.instance_map[instance_id]['State']['Name']
        if instance_state in ('shutting-down', 'terminated'):
            self.log.debug('Skipping terminating instance: %s' % instance_id)
            return
        elif instance_state in ('running',):
            client.stop_instances(InstanceIds=[instance_id])
            self.wait_on_resource(client, instance_id=instance_id)
            return True
        return False

    def create_encrypted_volume(self, ec2, v, key_id, instance_id):
        unencrypted_volume_tags = v.get('Tags', [])
        # Create a current snapshot
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
                 'Value': v['Attachments'][0]['Device']}] + unencrypted_volume_tags)

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


@EBS.action_registry.register('snapshot')
class CreateSnapshot(BaseAction):
    """Snapshot an EBS volume.

    Tags may be optionally added to the snapshot during creation.

    - `copy-volume-tags` copies all the tags from the specified
      volume to the corresponding snapshot.
    - `copy-tags` copies the listed tags from each volume
      to the snapshot.  This is mutually exclusive with
      `copy-volume-tags`.
    - `tags` allows new tags to be added to each snapshot.  If
      no tags are specified, then the tag `custodian_snapshot`
      is added.

    The default behavior is `copy-volume-tags: true`.

    :example:

    .. code-block:: yaml

            policies:
              - name: snapshot-volumes
                resource: ebs
                filters:
                  - Attachments: []
                  - State: available
                actions:
                  - type: snapshot
                    copy-tags:
                      - Name
                    tags:
                        custodian_snapshot: True
    """
    schema = type_schema(
        'snapshot',
        **{'copy-tags': {'type': 'array', 'items': {'type': 'string'}},
           'copy-volume-tags': {'type': 'boolean'},
           'tags': {'type': 'object'},
           'description': {'type': 'string'}})
    permissions = ('ec2:CreateSnapshot', 'ec2:CreateTags',)

    def validate(self):
        if self.data.get('copy-tags') and 'copy-volume-tags' in self.data:
            raise PolicyValidationError(
                "Can specify copy-tags or copy-volume-tags, not both")

    def process(self, volumes):
        client = local_session(self.manager.session_factory).client('ec2')
        retry = get_retry(['Throttled'], max_attempts=5)
        for vol in volumes:
            vol_id = vol['VolumeId']
            tags = [{
                'ResourceType': 'snapshot',
                'Tags': self.get_snapshot_tags(vol)
            }]
            retry(self.process_volume, client=client, volume=vol_id, tags=tags)

    def process_volume(self, client, volume, tags):
        description = self.data.get('description')
        if not description:
            description = "Automated snapshot by c7n - %s" % (self.manager.ctx.policy.name)

        try:
            client.create_snapshot(
                VolumeId=volume,
                Description=description,
                TagSpecifications=tags
            )
        except ClientError as e:
            if e.response['Error']['Code'] == 'InvalidVolume.NotFound':
                return
            raise

    def get_snapshot_tags(self, resource):
        user_tags = self.data.get('tags', {}) or {'custodian_snapshot': ''}
        copy_tags = self.data.get('copy-tags', []) or self.data.get('copy-volume-tags', True)
        return coalesce_copy_user_tags(resource, copy_tags, user_tags)


@EBS.action_registry.register('delete')
class Delete(BaseAction):
    """Delete an ebs volume.

    If the force boolean is true, we will detach an attached volume
    from an instance. Note this cannot be done for running instance
    root volumes.

    :example:

    .. code-block:: yaml

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
        client = local_session(self.manager.session_factory).client('ec2')
        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for v in volumes:
                futures[
                    w.submit(self.process_volume, client, v)] = v
            for f in as_completed(futures):
                v = futures[f]
                if f.exception():
                    self.log.error(
                        "Error processing volume:%s error:%s",
                        v['VolumeId'], f.exception())

    def process_volume(self, client, volume):
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


@EBS.filter_registry.register('modifyable')
class ModifyableVolume(Filter):
    """Check if an ebs volume is modifyable online.

    Considerations:
     https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/limitations.html

    Consideration Summary
      - only current instance types are supported (one exception m3.medium)
        Current Generation Instances (2017-2)
        https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-types.html#current-gen-instances

      - older magnetic volume types are not supported
      - shrinking volumes is not supported
      - must wait at least 6hrs between modifications to the same volume.
      - volumes must have been attached after nov 1st, 2016.

    See :ref:`modify action <aws.ebs.actions.modify>` for examples.
    """

    schema = type_schema('modifyable')

    older_generation = {
        'm1.small', 'm1.medium', 'm1.large', 'm1.xlarge',
        'c1.medium', 'c1.xlarge', 'cc2.8xlarge',
        'm2.xlarge', 'm2.2xlarge', 'm2.4xlarge', 'cr1.8xlarge',
        'hi1.4xlarge', 'hs1.8xlarge', 'cg1.4xlarge', 't1.micro',
        # two legs good, not all current gen work either.
        'm3.large', 'm3.xlarge', 'm3.2xlarge'
    }

    permissions = ("ec2:DescribeInstances",)

    def process(self, resources, event=None):
        results = []
        filtered = []
        attached = []
        stats = Counter()
        marker_date = parse_date('2016-11-01T00:00:00+00:00')

        # Filter volumes
        for r in resources:
            # unsupported type
            if r['VolumeType'] == 'standard':
                stats['vol-type'] += 1
                filtered.append(r['VolumeId'])
                continue

            # unattached are easy
            if not r.get('Attachments'):
                results.append(r)
                continue

            # check for attachment date older then supported date
            if r['Attachments'][0]['AttachTime'] < marker_date:
                stats['attach-time'] += 1
                filtered.append(r['VolumeId'])
                continue

            attached.append(r)

        # Filter volumes attached to unsupported instance types
        ec2 = self.manager.get_resource_manager('ec2')
        instance_map = {}
        for v in attached:
            instance_map.setdefault(
                v['Attachments'][0]['InstanceId'], []).append(v)

        instances = ec2.get_resources(list(instance_map.keys()))
        for i in instances:
            if i['InstanceType'] in self.older_generation:
                stats['instance-type'] += len(instance_map[i['InstanceId']])
                filtered.extend([v['VolumeId'] for v in instance_map.pop(i['InstanceId'])])
            else:
                results.extend(instance_map.pop(i['InstanceId']))

        # Filter volumes that are currently under modification
        client = local_session(self.manager.session_factory).client('ec2')
        modifying = set()

        # Re 197 - Max number of filters is 200, and we have to use
        # three additional attribute filters.
        for vol_set in chunks(list(results), 197):
            vol_ids = [v['VolumeId'] for v in vol_set]
            mutating = client.describe_volumes_modifications(
                Filters=[
                    {'Name': 'volume-id',
                     'Values': vol_ids},
                    {'Name': 'modification-state',
                     'Values': ['modifying', 'optimizing', 'failed']}])
            for vm in mutating.get('VolumesModifications', ()):
                stats['vol-mutation'] += 1
                filtered.append(vm['VolumeId'])
                modifying.add(vm['VolumeId'])

        self.log.debug(
            "filtered %d of %d volumes due to %s",
            len(filtered), len(resources), sorted(stats.items()))

        return [r for r in results if r['VolumeId'] not in modifying]


@EBS.action_registry.register('modify')
class ModifyVolume(BaseAction):
    """Modify an ebs volume online.

    **Note this action requires use of modifyable filter**

    Intro Blog & Use Cases:
     https://aws.amazon.com/blogs/aws/amazon-ebs-update-new-elastic-volumes-change-everything/
    Docs:
     https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ebs-modify-volume.html
    Considerations:
     https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/limitations.html

    :example:

      Find under utilized provisioned iops volumes older than a week
      and change their type.

    .. code-block:: yaml

           policies:
            - name: ebs-remove-piops
              resource: ebs
              filters:
               - type: value
                 key: CreateTime
                 value_type: age
                 value: 7
                 op: greater-than
               - VolumeType: io1
               - type: metrics
                 name: VolumeConsumedReadWriteOps
                 statistics: Maximum
                 value: 100
                 op: less-than
                 days: 7
               - modifyable
              actions:
               - type: modify
                 volume-type: gp2

    `iops-percent` and `size-percent` can be used to modify
    respectively iops on io1/io2 volumes and volume size.

    When converting to io1/io2, `iops-percent` is used to set the iops
    allocation for the new volume against the extant value for the old
    volume.

    :example:

      Double storage and quadruple iops for all io1 volumes.

    .. code-block:: yaml

           policies:
            - name: ebs-upsize-piops
              resource: ebs
              filters:
                - VolumeType: io1
                - modifyable
              actions:
                - type: modify
                  size-percent: 200
                  iops-percent: 400


    **Note** resizing down aka shrinking requires OS and FS support
    and potentially additional preparation, else data-loss may occur.
    To prevent accidents, shrinking must be explicitly enabled by also
    setting `shrink: true` on the action.
    """

    schema = type_schema(
        'modify',
        **{'volume-type': {'enum': ['io1', 'io2', 'gp2', 'gp3', 'st1', 'sc1']},
           'shrink': False,
           'size-percent': {'type': 'number'},
           'iops-percent': {'type': 'number'}})

    # assumptions as its the closest i can find.
    permissions = ("ec2:ModifyVolumeAttribute",)

    def validate(self):
        if 'modifyable' not in self.manager.data.get('filters', ()):
            raise PolicyValidationError(
                "modify action requires modifyable filter in policy")
        if self.data.get('size-percent', 100) < 100 and not self.data.get('shrink', False):
            raise PolicyValidationError((
                "shrinking volumes requires os/fs support "
                "or data-loss may ensue, use `shrink: true` to override"))
        return self

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        for resource_set in chunks(resources, 50):
            self.process_resource_set(client, resource_set)

    def process_resource_set(self, client, resource_set):
        vtype = self.data.get('volume-type')
        psize = self.data.get('size-percent')
        piops = self.data.get('iops-percent')

        for r in resource_set:
            params = {'VolumeId': r['VolumeId']}
            if piops and ('io1' in (vtype, r['VolumeType']) or
                          'io2' in (vtype, r['VolumeType'])):
                # default here if we're changing to io1
                params['Iops'] = max(int(r.get('Iops', 10) * piops / 100.0), 100)
            if psize:
                params['Size'] = max(int(r['Size'] * psize / 100.0), 1)
            if vtype:
                params['VolumeType'] = vtype
            self.manager.retry(client.modify_volume, **params)
