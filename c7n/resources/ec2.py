# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import base64
import itertools
import operator
import random
import re
import zlib
from typing import List
from c7n.vendored.distutils.version import LooseVersion

import botocore
from botocore.exceptions import ClientError
from dateutil.parser import parse
from concurrent.futures import as_completed

from c7n.actions import (
    ActionRegistry, BaseAction, ModifyVpcSecurityGroupsAction, AutoscalingBase
)

from c7n.exceptions import PolicyValidationError
from c7n.filters import (
    FilterRegistry, AgeFilter, ValueFilter, Filter
)
from c7n.filters.offhours import OffHour, OnHour
from c7n.filters.costhub import CostHubRecommendation
import c7n.filters.vpc as net_filters

from c7n.manager import resources
from c7n import query, utils
from c7n.tags import coalesce_copy_user_tags
from c7n.utils import type_schema, filter_empty, jmespath_search, jmespath_compile

from c7n.resources.iam import CheckPermissions, SpecificIamProfileManagedPolicy
from c7n.resources.securityhub import PostFinding

RE_ERROR_INSTANCE_ID = re.compile("'(?P<instance_id>i-.*?)'")

filters = FilterRegistry('ec2.filters')
actions = ActionRegistry('ec2.actions')


class DescribeEC2(query.DescribeSource):

    def get_query_params(self, query_params):
        queries = QueryFilter.parse(self.manager.data.get('query', []))
        qf = []
        for q in queries:
            qd = q.query()
            found = False
            for f in qf:
                if qd['Name'] == f['Name']:
                    f['Values'].extend(qd['Values'])
                    found = True
            if not found:
                qf.append(qd)
        query_params = query_params or {}
        query_params['Filters'] = qf
        return query_params

    def augment(self, resources):
        """EC2 API and AWOL Tags

        While ec2 api generally returns tags when doing describe_x on for
        various resources, it may also silently fail to do so unless a tag
        is used as a filter.

        See footnote on for official documentation.
        https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Using_Tags.html#Using_Tags_CLI

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
            r['Tags'] = resource_tags.get(r[m.id], [])
        return resources


@resources.register('ec2')
class EC2(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'instance'
        enum_spec = ('describe_instances', 'Reservations[].Instances[]', None)
        id = 'InstanceId'
        filter_name = 'InstanceIds'
        filter_type = 'list'
        name = 'PublicDnsName'
        date = 'LaunchTime'
        dimension = 'InstanceId'
        cfn_type = config_type = "AWS::EC2::Instance"
        id_prefix = 'i-'
        permissions_augment = ('ec2:DescribeTags',)

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
    source_mapping = {
        'describe': DescribeEC2,
        'config': query.ConfigSource
    }


@filters.register('security-group')
class SecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "NetworkInterfaces[].Groups[].GroupId"


@filters.register('subnet')
class SubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "NetworkInterfaces[].SubnetId"


@filters.register('vpc')
class VpcFilter(net_filters.VpcFilter):

    RelatedIdsExpression = "VpcId"


@filters.register('check-permissions')
class ComputePermissions(CheckPermissions):

    def get_iam_arns(self, resources):
        profile_arn_map = {
            r['IamInstanceProfile']['Arn']: r['IamInstanceProfile']['Id']
            for r in resources if 'IamInstanceProfile' in r}

        # py2 compat on dict ordering
        profile_arns = list(profile_arn_map.items())
        profile_role_map = {
            arn: profile['Roles'][0]['Arn']
            for arn, profile in zip(
                [p[0] for p in profile_arns],
                self.manager.get_resource_manager(
                    'iam-profile').get_resources(
                        [p[0].split('/', 1)[-1] for p in profile_arns]))}
        return [
            profile_role_map.get(r.get('IamInstanceProfile', {}).get('Arn'))
            for r in resources]


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
    RE_PARSE_AGE = re.compile(r"\(.*?\)")

    # this filter doesn't use date_attribute, but needs to define it
    # to pass AgeFilter's validate method
    date_attribute = "dummy"

    schema = type_schema(
        'state-age',
        op={'$ref': '#/definitions/filters_common/comparison_operators'},
        days={'type': 'number'})

    def get_resource_date(self, i):
        v = i.get('StateTransitionReason')
        if not v:
            return None
        dates = self.RE_PARSE_AGE.findall(v)
        if dates:
            return parse(dates[0][1:-1])
        return None


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
    schema_alias = False

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


@filters.register('stop-protected')
class DisableApiStop(Filter):
    """EC2 instances with ``disableApiStop`` attribute set

    Filters EC2 instances with ``disableApiStop`` attribute set to true.

    :Example:

    .. code-block:: yaml

        policies:
          - name: stop-protection-enabled
            resource: ec2
            filters:
              - type: stop-protected

    :Example:

    .. code-block:: yaml

        policies:
          - name: stop-protection-NOT-enabled
            resource: ec2
            filters:
              - not:
                - type: stop-protected
    """

    schema = type_schema('stop-protected')
    permissions = ('ec2:DescribeInstanceAttribute',)

    def process(self, resources: List[dict], event=None) -> List[dict]:
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        return [r for r in resources
                if self._is_stop_protection_enabled(client, r)]

    def _is_stop_protection_enabled(self, client, instance: dict) -> bool:
        attr_val = self.manager.retry(
            client.describe_instance_attribute,
            Attribute='disableApiStop',
            InstanceId=instance['InstanceId']
        )
        return attr_val['DisableApiStop']['Value']

    def validate(self) -> None:
        botocore_min_version = '1.26.7'

        if LooseVersion(botocore.__version__) < LooseVersion(botocore_min_version):
            raise PolicyValidationError(
                "'stop-protected' filter requires botocore version "
                f'{botocore_min_version} or above. '
                f'Installed version is {botocore.__version__}.'
            )


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


class InstanceImageBase:

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
        op={'$ref': '#/definitions/filters_common/comparison_operators'},
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
    schema_alias = False

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
class InstanceOffHour(OffHour):
    """Custodian OffHour filter

    Filters running EC2 instances with the intent to stop at a given hour of
    the day. A list of days to excluded can be included as a list of strings
    with the format YYYY-MM-DD. Alternatively, the list (using the same syntax)
    can be taken from a specified url.

    Note: You can disable filtering of only running instances by setting
    `state-filter: false`

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

    schema = type_schema(
        'offhour', rinherit=OffHour.schema,
        **{'state-filter': {'type': 'boolean'}})
    schema_alias = False

    valid_origin_states = ('running',)

    def process(self, resources, event=None):
        if self.data.get('state-filter', True):
            return super(InstanceOffHour, self).process(
                self.filter_resources(resources, 'State.Name', self.valid_origin_states))
        else:
            return super(InstanceOffHour, self).process(resources)


@filters.register('network-location')
class EC2NetworkLocation(net_filters.NetworkLocation):

    valid_origin_states = ('pending', 'running', 'shutting-down', 'stopping',
                           'stopped')

    def process(self, resources, event=None):
        resources = self.filter_resources(resources, 'State.Name', self.valid_origin_states)
        if not resources:
            return []
        return super(EC2NetworkLocation, self).process(resources)


@filters.register('onhour')
class InstanceOnHour(OnHour):
    """Custodian OnHour filter

    Filters stopped EC2 instances with the intent to start at a given hour of
    the day. A list of days to excluded can be included as a list of strings
    with the format YYYY-MM-DD. Alternatively, the list (using the same syntax)
    can be taken from a specified url.

    Note: You can disable filtering of only stopped instances by setting
    `state-filter: false`

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

    schema = type_schema(
        'onhour', rinherit=OnHour.schema,
        **{'state-filter': {'type': 'boolean'}})
    schema_alias = False

    valid_origin_states = ('stopped',)

    def process(self, resources, event=None):
        if self.data.get('state-filter', True):
            return super(InstanceOnHour, self).process(
                self.filter_resources(resources, 'State.Name', self.valid_origin_states))
        else:
            return super(InstanceOnHour, self).process(resources)


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
        op={'$ref': '#/definitions/filters_common/comparison_operators'},
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
        op={'$ref': '#/definitions/filters_common/comparison_operators'},
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
class DefaultVpc(net_filters.DefaultVpcBase):
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
    schema_alias = False
    batch_size = 50
    annotation = 'c7n:user-data'
    permissions = ('ec2:DescribeInstanceAttribute',)

    def __init__(self, data, manager):
        super(UserData, self).__init__(data, manager)
        self.data['key'] = '"c7n:user-data"'

    def process(self, resources, event=None):
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
class SingletonFilter(Filter):
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
            self.filter_resources(instances, 'State.Name', self.valid_origin_states))

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


@EC2.filter_registry.register('ssm')
class SsmStatus(ValueFilter):
    """Filter ec2 instances by their ssm status information.

    :Example:

    Find ubuntu 18.04 instances are active with ssm.

    .. code-block:: yaml

        policies:
          - name: ec2-ssm-check
            resource: ec2
            filters:
              - type: ssm
                key: PingStatus
                value: Online
              - type: ssm
                key: PlatformName
                value: Ubuntu
              - type: ssm
                key: PlatformVersion
                value: 18.04
    """
    schema = type_schema('ssm', rinherit=ValueFilter.schema)
    schema_alias = False
    permissions = ('ssm:DescribeInstanceInformation',)
    annotation = 'c7n:SsmState'

    def process(self, resources, event=None):
        client = utils.local_session(self.manager.session_factory).client('ssm')
        results = []
        for resource_set in utils.chunks(
                [r for r in resources if self.annotation not in r], 50):
            self.process_resource_set(client, resource_set)
        for r in resources:
            if self.match(r[self.annotation]):
                results.append(r)
        return results

    def process_resource_set(self, client, resources):
        instance_ids = [i['InstanceId'] for i in resources]
        info_map = {
            info['InstanceId']: info for info in
            client.describe_instance_information(
                Filters=[{'Key': 'InstanceIds', 'Values': instance_ids}]).get(
                    'InstanceInformationList', [])}
        for r in resources:
            r[self.annotation] = info_map.get(r['InstanceId'], {})


@EC2.filter_registry.register('ssm-inventory')
class SsmInventory(Filter):
    """Filter EC2 instances by their SSM software inventory.

    :Example:

    Find instances that have a specific package installed.

    .. code-block:: yaml

        policies:
        - name: ec2-find-specific-package
          resource: ec2
          filters:
          - type: ssm-inventory
            query:
            - Key: Name
              Values:
              - "docker"
              Type: Equal

        - name: ec2-get-all-packages
          resource: ec2
          filters:
          - type: ssm-inventory
    """
    schema = type_schema(
        'ssm-inventory',
        **{'query': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {
                'Key': {'type': 'string'},
                'Values': {'type': 'array', 'items': {'type': 'string'}},
                'Type': {'enum': ['Equal', 'NotEqual', 'BeginWith', 'LessThan',
                  'GreaterThan', 'Exists']}},
            'required': ['Key', 'Values']}}})

    permissions = ('ssm:ListInventoryEntries',)
    annotation_key = 'c7n:SSM-Inventory'

    def process(self, resources, event=None):
        client = utils.local_session(self.manager.session_factory).client('ssm')
        query = self.data.get("query")
        found = []
        for r in resources:
            entries = []
            next_token = None
            while True:
                params = {
                    "InstanceId": r["InstanceId"],
                    "TypeName": "AWS:Application"
                }
                if next_token:
                    params['NextToken'] = next_token
                if query:
                    params['Filters'] = query
                response = client.list_inventory_entries(**params)
                all_entries = response["Entries"]
                if all_entries:
                    entries.extend(all_entries)
                next_token = response.get('NextToken')
                if not next_token:
                    break
            if entries:
                r[self.annotation_key] = entries
                found.append(r)
        return found


@EC2.filter_registry.register('ssm-compliance')
class SsmCompliance(Filter):
    """Filter ec2 instances by their ssm compliance status.

    :Example:

    Find non-compliant ec2 instances.

    .. code-block:: yaml

        policies:
          - name: ec2-ssm-compliance
            resource: ec2
            filters:
              - type: ssm-compliance
                compliance_types:
                  - Association
                  - Patch
                severity:
                  - CRITICAL
                  - HIGH
                  - MEDIUM
                  - LOW
                  - UNSPECIFIED
                states:
                  - NON_COMPLIANT
                eval_filters:
                 - type: value
                   key: ExecutionSummary.ExecutionTime
                   value_type: age
                   value: 30
                   op: less-than
    """
    schema = type_schema(
        'ssm-compliance',
        **{'required': ['compliance_types'],
           'compliance_types': {'type': 'array', 'items': {'type': 'string'}},
           'severity': {'type': 'array', 'items': {'type': 'string'}},
           'op': {'enum': ['or', 'and']},
           'eval_filters': {'type': 'array', 'items': {
                            'oneOf': [
                                {'$ref': '#/definitions/filters/valuekv'},
                                {'$ref': '#/definitions/filters/value'}]}},
           'states': {'type': 'array',
                      'default': ['NON_COMPLIANT'],
                      'items': {
                          'enum': [
                              'COMPLIANT',
                              'NON_COMPLIANT'
                          ]}}})
    permissions = ('ssm:ListResourceComplianceSummaries',)
    annotation = 'c7n:ssm-compliance'

    def process(self, resources, event=None):
        op = self.data.get('op', 'or') == 'or' and any or all
        eval_filters = []
        for f in self.data.get('eval_filters', ()):
            vf = ValueFilter(f)
            vf.annotate = False
            eval_filters.append(vf)

        client = utils.local_session(self.manager.session_factory).client('ssm')
        filters = [
            {
                'Key': 'Status',
                'Values': self.data['states'],
                'Type': 'EQUAL'
            },
            {
                'Key': 'ComplianceType',
                'Values': self.data['compliance_types'],
                'Type': 'EQUAL'
            }
        ]
        severity = self.data.get('severity')
        if severity:
            filters.append(
                {
                    'Key': 'OverallSeverity',
                    'Values': severity,
                    'Type': 'EQUAL'
                })

        resource_map = {}
        pager = client.get_paginator('list_resource_compliance_summaries')
        for page in pager.paginate(Filters=filters):
            items = page['ResourceComplianceSummaryItems']
            for i in items:
                if not eval_filters:
                    resource_map.setdefault(
                        i['ResourceId'], []).append(i)
                    continue
                if op([f.match(i) for f in eval_filters]):
                    resource_map.setdefault(
                        i['ResourceId'], []).append(i)

        results = []
        for r in resources:
            result = resource_map.get(r['InstanceId'])
            if result:
                r[self.annotation] = result
                results.append(r)

        return results


@actions.register('set-monitoring')
class MonitorInstances(BaseAction):
    """Action on EC2 Instances to enable/disable detailed monitoring

    The different states of detailed monitoring status are :
    'disabled'|'disabling'|'enabled'|'pending'
    (https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html#EC2.Client.describe_instances)

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-detailed-monitoring-activation
            resource: ec2
            filters:
              - Monitoring.State: disabled
            actions:
              - type: set-monitoring
                state: enable

    References

     https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-cloudwatch-new.html
    """
    schema = type_schema('set-monitoring',
        **{'state': {'enum': ['enable', 'disable']}})
    permissions = ('ec2:MonitorInstances', 'ec2:UnmonitorInstances')

    def process(self, resources, event=None):
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        actions = {
            'enable': self.enable_monitoring,
            'disable': self.disable_monitoring
        }
        for instances_set in utils.chunks(resources, 20):
            actions[self.data.get('state')](client, instances_set)

    def enable_monitoring(self, client, resources):
        try:
            client.monitor_instances(
                InstanceIds=[inst['InstanceId'] for inst in resources]
            )
        except ClientError as e:
            if e.response['Error']['Code'] != 'InvalidInstanceId.NotFound':
                raise

    def disable_monitoring(self, client, resources):
        try:
            client.unmonitor_instances(
                InstanceIds=[inst['InstanceId'] for inst in resources]
            )
        except ClientError as e:
            if e.response['Error']['Code'] != 'InvalidInstanceId.NotFound':
                raise


@EC2.action_registry.register('set-metadata-access')
class SetMetadataServerAccess(BaseAction):
    """Set instance metadata server access for an instance.

    :example:

    Require instances to use IMDSv2

    .. code-block:: yaml

       policies:
         - name: ec2-require-imdsv2
           resource: ec2
           filters:
             - MetadataOptions.HttpTokens: optional
           actions:
             - type: set-metadata-access
               tokens: required

    :example:

    Disable metadata server access

    .. code-block: yaml

       policies:
         - name: ec2-disable-imds
           resource: ec2
           filters:
             - MetadataOptions.HttpEndpoint: enabled
           actions:
             - type: set-metadata-access
               endpoint: disabled

       policies:
         - name: ec2-enable-metadata-tags
           resource: ec2
           filters:
             - MetadataOptions.InstanceMetadataTags: disabled
           actions:
             - type: set-metadata-access
               metadata-tags: enabled

    Reference: https://amzn.to/2XOuxpQ
    """

    AllowedValues = {
        'HttpEndpoint': ['enabled', 'disabled'],
        'HttpTokens': ['required', 'optional'],
        'InstanceMetadataTags': ['enabled', 'disabled'],
        'HttpPutResponseHopLimit': list(range(1, 65))
    }

    schema = type_schema(
        'set-metadata-access',
        anyOf=[{'required': ['endpoint']},
               {'required': ['tokens']},
               {'required': ['metadatatags']},
               {'required': ['hop-limit']}],
        **{'endpoint': {'enum': AllowedValues['HttpEndpoint']},
           'tokens': {'enum': AllowedValues['HttpTokens']},
           'metadata-tags': {'enum': AllowedValues['InstanceMetadataTags']},
           'hop-limit': {'type': 'integer', 'minimum': 1, 'maximum': 64}}
    )
    permissions = ('ec2:ModifyInstanceMetadataOptions',)

    def get_params(self):
        return filter_empty({
            'HttpEndpoint': self.data.get('endpoint'),
            'HttpTokens': self.data.get('tokens'),
            'InstanceMetadataTags': self.data.get('metadata-tags'),
            'HttpPutResponseHopLimit': self.data.get('hop-limit')})

    def process(self, resources):
        params = self.get_params()
        for k, v in params.items():
            allowed_values = list(self.AllowedValues[k])
            allowed_values.remove(v)
            resources = self.filter_resources(
                resources, 'MetadataOptions.%s' % k, allowed_values)

        if not resources:
            return

        client = utils.local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            self.manager.retry(
                client.modify_instance_metadata_options,
                ignore_err_codes=('InvalidInstanceId.NotFound',),
                InstanceId=r['InstanceId'],
                **params)


@EC2.action_registry.register("post-finding")
class InstanceFinding(PostFinding):

    resource_type = 'AwsEc2Instance'

    def format_resource(self, r):
        ip_addresses = jmespath_search(
            "NetworkInterfaces[].PrivateIpAddresses[].PrivateIpAddress", r)

        # limit to max 10 ip addresses, per security hub service limits
        ip_addresses = ip_addresses and ip_addresses[:10] or ip_addresses
        details = {
            "Type": r["InstanceType"],
            "ImageId": r["ImageId"],
            "IpV4Addresses": ip_addresses,
            "KeyName": r.get("KeyName"),
            "LaunchedAt": r["LaunchTime"].isoformat()
        }

        if "VpcId" in r:
            details["VpcId"] = r["VpcId"]
        if "SubnetId" in r:
            details["SubnetId"] = r["SubnetId"]
        # config will use an empty key
        if "IamInstanceProfile" in r and r['IamInstanceProfile']:
            details["IamInstanceProfileArn"] = r["IamInstanceProfile"]["Arn"]

        instance = {
            "Type": self.resource_type,
            "Id": "arn:{}:ec2:{}:{}:instance/{}".format(
                utils.get_partition(self.manager.config.region),
                self.manager.config.region,
                self.manager.config.account_id,
                r["InstanceId"]),
            "Region": self.manager.config.region,
            "Tags": {t["Key"]: t["Value"] for t in r.get("Tags", [])},
            "Details": {self.resource_type: filter_empty(details)},
        }

        instance = filter_empty(instance)
        return instance


@actions.register('start')
class Start(BaseAction):
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
            self.filter_resources(instances, 'State.Name', self.valid_origin_states))
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
                fail_count, len(instances), utils.dumps(failures))
            self.log.warning(msg)
            raise RuntimeError(msg)

    def process_instance_set(self, client, instances, itype, izone):
        # Setup retry with insufficient capacity as well
        retryable = ('InsufficientInstanceCapacity', 'RequestLimitExceeded',
                     'Client.RequestLimitExceeded', 'Server.InsufficientInstanceCapacity'),
        retry = utils.get_retry(retryable, max_attempts=5)
        instance_ids = [i['InstanceId'] for i in instances]
        while instance_ids:
            try:
                retry(client.start_instances, InstanceIds=instance_ids)
                break
            except ClientError as e:
                if e.response['Error']['Code'] in retryable:
                    # we maxed out on our retries
                    return True
                elif e.response['Error']['Code'] == 'IncorrectInstanceState':
                    instance_ids.remove(extract_instance_id(e))
                else:
                    raise


def extract_instance_id(state_error):
    "Extract an instance id from an error"
    instance_id = None
    match = RE_ERROR_INSTANCE_ID.search(str(state_error))
    if match:
        instance_id = match.groupdict().get('instance_id')
    if match is None or instance_id is None:
        raise ValueError("Could not extract instance id from error: %s" % state_error)
    return instance_id


@actions.register('resize')
class Resize(BaseAction):
    """Change an instance's size.

    An instance can only be resized when its stopped, this action
    can optionally stop/start an instance if needed to effect the instance
    type change. Instances are always left in the run state they were
    found in.

    There are a few caveats to be aware of, instance resizing
    needs to maintain compatibility for architecture, virtualization type
    hvm/pv, and ebs optimization at minimum.

    http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-resize.html

    This action also has specific support for enacting recommendations
    from the AWS Cost Optimization Hub for resizing.

    :example:

      .. code-block:: yaml

         policies:
           - name: ec2-rightsize
             resource: aws.ec2
             filters:
               - type: cost-optimization
                 attrs:
                  - actionType: Rightsize
             actions:
               - resize

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
        stopped_instances = self.filter_resources(resources, 'State.Name', ('stopped',))
        running_instances = self.filter_resources(resources, 'State.Name', ('running',))

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

        client = utils.local_session(self.manager.session_factory).client('ec2')

        for instance_set in utils.chunks(itertools.chain(
                stopped_instances, running_instances), 20):
            self.process_resource_set(instance_set, client)

        if self.data.get('restart') and running_instances:
            client.start_instances(
                InstanceIds=[i['InstanceId'] for i in running_instances])
        return list(itertools.chain(stopped_instances, running_instances))

    def process_resource_set(self, instance_set, client):

        for i in instance_set:
            new_type = self.get_target_instance_type(i)
            self.log.debug(
                "resizing %s %s -> %s" % (i['InstanceId'], i['InstanceType'], new_type)
            )

            if not new_type or new_type == i['InstanceType']:
                continue
            try:
                client.modify_instance_attribute(
                    InstanceId=i['InstanceId'],
                    InstanceType={'Value': new_type})
            except ClientError as e:
                self.log.exception(
                    "Exception resizing instance:%s new:%s old:%s \n %s" % (
                        i['InstanceId'], new_type, i['InstanceType'], e))

    def get_target_instance_type(self, i):
        optimizer_recommend = i.get(CostHubRecommendation.annotation_key)
        if optimizer_recommend and optimizer_recommend['actionType'] == 'Rightsize':
            return optimizer_recommend['recommendedResourceSummary']
        type_map = self.data.get('type-map', {})
        default_type = self.data.get('default')
        return type_map.get(i['InstanceType'], default_type)


@actions.register('stop')
class Stop(BaseAction):
    """Stops or hibernates a running EC2 instances

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-stop-running-instances
            resource: ec2
            query:
              - instance-state-name: running
            actions:
              - stop

          - name: ec2-hibernate-instances
            resources: ec2
            query:
              - instance-state-name: running
            actions:
              - type: stop
                hibernate: true


    Note when using hiberate, instances not configured for hiberation
    will just be stopped.
    """
    valid_origin_states = ('running',)

    schema = type_schema(
        'stop',
        **{
            "terminate-ephemeral": {"type": "boolean"},
            "hibernate": {"type": "boolean"},
            "force": {"type": "boolean"},
        },
    )

    has_hibernate = jmespath_compile('[].HibernationOptions.Configured')

    def get_permissions(self):
        perms = ('ec2:StopInstances',)
        if self.data.get('terminate-ephemeral', False):
            perms += ('ec2:TerminateInstances',)
        if self.data.get("force"):
            perms += ("ec2:ModifyInstanceAttribute",)
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

    def split_on_hibernate(self, instances):
        enabled, disabled = [], []
        for status, i in zip(self.has_hibernate.search(instances), instances):
            if status is True:
                enabled.append(i)
            else:
                disabled.append(i)
        return enabled, disabled

    def process(self, instances):
        instances = self.filter_resources(instances, 'State.Name', self.valid_origin_states)
        if not len(instances):
            return
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        # Ephemeral instance can't be stopped.
        ephemeral, persistent = self.split_on_storage(instances)
        if self.data.get('terminate-ephemeral', False) and ephemeral:
            self._run_instances_op(client, 'terminate', ephemeral)
        if persistent:
            if self.data.get('hibernate', False):
                enabled, persistent = self.split_on_hibernate(persistent)
                if enabled:
                    self._run_instances_op(client, 'stop', enabled, Hibernate=True)
            self._run_instances_op(client, 'stop', persistent)
        return instances

    def disable_protection(self, client, op, instances):
        def modify_instance(i, attribute):
            try:
                self.manager.retry(
                    client.modify_instance_attribute,
                    InstanceId=i['InstanceId'],
                    Attribute=attribute,
                    Value='false',
                )
            except ClientError as e:
                if e.response['Error']['Code'] == 'IncorrectInstanceState':
                    return
                raise

        def process_instance(i, op):
            modify_instance(i, 'disableApiStop')
            if op == 'terminate':
                modify_instance(i, 'disableApiTermination')

        with self.executor_factory(max_workers=2) as w:
            list(w.map(process_instance, instances, [op] * len(instances)))

    def _run_instances_op(self, client, op, instances, **kwargs):
        client_op = client.stop_instances
        if op == 'terminate':
            client_op = client.terminate_instances

        instance_ids = [i['InstanceId'] for i in instances]

        while instances:
            try:
                return self.manager.retry(client_op, InstanceIds=instance_ids, **kwargs)
            except ClientError as e:
                if e.response['Error']['Code'] == 'IncorrectInstanceState':
                    instance_ids.remove(extract_instance_id(e))
                if (
                    e.response['Error']['Code'] == 'OperationNotPermitted' and
                    self.data.get('force')
                ):
                    self.log.info("Disabling stop and termination protection on instances")
                    self.disable_protection(
                        client,
                        op,
                        [i for i in instances if i.get('InstanceLifecycle') != 'spot'],
                    )
                    continue
                raise


@actions.register('reboot')
class Reboot(BaseAction):
    """Reboots a previously running EC2 instance.

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
            self.filter_resources(instances, 'State.Name', self.valid_origin_states))
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
class Terminate(BaseAction):
    """ Terminate a set of instances.

    While ec2 offers a bulk delete api, any given instance can be configured
    with api deletion termination protection, so we can't use the bulk call
    reliabily, we need to process the instances individually. Additionally
    If we're configured with 'force' then we'll turn off instance termination
    and stop protection.

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

    def process_terminate(self, instances):
        client = utils.local_session(
            self.manager.session_factory).client('ec2')
        try:
            self.manager.retry(
                client.terminate_instances,
                InstanceIds=[i['InstanceId'] for i in instances])
            return
        except ClientError as e:
            if e.response['Error']['Code'] != 'OperationNotPermitted':
                raise
            if not self.data.get('force'):
                raise

            self.log.info("Disabling stop and termination protection on instances")
            self.disable_deletion_protection(
                client,
                [i for i in instances if i.get('InstanceLifecycle') != 'spot'])
            self.manager.retry(
                client.terminate_instances,
                InstanceIds=[i['InstanceId'] for i in instances])

    def process(self, instances):
        instances = self.filter_resources(instances, 'State.Name', self.valid_origin_states)
        if not len(instances):
            return
        # limit batch sizes to avoid api limits
        for batch in utils.chunks(instances, 100):
            self.process_terminate(batch)

    def disable_deletion_protection(self, client, instances):

        def modify_instance(i, attribute):
            try:
                self.manager.retry(
                    client.modify_instance_attribute,
                    InstanceId=i['InstanceId'],
                    Attribute=attribute,
                    Value='false')
            except ClientError as e:
                if e.response['Error']['Code'] == 'IncorrectInstanceState':
                    return
                raise

        def process_instance(i):
            modify_instance(i, 'disableApiTermination')
            modify_instance(i, 'disableApiStop')

        with self.executor_factory(max_workers=2) as w:
            list(w.map(process_instance, instances))


@actions.register('snapshot')
class Snapshot(BaseAction):
    """Snapshot the volumes attached to an EC2 instance.

    Tags may be optionally added to the snapshot during creation.

    - `copy-volume-tags` copies all the tags from the specified
      volume to the corresponding snapshot.
    - `copy-tags` copies the listed tags from each volume
      to the snapshot.  This is mutually exclusive with
      `copy-volume-tags`.
    - `tags` allows new tags to be added to each snapshot when using
      'copy-tags`.  If no tags are specified, then the tag
      `custodian_snapshot` is added.

    The default behavior is `copy-volume-tags: true`.

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-snapshots
            resource: ec2
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
           'exclude-boot': {'type': 'boolean', 'default': False}})
    permissions = ('ec2:CreateSnapshot', 'ec2:CreateTags',)

    def validate(self):
        if self.data.get('copy-tags') and 'copy-volume-tags' in self.data:
            raise PolicyValidationError(
                "Can specify copy-tags or copy-volume-tags, not both")

    def process(self, resources):
        client = utils.local_session(self.manager.session_factory).client('ec2')
        err = None
        with self.executor_factory(max_workers=2) as w:
            futures = {}
            for resource in resources:
                futures[w.submit(
                    self.process_volume_set, client, resource)] = resource
            for f in as_completed(futures):
                if f.exception():
                    err = f.exception()
                    resource = futures[f]
                    self.log.error(
                        "Exception creating snapshot set instance:%s \n %s" % (
                            resource['InstanceId'], err))
        if err:
            raise err

    def get_instance_name(self, resource):
        tags = resource.get('Tags', [])
        for tag in tags:
            if tag['Key'] == 'Name':
                return tag['Value']
        return "-"

    def process_volume_set(self, client, resource):
        i_name = self.get_instance_name(resource)
        params = dict(
            Description=f"Snapshot Created for {resource['InstanceId']} ({i_name})",
            InstanceSpecification={
                'ExcludeBootVolume': self.data.get('exclude-boot', False),
                'InstanceId': resource['InstanceId']})
        if 'copy-tags' in self.data:
            params['TagSpecifications'] = [{
                'ResourceType': 'snapshot',
                'Tags': self.get_snapshot_tags(resource)}]
        elif self.data.get('copy-volume-tags', True):
            params['CopyTagsFromSource'] = 'volume'

        try:
            result = self.manager.retry(client.create_snapshots, **params)
            resource['c7n:snapshots'] = [
                s['SnapshotId'] for s in result['Snapshots']]
        except ClientError as e:
            err_code = e.response['Error']['Code']
            if err_code not in (
                    'InvalidInstanceId.NotFound',
                    'ConcurrentSnapshotLimitExceeded',
                    'IncorrectState'):
                raise
            self.log.warning(
                "action:snapshot instance:%s error:%s",
                resource['InstanceId'], err_code)

    def get_snapshot_tags(self, resource):
        user_tags = self.data.get('tags', {}) or {'custodian_snapshot': ''}
        copy_tags = self.data.get('copy-tags', [])
        return coalesce_copy_user_tags(resource, copy_tags, user_tags)


@actions.register('modify-security-groups')
class EC2ModifyVpcSecurityGroups(ModifyVpcSecurityGroupsAction):
    """Modify security groups on an instance."""

    permissions = ("ec2:ModifyNetworkInterfaceAttribute",)
    sg_expr = jmespath_compile("Groups[].GroupId")

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
class AutorecoverAlarm(BaseAction):
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
    permissions = ('cloudwatch:PutMetricAlarm',)
    valid_origin_states = ('running', 'stopped', 'pending', 'stopping')
    filter_asg_membership = ValueFilter({
        'key': 'tag:aws:autoscaling:groupName',
        'value': 'empty'}).validate()

    def process(self, instances):
        instances = self.filter_asg_membership.process(
            self.filter_resources(instances, 'State.Name', self.valid_origin_states))
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
                    'arn:{}:automate:{}:ec2:recover'.format(
                        utils.get_partition(
                            self.manager.config.region),
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
class SetInstanceProfile(BaseAction):
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
        instances = self.filter_resources(instances, 'State.Name', self.valid_origin_states)
        if not len(instances):
            return
        client = utils.local_session(self.manager.session_factory).client('ec2')
        profile_name = self.data.get('name')
        profile_instances = [i for i in instances if i.get('IamInstanceProfile')]

        if profile_instances:
            associations = {
                a['InstanceId']: (a['AssociationId'], a['IamInstanceProfile']['Arn'])
                for a in client.describe_iam_instance_profile_associations(
                    Filters=[
                        {'Name': 'instance-id',
                         'Values': [i['InstanceId'] for i in profile_instances]},
                        {'Name': 'state', 'Values': ['associating', 'associated']}]
                ).get('IamInstanceProfileAssociations', ())}
        else:
            associations = {}

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

    .. code-block:: yaml

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


class QueryFilter:

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
        if isinstance(self.value, str):
            value = [self.value]

        return {'Name': self.key, 'Values': value}


@filters.register('instance-attribute')
class InstanceAttribute(ValueFilter):
    """EC2 Instance Value Filter on a given instance attribute.

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
    schema_alias = False

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


@resources.register('launch-template-version')
class LaunchTemplate(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        id = 'LaunchTemplateId'
        id_prefix = 'lt-'
        name = 'LaunchTemplateName'
        service = 'ec2'
        date = 'CreateTime'
        enum_spec = (
            'describe_launch_templates', 'LaunchTemplates', None)
        filter_name = 'LaunchTemplateIds'
        filter_type = 'list'
        arn_type = "launch-template"
        cfn_type = "AWS::EC2::LaunchTemplate"

    def augment(self, resources):
        client = utils.local_session(
            self.session_factory).client('ec2')
        template_versions = []
        for r in resources:
            template_versions.extend(
                client.describe_launch_template_versions(
                    LaunchTemplateId=r['LaunchTemplateId']).get(
                        'LaunchTemplateVersions', ()))
        return template_versions

    def get_arns(self, resources):
        arns = []
        for r in resources:
            arns.append(self.generate_arn(f"{r['LaunchTemplateId']}/{r['VersionNumber']}"))
        return arns

    def get_resources(self, rids, cache=True):
        # Launch template versions have a compound primary key
        #
        # Support one of four forms of resource ids:
        #
        #  - array of launch template ids
        #  - array of tuples (launch template id, version id)
        #  - array of dicts (with LaunchTemplateId and VersionNumber)
        #  - array of dicts (with LaunchTemplateId and LatestVersionNumber)
        #
        # If an alias version is given $Latest, $Default, the alias will be
        # preserved as an annotation on the returned object 'c7n:VersionAlias'
        if not rids:
            return []

        t_versions = {}
        if isinstance(rids[0], tuple):
            for tid, tversion in rids:
                t_versions.setdefault(tid, []).append(tversion)
        elif isinstance(rids[0], dict):
            for tinfo in rids:
                t_versions.setdefault(
                    tinfo['LaunchTemplateId'], []).append(
                        tinfo.get('VersionNumber', tinfo.get('LatestVersionNumber')))
        elif isinstance(rids[0], str):
            for tid in rids:
                t_versions[tid] = []

        client = utils.local_session(self.session_factory).client('ec2')

        results = []
        # We may end up fetching duplicates on $Latest and $Version
        for tid, tversions in t_versions.items():
            try:
                ltv = client.describe_launch_template_versions(
                    LaunchTemplateId=tid, Versions=tversions).get(
                        'LaunchTemplateVersions')
            except ClientError as e:
                if e.response['Error']['Code'] == "InvalidLaunchTemplateId.NotFound":
                    continue
                if e.response['Error']['Code'] == "InvalidLaunchTemplateId.VersionNotFound":
                    continue
                raise
            if not tversions:
                tversions = [str(t['VersionNumber']) for t in ltv]
            for tversion, t in zip(tversions, ltv):
                if not tversion.isdigit():
                    t['c7n:VersionAlias'] = tversion
                results.append(t)
        return results

    def get_asg_templates(self, asgs):
        templates = {}
        for a in asgs:
            t = None
            if 'LaunchTemplate' in a:
                t = a['LaunchTemplate']
            elif 'MixedInstancesPolicy' in a:
                t = a['MixedInstancesPolicy'][
                    'LaunchTemplate']['LaunchTemplateSpecification']
            if t is None:
                continue
            templates.setdefault(
                (t['LaunchTemplateId'],
                 t.get('Version', '$Default')), []).append(a['AutoScalingGroupName'])
        return templates


@resources.register('ec2-reserved')
class ReservedInstance(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        name = id = 'ReservedInstancesId'
        id_prefix = ""
        date = 'Start'
        enum_spec = (
            'describe_reserved_instances', 'ReservedInstances', None)
        filter_name = 'ReservedInstancesIds'
        filter_type = 'list'
        arn_type = "reserved-instances"


@resources.register('ec2-host')
class DedicatedHost(query.QueryResourceManager):
    """Custodian resource for managing EC2 Dedicated Hosts.
    """

    class resource_type(query.TypeInfo):
        service = 'ec2'
        name = id = 'HostId'
        id_prefix = 'h-'
        enum_spec = ('describe_hosts', 'Hosts', None)
        arn_type = "dedicated-host"
        filter_name = 'HostIds'
        filter_type = 'list'
        date = 'AllocationTime'
        cfn_type = config_type = 'AWS::EC2::Host'
        permissions_enum = ('ec2:DescribeHosts',)


@resources.register('ec2-spot-fleet-request')
class SpotFleetRequest(query.QueryResourceManager):
    """Custodian resource for managing EC2 Spot Fleet Requests.
    """

    class resource_type(query.TypeInfo):
        service = 'ec2'
        name = id = 'SpotFleetRequestId'
        id_prefix = 'sfr-'
        enum_spec = ('describe_spot_fleet_requests', 'SpotFleetRequestConfigs', None)
        filter_name = 'SpotFleetRequestIds'
        filter_type = 'list'
        date = 'CreateTime'
        arn_type = 'spot-fleet-request'
        config_type = cfn_type = 'AWS::EC2::SpotFleet'
        permissions_enum = ('ec2:DescribeSpotFleetRequests',)


SpotFleetRequest.filter_registry.register('offhour', OffHour)
SpotFleetRequest.filter_registry.register('onhour', OnHour)


@SpotFleetRequest.action_registry.register('resize')
class AutoscalingSpotFleetRequest(AutoscalingBase):
    permissions = (
        'ec2:CreateTags',
        'ec2:ModifySpotFleetRequest',
    )

    service_namespace = 'ec2'
    scalable_dimension = 'ec2:spot-fleet-request:TargetCapacity'

    def get_resource_id(self, resource):
        return 'spot-fleet-request/%s' % resource['SpotFleetRequestId']

    def get_resource_tag(self, resource, key):
        if 'Tags' in resource:
            for tag in resource['Tags']:
                if tag['Key'] == key:
                    return tag['Value']
        return None

    def get_resource_desired(self, resource):
        return int(resource['SpotFleetRequestConfig']['TargetCapacity'])

    def set_resource_desired(self, resource, desired):
        client = utils.local_session(self.manager.session_factory).client('ec2')
        client.modify_spot_fleet_request(
            SpotFleetRequestId=resource['SpotFleetRequestId'],
            TargetCapacity=desired,
        )


@EC2.filter_registry.register('has-specific-managed-policy')
class HasSpecificManagedPolicy(SpecificIamProfileManagedPolicy):
    """Filter an EC2 instance that has an IAM instance profile that contains an IAM role that has
       a specific managed IAM policy. If an EC2 instance does not have a profile or the profile
       does not contain an IAM role, then it will be treated as not having the policy.

    :example:

    .. code-block:: yaml

        policies:
          - name: ec2-instance-has-admin-policy
            resource: aws.ec2
            filters:
              - type: has-specific-managed-policy
                value: admin-policy

    :example:

    Check for EC2 instances with instance profile roles that have an
    attached policy matching a given list:

    .. code-block:: yaml

        policies:
          - name: ec2-instance-with-selected-policies
            resource: aws.ec2
            filters:
              - type: has-specific-managed-policy
                op: in
                value:
                  - AmazonS3FullAccess
                  - AWSOrganizationsFullAccess

    :example:

    Check for EC2 instances with instance profile roles that have
    attached policy names matching a pattern:

    .. code-block:: yaml

        policies:
          - name: ec2-instance-with-full-access-policies
            resource: aws.ec2
            filters:
              - type: has-specific-managed-policy
                op: glob
                value: "*FullAccess"

    Check for EC2 instances with instance profile roles that have
    attached policy ARNs matching a pattern:

    .. code-block:: yaml

        policies:
          - name: ec2-instance-with-aws-full-access-policies
            resource: aws.ec2
            filters:
              - type: has-specific-managed-policy
                key: PolicyArn
                op: regex
                value: "arn:aws:iam::aws:policy/.*FullAccess"
    """

    permissions = (
        'iam:GetInstanceProfile',
        'iam:ListInstanceProfiles',
        'iam:ListAttachedRolePolicies')

    def process(self, resources, event=None):
        client = utils.local_session(self.manager.session_factory).client('iam')
        iam_profiles = self.manager.get_resource_manager('iam-profile').resources()
        iam_profiles_mapping = {profile['Arn']: profile for profile in iam_profiles}

        results = []
        for r in resources:
            if r['State']['Name'] == 'terminated':
                continue
            instance_profile_arn = r.get('IamInstanceProfile', {}).get('Arn')
            if not instance_profile_arn:
                continue

            profile = iam_profiles_mapping.get(instance_profile_arn)
            if not profile:
                continue

            self.get_managed_policies(client, [profile])

            matched_keys = [k for k in profile[self.annotation_key] if self.match(k)]
            self.merge_annotation(profile, self.matched_annotation_key, matched_keys)
            if matched_keys:
                results.append(r)

        return results


@resources.register('ec2-capacity-reservation')
class CapacityReservation(query.QueryResourceManager):
    """Custodian resource for managing EC2 Capacity Reservation.
    """

    class resource_type(query.TypeInfo):
        name = id = 'CapacityReservationId'
        service = 'ec2'
        enum_spec = ('describe_capacity_reservations',
                     'CapacityReservations', None)

        id_prefix = 'cr-'
        arn = "CapacityReservationArn"
        filter_name = 'CapacityReservationIds'
        filter_type = 'list'
        cfn_type = 'AWS::EC2::CapacityReservation'
        permissions_enum = ('ec2:DescribeCapacityReservations',)
