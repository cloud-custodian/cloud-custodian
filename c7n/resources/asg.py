# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from botocore.client import ClientError

from collections import Counter
from concurrent.futures import as_completed

from dateutil.parser import parse

import itertools
import time

from c7n.actions import Action
from c7n.exceptions import PolicyValidationError
from c7n.filters import ValueFilter, AgeFilter, Filter
from c7n.filters.offhours import OffHour, OnHour
import c7n.filters.vpc as net_filters

from c7n.manager import resources
from c7n import query
from c7n.resources.securityhub import PostFinding
from c7n.tags import TagActionFilter, DEFAULT_TAG, TagCountFilter, TagTrim, TagDelayedAction
from c7n.utils import (
    local_session, type_schema, chunks, get_retry, select_keys)

from .ec2 import deserialize_user_data


@resources.register('asg')
class ASG(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'autoscaling'
        arn = 'AutoScalingGroupARN'
        arn_type = 'autoScalingGroup'
        arn_separator = ":"
        id = name = 'AutoScalingGroupName'
        date = 'CreatedTime'
        dimension = 'AutoScalingGroupName'
        enum_spec = ('describe_auto_scaling_groups', 'AutoScalingGroups', None)
        filter_name = 'AutoScalingGroupNames'
        filter_type = 'list'
        config_type = 'AWS::AutoScaling::AutoScalingGroup'
        cfn_type = 'AWS::AutoScaling::AutoScalingGroup'

        default_report_fields = (
            'AutoScalingGroupName',
            'CreatedTime',
            'LaunchConfigurationName',
            'count:Instances',
            'DesiredCapacity',
            'HealthCheckType',
            'list:LoadBalancerNames',
        )

    retry = staticmethod(get_retry(('ResourceInUse', 'Throttling',)))


ASG.filter_registry.register('offhour', OffHour)
ASG.filter_registry.register('onhour', OnHour)
ASG.filter_registry.register('tag-count', TagCountFilter)
ASG.filter_registry.register('marked-for-op', TagActionFilter)
ASG.filter_registry.register('network-location', net_filters.NetworkLocation)


class LaunchInfo:

    permissions = ("ec2:DescribeLaunchTemplateVersions",
                   "autoscaling:DescribeLaunchConfigurations",)

    def __init__(self, manager):
        self.manager = manager

    def initialize(self, asgs):
        self.templates = self.get_launch_templates(asgs)
        self.configs = self.get_launch_configs(asgs)
        return self

    def get_launch_templates(self, asgs):
        tmpl_mgr = self.manager.get_resource_manager('launch-template-version')
        # template ids include version identifiers
        template_ids = list(tmpl_mgr.get_asg_templates(asgs))
        if not template_ids:
            return {}
        return {
            (t['LaunchTemplateId'],
             str(t.get('c7n:VersionAlias', t['VersionNumber']))): t['LaunchTemplateData']
            for t in tmpl_mgr.get_resources(template_ids)}

    def get_launch_configs(self, asgs):
        """Return a mapping of launch configs for the given set of asgs"""
        config_names = set()
        for a in asgs:
            if 'LaunchConfigurationName' not in a:
                continue
            config_names.add(a['LaunchConfigurationName'])
        if not config_names:
            return {}
        lc_resources = self.manager.get_resource_manager('launch-config')
        if len(config_names) < 5:
            configs = lc_resources.get_resources(list(config_names))
        else:
            configs = lc_resources.resources()
        return {
            cfg['LaunchConfigurationName']: cfg for cfg in configs
            if cfg['LaunchConfigurationName'] in config_names}

    def get_launch_id(self, asg):
        lid = asg.get('LaunchConfigurationName')
        if lid is not None:
            # We've noticed trailing white space allowed in some asgs
            return lid.strip()

        lid = asg.get('LaunchTemplate')
        if lid is not None:
            return (lid['LaunchTemplateId'], lid.get('Version', '$Default'))

        if 'MixedInstancesPolicy' in asg:
            mip_spec = asg['MixedInstancesPolicy'][
                'LaunchTemplate']['LaunchTemplateSpecification']
            return (mip_spec['LaunchTemplateId'], mip_spec.get('Version', '$Default'))

        # we've noticed some corner cases where the asg name is the lc name, but not
        # explicitly specified as launchconfiguration attribute.
        lid = asg['AutoScalingGroupName']
        return lid

    def get(self, asg):
        lid = self.get_launch_id(asg)
        if isinstance(lid, tuple):
            return self.templates.get(lid)
        else:
            return self.configs.get(lid)

    def items(self):
        return itertools.chain(*(
            self.configs.items(), self.templates.items()))

    def get_image_ids(self):
        image_ids = {}
        for cid, c in self.items():
            if c.get('ImageId'):
                image_ids.setdefault(c['ImageId'], []).append(cid)
        return image_ids

    def get_image_map(self):
        # The describe_images api historically would return errors
        # on an unknown ami in the set of images ids passed in.
        # It now just silently drops those items, which is actually
        # ideally for our use case.
        #
        # We used to do some balancing of picking up our asgs using
        # the resource manager abstraction to take advantage of
        # resource caching, but then we needed to do separate api
        # calls to intersect with third party amis. Given the new
        # describe behavior, we'll just do the api call to fetch the
        # amis, it doesn't seem to have any upper bound on number of
        # ImageIds to pass (Tested with 1k+ ImageIds)
        #
        # Explicitly use a describe source. Can't use a config source
        # since it won't have state for third party ami, we auto
        # propagate source normally. Can't use a cache either as their
        # not in the account.
        return {i['ImageId']: i for i in
                self.manager.get_resource_manager(
                    'ami').get_source('describe').get_resources(
                        list(self.get_image_ids()), cache=False)}

    def get_security_group_ids(self):
        # return set of security group ids for given asg
        sg_ids = set()
        for k, v in self.items():
            sg_ids.update(v.get('SecurityGroupIds', ()))
            sg_ids.update(v.get('SecurityGroups', ()))
        return sg_ids


@ASG.filter_registry.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = ""

    permissions = ('ec2:DescribeSecurityGroups',) + LaunchInfo.permissions

    def get_related_ids(self, asgs):
        return self.launch_info.get_security_group_ids()

    def process(self, asgs, event=None):
        self.launch_info = LaunchInfo(self.manager).initialize(asgs)
        return super(SecurityGroupFilter, self).process(asgs, event)


@ASG.filter_registry.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = ""

    def get_related_ids(self, asgs):
        subnet_ids = set()
        for asg in asgs:
            subnet_ids.update(
                [sid.strip() for sid in asg.get('VPCZoneIdentifier', '').split(',')])
        return subnet_ids


@ASG.filter_registry.register('launch-config')
class LaunchConfigFilter(ValueFilter):
    """Filter asg by launch config attributes.

    This will also filter to launch template data in addition
    to launch configurations.

    :example:

    .. code-block:: yaml

        policies:
          - name: launch-configs-with-public-address
            resource: asg
            filters:
              - type: launch-config
                key: AssociatePublicIpAddress
                value: true
    """
    schema = type_schema(
        'launch-config', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ("autoscaling:DescribeLaunchConfigurations",)

    def process(self, asgs, event=None):
        self.launch_info = LaunchInfo(self.manager).initialize(asgs)
        return super(LaunchConfigFilter, self).process(asgs, event)

    def __call__(self, asg):
        return self.match(self.launch_info.get(asg))


class ConfigValidFilter(Filter):

    def get_permissions(self):
        return list(itertools.chain(*[
            self.manager.get_resource_manager(m).get_permissions()
            for m in ('subnet', 'security-group', 'key-pair', 'elb',
                      'app-elb-target-group', 'ebs-snapshot', 'ami')]))

    def validate(self):
        if self.manager.data.get('mode'):
            raise PolicyValidationError(
                "invalid-config makes too many queries to be run in lambda")
        return self

    def initialize(self, asgs):
        self.launch_info = LaunchInfo(self.manager).initialize(asgs)
        # pylint: disable=attribute-defined-outside-init
        self.subnets = self.get_subnets()
        self.security_groups = self.get_security_groups()
        self.key_pairs = self.get_key_pairs()
        self.elbs = self.get_elbs()
        self.appelb_target_groups = self.get_appelb_target_groups()
        self.snapshots = self.get_snapshots()
        self.images, self.image_snaps = self.get_images()

    def get_subnets(self):
        manager = self.manager.get_resource_manager('subnet')
        return {s['SubnetId'] for s in manager.resources()}

    def get_security_groups(self):
        manager = self.manager.get_resource_manager('security-group')
        return {s['GroupId'] for s in manager.resources()}

    def get_key_pairs(self):
        manager = self.manager.get_resource_manager('key-pair')
        return {k['KeyName'] for k in manager.resources()}

    def get_elbs(self):
        manager = self.manager.get_resource_manager('elb')
        return {e['LoadBalancerName'] for e in manager.resources()}

    def get_appelb_target_groups(self):
        manager = self.manager.get_resource_manager('app-elb-target-group')
        return {a['TargetGroupArn'] for a in manager.resources()}

    def get_images(self):
        images = self.launch_info.get_image_map()
        image_snaps = set()

        for a in images.values():
            # Capture any snapshots, images strongly reference their
            # snapshots, and some of these will be third party in the
            # case of a third party image.
            for bd in a.get('BlockDeviceMappings', ()):
                if 'Ebs' not in bd or 'SnapshotId' not in bd['Ebs']:
                    continue
                image_snaps.add(bd['Ebs']['SnapshotId'].strip())
        return set(images), image_snaps

    def get_snapshots(self):
        snaps = set()
        for cid, cfg in self.launch_info.items():
            for bd in cfg.get('BlockDeviceMappings', ()):
                if 'Ebs' not in bd or 'SnapshotId' not in bd['Ebs']:
                    continue
                snaps.add(bd['Ebs']['SnapshotId'].strip())
        manager = self.manager.get_resource_manager('ebs-snapshot')
        return {s['SnapshotId'] for s in manager.get_resources(
                list(snaps), cache=False)}

    def process(self, asgs, event=None):
        self.initialize(asgs)
        return super(ConfigValidFilter, self).process(asgs, event)

    def get_asg_errors(self, asg):
        errors = []
        subnets = asg.get('VPCZoneIdentifier', '').split(',')

        for subnet in subnets:
            subnet = subnet.strip()
            if subnet not in self.subnets:
                errors.append(('invalid-subnet', subnet))

        for elb in asg['LoadBalancerNames']:
            elb = elb.strip()
            if elb not in self.elbs:
                errors.append(('invalid-elb', elb))

        for appelb_target in asg.get('TargetGroupARNs', []):
            appelb_target = appelb_target.strip()
            if appelb_target not in self.appelb_target_groups:
                errors.append(('invalid-appelb-target-group', appelb_target))

        cfg_id = self.launch_info.get_launch_id(asg)
        cfg = self.launch_info.get(asg)

        if cfg is None:
            errors.append(('invalid-config', cfg_id))
            self.log.debug(
                "asg:%s no launch config or template found" % asg['AutoScalingGroupName'])
            asg['Invalid'] = errors
            return True

        for sg in itertools.chain(*(
                cfg.get('SecurityGroups', ()), cfg.get('SecurityGroupIds', ()))):
            sg = sg.strip()
            if sg not in self.security_groups:
                errors.append(('invalid-security-group', sg))

        if cfg.get('KeyName') and cfg['KeyName'].strip() not in self.key_pairs:
            errors.append(('invalid-key-pair', cfg['KeyName']))

        if cfg.get('ImageId') and cfg['ImageId'].strip() not in self.images:
            errors.append(('invalid-image', cfg['ImageId']))

        for bd in cfg.get('BlockDeviceMappings', ()):
            if 'Ebs' not in bd or 'SnapshotId' not in bd['Ebs']:
                continue
            snapshot_id = bd['Ebs']['SnapshotId'].strip()
            if snapshot_id in self.image_snaps:
                continue
            if snapshot_id not in self.snapshots:
                errors.append(('invalid-snapshot', bd['Ebs']['SnapshotId']))
        return errors


@ASG.filter_registry.register('valid')
class ValidConfigFilter(ConfigValidFilter):
    """Filters autoscale groups to find those that are structurally valid.

    This operates as the inverse of the invalid filter for multi-step
    workflows.

    See details on the invalid filter for a list of checks made.

    :example:

      .. code-block:: yaml

          policies:
            - name: asg-valid-config
              resource: asg
              filters:
               - valid
    """

    schema = type_schema('valid')

    def __call__(self, asg):
        errors = self.get_asg_errors(asg)
        return not bool(errors)


@ASG.filter_registry.register('invalid')
class InvalidConfigFilter(ConfigValidFilter):
    """Filter autoscale groups to find those that are structurally invalid.

    Structurally invalid means that the auto scale group will not be able
    to launch an instance succesfully as the configuration has

    - invalid subnets
    - invalid security groups
    - invalid key pair name
    - invalid launch config volume snapshots
    - invalid amis
    - invalid health check elb (slower)

    Internally this tries to reuse other resource managers for better
    cache utilization.

    :example:

        .. code-block:: yaml

            policies:
              - name: asg-invalid-config
                resource: asg
                filters:
                  - invalid
    """
    schema = type_schema('invalid')

    def __call__(self, asg):
        errors = self.get_asg_errors(asg)
        if errors:
            asg['Invalid'] = errors
            return True


@ASG.filter_registry.register('not-encrypted')
class NotEncryptedFilter(Filter):
    """Check if an ASG is configured to have unencrypted volumes.

    Checks both the ami snapshots and the launch configuration.

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-unencrypted
                resource: asg
                filters:
                  - type: not-encrypted
                    exclude_image: true
    """

    schema = type_schema('not-encrypted', exclude_image={'type': 'boolean'})
    permissions = (
        'ec2:DescribeImages',
        'ec2:DescribeSnapshots',
        'autoscaling:DescribeLaunchConfigurations')

    images = unencrypted_configs = unencrypted_images = None

    # TODO: resource-manager, notfound err mgr

    def process(self, asgs, event=None):
        self.launch_info = LaunchInfo(self.manager).initialize(asgs)
        self.images = self.launch_info.get_image_map()

        if not self.data.get('exclude_image'):
            self.unencrypted_images = self.get_unencrypted_images()

        self.unencrypted_launch = self.get_unencrypted_configs()
        return super(NotEncryptedFilter, self).process(asgs, event)

    def __call__(self, asg):
        launch = self.launch_info.get(asg)
        if not launch:
            self.log.warning(
                "ASG %s instances: %d has missing config or template",
                asg['AutoScalingGroupName'], len(asg['Instances']))
            return False

        launch_id = self.launch_info.get_launch_id(asg)
        unencrypted = []
        if not self.data.get('exclude_image'):
            if launch['ImageId'] in self.unencrypted_images:
                unencrypted.append('Image')

        if launch_id in self.unencrypted_launch:
            unencrypted.append('LaunchConfig')
        if unencrypted:
            asg['Unencrypted'] = unencrypted
        return bool(unencrypted)

    def get_unencrypted_images(self):
        """retrieve images which have unencrypted snapshots referenced."""
        unencrypted_images = set()
        for i in self.images.values():
            for bd in i['BlockDeviceMappings']:
                if 'Ebs' in bd and not bd['Ebs'].get('Encrypted'):
                    unencrypted_images.add(i['ImageId'])
                    break
        return unencrypted_images

    def get_unencrypted_configs(self):
        """retrieve configs that have unencrypted ebs voluems referenced."""
        unencrypted_configs = set()
        snaps = {}

        for cid, c in self.launch_info.items():
            image = self.images.get(c.get('ImageId', ''))
            # image deregistered/unavailable or exclude_image set
            if image is not None:
                image_block_devs = {
                    bd['DeviceName'] for bd in
                    image['BlockDeviceMappings'] if 'Ebs' in bd}
            else:
                image_block_devs = set()
            for bd in c.get('BlockDeviceMappings', ()):
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

        for s in self.get_snapshots(list(snaps.keys())):
            if not s.get('Encrypted'):
                unencrypted_configs.update(snaps[s['SnapshotId']])
        return unencrypted_configs

    def get_snapshots(self, snap_ids):
        """get snapshots corresponding to id, but tolerant of invalid id's."""
        return self.manager.get_resource_manager('ebs-snapshot').get_resources(
            snap_ids, cache=False)


@ASG.filter_registry.register('image-age')
class ImageAgeFilter(AgeFilter):
    """Filter asg by image age (in days).

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-older-image
                resource: asg
                filters:
                  - type: image-age
                    days: 90
                    op: ge
    """
    permissions = (
        "ec2:DescribeImages",
        "autoscaling:DescribeLaunchConfigurations")

    date_attribute = "CreationDate"
    schema = type_schema(
        'image-age',
        op={'$ref': '#/definitions/filters_common/comparison_operators'},
        days={'type': 'number'})

    def process(self, asgs, event=None):
        self.launch_info = LaunchInfo(self.manager).initialize(asgs)
        self.images = self.launch_info.get_image_map()
        return super(ImageAgeFilter, self).process(asgs, event)

    def get_resource_date(self, asg):
        cfg = self.launch_info.get(asg)
        if cfg is None:
            cfg = {}
        ami = self.images.get(cfg.get('ImageId'), {})
        return parse(ami.get(
            self.date_attribute, "2000-01-01T01:01:01.000Z"))


@ASG.filter_registry.register('image')
class ImageFilter(ValueFilter):
    """Filter asg by image

    :example:

    .. code-block:: yaml

        policies:
          - name: non-windows-asg
            resource: asg
            filters:
              - type: image
                key: Platform
                value: Windows
                op: ne
    """
    permissions = (
        "ec2:DescribeImages",
        "autoscaling:DescribeLaunchConfigurations")

    schema = type_schema('image', rinherit=ValueFilter.schema)
    schema_alias = True

    def process(self, asgs, event=None):
        self.launch_info = LaunchInfo(self.manager).initialize(asgs)
        self.images = self.launch_info.get_image_map()
        return super(ImageFilter, self).process(asgs, event)

    def __call__(self, i):
        image = self.images.get(self.launch_info.get(i).get('ImageId', None))
        # Finally, if we have no image...
        if not image:
            self.log.warning(
                "Could not locate image for instance:%s ami:%s" % (
                    i['InstanceId'], i["ImageId"]))
            # Match instead on empty skeleton?
            return False
        return self.match(image)


@ASG.filter_registry.register('vpc-id')
class VpcIdFilter(ValueFilter):
    """Filters ASG based on the VpcId

    This filter is available as a ValueFilter as the vpc-id is not natively
    associated to the results from describing the autoscaling groups.

    :example:

    .. code-block:: yaml

        policies:
          - name: asg-vpc-xyz
            resource: asg
            filters:
              - type: vpc-id
                value: vpc-12ab34cd
    """

    schema = type_schema(
        'vpc-id', rinherit=ValueFilter.schema)
    schema['properties'].pop('key')
    schema_alias = False
    permissions = ('ec2:DescribeSubnets',)

    # TODO: annotation

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

        subnet_manager = self.manager.get_resource_manager('subnet')
        # Invalid subnets on asgs happen, so query all
        all_subnets = {s['SubnetId']: s for s in subnet_manager.resources()}

        for s, s_asgs in subnets.items():
            if s not in all_subnets:
                self.log.warning(
                    "invalid subnet %s for asgs: %s",
                    s, [a['AutoScalingGroupName'] for a in s_asgs])
                continue
            for a in s_asgs:
                a['VpcId'] = all_subnets[s]['VpcId']
        return super(VpcIdFilter, self).process(asgs)


@ASG.filter_registry.register('progagated-tags')  # compatibility
@ASG.filter_registry.register('propagated-tags')
class PropagatedTagFilter(Filter):
    """Filter ASG based on propagated tags

    This filter is designed to find all autoscaling groups that have a list
    of tag keys (provided) that are set to propagate to new instances. Using
    this will allow for easy validation of asg tag sets are in place across an
    account for compliance.

    :example:

       .. code-block:: yaml

            policies:
              - name: asg-non-propagated-tags
                resource: asg
                filters:
                  - type: propagated-tags
                    keys: ["ABC", "BCD"]
                    match: false
                    propagate: true
    """
    schema = type_schema(
        'progagated-tags',
        aliases=('propagated-tags',),
        keys={'type': 'array', 'items': {'type': 'string'}},
        match={'type': 'boolean'},
        propagate={'type': 'boolean'})
    permissions = (
        "autoscaling:DescribeLaunchConfigurations",
        "autoscaling:DescribeAutoScalingGroups")

    def process(self, asgs, event=None):
        keys = self.data.get('keys', [])
        match = self.data.get('match', True)
        results = []
        for asg in asgs:
            if self.data.get('propagate', True):
                tags = [t['Key'] for t in asg.get('Tags', []) if t[
                    'Key'] in keys and t['PropagateAtLaunch']]
                if match and all(k in tags for k in keys):
                    results.append(asg)
                if not match and not all(k in tags for k in keys):
                    results.append(asg)
            else:
                tags = [t['Key'] for t in asg.get('Tags', []) if t[
                    'Key'] in keys and not t['PropagateAtLaunch']]
                if match and all(k in tags for k in keys):
                    results.append(asg)
                if not match and not all(k in tags for k in keys):
                    results.append(asg)
        return results


@ASG.action_registry.register('post-finding')
class AsgPostFinding(PostFinding):

    resource_type = 'AwsAutoScalingAutoScalingGroup'
    launch_info = LaunchInfo(None)

    def format_resource(self, r):
        envelope, payload = self.format_envelope(r)
        details = select_keys(r, [
            'CreatedTime', 'HealthCheckType', 'HealthCheckGracePeriod', 'LoadBalancerNames'])
        lid = self.launch_info.get_launch_id(r)
        if isinstance(lid, tuple):
            lid = "%s:%s" % lid
        details['CreatedTime'] = details['CreatedTime'].isoformat()
        # let's arbitrarily cut off key information per security hub's restrictions...
        details['LaunchConfigurationName'] = lid[:32]
        payload.update(details)
        return envelope


@ASG.action_registry.register('tag-trim')
class GroupTagTrim(TagTrim):
    """Action to trim the number of tags to avoid hitting tag limits

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-tag-trim
                resource: asg
                filters:
                  - type: tag-count
                    count: 10
                actions:
                  - type: tag-trim
                    space: 1
                    preserve:
                      - OwnerName
                      - OwnerContact
    """

    max_tag_count = 10
    permissions = ('autoscaling:DeleteTags',)

    def process_tag_removal(self, client, resource, candidates):
        tags = []
        for t in candidates:
            tags.append(
                dict(Key=t, ResourceType='auto-scaling-group',
                     ResourceId=resource['AutoScalingGroupName']))
        client.delete_tags(Tags=tags)


@ASG.filter_registry.register('capacity-delta')
class CapacityDelta(Filter):
    """Filter returns ASG that have less instances than desired or required

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-capacity-delta
                resource: asg
                filters:
                  - capacity-delta
    """

    schema = type_schema('capacity-delta')

    def process(self, asgs, event=None):
        return [
            a for a in asgs if len(
                a['Instances']) < a['DesiredCapacity'] or len(
                    a['Instances']) < a['MinSize']]


@ASG.filter_registry.register('user-data')
class UserDataFilter(ValueFilter):
    """Filter on ASG's whose launch configs have matching userdata.
    Note: It is highly recommended to use regexes with the ?sm flags, since Custodian
    uses re.match() and userdata spans multiple lines.

    :example:

    .. code-block:: yaml

            policies:
              - name: lc_userdata
                resource: asg
                filters:
                  - type: user-data
                    op: regex
                    value: (?smi).*password=
                actions:
                  - delete
    """

    schema = type_schema('user-data', rinherit=ValueFilter.schema)
    schema_alias = False
    batch_size = 50
    annotation = 'c7n:user-data'

    def __init__(self, data, manager):
        super(UserDataFilter, self).__init__(data, manager)
        self.data['key'] = '"c7n:user-data"'

    def get_permissions(self):
        return self.manager.get_resource_manager('asg').get_permissions()

    def process(self, asgs, event=None):
        '''Get list of autoscaling groups whose launch configs match the
        user-data filter.

        :return: List of ASG's with matching launch configs
        '''
        self.data['key'] = '"c7n:user-data"'
        launch_info = LaunchInfo(self.manager).initialize(asgs)

        results = []
        for asg in asgs:
            launch_config = launch_info.get(asg)
            if self.annotation not in launch_config:
                if not launch_config.get('UserData'):
                    asg[self.annotation] = None
                else:
                    asg[self.annotation] = deserialize_user_data(
                        launch_config['UserData'])
            if self.match(asg):
                results.append(asg)
        return results


@ASG.action_registry.register('resize')
class Resize(Action):
    """Action to resize the min/max/desired instances in an ASG

    There are several ways to use this action:

    1. set min/desired to current running instances

    .. code-block:: yaml

            policies:
              - name: asg-resize
                resource: asg
                filters:
                  - capacity-delta
                actions:
                  - type: resize
                    desired-size: "current"

    2. apply a fixed resize of min, max or desired, optionally saving the
       previous values to a named tag (for restoring later):

    .. code-block:: yaml

            policies:
              - name: offhours-asg-off
                resource: asg
                filters:
                  - type: offhour
                    offhour: 19
                    default_tz: bst
                actions:
                  - type: resize
                    min-size: 0
                    desired-size: 0
                    save-options-tag: OffHoursPrevious

    3. restore previous values for min/max/desired from a tag:

    .. code-block:: yaml

            policies:
              - name: offhours-asg-on
                resource: asg
                filters:
                  - type: onhour
                    onhour: 8
                    default_tz: bst
                actions:
                  - type: resize
                    restore-options-tag: OffHoursPrevious

    """

    schema = type_schema(
        'resize',
        **{
            'min-size': {'type': 'integer', 'minimum': 0},
            'max-size': {'type': 'integer', 'minimum': 0},
            'desired-size': {
                "anyOf": [
                    {'enum': ["current"]},
                    {'type': 'integer', 'minimum': 0}
                ]
            },
            # support previous key name with underscore
            'desired_size': {
                "anyOf": [
                    {'enum': ["current"]},
                    {'type': 'integer', 'minimum': 0}
                ]
            },
            'save-options-tag': {'type': 'string'},
            'restore-options-tag': {'type': 'string'},
        }
    )
    permissions = (
        'autoscaling:UpdateAutoScalingGroup',
        'autoscaling:CreateOrUpdateTags'
    )

    def process(self, asgs):
        # ASG parameters to save to/restore from a tag
        asg_params = ['MinSize', 'MaxSize', 'DesiredCapacity']

        # support previous param desired_size when desired-size is not present
        if 'desired_size' in self.data and 'desired-size' not in self.data:
            self.data['desired-size'] = self.data['desired_size']

        client = local_session(self.manager.session_factory).client(
            'autoscaling')
        for a in asgs:
            tag_map = {t['Key']: t['Value'] for t in a.get('Tags', [])}
            update = {}
            current_size = len(a['Instances'])

            if 'restore-options-tag' in self.data:
                # we want to restore all ASG size params from saved data
                self.log.debug(
                    'Want to restore ASG %s size from tag %s' %
                    (a['AutoScalingGroupName'], self.data['restore-options-tag']))
                if self.data['restore-options-tag'] in tag_map:
                    for field in tag_map[self.data['restore-options-tag']].split(';'):
                        (param, value) = field.split('=')
                        if param in asg_params:
                            update[param] = int(value)

            else:
                # we want to resize, parse provided params
                if 'min-size' in self.data:
                    update['MinSize'] = self.data['min-size']

                if 'max-size' in self.data:
                    update['MaxSize'] = self.data['max-size']

                if 'desired-size' in self.data:
                    if self.data['desired-size'] == 'current':
                        update['DesiredCapacity'] = min(current_size, a['DesiredCapacity'])
                        if 'MinSize' not in update:
                            # unless we were given a new value for min_size then
                            # ensure it is at least as low as current_size
                            update['MinSize'] = min(current_size, a['MinSize'])
                    elif type(self.data['desired-size']) == int:
                        update['DesiredCapacity'] = self.data['desired-size']

            if update:
                self.log.debug('ASG %s size: current=%d, min=%d, max=%d, desired=%d'
                    % (a['AutoScalingGroupName'], current_size, a['MinSize'],
                    a['MaxSize'], a['DesiredCapacity']))

                if 'save-options-tag' in self.data:
                    # save existing ASG params to a tag before changing them
                    self.log.debug('Saving ASG %s size to tag %s' %
                        (a['AutoScalingGroupName'], self.data['save-options-tag']))
                    tags = [dict(
                        Key=self.data['save-options-tag'],
                        PropagateAtLaunch=False,
                        Value=';'.join({'%s=%d' % (param, a[param]) for param in asg_params}),
                        ResourceId=a['AutoScalingGroupName'],
                        ResourceType='auto-scaling-group',
                    )]
                    self.manager.retry(client.create_or_update_tags, Tags=tags)

                self.log.debug('Resizing ASG %s with %s' % (a['AutoScalingGroupName'],
                    str(update)))
                self.manager.retry(
                    client.update_auto_scaling_group,
                    AutoScalingGroupName=a['AutoScalingGroupName'],
                    **update)
            else:
                self.log.debug('nothing to resize')


@ASG.action_registry.register('remove-tag')
@ASG.action_registry.register('untag')  # compatibility
@ASG.action_registry.register('unmark')  # compatibility
class RemoveTag(Action):
    """Action to remove tag/tags from an ASG

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-remove-unnecessary-tags
                resource: asg
                filters:
                  - "tag:UnnecessaryTag": present
                actions:
                  - type: remove-tag
                    key: UnnecessaryTag
    """

    schema = type_schema(
        'remove-tag',
        aliases=('untag', 'unmark'),
        tags={'type': 'array', 'items': {'type': 'string'}},
        key={'type': 'string'})

    permissions = ('autoscaling:DeleteTags',)
    batch_size = 1

    def process(self, asgs):
        error = False
        tags = self.data.get('tags', [])
        if not tags:
            tags = [self.data.get('key', DEFAULT_TAG)]
        client = local_session(self.manager.session_factory).client('autoscaling')

        with self.executor_factory(max_workers=2) as w:
            futures = {}
            for asg_set in chunks(asgs, self.batch_size):
                futures[w.submit(
                    self.process_resource_set, client, asg_set, tags)] = asg_set
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

    def process_resource_set(self, client, asgs, tags):
        tag_set = []
        for a in asgs:
            for t in tags:
                tag_set.append(dict(
                    Key=t, ResourceType='auto-scaling-group',
                    ResourceId=a['AutoScalingGroupName']))
        self.manager.retry(client.delete_tags, Tags=tag_set)


@ASG.action_registry.register('tag')
@ASG.action_registry.register('mark')
class Tag(Action):
    """Action to add a tag to an ASG

    The *propagate* parameter can be used to specify that the tag being added
    will need to be propagated down to each ASG instance associated or simply
    to the ASG itself.

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-add-owner-tag
                resource: asg
                filters:
                  - "tag:OwnerName": absent
                actions:
                  - type: tag
                    key: OwnerName
                    value: OwnerName
                    propagate: true
    """

    schema = type_schema(
        'tag',
        key={'type': 'string'},
        value={'type': 'string'},
        tags={'type': 'object'},
        # Backwards compatibility
        tag={'type': 'string'},
        msg={'type': 'string'},
        propagate={'type': 'boolean'},
        aliases=('mark',)
    )
    permissions = ('autoscaling:CreateOrUpdateTags',)
    batch_size = 1

    def get_tag_set(self):
        tags = []
        key = self.data.get('key', self.data.get('tag', DEFAULT_TAG))
        value = self.data.get(
            'value', self.data.get(
                'msg', 'AutoScaleGroup does not meet policy guidelines'))
        if key and value:
            tags.append({'Key': key, 'Value': value})

        for k, v in self.data.get('tags', {}).items():
            tags.append({'Key': k, 'Value': v})

        return tags

    def process(self, asgs):
        tags = self.get_tag_set()
        error = None

        client = self.get_client()
        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for asg_set in chunks(asgs, self.batch_size):
                futures[w.submit(
                    self.process_resource_set, client, asg_set, tags)] = asg_set
            for f in as_completed(futures):
                asg_set = futures[f]
                if f.exception():
                    self.log.exception(
                        "Exception tagging tag:%s error:%s asg:%s" % (
                            tags,
                            f.exception(),
                            ", ".join([a['AutoScalingGroupName']
                                       for a in asg_set])))
        if error:
            raise error

    def process_resource_set(self, client, asgs, tags):
        tag_params = []
        propagate = self.data.get('propagate', False)
        for t in tags:
            if 'PropagateAtLaunch' not in t:
                t['PropagateAtLaunch'] = propagate
        for t in tags:
            for a in asgs:
                atags = dict(t)
                atags['ResourceType'] = 'auto-scaling-group'
                atags['ResourceId'] = a['AutoScalingGroupName']
                tag_params.append(atags)
        self.manager.retry(client.create_or_update_tags, Tags=tag_params)

    def get_client(self):
        return local_session(self.manager.session_factory).client('autoscaling')


@ASG.action_registry.register('propagate-tags')
class PropagateTags(Action):
    """Propagate tags to an asg instances.

    In AWS changing an asg tag does not propagate to instances.

    This action exists to do that, and can also trim older tags
    not present on the asg anymore that are present on instances.


    :example:

    .. code-block:: yaml

            policies:
              - name: asg-propagate-required
                resource: asg
                filters:
                  - "tag:OwnerName": present
                actions:
                  - type: propagate-tags
                    tags:
                      - OwnerName
    """

    schema = type_schema(
        'propagate-tags',
        tags={'type': 'array', 'items': {'type': 'string'}},
        trim={'type': 'boolean'})
    permissions = ('ec2:DeleteTags', 'ec2:CreateTags')

    def validate(self):
        if not isinstance(self.data.get('tags', []), (list, tuple)):
            raise ValueError("No tags specified")
        return self

    def process(self, asgs):
        if not asgs:
            return
        if self.data.get('trim', False):
            self.instance_map = self.get_instance_map(asgs)
        with self.executor_factory(max_workers=3) as w:
            instance_count = sum(list(w.map(self.process_asg, asgs)))
            self.log.info("Applied tags to %d instances" % instance_count)

    def process_asg(self, asg):
        client = local_session(self.manager.session_factory).client('ec2')
        instance_ids = [i['InstanceId'] for i in asg['Instances']]
        tag_map = {t['Key']: t['Value'] for t in asg.get('Tags', [])
                   if t['PropagateAtLaunch'] and not t['Key'].startswith('aws:')}

        if self.data.get('tags'):
            tag_map = {
                k: v for k, v in tag_map.items()
                if k in self.data['tags']}

        tag_set = set(tag_map)
        if self.data.get('trim', False):
            instances = [self.instance_map[i] for i in instance_ids]
            self.prune_instance_tags(client, asg, tag_set, instances)
        if not self.manager.config.dryrun and instances:
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
            self.log.debug("Pruning asg:%s instances:%d of old tags: %s" % (
                asg['AutoScalingGroupName'], instance_count, remove_tags))
        if extra_tags:
            self.log.debug("Asg: %s has uneven tags population: %s" % (
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
        return {i['InstanceId']: i for i in
                self.manager.get_resource_manager(
                    'ec2').get_resources(instance_ids)}


@ASG.action_registry.register('rename-tag')
class RenameTag(Action):
    """Rename a tag on an AutoScaleGroup.

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-rename-owner-tag
                resource: asg
                filters:
                  - "tag:OwnerNames": present
                actions:
                  - type: rename-tag
                    propagate: true
                    source: OwnerNames
                    dest: OwnerName
    """

    schema = type_schema(
        'rename-tag', required=['source', 'dest'],
        propagate={'type': 'boolean'},
        source={'type': 'string'},
        dest={'type': 'string'})

    def get_permissions(self):
        permissions = (
            'autoscaling:CreateOrUpdateTags',
            'autoscaling:DeleteTags')
        if self.data.get('propagate', True):
            permissions += ('ec2:CreateTags', 'ec2:DeleteTags')
        return permissions

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
        self.log.info("Filtered from %d asgs to %d", count, len(asgs))
        self.log.info(
            "Renaming %s to %s on %d asgs", source, dest, len(filtered))
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
        if propagate:
            self.propagate_instance_tag(source, destination_tag, asg)

    def propagate_instance_tag(self, source, destination_tag, asg):
        client = local_session(self.manager.session_factory).client('ec2')
        client.delete_tags(
            Resources=[i['InstanceId'] for i in asg['Instances']],
            Tags=[{"Key": source['Key']}])
        client.create_tags(
            Resources=[i['InstanceId'] for i in asg['Instances']],
            Tags=[{'Key': destination_tag, 'Value': source['Value']}])


@ASG.action_registry.register('mark-for-op')
class MarkForOp(TagDelayedAction):
    """Action to create a delayed action for a later date

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-suspend-schedule
                resource: asg
                filters:
                  - type: value
                    key: MinSize
                    value: 2
                actions:
                  - type: mark-for-op
                    tag: custodian_suspend
                    message: "Suspending: {op}@{action_date}"
                    op: suspend
                    days: 7
    """

    schema = type_schema(
        'mark-for-op',
        op={'type': 'string'},
        key={'type': 'string'},
        tag={'type': 'string'},
        tz={'type': 'string'},
        msg={'type': 'string'},
        message={'type': 'string'},
        days={'type': 'number', 'minimum': 0},
        hours={'type': 'number', 'minimum': 0})
    schema_alias = False
    default_template = (
        'AutoScaleGroup does not meet org policy: {op}@{action_date}')

    def get_config_values(self):
        d = {
            'op': self.data.get('op', 'stop'),
            'tag': self.data.get('key', self.data.get('tag', DEFAULT_TAG)),
            'msg': self.data.get('message', self.data.get('msg', self.default_template)),
            'tz': self.data.get('tz', 'utc'),
            'days': self.data.get('days', 0),
            'hours': self.data.get('hours', 0)}
        d['action_date'] = self.generate_timestamp(
            d['days'], d['hours'])
        return d


@ASG.action_registry.register('suspend')
class Suspend(Action):
    """Action to suspend ASG processes and instances

    AWS ASG suspend/resume and process docs
     https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-suspend-resume-processes.html

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-suspend-processes
                resource: asg
                filters:
                  - "tag:SuspendTag": present
                actions:
                  - type: suspend
    """
    permissions = ("autoscaling:SuspendProcesses", "ec2:StopInstances")

    ASG_PROCESSES = [
        "Launch",
        "Terminate",
        "HealthCheck",
        "ReplaceUnhealthy",
        "AZRebalance",
        "AlarmNotification",
        "ScheduledActions",
        "AddToLoadBalancer"]

    schema = type_schema(
        'suspend',
        exclude={
            'type': 'array',
            'title': 'ASG Processes to not suspend',
            'items': {'enum': ASG_PROCESSES}})

    ASG_PROCESSES = set(ASG_PROCESSES)

    def process(self, asgs):
        with self.executor_factory(max_workers=3) as w:
            list(w.map(self.process_asg, asgs))

    def process_asg(self, asg):
        """Multistep process to stop an asg aprori of setup

        - suspend processes
        - stop instances
        """
        session = local_session(self.manager.session_factory)
        asg_client = session.client('autoscaling')
        processes = list(self.ASG_PROCESSES.difference(
            self.data.get('exclude', ())))

        try:
            self.manager.retry(
                asg_client.suspend_processes,
                ScalingProcesses=processes,
                AutoScalingGroupName=asg['AutoScalingGroupName'])
        except ClientError as e:
            if e.response['Error']['Code'] == 'ValidationError':
                return
            raise
        ec2_client = session.client('ec2')
        try:
            instance_ids = [i['InstanceId'] for i in asg['Instances']]
            if not instance_ids:
                return
            retry = get_retry((
                'RequestLimitExceeded', 'Client.RequestLimitExceeded'))
            retry(ec2_client.stop_instances, InstanceIds=instance_ids)
        except ClientError as e:
            if e.response['Error']['Code'] in (
                    'InvalidInstanceID.NotFound',
                    'IncorrectInstanceState'):
                self.log.warning("Erroring stopping asg instances %s %s" % (
                    asg['AutoScalingGroupName'], e))
                return
            raise


@ASG.action_registry.register('resume')
class Resume(Action):
    """Resume a suspended autoscale group and its instances

    Parameter 'delay' is the amount of time (in seconds) to wait
    between resuming instances in the asg, and restarting the internal
    asg processed which gives some grace period before health checks
    turn on within the ASG (default value: 30)

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-resume-processes
                resource: asg
                filters:
                  - "tag:Resume": present
                actions:
                  - type: resume
                    delay: 300

    """
    schema = type_schema('resume', delay={'type': 'number'})
    permissions = ("autoscaling:ResumeProcesses", "ec2:StartInstances")

    def process(self, asgs):
        original_count = len(asgs)
        asgs = [a for a in asgs if a['SuspendedProcesses']]
        self.delay = self.data.get('delay', 30)
        self.log.debug("Filtered from %d to %d suspended asgs",
                       original_count, len(asgs))

        session = local_session(self.manager.session_factory)
        ec2_client = session.client('ec2')
        asg_client = session.client('autoscaling')

        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for a in asgs:
                futures[w.submit(self.resume_asg_instances, ec2_client, a)] = a
            for f in as_completed(futures):
                if f.exception():
                    self.log.error("Traceback resume asg:%s instances error:%s" % (
                        futures[f]['AutoScalingGroupName'],
                        f.exception()))
                    continue

        self.log.debug("Sleeping for asg health check grace")
        time.sleep(self.delay)

        with self.executor_factory(max_workers=3) as w:
            futures = {}
            for a in asgs:
                futures[w.submit(self.resume_asg, asg_client, a)] = a
            for f in as_completed(futures):
                if f.exception():
                    self.log.error("Traceback resume asg:%s error:%s" % (
                        futures[f]['AutoScalingGroupName'],
                        f.exception()))

    def resume_asg_instances(self, ec2_client, asg):
        """Resume asg instances.
        """
        instance_ids = [i['InstanceId'] for i in asg['Instances']]
        if not instance_ids:
            return
        retry = get_retry((
            'RequestLimitExceeded', 'Client.RequestLimitExceeded'))
        retry(ec2_client.start_instances, InstanceIds=instance_ids)

    def resume_asg(self, asg_client, asg):
        """Resume asg processes.
        """
        self.manager.retry(
            asg_client.resume_processes,
            AutoScalingGroupName=asg['AutoScalingGroupName'])


@ASG.action_registry.register('delete')
class Delete(Action):
    """Action to delete an ASG

    The 'force' parameter is needed when deleting an ASG that has instances
    attached to it.

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-delete-bad-encryption
                resource: asg
                filters:
                  - type: not-encrypted
                    exclude_image: true
                actions:
                  - type: delete
                    force: true
    """

    schema = type_schema('delete', force={'type': 'boolean'})
    permissions = ("autoscaling:DeleteAutoScalingGroup",)

    def process(self, asgs):
        client = local_session(
            self.manager.session_factory).client('autoscaling')
        for asg in asgs:
            self.process_asg(client, asg)

    def process_asg(self, client, asg):
        force_delete = self.data.get('force', False)
        try:
            self.manager.retry(
                client.delete_auto_scaling_group,
                AutoScalingGroupName=asg['AutoScalingGroupName'],
                ForceDelete=force_delete)
        except ClientError as e:
            if e.response['Error']['Code'] == 'ValidationError':
                return
            raise


@resources.register('launch-config')
class LaunchConfig(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'autoscaling'
        arn_type = 'launchConfiguration'
        id = name = 'LaunchConfigurationName'
        date = 'CreatedTime'
        enum_spec = (
            'describe_launch_configurations', 'LaunchConfigurations', None)
        filter_name = 'LaunchConfigurationNames'
        filter_type = 'list'
        cfn_type = config_type = 'AWS::AutoScaling::LaunchConfiguration'


@LaunchConfig.filter_registry.register('age')
class LaunchConfigAge(AgeFilter):
    """Filter ASG launch configuration by age (in days)

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-launch-config-old
                resource: launch-config
                filters:
                  - type: age
                    days: 90
                    op: ge
    """

    date_attribute = "CreatedTime"
    schema = type_schema(
        'age',
        op={'$ref': '#/definitions/filters_common/comparison_operators'},
        days={'type': 'number'})


@LaunchConfig.filter_registry.register('unused')
class UnusedLaunchConfig(Filter):
    """Filters all launch configurations that are not in use but exist

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-unused-launch-config
                resource: launch-config
                filters:
                  - unused
    """

    schema = type_schema('unused')

    def get_permissions(self):
        return self.manager.get_resource_manager('asg').get_permissions()

    def process(self, configs, event=None):
        asgs = self.manager.get_resource_manager('asg').resources()
        used = {a.get('LaunchConfigurationName', a['AutoScalingGroupName'])
                for a in asgs if not a.get('LaunchTemplate')}
        return [c for c in configs if c['LaunchConfigurationName'] not in used]


@LaunchConfig.action_registry.register('delete')
class LaunchConfigDelete(Action):
    """Filters all unused launch configurations

    :example:

    .. code-block:: yaml

            policies:
              - name: asg-unused-launch-config-delete
                resource: launch-config
                filters:
                  - unused
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ("autoscaling:DeleteLaunchConfiguration",)

    def process(self, configs):
        client = local_session(self.manager.session_factory).client('autoscaling')

        for c in configs:
            self.process_config(client, c)

    def process_config(self, client, config):
        try:
            client.delete_launch_configuration(
                LaunchConfigurationName=config[
                    'LaunchConfigurationName'])
        except ClientError as e:
            # Catch already deleted
            if e.response['Error']['Code'] == 'ValidationError':
                return
            raise
