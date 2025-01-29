# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import itertools
import zlib
import re
from c7n.actions import BaseAction, ModifyVpcSecurityGroupsAction
from c7n.deprecated import DeprecatedField
from c7n.exceptions import PolicyValidationError, ClientError
from c7n.filters import Filter, ValueFilter, MetricsFilter, ListItemFilter
import c7n.filters.vpc as net_filters
from c7n.filters.iamaccess import CrossAccountAccessFilter
from c7n.filters.related import RelatedResourceFilter, RelatedResourceByIdFilter
from c7n.filters.revisions import Diff
from c7n import query, resolver
from c7n.manager import resources
from c7n.resources.securityhub import OtherResourcePostFinding, PostFinding
from c7n.utils import (
    chunks,
    get_eni_resource_type,
    get_retry,
    jmespath_compile,
    jmespath_search,
    local_session,
    merge_dict,
    parse_cidr,
    type_schema,
)
from c7n.resources.aws import shape_validate
from c7n.resources.shield import IsEIPShieldProtected, SetEIPShieldProtection
from c7n.filters.policystatement import HasStatementFilter


@resources.register('vpc')
class Vpc(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'vpc'
        enum_spec = ('describe_vpcs', 'Vpcs', None)
        name = id = 'VpcId'
        filter_name = 'VpcIds'
        filter_type = 'list'
        cfn_type = config_type = 'AWS::EC2::VPC'
        id_prefix = "vpc-"


@Vpc.filter_registry.register('metrics')
class VpcMetrics(MetricsFilter):

    def get_dimensions(self, resource):
        return [{"Name": "Per-VPC Metrics",
                 "Value": resource["VpcId"]}]


@Vpc.action_registry.register('modify')
class ModifyVpc(BaseAction):
    """Modify vpc settings
    """

    schema = type_schema(
        'modify',
        **{'dnshostnames': {'type': 'boolean'},
           'dnssupport': {'type': 'boolean'},
           'addressusage': {'type': 'boolean'}}
    )

    key_params = (
        ('dnshostnames', 'EnableDnsHostnames'),
        ('dnssupport', 'EnableDnsSupport'),
        ('addressusage', 'EnableNetworkAddressUsageMetrics')
    )

    permissions = ('ec2:ModifyVpcAttribute',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')

        for policy_key, param_name in self.key_params:
            if policy_key not in self.data:
                continue
            params = {param_name: {'Value': self.data[policy_key]}}
            # can only modify one attribute per request
            for r in resources:
                params['VpcId'] = r['VpcId']
                client.modify_vpc_attribute(**params)


@Vpc.action_registry.register('delete-empty')
class DeleteVpc(BaseAction):
    """Delete an empty VPC

    For example, if you want to delete an empty VPC

    :example:

      .. code-block:: yaml

        - name: aws-ec2-vpc-delete
          resource: vpc
          actions:
            - type: delete-empty

    """
    schema = type_schema('delete-empty',)
    permissions = ('ec2:DeleteVpc',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')

        for vpc in resources:
            self.manager.retry(
                client.delete_vpc,
                VpcId=vpc['VpcId'],
                ignore_err_codes=(
                    'NoSuchEntityException',
                    'DeleteConflictException',
                ),
            )


class DescribeFlow(query.DescribeSource):

    def get_resources(self, ids, cache=True):
        params = {'Filters': [{'Name': 'flow-log-id', 'Values': ids}]}
        return self.query.filter(self.resource_manager, **params)


@resources.register('flow-log')
class FlowLog(query.QueryResourceManager):

    class resource_type(query.TypeInfo):

        service = 'ec2'
        arn_type = 'vpc-flow-log'
        enum_spec = ('describe_flow_logs', 'FlowLogs', None)
        name = id = 'FlowLogId'
        cfn_type = config_type = 'AWS::EC2::FlowLog'
        id_prefix = 'fl-'

    source_mapping = {
        'describe': DescribeFlow,
        'config': query.ConfigSource
    }


@Vpc.filter_registry.register('flow-logs')
class FlowLogv2Filter(ListItemFilter):
    """Are flow logs enabled on the resource.

    This filter reuses `list-item` filter for arbitrary filtering
    on the flow log attibutes, it also  maintains compatiblity
    with the legacy flow-log filter.

    ie to find all vpcs with flows logs disabled we can do this

    :example:

    .. code-block:: yaml

            policies:
              - name: flow-logs-enabled
                resource: vpc
                filters:
                  - flow-logs

    or to find all vpcs with flow logs but that don't match a
    particular configuration.

    :example:

    .. code-block:: yaml

            policies:
              - name: flow-mis-configured
                resource: vpc
                filters:
                  - not:
                    - type: flow-logs
                      attrs:
                        - TrafficType: ALL
                        - FlowLogStatus: ACTIVE
                        - LogGroupName: vpc-logs
    """

    legacy_schema = {
        'enabled': {'type': 'boolean', 'default': False},
        'op': {'enum': ['equal', 'not-equal'], 'default': 'equal'},
        'set-op': {'enum': ['or', 'and'], 'default': 'or'},
        'status': {'enum': ['active']},
        'deliver-status': {'enum': ['success', 'failure']},
        'destination': {'type': 'string'},
        'destination-type': {'enum': ['s3', 'cloud-watch-logs']},
        'traffic-type': {'enum': ['accept', 'reject', 'all']},
        'log-format': {'type': 'string'},
        'log-group': {'type': 'string'}
    }

    schema = type_schema(
        'flow-logs',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'},
        count={'type': 'number'},
        count_op={'$ref': '#/definitions/filters_common/comparison_operators'},
        **legacy_schema
    )
    schema_alias = True
    annotate_items = True
    permissions = ('ec2:DescribeFlowLogs',)

    compat_conversion = {
        'status': {
            'key': 'FlowLogStatus',
            'values': {'active': 'ACTIVE'},
        },
        'deliver-status': {
            'key': 'DeliverLogsStatus',
            'values': {'success': 'SUCCESS',
                       'failure': 'FAILED'}
        },
        'destination': {
            'key': 'LogDestination',
        },
        'destination-type': {
            'key': 'LogDestinationType',
            # values ?
        },
        'traffic-type': {
            'key': 'TrafficType',
            'values': {'all': 'ALL',
                       'reject': 'REJECT',
                       'accept': 'ACCEPT'},
        },
        'log-format': {
            'key': 'LogFormat',
        },
        'log-group': {
            'key': 'LogGroupName'
        }
    }

    flow_log_map = None

    def get_deprecations(self):
        filter_name = self.data["type"]
        return [
            DeprecatedField(f"{filter_name}.{k}", "use list-item style attrs and set operators")
            for k in set(self.legacy_schema).intersection(self.data)
        ]

    def validate(self):
        keys = set(self.data)
        if 'attrs' in keys and keys.intersection(self.compat_conversion):
            raise PolicyValidationError(
                "flow-log filter doesn't allow combining legacy keys with list-item attrs")
        return super().validate()

    def convert(self):
        self.source_data = {}
        # no mixing of legacy and list-item style
        if 'attrs' in self.data:
            return
        data = {}
        if self.data.get('enabled', False):
            data['count_op'] = 'gte'
            data['count'] = 1
        else:
            data['count'] = 0
        attrs = []
        for k in self.compat_conversion:
            if k not in self.data:
                continue
            afilter = {}
            cinfo = self.compat_conversion[k]
            ak = cinfo['key']
            av = self.data[k]
            if 'values' in cinfo:
                av = cinfo['values'][av]
            if 'op' in self.data and self.data['op'] == 'not-equal':
                av = {'value': av, 'op': 'not-equal'}
            afilter[ak] = av
            attrs.append(afilter)
        if attrs:
            data['attrs'] = attrs
        data['type'] = self.type
        self.source_data = self.data
        self.data = data

    def get_item_values(self, resource):
        flogs = self.flow_log_map.get(resource[self.manager.resource_type.id], ())
        # compatibility with v1 filter, we also add list-item annotation
        # for matched flow logs
        resource['c7n:flow-logs'] = flogs

        # set operators are a little odd, but for list-item do require
        # some runtime modification to ensure compatiblity.
        if self.source_data.get('set-op', 'or') == 'and':
            self.data['count'] = len(flogs)
        return flogs

    def process(self, resources, event=None):
        self.convert()
        self.flow_log_map = {}
        for r in self.manager.get_resource_manager('flow-log').resources():
            self.flow_log_map.setdefault(r['ResourceId'], []).append(r)
        return super().process(resources, event)


@Vpc.filter_registry.register('security-group')
class VpcSecurityGroupFilter(RelatedResourceFilter):
    """Filter VPCs based on Security Group attributes

    :example:

    .. code-block:: yaml

            policies:
              - name: vpc-by-sg
                resource: vpc
                filters:
                  - type: security-group
                    key: tag:Color
                    value: Gray
    """
    schema = type_schema(
        'security-group', rinherit=ValueFilter.schema,
        **{'match-resource': {'type': 'boolean'},
           'operator': {'enum': ['and', 'or']}})
    RelatedResource = "c7n.resources.vpc.SecurityGroup"
    RelatedIdsExpression = '[SecurityGroups][].GroupId'
    AnnotationKey = "matched-vpcs"

    def get_related_ids(self, resources):
        vpc_ids = [vpc['VpcId'] for vpc in resources]
        vpc_group_ids = {
            g['GroupId'] for g in
            self.manager.get_resource_manager('security-group').resources()
            if g.get('VpcId', '') in vpc_ids
        }
        return vpc_group_ids


@Vpc.filter_registry.register('subnet')
class VpcSubnetFilter(RelatedResourceFilter):
    """Filter VPCs based on Subnet attributes

    :example:

    .. code-block:: yaml

            policies:
              - name: vpc-by-subnet
                resource: vpc
                filters:
                  - type: subnet
                    key: tag:Color
                    value: Gray
    """
    schema = type_schema(
        'subnet', rinherit=ValueFilter.schema,
        **{'match-resource': {'type': 'boolean'},
           'operator': {'enum': ['and', 'or']}})
    RelatedResource = "c7n.resources.vpc.Subnet"
    RelatedIdsExpression = '[Subnets][].SubnetId'
    AnnotationKey = "MatchedVpcsSubnets"

    def get_related_ids(self, resources):
        vpc_ids = [vpc['VpcId'] for vpc in resources]
        vpc_subnet_ids = {
            g['SubnetId'] for g in
            self.manager.get_resource_manager('subnet').resources()
            if g.get('VpcId', '') in vpc_ids
        }
        return vpc_subnet_ids


@Vpc.filter_registry.register('nat-gateway')
class VpcNatGatewayFilter(RelatedResourceFilter):
    """Filter VPCs based on NAT Gateway attributes

    :example:

    .. code-block:: yaml

            policies:
              - name: vpc-by-nat
                resource: vpc
                filters:
                  - type: nat-gateway
                    key: tag:Color
                    value: Gray
    """
    schema = type_schema(
        'nat-gateway', rinherit=ValueFilter.schema,
        **{'match-resource': {'type': 'boolean'},
           'operator': {'enum': ['and', 'or']}})
    RelatedResource = "c7n.resources.vpc.NATGateway"
    RelatedIdsExpression = '[NatGateways][].NatGatewayId'
    AnnotationKey = "MatchedVpcsNatGateways"

    def get_related_ids(self, resources):
        vpc_ids = [vpc['VpcId'] for vpc in resources]
        vpc_natgw_ids = {
            g['NatGatewayId'] for g in
            self.manager.get_resource_manager('nat-gateway').resources()
            if g.get('VpcId', '') in vpc_ids
        }
        return vpc_natgw_ids


@Vpc.filter_registry.register('internet-gateway')
class VpcInternetGatewayFilter(RelatedResourceFilter):
    """Filter VPCs based on Internet Gateway attributes

    :example:

    .. code-block:: yaml

            policies:
              - name: vpc-by-igw
                resource: vpc
                filters:
                  - type: internet-gateway
                    key: tag:Color
                    value: Gray
    """
    schema = type_schema(
        'internet-gateway', rinherit=ValueFilter.schema,
        **{'match-resource': {'type': 'boolean'},
           'operator': {'enum': ['and', 'or']}})
    RelatedResource = "c7n.resources.vpc.InternetGateway"
    RelatedIdsExpression = '[InternetGateways][].InternetGatewayId'
    AnnotationKey = "MatchedVpcsIgws"

    def get_related_ids(self, resources):
        vpc_ids = [vpc['VpcId'] for vpc in resources]
        vpc_igw_ids = set()
        for igw in self.manager.get_resource_manager('internet-gateway').resources():
            for attachment in igw['Attachments']:
                if attachment.get('VpcId', '') in vpc_ids:
                    vpc_igw_ids.add(igw['InternetGatewayId'])
        return vpc_igw_ids


@Vpc.filter_registry.register('vpc-attributes')
class AttributesFilter(Filter):
    """Filters VPCs based on their DNS attributes

    :example:

    .. code-block:: yaml

            policies:
              - name: dns-hostname-enabled
                resource: vpc
                filters:
                  - type: vpc-attributes
                    dnshostnames: True
    """
    schema = type_schema(
        'vpc-attributes',
        dnshostnames={'type': 'boolean'},
        addressusage={'type': 'boolean'},
        dnssupport={'type': 'boolean'})

    permissions = ('ec2:DescribeVpcAttribute',)

    key_params = (
        ('dnshostnames', 'enableDnsHostnames'),
        ('dnssupport', 'enableDnsSupport'),
        ('addressusage', 'enableNetworkAddressUsageMetrics')
    )
    annotation_key = 'c7n:attributes'

    def process(self, resources, event=None):
        results = []
        client = local_session(self.manager.session_factory).client('ec2')

        for r in resources:
            found = True
            for policy_key, vpc_attr in self.key_params:
                if policy_key not in self.data:
                    continue
                policy_value = self.data[policy_key]
                response_attr = "%s%s" % (vpc_attr[0].upper(), vpc_attr[1:])
                value = client.describe_vpc_attribute(
                    VpcId=r['VpcId'],
                    Attribute=vpc_attr
                )
                value = value[response_attr]['Value']
                r.setdefault(self.annotation_key, {})[policy_key] = value
                if policy_value != value:
                    found = False
                    break
            if found:
                results.append(r)
        return results


@Vpc.filter_registry.register('dhcp-options')
class DhcpOptionsFilter(Filter):
    """Filter VPCs based on their dhcp options

     :example:

     .. code-block:: yaml

          policies:
             - name: vpcs-in-domain
               resource: vpc
               filters:
                 - type: dhcp-options
                   domain-name: ec2.internal

    if an option value is specified as a list, then all elements must be present.
    if an option value is specified as a string, then that string must be present.

    vpcs not matching a given option value can be found via specifying
    a `present: false` parameter.

    """

    option_keys = ('domain-name', 'domain-name-servers', 'ntp-servers')
    schema = type_schema('dhcp-options', **{
        k: {'oneOf': [
            {'type': 'array', 'items': {'type': 'string'}},
            {'type': 'string'}]}
        for k in option_keys})
    schema['properties']['present'] = {'type': 'boolean'}
    permissions = ('ec2:DescribeDhcpOptions',)

    def validate(self):
        if not any([self.data.get(k) for k in self.option_keys]):
            raise PolicyValidationError("one of %s required" % (self.option_keys,))
        return self

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ec2')
        option_ids = [r['DhcpOptionsId'] for r in resources]
        options_map = {}
        results = []
        for options in client.describe_dhcp_options(
                Filters=[{
                    'Name': 'dhcp-options-id',
                    'Values': option_ids}]).get('DhcpOptions', ()):
            options_map[options['DhcpOptionsId']] = {
                o['Key']: [v['Value'] for v in o['Values']]
                for o in options['DhcpConfigurations']}

        for vpc in resources:
            if self.process_vpc(vpc, options_map[vpc['DhcpOptionsId']]):
                results.append(vpc)
        return results

    def process_vpc(self, vpc, dhcp):
        vpc['c7n:DhcpConfiguration'] = dhcp
        found = True
        for k in self.option_keys:
            if k not in self.data:
                continue
            is_list = isinstance(self.data[k], list)
            if k not in dhcp:
                found = False
            elif not is_list and self.data[k] not in dhcp[k]:
                found = False
            elif is_list and sorted(self.data[k]) != sorted(dhcp[k]):
                found = False
        if not self.data.get('present', True):
            found = not found
        return found


@Vpc.action_registry.register('post-finding')
class VpcPostFinding(PostFinding):

    resource_type = "AwsEc2Vpc"

    def format_resource(self, r):
        envelope, payload = self.format_envelope(r)
        # more inane sechub formatting deltas
        detail = {
            'DhcpOptionsId': r.get('DhcpOptionsId'),
            'State': r['State']}

        for assoc in r.get('CidrBlockAssociationSet', ()):
            detail.setdefault('CidrBlockAssociationSet', []).append(dict(
                AssociationId=assoc['AssociationId'],
                CidrBlock=assoc['CidrBlock'],
                CidrBlockState=assoc['CidrBlockState']['State']))

        for assoc in r.get('Ipv6CidrBlockAssociationSet', ()):
            detail.setdefault('Ipv6CidrBlockAssociationSet', []).append(dict(
                AssociationId=assoc['AssociationId'],
                Ipv6CidrBlock=assoc['Ipv6CidrBlock'],
                CidrBlockState=assoc['Ipv6CidrBlockState']['State']))
        payload.update(self.filter_empty(detail))
        return envelope


class DescribeSubnets(query.DescribeSource):

    def get_resources(self, resource_ids):
        while resource_ids:
            try:
                return super().get_resources(resource_ids)
            except ClientError as e:
                if e.response['Error']['Code'] != 'InvalidSubnetID.NotFound':
                    raise
                sid = extract_subnet_id(e)
                if sid:
                    resource_ids.remove(sid)
                else:
                    return []


RE_ERROR_SUBNET_ID = re.compile("'(?P<subnet_id>subnet-.*?)'")


def extract_subnet_id(state_error):
    "Extract an subnet id from an error"
    subnet_id = None
    match = RE_ERROR_SUBNET_ID.search(str(state_error))
    if match:
        subnet_id = match.groupdict().get('subnet_id')
    return subnet_id


@resources.register('subnet')
class Subnet(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'subnet'
        enum_spec = ('describe_subnets', 'Subnets', None)
        name = id = 'SubnetId'
        filter_name = 'SubnetIds'
        filter_type = 'list'
        cfn_type = config_type = 'AWS::EC2::Subnet'
        id_prefix = "subnet-"

    source_mapping = {
        'describe': DescribeSubnets,
        'config': query.ConfigSource}


Subnet.filter_registry.register('flow-logs', FlowLogv2Filter)


@Subnet.filter_registry.register('vpc')
class SubnetVpcFilter(net_filters.VpcFilter):

    RelatedIdsExpression = "VpcId"


@Subnet.filter_registry.register('ip-address-usage')
class SubnetIpAddressUsageFilter(ValueFilter):
    """Filter subnets based on available IP addresses.

    :example:

    Show subnets with no addresses in use.

    .. code-block:: yaml

            policies:
              - name: empty-subnets
                resource: aws.subnet
                filters:
                  - type: ip-address-usage
                    key: NumberUsed
                    value: 0

    :example:

    Show subnets where 90% or more addresses are in use.

    .. code-block:: yaml

            policies:
              - name: almost-full-subnets
                resource: aws.subnet
                filters:
                  - type: ip-address-usage
                    key: PercentUsed
                    op: greater-than
                    value: 90

    This filter allows ``key`` to be:

    * ``MaxAvailable``: the number of addresses available based on a subnet's CIDR block size
      (minus the 5 addresses
      `reserved by AWS <https://docs.aws.amazon.com/vpc/latest/userguide/subnet-sizing.html>`_)
    * ``NumberUsed``: ``MaxAvailable`` minus the subnet's ``AvailableIpAddressCount`` value
    * ``PercentUsed``: ``NumberUsed`` divided by ``MaxAvailable``
    """
    annotation_key = 'c7n:IpAddressUsage'
    aws_reserved_addresses = 5
    schema_alias = False
    schema = type_schema(
        'ip-address-usage',
        key={'enum': ['MaxAvailable', 'NumberUsed', 'PercentUsed']},
        rinherit=ValueFilter.schema,
    )

    def augment(self, resource):
        cidr_block = parse_cidr(resource['CidrBlock'])
        max_addresses = cidr_block.num_addresses - self.aws_reserved_addresses
        resource[self.annotation_key] = dict(
            MaxAvailable=max_addresses,
            NumberUsed=max_addresses - resource['AvailableIpAddressCount'],
            PercentUsed=round(
                (max_addresses - resource['AvailableIpAddressCount']) / max_addresses * 100.0,
                2
            ),
        )

    def process(self, resources, event=None):
        results = []
        for r in resources:
            if self.annotation_key not in r:
                self.augment(r)
            if self.match(r[self.annotation_key]):
                results.append(r)
        return results


class ConfigSG(query.ConfigSource):

    def load_resource(self, item):
        r = super(ConfigSG, self).load_resource(item)
        for rset in ('IpPermissions', 'IpPermissionsEgress'):
            for p in r.get(rset, ()):
                if p.get('FromPort', '') is None:
                    p.pop('FromPort')
                if p.get('ToPort', '') is None:
                    p.pop('ToPort')
                if 'Ipv6Ranges' not in p:
                    p[u'Ipv6Ranges'] = []
                for i in p.get('UserIdGroupPairs', ()):
                    for k, v in list(i.items()):
                        if v is None:
                            i.pop(k)
                # legacy config form, still version 1.2
                for attribute, element_key in (('IpRanges', u'CidrIp'),):
                    if attribute not in p:
                        continue
                    p[attribute] = [{element_key: v} for v in p[attribute]]
                if 'Ipv4Ranges' in p:
                    p['IpRanges'] = p.pop('Ipv4Ranges')
        return r


@resources.register('security-group')
class SecurityGroup(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'security-group'
        enum_spec = ('describe_security_groups', 'SecurityGroups', None)
        id = 'GroupId'
        name = 'GroupName'
        filter_name = "GroupIds"
        filter_type = 'list'
        cfn_type = config_type = "AWS::EC2::SecurityGroup"
        id_prefix = "sg-"

    source_mapping = {
        'config': ConfigSG,
        'describe': query.DescribeSource
    }


@SecurityGroup.filter_registry.register('diff')
class SecurityGroupDiffFilter(Diff):

    def diff(self, source, target):
        differ = SecurityGroupDiff()
        return differ.diff(source, target)


class SecurityGroupDiff:
    """Diff two versions of a security group

    Immutable: GroupId, GroupName, Description, VpcId, OwnerId
    Mutable: Tags, Rules
    """

    def diff(self, source, target):
        delta = {}
        tag_delta = self.get_tag_delta(source, target)
        if tag_delta:
            delta['tags'] = tag_delta
        ingress_delta = self.get_rule_delta('IpPermissions', source, target)
        if ingress_delta:
            delta['ingress'] = ingress_delta
        egress_delta = self.get_rule_delta(
            'IpPermissionsEgress', source, target)
        if egress_delta:
            delta['egress'] = egress_delta
        if delta:
            return delta

    def get_tag_delta(self, source, target):
        source_tags = {t['Key']: t['Value'] for t in source.get('Tags', ())}
        target_tags = {t['Key']: t['Value'] for t in target.get('Tags', ())}
        target_keys = set(target_tags.keys())
        source_keys = set(source_tags.keys())
        removed = source_keys.difference(target_keys)
        added = target_keys.difference(source_keys)
        changed = set()
        for k in target_keys.intersection(source_keys):
            if source_tags[k] != target_tags[k]:
                changed.add(k)
        return {k: v for k, v in {
            'added': {k: target_tags[k] for k in added},
            'removed': {k: source_tags[k] for k in removed},
            'updated': {k: target_tags[k] for k in changed}}.items() if v}

    def get_rule_delta(self, key, source, target):
        source_rules = {
            self.compute_rule_hash(r): r for r in source.get(key, ())}
        target_rules = {
            self.compute_rule_hash(r): r for r in target.get(key, ())}
        source_keys = set(source_rules.keys())
        target_keys = set(target_rules.keys())
        removed = source_keys.difference(target_keys)
        added = target_keys.difference(source_keys)
        return {k: v for k, v in
                {'removed': [source_rules[rid] for rid in sorted(removed)],
                 'added': [target_rules[rid] for rid in sorted(added)]}.items() if v}

    RULE_ATTRS = (
        ('PrefixListIds', 'PrefixListId'),
        ('UserIdGroupPairs', 'GroupId'),
        ('IpRanges', 'CidrIp'),
        ('Ipv6Ranges', 'CidrIpv6')
    )

    def compute_rule_hash(self, rule):
        buf = "%d-%d-%s-" % (
            rule.get('FromPort', 0) or 0,
            rule.get('ToPort', 0) or 0,
            rule.get('IpProtocol', '-1') or '-1'
        )
        for a, ke in self.RULE_ATTRS:
            if a not in rule:
                continue
            ev = [e[ke] for e in rule[a]]
            ev.sort()
            for e in ev:
                buf += "%s-" % e
        # mask to generate the same numeric value across all Python versions
        return zlib.crc32(buf.encode('ascii')) & 0xffffffff


@SecurityGroup.action_registry.register('patch')
class SecurityGroupApplyPatch(BaseAction):
    """Modify a resource via application of a reverse delta.
    """
    schema = type_schema('patch')

    permissions = ('ec2:AuthorizeSecurityGroupIngress',
                   'ec2:AuthorizeSecurityGroupEgress',
                   'ec2:RevokeSecurityGroupIngress',
                   'ec2:RevokeSecurityGroupEgress',
                   'ec2:CreateTags',
                   'ec2:DeleteTags')

    def validate(self):
        diff_filters = [n for n in self.manager.iter_filters() if isinstance(
            n, SecurityGroupDiffFilter)]
        if not len(diff_filters):
            raise PolicyValidationError(
                "resource patching requires diff filter")
        return self

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        differ = SecurityGroupDiff()
        patcher = SecurityGroupPatch()
        for r in resources:
            # reverse the patch by computing fresh, the forward
            # patch is for notifications
            d = differ.diff(r, r['c7n:previous-revision']['resource'])
            patcher.apply_delta(client, r, d)


class SecurityGroupPatch:

    RULE_TYPE_MAP = {
        'egress': ('IpPermissionsEgress',
                   'revoke_security_group_egress',
                   'authorize_security_group_egress'),
        'ingress': ('IpPermissions',
                    'revoke_security_group_ingress',
                    'authorize_security_group_ingress')}

    retry = staticmethod(get_retry((
        'RequestLimitExceeded', 'Client.RequestLimitExceeded')))

    def apply_delta(self, client, target, change_set):
        if 'tags' in change_set:
            self.process_tags(client, target, change_set['tags'])
        if 'ingress' in change_set:
            self.process_rules(
                client, 'ingress', target, change_set['ingress'])
        if 'egress' in change_set:
            self.process_rules(
                client, 'egress', target, change_set['egress'])

    def process_tags(self, client, group, tag_delta):
        if 'removed' in tag_delta:
            self.retry(client.delete_tags,
                       Resources=[group['GroupId']],
                       Tags=[{'Key': k}
                             for k in tag_delta['removed']])
        tags = []
        if 'added' in tag_delta:
            tags.extend(
                [{'Key': k, 'Value': v}
                 for k, v in tag_delta['added'].items()])
        if 'updated' in tag_delta:
            tags.extend(
                [{'Key': k, 'Value': v}
                 for k, v in tag_delta['updated'].items()])
        if tags:
            self.retry(
                client.create_tags, Resources=[group['GroupId']], Tags=tags)

    def process_rules(self, client, rule_type, group, delta):
        _, revoke_op, auth_op = self.RULE_TYPE_MAP[rule_type]
        revoke, authorize = getattr(
            client, revoke_op), getattr(client, auth_op)

        # Process removes
        if 'removed' in delta:
            self.retry(revoke, GroupId=group['GroupId'],
                       IpPermissions=[r for r in delta['removed']])

        # Process adds
        if 'added' in delta:
            self.retry(authorize, GroupId=group['GroupId'],
                       IpPermissions=[r for r in delta['added']])


class SGUsage(Filter):

    nics = ()

    def get_permissions(self):
        return list(itertools.chain(
            *[self.manager.get_resource_manager(m).get_permissions()
             for m in
             ['lambda', 'eni', 'launch-config', 'security-group', 'event-rule-target',
              'aws.batch-compute']]))

    def filter_peered_refs(self, resources):
        if not resources:
            return resources
        # Check that groups are not referenced across accounts
        client = local_session(self.manager.session_factory).client('ec2')
        peered_ids = set()
        for resource_set in chunks(resources, 200):
            for sg_ref in client.describe_security_group_references(
                    GroupId=[r['GroupId'] for r in resource_set]
            )['SecurityGroupReferenceSet']:
                peered_ids.add(sg_ref['GroupId'])
        self.log.debug(
            "%d of %d groups w/ peered refs", len(peered_ids), len(resources))
        return [r for r in resources if r['GroupId'] not in peered_ids]

    def get_scanners(self):
        return (
            ("nics", self.get_eni_sgs),
            ("sg-perm-refs", self.get_sg_refs),
            ('lambdas', self.get_lambda_sgs),
            ("launch-configs", self.get_launch_config_sgs),
            ("ecs-cwe", self.get_ecs_cwe_sgs),
            ("codebuild", self.get_codebuild_sgs),
            ("batch", self.get_batch_sgs),
        )

    def scan_groups(self):
        used = set()
        for kind, scanner in self.get_scanners():
            sg_ids = scanner()
            new_refs = sg_ids.difference(used)
            used = used.union(sg_ids)
            self.log.debug(
                "%s using %d sgs, new refs %s total %s",
                kind, len(sg_ids), len(new_refs), len(used))

        return used

    def get_launch_config_sgs(self):
        # Note assuming we also have launch config garbage collection
        # enabled.
        sg_ids = set()
        for cfg in self.manager.get_resource_manager('launch-config').resources():
            for g in cfg['SecurityGroups']:
                sg_ids.add(g)
            for g in cfg['ClassicLinkVPCSecurityGroups']:
                sg_ids.add(g)
        return sg_ids

    def get_lambda_sgs(self):
        sg_ids = set()
        for func in self.manager.get_resource_manager('lambda').resources(augment=False):
            if 'VpcConfig' not in func:
                continue
            for g in func['VpcConfig']['SecurityGroupIds']:
                sg_ids.add(g)
        return sg_ids

    def get_eni_sgs(self):
        sg_ids = set()
        self.nics = self.manager.get_resource_manager('eni').resources()
        for nic in self.nics:
            for g in nic['Groups']:
                sg_ids.add(g['GroupId'])
        return sg_ids

    def get_codebuild_sgs(self):
        sg_ids = set()
        for cb in self.manager.get_resource_manager('codebuild').resources():
            sg_ids |= set(cb.get('vpcConfig', {}).get('securityGroupIds', []))
        return sg_ids

    def get_sg_refs(self):
        sg_ids = set()
        for sg in self.manager.get_resource_manager('security-group').resources():
            for perm_type in ('IpPermissions', 'IpPermissionsEgress'):
                for p in sg.get(perm_type, []):
                    for g in p.get('UserIdGroupPairs', ()):
                        # self references aren't usage.
                        if g['GroupId'] != sg['GroupId']:
                            sg_ids.add(g['GroupId'])
        return sg_ids

    def get_ecs_cwe_sgs(self):
        sg_ids = set()
        expr = jmespath_compile(
            'EcsParameters.NetworkConfiguration.awsvpcConfiguration.SecurityGroups[]')
        for rule in self.manager.get_resource_manager(
                'event-rule-target').resources(augment=False):
            ids = expr.search(rule)
            if ids:
                sg_ids.update(ids)
        return sg_ids

    def get_batch_sgs(self):
        expr = jmespath_compile('[].computeResources.securityGroupIds[]')
        resources = self.manager.get_resource_manager('aws.batch-compute').resources(augment=False)
        return set(expr.search(resources) or [])


@SecurityGroup.filter_registry.register('unused')
class UnusedSecurityGroup(SGUsage):
    """Filter to just vpc security groups that are not used.

    We scan all extant enis in the vpc to get a baseline set of groups
    in use. Then augment with those referenced by launch configs, and
    lambdas as they may not have extant resources in the vpc at a
    given moment. We also find any security group with references from
    other security group either within the vpc or across peered
    connections. Also checks cloud watch event targeting ecs.

    Checks - enis, lambda, launch-configs, sg rule refs, and ecs cwe
    targets.

    Note this filter does not support classic security groups atm.

    :example:

    .. code-block:: yaml

            policies:
              - name: security-groups-unused
                resource: security-group
                filters:
                  - unused

    """
    schema = type_schema('unused')

    def process(self, resources, event=None):
        used = self.scan_groups()
        unused = [
            r for r in resources
            if r['GroupId'] not in used and 'VpcId' in r]
        return unused and self.filter_peered_refs(unused) or []


@SecurityGroup.filter_registry.register('used')
class UsedSecurityGroup(SGUsage):
    """Filter to security groups that are used.
    This operates as a complement to the unused filter for multi-step
    workflows.

    :example:

    .. code-block:: yaml

            policies:
              - name: security-groups-in-use
                resource: security-group
                filters:
                  - used

            policies:
              - name: security-groups-used-by-rds
                resource: security-group
                filters:
                  - used
                  - type: value
                    key: c7n:InstanceOwnerIds
                    op: intersect
                    value:
                      - amazon-rds

            policies:
              - name: security-groups-used-by-natgw
                resource: security-group
                filters:
                  - used
                  - type: value
                    key: c7n:InterfaceTypes
                    op: intersect
                    value:
                      - nat_gateway

            policies:
              - name: security-groups-used-by-alb
                resource: security-group
                filters:
                  - used
                  - type: value
                    key: c7n:InterfaceResourceTypes
                    op: intersect
                    value:
                      - elb-app
    """
    schema = type_schema('used')

    instance_owner_id_key = 'c7n:InstanceOwnerIds'
    interface_type_key = 'c7n:InterfaceTypes'
    interface_resource_type_key = 'c7n:InterfaceResourceTypes'

    def _get_eni_attributes(self):
        group_enis = {}
        for nic in self.nics:
            instance_owner_id, interface_resource_type = '', ''
            if nic['Status'] == 'in-use':
                if nic.get('Attachment') and 'InstanceOwnerId' in nic['Attachment']:
                    instance_owner_id = nic['Attachment']['InstanceOwnerId']
                interface_resource_type = get_eni_resource_type(nic)
            interface_type = nic.get('InterfaceType')
            for g in nic['Groups']:
                group_enis.setdefault(g['GroupId'], []).append({
                    'InstanceOwnerId': instance_owner_id,
                    'InterfaceType': interface_type,
                    'InterfaceResourceType': interface_resource_type
                })
        return group_enis

    def process(self, resources, event=None):
        used = self.scan_groups()
        unused = [
            r for r in resources
            if r['GroupId'] not in used and 'VpcId' in r]
        unused = {g['GroupId'] for g in self.filter_peered_refs(unused)}
        group_enis = self._get_eni_attributes()
        for r in resources:
            enis = group_enis.get(r['GroupId'], ())
            r[self.instance_owner_id_key] = list({
                i['InstanceOwnerId'] for i in enis if i['InstanceOwnerId']})
            r[self.interface_type_key] = list({
                i['InterfaceType'] for i in enis if i['InterfaceType']})
            r[self.interface_resource_type_key] = list({
                i['InterfaceResourceType'] for i in enis if i['InterfaceResourceType']})
        return [r for r in resources if r['GroupId'] not in unused]


@SecurityGroup.filter_registry.register('stale')
class Stale(Filter):
    """Filter to find security groups that contain stale references
    to other groups that are either no longer present or traverse
    a broken vpc peering connection. Note this applies to VPC
    Security groups only and will implicitly filter security groups.

    AWS Docs:
      https://docs.aws.amazon.com/vpc/latest/peering/vpc-peering-security-groups.html

    :example:

    .. code-block:: yaml

            policies:
              - name: stale-security-groups
                resource: security-group
                filters:
                  - stale
    """
    schema = type_schema('stale')
    permissions = ('ec2:DescribeStaleSecurityGroups',)

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ec2')
        vpc_ids = {r['VpcId'] for r in resources if 'VpcId' in r}
        group_map = {r['GroupId']: r for r in resources}
        results = []
        self.log.debug("Querying %d vpc for stale refs", len(vpc_ids))
        stale_count = 0
        for vpc_id in vpc_ids:
            stale_groups = client.describe_stale_security_groups(
                VpcId=vpc_id).get('StaleSecurityGroupSet', ())

            stale_count += len(stale_groups)
            for s in stale_groups:
                if s['GroupId'] in group_map:
                    r = group_map[s['GroupId']]
                    if 'StaleIpPermissions' in s:
                        r['MatchedIpPermissions'] = s['StaleIpPermissions']
                    if 'StaleIpPermissionsEgress' in s:
                        r['MatchedIpPermissionsEgress'] = s[
                            'StaleIpPermissionsEgress']
                    results.append(r)
        self.log.debug("Found %d stale security groups", stale_count)
        return results


@SecurityGroup.filter_registry.register('default-vpc')
class SGDefaultVpc(net_filters.DefaultVpcBase):
    """Filter that returns any security group that exists within the default vpc

    :example:

    .. code-block:: yaml

            policies:
              - name: security-group-default-vpc
                resource: security-group
                filters:
                  - default-vpc
    """

    schema = type_schema('default-vpc')

    def __call__(self, resource, event=None):
        if 'VpcId' not in resource:
            return False
        return self.match(resource['VpcId'])


class SGPermission(Filter):
    """Filter for verifying security group ingress and egress permissions

    All attributes of a security group permission are available as
    value filters.

    If multiple attributes are specified the permission must satisfy
    all of them. Note that within an attribute match against a list value
    of a permission we default to or.

    If a group has any permissions that match all conditions, then it
    matches the filter.

    Permissions that match on the group are annotated onto the group and
    can subsequently be used by the remove-permission action.

    We have specialized handling for matching `Ports` in ingress/egress
    permission From/To range. The following example matches on ingress
    rules which allow for a range that includes all of the given ports.

    .. code-block:: yaml

      - type: ingress
        Ports: [22, 443, 80]

    As well for verifying that a rule only allows for a specific set of ports
    as in the following example. The delta between this and the previous
    example is that if the permission allows for any ports not specified here,
    then the rule will match. ie. OnlyPorts is a negative assertion match,
    it matches when a permission includes ports outside of the specified set.

    .. code-block:: yaml

      - type: ingress
        OnlyPorts: [22]

    For simplifying ipranges handling which is specified as a list on a rule
    we provide a `Cidr` key which can be used as a value type filter evaluated
    against each of the rules. If any iprange cidr match then the permission
    matches.

    .. code-block:: yaml

      - type: ingress
        IpProtocol: -1
        FromPort: 445

    We also have specialized handling for matching self-references in
    ingress/egress permissions. The following example matches on ingress
    rules which allow traffic its own same security group.

    .. code-block:: yaml

      - type: ingress
        SelfReference: True

    As well for assertions that a ingress/egress permission only matches
    a given set of ports, *note* OnlyPorts is an inverse match.

    .. code-block:: yaml

      - type: egress
        OnlyPorts: [22, 443, 80]

      - type: egress
        Cidr:
          value_type: cidr
          op: in
          value: x.y.z

    `value_type: cidr` can also filter if cidr is a subset of cidr
    value range. In this example we are allowing any smaller cidrs within
    allowed_cidrs.csv.

    .. code-block:: yaml

      - type: ingress
        Cidr:
          value_type: cidr
          op: not-in
          value_from:
            url: s3://a-policy-data-us-west-2/allowed_cidrs.csv
            format: csv

    or value can be specified as a list.

    .. code-block:: yaml

      - type: ingress
        Cidr:
          value_type: cidr
          op: not-in
          value: ["10.0.0.0/8", "192.168.0.0/16"]

    `Cidr` can match ipv4 rules and `CidrV6` can match ipv6 rules.  In
    this example we are blocking global inbound connections to SSH or
    RDP.

    .. code-block:: yaml

      - or:
        - type: ingress
          Ports: [22, 3389]
          Cidr:
            value: "0.0.0.0/0"
        - type: ingress
          Ports: [22, 3389]
          CidrV6:
            value: "::/0"

    `SGReferences` can be used to filter out SG references in rules.
    In this example we want to block ingress rules that reference a SG
    that is tagged with `Access: Public`.

    .. code-block:: yaml

      - type: ingress
        SGReferences:
          key: "tag:Access"
          value: "Public"
          op: equal

    We can also filter SG references based on the VPC that they are
    within. In this example we want to ensure that our outbound rules
    that reference SGs are only referencing security groups within a
    specified VPC.

    .. code-block:: yaml

      - type: egress
        SGReferences:
          key: 'VpcId'
          value: 'vpc-11a1a1aa'
          op: equal

    Likewise, we can also filter SG references by their description.
    For example, we can prevent egress rules from referencing any
    SGs that have a description of "default - DO NOT USE".

    .. code-block:: yaml

      - type: egress
        SGReferences:
          key: 'Description'
          value: 'default - DO NOT USE'
          op: equal

    By default, this filter matches a security group rule if
    _all_ of its keys match. Using `match-operator: or` causes a match
    if _any_ key matches. This can help consolidate some simple
    cases that would otherwise require multiple filters. To find
    security groups that allow all inbound traffic over IPv4 or IPv6,
    for example, we can use two filters inside an `or` block:

    .. code-block:: yaml

      - or:
        - type: ingress
          Cidr: "0.0.0.0/0"
        - type: ingress
          CidrV6: "::/0"

    or combine them into a single filter:

    .. code-block:: yaml

      - type: ingress
        match-operator: or
          Cidr: "0.0.0.0/0"
          CidrV6: "::/0"

    Note that evaluating _combinations_ of factors (e.g. traffic over
    port 22 from 0.0.0.0/0) still requires separate filters.
    """

    perm_attrs = {
        'IpProtocol', 'FromPort', 'ToPort', 'UserIdGroupPairs',
        'IpRanges', 'PrefixListIds'}
    filter_attrs = {
        'Cidr', 'CidrV6', 'Ports', 'OnlyPorts',
        'SelfReference', 'Description', 'SGReferences'}
    attrs = perm_attrs.union(filter_attrs)
    attrs.add('match-operator')
    attrs.add('match-operator')

    def validate(self):
        delta = set(self.data.keys()).difference(self.attrs)
        delta.remove('type')
        if delta:
            raise PolicyValidationError("Unknown keys %s on %s" % (
                ", ".join(delta), self.manager.data))
        return self

    def process(self, resources, event=None):
        self.vfilters = []
        fattrs = list(sorted(self.perm_attrs.intersection(self.data.keys())))
        self.ports = 'Ports' in self.data and self.data['Ports'] or ()
        self.only_ports = (
            'OnlyPorts' in self.data and self.data['OnlyPorts'] or ())
        for f in fattrs:
            fv = self.data.get(f)
            if isinstance(fv, dict):
                fv['key'] = f
            else:
                fv = {f: fv}
            vf = ValueFilter(fv, self.manager)
            vf.annotate = False
            self.vfilters.append(vf)
        return super(SGPermission, self).process(resources, event)

    def process_ports(self, perm):
        found = None
        if 'FromPort' in perm and 'ToPort' in perm:
            for port in self.ports:
                if port >= perm['FromPort'] and port <= perm['ToPort']:
                    found = True
                    break
                found = False
            only_found = False
            for port in self.only_ports:
                if port == perm['FromPort'] and port == perm['ToPort']:
                    only_found = True
            if self.only_ports and not only_found:
                found = found is None or found and True or False
            if self.only_ports and only_found:
                found = False
        return found

    def _process_cidr(self, cidr_key, cidr_type, range_type, perm):

        found = None
        ip_perms = perm.get(range_type, [])
        if not ip_perms:
            return False

        match_range = self.data[cidr_key]

        if isinstance(match_range, dict):
            match_range['key'] = cidr_type
        else:
            match_range = {cidr_type: match_range}

        vf = ValueFilter(match_range, self.manager)
        vf.annotate = False

        for ip_range in ip_perms:
            found = vf(ip_range)
            if found:
                break
            else:
                found = False
        return found

    def process_cidrs(self, perm):
        found_v6 = found_v4 = None
        if 'CidrV6' in self.data:
            found_v6 = self._process_cidr('CidrV6', 'CidrIpv6', 'Ipv6Ranges', perm)
        if 'Cidr' in self.data:
            found_v4 = self._process_cidr('Cidr', 'CidrIp', 'IpRanges', perm)
        match_op = self.data.get('match-operator', 'and') == 'and' and all or any
        cidr_match = [k for k in (found_v6, found_v4) if k is not None]
        if not cidr_match:
            return None
        return match_op(cidr_match)

    def process_description(self, perm):
        if 'Description' not in self.data:
            return None

        d = dict(self.data['Description'])
        d['key'] = 'Description'

        vf = ValueFilter(d, self.manager)
        vf.annotate = False

        for k in ('Ipv6Ranges', 'IpRanges', 'UserIdGroupPairs', 'PrefixListIds'):
            if k not in perm or not perm[k]:
                continue
            return vf(perm[k][0])
        return False

    def process_self_reference(self, perm, sg_id):
        found = None
        ref_match = self.data.get('SelfReference')
        if ref_match is not None:
            found = False
        if 'UserIdGroupPairs' in perm and 'SelfReference' in self.data:
            self_reference = sg_id in [p['GroupId']
                                       for p in perm['UserIdGroupPairs']]
            if ref_match is False and not self_reference:
                found = True
            if ref_match is True and self_reference:
                found = True
        return found

    def process_sg_references(self, perm, owner_id):
        sg_refs = self.data.get('SGReferences')
        if not sg_refs:
            return None

        sg_perm = perm.get('UserIdGroupPairs', [])
        if not sg_perm:
            return False

        sg_group_ids = [p['GroupId'] for p in sg_perm if p.get('UserId', '') == owner_id]
        sg_resources = self.manager.get_resources(sg_group_ids)
        vf = ValueFilter(sg_refs, self.manager)
        vf.annotate = False

        for sg in sg_resources:
            if vf(sg):
                return True
        return False

    def expand_permissions(self, permissions):
        """Expand each list of cidr, prefix list, user id group pair
        by port/protocol as an individual rule.

        The console ux automatically expands them out as addition/removal is
        per this expansion, the describe calls automatically group them.
        """
        for p in permissions:
            np = dict(p)
            values = {}
            for k in (u'IpRanges',
                      u'Ipv6Ranges',
                      u'PrefixListIds',
                      u'UserIdGroupPairs'):
                values[k] = np.pop(k, ())
                np[k] = []
            for k, v in values.items():
                if not v:
                    continue
                for e in v:
                    ep = dict(np)
                    ep[k] = [e]
                    yield ep

    def __call__(self, resource):
        matched = []
        sg_id = resource['GroupId']
        owner_id = resource['OwnerId']
        match_op = self.data.get('match-operator', 'and') == 'and' and all or any
        for perm in self.expand_permissions(resource[self.ip_permissions_key]):
            perm_matches = {}
            for idx, f in enumerate(self.vfilters):
                perm_matches[idx] = bool(f(perm))
            perm_matches['description'] = self.process_description(perm)
            perm_matches['ports'] = self.process_ports(perm)
            perm_matches['cidrs'] = self.process_cidrs(perm)
            perm_matches['self-refs'] = self.process_self_reference(perm, sg_id)
            perm_matches['sg-refs'] = self.process_sg_references(perm, owner_id)
            perm_match_values = list(filter(
                lambda x: x is not None, perm_matches.values()))

            # account for one python behavior any([]) == False, all([]) == True
            if match_op == all and not perm_match_values:
                continue

            match = match_op(perm_match_values)
            if match:
                matched.append(perm)

        if matched:
            matched_annotation = resource.setdefault('Matched%s' % self.ip_permissions_key, [])
            # If the same rule matches multiple filters, only add it to the match annotation
            # once. Note: Because we're looking for unique dicts and those aren't hashable,
            # we can't conveniently use set() to de-duplicate rules.
            matched_annotation.extend(m for m in matched if m not in matched_annotation)
            return True


SGPermissionSchema = {
    'match-operator': {'type': 'string', 'enum': ['or', 'and']},
    'Ports': {'type': 'array', 'items': {'type': 'integer'}},
    'SelfReference': {'type': 'boolean'},
    'OnlyPorts': {'type': 'array', 'items': {'type': 'integer'}},
    'IpProtocol': {
        'oneOf': [
            {'enum': ["-1", -1, 'tcp', 'udp', 'icmp', 'icmpv6']},
            {'$ref': '#/definitions/filters/value'}
        ]
    },
    'FromPort': {'oneOf': [
        {'$ref': '#/definitions/filters/value'},
        {'type': 'integer'}]},
    'ToPort': {'oneOf': [
        {'$ref': '#/definitions/filters/value'},
        {'type': 'integer'}]},
    'UserIdGroupPairs': {},
    'IpRanges': {},
    'PrefixListIds': {},
    'Description': {},
    'Cidr': {},
    'CidrV6': {},
    'SGReferences': {}
}


@SecurityGroup.filter_registry.register('ingress')
class IPPermission(SGPermission):

    ip_permissions_key = "IpPermissions"
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {'type': {'enum': ['ingress']}},
        'required': ['type']}
    schema['properties'].update(SGPermissionSchema)


@SecurityGroup.filter_registry.register('egress')
class IPPermissionEgress(SGPermission):

    ip_permissions_key = "IpPermissionsEgress"
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {'type': {'enum': ['egress']}},
        'required': ['type']}
    schema['properties'].update(SGPermissionSchema)


@SecurityGroup.action_registry.register('delete')
class Delete(BaseAction):
    """Action to delete security group(s)

    It is recommended to apply a filter to the delete policy to avoid the
    deletion of all security groups returned.

    :example:

    .. code-block:: yaml

            policies:
              - name: security-groups-unused-delete
                resource: security-group
                filters:
                  - type: unused
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('ec2:DeleteSecurityGroup',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            client.delete_security_group(GroupId=r['GroupId'])


@SecurityGroup.action_registry.register('remove-permissions')
class RemovePermissions(BaseAction):
    """Action to remove ingress/egress rule(s) from a security group

    :example:

    .. code-block:: yaml

            policies:
              - name: security-group-revoke-8080
                resource: security-group
                filters:
                  - type: ingress
                    IpProtocol: tcp
                    Ports: [8080]
                actions:
                  - type: remove-permissions
                    ingress: matched

    """
    schema = type_schema(
        'remove-permissions',
        ingress={'type': 'string', 'enum': ['matched', 'all']},
        egress={'type': 'string', 'enum': ['matched', 'all']})

    permissions = ('ec2:RevokeSecurityGroupIngress',
                   'ec2:RevokeSecurityGroupEgress')

    def process(self, resources):
        i_perms = self.data.get('ingress', 'matched')
        e_perms = self.data.get('egress', 'matched')

        client = local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            for label, perms in [('ingress', i_perms), ('egress', e_perms)]:
                if perms == 'matched':
                    key = 'MatchedIpPermissions%s' % (
                        label == 'egress' and 'Egress' or '')
                    groups = r.get(key, ())
                elif perms == 'all':
                    key = 'IpPermissions%s' % (
                        label == 'egress' and 'Egress' or '')
                    groups = r.get(key, ())
                elif isinstance(perms, list):
                    groups = perms
                else:
                    continue
                if not groups:
                    continue
                method = getattr(client, 'revoke_security_group_%s' % label)
                method(GroupId=r['GroupId'], IpPermissions=groups)


@SecurityGroup.action_registry.register('set-permissions')
class SetPermissions(BaseAction):
    """Action to add/remove ingress/egress rule(s) to a security group

    :example:

    .. code-block:: yaml

       policies:
         - name: ops-access-via
           resource: aws.security-group
           filters:
             - type: ingress
               IpProtocol: "-1"
               Ports: [22, 3389]
               Cidr: "0.0.0.0/0"
           actions:
            - type: set-permissions
              # remove the permission matched by a previous ingress filter.
              remove-ingress: matched
              # remove permissions by specifying them fully, ie remove default outbound
              # access.
              remove-egress:
                 - IpProtocol: "-1"
                   Cidr: "0.0.0.0/0"

              # add a list of permissions to the group.
              add-ingress:
                # full syntax/parameters to authorize can be used.
                - IpPermissions:
                   - IpProtocol: TCP
                     FromPort: 22
                     ToPort: 22
                     IpRanges:
                       - Description: Ops SSH Access
                         CidrIp: "1.1.1.1/32"
                       - Description: Security SSH Access
                         CidrIp: "2.2.2.2/32"
              # add a list of egress permissions to a security group
              add-egress:
                 - IpProtocol: "TCP"
                   FromPort: 5044
                   ToPort: 5044
                   CidrIp: "192.168.1.2/32"

    """
    schema = type_schema(
        'set-permissions',
        **{'add-ingress': {'type': 'array', 'items': {'type': 'object', 'minProperties': 1}},
           'remove-ingress': {'oneOf': [
               {'enum': ['all', 'matched']},
               {'type': 'array', 'items': {'type': 'object', 'minProperties': 2}}]},
           'add-egress': {'type': 'array', 'items': {'type': 'object', 'minProperties': 1}},
           'remove-egress': {'oneOf': [
               {'enum': ['all', 'matched']},
               {'type': 'array', 'items': {'type': 'object', 'minProperties': 2}}]}}
    )
    permissions = (
        'ec2:AuthorizeSecurityGroupEgress',
        'ec2:AuthorizeSecurityGroupIngress',)

    ingress_shape = "AuthorizeSecurityGroupIngressRequest"
    egress_shape = "AuthorizeSecurityGroupEgressRequest"

    def validate(self):
        request_template = {'GroupId': 'sg-06bc5ce18a2e5d57a'}
        for perm_type, shape in (
                ('egress', self.egress_shape), ('ingress', self.ingress_shape)):
            for perm in self.data.get('add-%s' % type, ()):
                params = dict(request_template)
                params.update(perm)
                shape_validate(params, shape, 'ec2')

    def get_permissions(self):
        perms = ()
        if 'add-ingress' in self.data:
            perms += ('ec2:AuthorizeSecurityGroupIngress',)
        if 'add-egress' in self.data:
            perms += ('ec2:AuthorizeSecurityGroupEgress',)
        if 'remove-ingress' in self.data or 'remove-egress' in self.data:
            perms += RemovePermissions.permissions
        if not perms:
            perms = self.permissions + RemovePermissions.permissions
        return perms

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            for method, permissions in (
                    (client.authorize_security_group_egress, self.data.get('add-egress', ())),
                    (client.authorize_security_group_ingress, self.data.get('add-ingress', ()))):
                for p in permissions:
                    p = dict(p)
                    p['GroupId'] = r['GroupId']
                    try:
                        method(**p)
                    except ClientError as e:
                        if e.response['Error']['Code'] != 'InvalidPermission.Duplicate':
                            raise

        remover = RemovePermissions(
            {'ingress': self.data.get('remove-ingress', ()),
             'egress': self.data.get('remove-egress', ())}, self.manager)
        remover.process(resources)


@SecurityGroup.action_registry.register('post-finding')
class SecurityGroupPostFinding(OtherResourcePostFinding):

    def format_resource(self, r):
        fr = super(SecurityGroupPostFinding, self).format_resource(r)
        fr['Type'] = 'AwsEc2SecurityGroup'
        return fr


class DescribeENI(query.DescribeSource):

    def augment(self, resources):
        for r in resources:
            r['Tags'] = r.pop('TagSet', [])
        return resources


@resources.register('eni')
class NetworkInterface(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'network-interface'
        enum_spec = ('describe_network_interfaces', 'NetworkInterfaces', None)
        name = id = 'NetworkInterfaceId'
        filter_name = 'NetworkInterfaceIds'
        filter_type = 'list'
        cfn_type = config_type = "AWS::EC2::NetworkInterface"
        id_prefix = "eni-"

    source_mapping = {
        'describe': DescribeENI,
        'config': query.ConfigSource
    }


NetworkInterface.filter_registry.register('flow-logs', FlowLogv2Filter)
NetworkInterface.filter_registry.register(
    'network-location', net_filters.NetworkLocation)


@NetworkInterface.filter_registry.register('subnet')
class InterfaceSubnetFilter(net_filters.SubnetFilter):
    """Network interface subnet filter

    :example:

    .. code-block:: yaml

            policies:
              - name: network-interface-in-subnet
                resource: eni
                filters:
                  - type: subnet
                    key: CidrBlock
                    value: 10.0.2.0/24
    """

    RelatedIdsExpression = "SubnetId"


@NetworkInterface.filter_registry.register('security-group')
class InterfaceSecurityGroupFilter(net_filters.SecurityGroupFilter):
    """Network interface security group filter

    :example:

    .. code-block:: yaml

            policies:
              - name: network-interface-ssh
                resource: eni
                filters:
                  - type: security-group
                    match-resource: true
                    key: FromPort
                    value: 22
    """

    RelatedIdsExpression = "Groups[].GroupId"


@NetworkInterface.filter_registry.register('vpc')
class InterfaceVpcFilter(net_filters.VpcFilter):

    RelatedIdsExpression = "VpcId"


@NetworkInterface.action_registry.register('modify-security-groups')
class InterfaceModifyVpcSecurityGroups(ModifyVpcSecurityGroupsAction):
    """Remove security groups from an interface.

    Can target either physical groups as a list of group ids or
    symbolic groups like 'matched' or 'all'. 'matched' uses
    the annotations of the 'group' interface filter.

    Note an interface always gets at least one security group, so
    we also allow specification of an isolation/quarantine group
    that can be specified if there would otherwise be no groups.


    :example:

    .. code-block:: yaml

            policies:
              - name: network-interface-remove-group
                resource: eni
                filters:
                  - type: security-group
                    match-resource: true
                    key: FromPort
                    value: 22
                actions:
                  - type: modify-security-groups
                    isolation-group: sg-01ab23c4
                    add: []
    """
    permissions = ('ec2:ModifyNetworkInterfaceAttribute',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        groups = super(
            InterfaceModifyVpcSecurityGroups, self).get_groups(resources)
        for idx, r in enumerate(resources):
            client.modify_network_interface_attribute(
                NetworkInterfaceId=r['NetworkInterfaceId'],
                Groups=groups[idx])


@NetworkInterface.action_registry.register('delete')
class DeleteNetworkInterface(BaseAction):
    """Delete a network interface.

    :example:

    .. code-block:: yaml

        policies:
          - name: mark-orphaned-enis
            comment: Flag abandoned Lambda VPC ENIs for deletion
            resource: eni
            filters:
              - Status: available
              - type: value
                op: glob
                key: Description
                value: "AWS Lambda VPC ENI*"
              - "tag:custodian_status": absent
            actions:
              - type: mark-for-op
                tag: custodian_status
                msg: "Orphaned Lambda VPC ENI: {op}@{action_date}"
                op: delete
                days: 1

          - name: delete-marked-enis
            comment: Delete flagged ENIs that have not been cleaned up naturally
            resource: eni
            filters:
              - type: marked-for-op
                tag: custodian_status
                op: delete
            actions:
              - type: delete
    """
    permissions = ('ec2:DeleteNetworkInterface',)
    schema = type_schema('delete')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            try:
                self.manager.retry(
                    client.delete_network_interface,
                    NetworkInterfaceId=r['NetworkInterfaceId'])
            except ClientError as err:
                if not err.response['Error']['Code'] == 'InvalidNetworkInterfaceID.NotFound':
                    raise


@NetworkInterface.action_registry.register('detach')
class DetachNetworkInterface(BaseAction):
    """Detach a network interface from an EC2 instance.

    :example:

    .. code-block:: yaml

        policies:
          - name: detach-enis
            comment: Detach ENIs attached to EC2 with public IP addresses
            resource: eni
            filters:
              - type: value
                key: Attachment.InstanceId
                value: present
              - type: value
                key: Association.PublicIp
                value: present
            actions:
              - type: detach
    """
    permissions = ('ec2:DetachNetworkInterface',)
    schema = type_schema('detach')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        att_resources = [ar for ar in resources if ('Attachment' in ar
            and ar['Attachment'].get('InstanceId')
            and ar['Attachment'].get('DeviceIndex') != 0)]
        if att_resources and (len(att_resources) < len(resources)):
            self.log.warning(
                "Filtered {} of {} non-primary network interfaces attatched to EC2".format(
                len(att_resources), len(resources))
            )
        elif not att_resources:
            self.log.warning("No non-primary EC2 interfaces indentified - revise c7n filters")
        for r in att_resources:
            client.detach_network_interface(AttachmentId=r['Attachment']['AttachmentId'])


@resources.register('route-table')
class RouteTable(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'route-table'
        enum_spec = ('describe_route_tables', 'RouteTables', None)
        name = id = 'RouteTableId'
        filter_name = 'RouteTableIds'
        filter_type = 'list'
        id_prefix = "rtb-"
        cfn_type = config_type = "AWS::EC2::RouteTable"


@RouteTable.filter_registry.register('vpc')
class RouteTableVpcFilter(net_filters.VpcFilter):

    RelatedIdsExpression = "VpcId"


@RouteTable.filter_registry.register('subnet')
class SubnetRoute(net_filters.SubnetFilter):
    """Filter a route table by its associated subnet attributes."""

    RelatedIdsExpression = "Associations[].SubnetId"

    RelatedMapping = None

    def get_related_ids(self, resources):
        if self.RelatedIdMapping is None:
            return super(SubnetRoute, self).get_related_ids(resources)
        return list(itertools.chain(*[self.RelatedIdMapping[r['RouteTableId']] for r in resources]))

    def get_related(self, resources):
        rt_subnet_map = {}
        main_tables = {}

        manager = self.get_resource_manager()
        for r in resources:
            rt_subnet_map[r['RouteTableId']] = []
            for a in r.get('Associations', ()):
                if 'SubnetId' in a:
                    rt_subnet_map[r['RouteTableId']].append(a['SubnetId'])
                elif a.get('Main'):
                    main_tables[r['VpcId']] = r['RouteTableId']
        explicit_subnet_ids = set(itertools.chain(*rt_subnet_map.values()))
        subnets = manager.resources()
        for s in subnets:
            if s['SubnetId'] in explicit_subnet_ids:
                continue
            if s['VpcId'] not in main_tables:
                continue
            rt_subnet_map.setdefault(main_tables[s['VpcId']], []).append(s['SubnetId'])
        related_subnets = set(itertools.chain(*rt_subnet_map.values()))
        self.RelatedIdMapping = rt_subnet_map
        return {s['SubnetId']: s for s in subnets if s['SubnetId'] in related_subnets}


@RouteTable.filter_registry.register('route')
class Route(ValueFilter):
    """Filter a route table by its routes' attributes."""

    schema = type_schema('route', rinherit=ValueFilter.schema)
    schema_alias = False

    def process(self, resources, event=None):
        results = []
        for r in resources:
            matched = []
            for route in r['Routes']:
                if self.match(route):
                    matched.append(route)
            if matched:
                r.setdefault('c7n:matched-routes', []).extend(matched)
                results.append(r)
        return results


@resources.register('transit-gateway')
class TransitGateway(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        enum_spec = ('describe_transit_gateways', 'TransitGateways', None)
        name = id = 'TransitGatewayId'
        arn = "TransitGatewayArn"
        id_prefix = "tgw-"
        filter_name = 'TransitGatewayIds'
        filter_type = 'list'
        config_type = cfn_type = 'AWS::EC2::TransitGateway'


TransitGateway.filter_registry.register('flow-logs', FlowLogv2Filter)


class TransitGatewayAttachmentQuery(query.ChildResourceQuery):

    def get_parent_parameters(self, params, parent_id, parent_key):
        merged_params = dict(params)
        merged_params.setdefault('Filters', []).append(
            {'Name': parent_key, 'Values': [parent_id]})
        return merged_params


@query.sources.register('transit-attachment')
class TransitAttachmentSource(query.ChildDescribeSource):

    resource_query_factory = TransitGatewayAttachmentQuery


@resources.register('transit-attachment')
class TransitGatewayAttachment(query.ChildResourceManager):

    child_source = 'transit-attachment'

    class resource_type(query.TypeInfo):
        service = 'ec2'
        enum_spec = ('describe_transit_gateway_attachments', 'TransitGatewayAttachments', None)
        parent_spec = ('transit-gateway', 'transit-gateway-id', None)
        id_prefix = 'tgw-attach-'
        name = id = 'TransitGatewayAttachmentId'
        metrics_namespace = 'AWS/TransitGateway'
        arn = False
        cfn_type = 'AWS::EC2::TransitGatewayAttachment'
        supports_trailevents = True


@TransitGatewayAttachment.filter_registry.register('metrics')
class TransitGatewayAttachmentMetricsFilter(MetricsFilter):

    def get_dimensions(self, resource):
        return [
            {'Name': 'TransitGateway', 'Value': resource['TransitGatewayId']},
            {'Name': 'TransitGatewayAttachment', 'Value': resource['TransitGatewayAttachmentId']}
        ]


@resources.register('peering-connection')
class PeeringConnection(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'vpc-peering-connection'
        enum_spec = ('describe_vpc_peering_connections',
                     'VpcPeeringConnections', None)
        name = id = 'VpcPeeringConnectionId'
        filter_name = 'VpcPeeringConnectionIds'
        filter_type = 'list'
        id_prefix = "pcx-"
        cfn_type = config_type = "AWS::EC2::VPCPeeringConnection"


@PeeringConnection.filter_registry.register('cross-account')
class CrossAccountPeer(CrossAccountAccessFilter):

    schema = type_schema(
        'cross-account',
        # white list accounts
        whitelist_from=resolver.ValuesFrom.schema,
        whitelist={'type': 'array', 'items': {'type': 'string'}})

    permissions = ('ec2:DescribeVpcPeeringConnections',)

    def process(self, resources, event=None):
        results = []
        accounts = self.get_accounts()
        owners = map(jmespath_compile, (
            'AccepterVpcInfo.OwnerId', 'RequesterVpcInfo.OwnerId'))

        for r in resources:
            for o_expr in owners:
                account_id = o_expr.search(r)
                if account_id and account_id not in accounts:
                    r.setdefault(
                        'c7n:CrossAccountViolations', []).append(account_id)
                    results.append(r)
        return results


@PeeringConnection.filter_registry.register('missing-route')
class MissingRoute(Filter):
    """Return peers which are missing a route in route tables.

    If the peering connection is between two vpcs in the same account,
    the connection is returned unless it is in present route tables in
    each vpc.

    If the peering connection is between accounts, then the local vpc's
    route table is checked.
    """

    schema = type_schema('missing-route')
    permissions = ('ec2:DescribeRouteTables',)

    def process(self, resources, event=None):
        tables = self.manager.get_resource_manager(
            'route-table').resources()
        routed_vpcs = {}
        mid = 'VpcPeeringConnectionId'
        for t in tables:
            for r in t.get('Routes', ()):
                if mid in r:
                    routed_vpcs.setdefault(r[mid], []).append(t['VpcId'])
        results = []
        for r in resources:
            if r[mid] not in routed_vpcs:
                results.append(r)
                continue
            for k in ('AccepterVpcInfo', 'RequesterVpcInfo'):
                if r[k]['OwnerId'] != self.manager.config.account_id:
                    continue
                if r[k].get('Region') and r['k']['Region'] != self.manager.config.region:
                    continue
                if r[k]['VpcId'] not in routed_vpcs[r['VpcPeeringConnectionId']]:
                    results.append(r)
                    break
        return results


@resources.register('network-acl')
class NetworkAcl(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'network-acl'
        enum_spec = ('describe_network_acls', 'NetworkAcls', None)
        name = id = 'NetworkAclId'
        filter_name = 'NetworkAclIds'
        filter_type = 'list'
        cfn_type = config_type = "AWS::EC2::NetworkAcl"
        id_prefix = "acl-"


@NetworkAcl.filter_registry.register('subnet')
class AclSubnetFilter(net_filters.SubnetFilter):
    """Filter network acls by the attributes of their attached subnets.

    :example:

    .. code-block:: yaml

            policies:
              - name: subnet-acl
                resource: network-acl
                filters:
                  - type: subnet
                    key: "tag:Location"
                    value: Public
    """

    RelatedIdsExpression = "Associations[].SubnetId"


@NetworkAcl.filter_registry.register('s3-cidr')
class AclAwsS3Cidrs(Filter):
    """Filter network acls by those that allow access to s3 cidrs.

    Defaults to filtering those nacls that do not allow s3 communication.

    :example:

        Find all nacls that do not allow communication with s3.

    .. code-block:: yaml

            policies:
              - name: s3-not-allowed-nacl
                resource: network-acl
                filters:
                  - s3-cidr
    """
    # TODO allow for port specification as range
    schema = type_schema(
        's3-cidr',
        egress={'type': 'boolean', 'default': True},
        ingress={'type': 'boolean', 'default': True},
        present={'type': 'boolean', 'default': False})

    permissions = ('ec2:DescribePrefixLists',)

    def process(self, resources, event=None):
        ec2 = local_session(self.manager.session_factory).client('ec2')
        cidrs = jmespath_search(
            "PrefixLists[].Cidrs[]", ec2.describe_prefix_lists())
        cidrs = [parse_cidr(cidr) for cidr in cidrs]
        results = []

        check_egress = self.data.get('egress', True)
        check_ingress = self.data.get('ingress', True)
        present = self.data.get('present', False)

        for r in resources:
            matched = {cidr: None for cidr in cidrs}
            for entry in r['Entries']:
                if entry['Egress'] and not check_egress:
                    continue
                if not entry['Egress'] and not check_ingress:
                    continue
                entry_cidr = parse_cidr(entry['CidrBlock'])
                for c in matched:
                    if c in entry_cidr and matched[c] is None:
                        matched[c] = (
                            entry['RuleAction'] == 'allow' and True or False)
            if present and all(matched.values()):
                results.append(r)
            elif not present and not all(matched.values()):
                results.append(r)
        return results


class DescribeElasticIp(query.DescribeSource):

    def augment(self, resources):
        return [r for r in resources if self.manager.resource_type.id in r]


@resources.register('elastic-ip', aliases=('network-addr',))
class NetworkAddress(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'elastic-ip'
        enum_spec = ('describe_addresses', 'Addresses', None)
        name = 'PublicIp'
        id = 'AllocationId'
        id_prefix = 'eipalloc-'
        filter_name = 'AllocationIds'
        filter_type = 'list'
        config_type = cfn_type = "AWS::EC2::EIP"

    source_mapping = {
        'describe': DescribeElasticIp,
        'config': query.ConfigSource
    }


NetworkAddress.filter_registry.register('shield-enabled', IsEIPShieldProtected)
NetworkAddress.action_registry.register('set-shield', SetEIPShieldProtection)


@NetworkAddress.action_registry.register('release')
class AddressRelease(BaseAction):
    """Action to release elastic IP address(es)

    Use the force option to cause any attached elastic IPs to
    also be released.  Otherwise, only unattached elastic IPs
    will be released.

    :example:

    .. code-block:: yaml

            policies:
              - name: release-network-addr
                resource: network-addr
                filters:
                  - AllocationId: ...
                actions:
                  - type: release
                    force: True
    """

    schema = type_schema('release', force={'type': 'boolean'})
    permissions = ('ec2:ReleaseAddress', 'ec2:DisassociateAddress',)

    def process_attached(self, client, associated_addrs):
        for aa in list(associated_addrs):
            try:
                client.disassociate_address(AssociationId=aa['AssociationId'])
            except ClientError as e:
                # If its already been diassociated ignore, else raise.
                if not (e.response['Error']['Code'] == 'InvalidAssocationID.NotFound' and
                       aa['AssocationId'] in e.response['Error']['Message']):
                    raise e
                associated_addrs.remove(aa)
        return associated_addrs

    def process(self, network_addrs):
        client = local_session(self.manager.session_factory).client('ec2')
        force = self.data.get('force')
        assoc_addrs = [addr for addr in network_addrs if 'AssociationId' in addr]
        unassoc_addrs = [addr for addr in network_addrs if 'AssociationId' not in addr]

        if len(assoc_addrs) and not force:
            self.log.warning(
                "Filtered %d attached eips of %d eips. Use 'force: true' to release them.",
                len(assoc_addrs), len(network_addrs))
        elif len(assoc_addrs) and force:
            unassoc_addrs = itertools.chain(
                unassoc_addrs, self.process_attached(client, assoc_addrs))

        for r in unassoc_addrs:
            try:
                client.release_address(AllocationId=r['AllocationId'])
            except ClientError as e:
                # If its already been released, ignore, else raise.
                if e.response['Error']['Code'] == 'InvalidAddress.PtrSet':
                    self.log.warning(
                        "EIP %s cannot be released because it has a PTR record set.",
                        r['AllocationId'])
                if e.response['Error']['Code'] == 'InvalidAddress.Locked':
                    self.log.warning(
                        "EIP %s cannot be released because it is locked to your account.",
                        r['AllocationId'])
                if e.response['Error']['Code'] != 'InvalidAllocationID.NotFound':
                    raise


@NetworkAddress.action_registry.register('disassociate')
class DisassociateAddress(BaseAction):
    """Disassociate elastic IP addresses from resources without releasing them.

    :example:

    .. code-block:: yaml

            policies:
              - name: disassociate-network-addr
                resource: network-addr
                filters:
                  - AllocationId: ...
                actions:
                  - type: disassociate
    """

    schema = type_schema('disassociate')
    permissions = ('ec2:DisassociateAddress',)

    def process(self, network_addrs):
        client = local_session(self.manager.session_factory).client('ec2')
        assoc_addrs = [addr for addr in network_addrs if 'AssociationId' in addr]

        for aa in assoc_addrs:
            try:
                client.disassociate_address(AssociationId=aa['AssociationId'])
            except ClientError as e:
                # If its already been diassociated ignore, else raise.
                if not (e.response['Error']['Code'] == 'InvalidAssocationID.NotFound' and
                       aa['AssocationId'] in e.response['Error']['Message']):
                    raise e


@resources.register('customer-gateway')
class CustomerGateway(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'customer-gateway'
        enum_spec = ('describe_customer_gateways', 'CustomerGateways', None)
        id = 'CustomerGatewayId'
        filter_name = 'CustomerGatewayIds'
        filter_type = 'list'
        name = 'CustomerGatewayId'
        id_prefix = "cgw-"
        cfn_type = config_type = 'AWS::EC2::CustomerGateway'


@resources.register('internet-gateway')
class InternetGateway(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'internet-gateway'
        enum_spec = ('describe_internet_gateways', 'InternetGateways', None)
        name = id = 'InternetGatewayId'
        filter_name = 'InternetGatewayIds'
        filter_type = 'list'
        cfn_type = config_type = "AWS::EC2::InternetGateway"
        id_prefix = "igw-"


@InternetGateway.action_registry.register('delete')
class DeleteInternetGateway(BaseAction):

    """Action to delete Internet Gateway

    :example:

    .. code-block:: yaml

            policies:
              - name: delete-internet-gateway
                resource: internet-gateway
                actions:
                  - type: delete
    """

    schema = type_schema('delete')
    permissions = ('ec2:DeleteInternetGateway',)

    def process(self, resources):

        client = local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            try:
                client.delete_internet_gateway(InternetGatewayId=r['InternetGatewayId'])
            except ClientError as err:
                if err.response['Error']['Code'] == 'DependencyViolation':
                    self.log.warning(
                        "%s error hit deleting internetgateway: %s",
                        err.response['Error']['Code'],
                        err.response['Error']['Message'],
                    )
                elif err.response['Error']['Code'] == 'InvalidInternetGatewayId.NotFound':
                    pass
                else:
                    raise


@resources.register('nat-gateway')
class NATGateway(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'natgateway'
        enum_spec = ('describe_nat_gateways', 'NatGateways', None)
        name = id = 'NatGatewayId'
        filter_name = 'NatGatewayIds'
        filter_type = 'list'
        date = 'CreateTime'
        dimension = 'NatGatewayId'
        metrics_namespace = 'AWS/NATGateway'
        id_prefix = "nat-"
        cfn_type = config_type = 'AWS::EC2::NatGateway'


@NATGateway.action_registry.register('delete')
class DeleteNATGateway(BaseAction):

    schema = type_schema('delete')
    permissions = ('ec2:DeleteNatGateway',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            client.delete_nat_gateway(NatGatewayId=r['NatGatewayId'])


@resources.register('vpn-connection')
class VPNConnection(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'vpn-connection'
        enum_spec = ('describe_vpn_connections', 'VpnConnections', None)
        name = id = 'VpnConnectionId'
        filter_name = 'VpnConnectionIds'
        filter_type = 'list'
        cfn_type = config_type = 'AWS::EC2::VPNConnection'
        id_prefix = "vpn-"


@resources.register('vpn-gateway')
class VPNGateway(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'vpn-gateway'
        enum_spec = ('describe_vpn_gateways', 'VpnGateways', None)
        name = id = 'VpnGatewayId'
        filter_name = 'VpnGatewayIds'
        filter_type = 'list'
        cfn_type = config_type = 'AWS::EC2::VPNGateway'
        id_prefix = "vgw-"


@resources.register('vpc-endpoint')
class VpcEndpoint(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'vpc-endpoint'
        enum_spec = ('describe_vpc_endpoints', 'VpcEndpoints', None)
        name = id = 'VpcEndpointId'
        metrics_namespace = "AWS/PrivateLinkEndpoints"
        date = 'CreationTimestamp'
        filter_name = 'VpcEndpointIds'
        filter_type = 'list'
        id_prefix = "vpce-"
        universal_taggable = object()
        cfn_type = config_type = "AWS::EC2::VPCEndpoint"


@VpcEndpoint.filter_registry.register('metrics')
class VpcEndpointMetricsFilter(MetricsFilter):

    def get_dimensions(self, resource):
        return [
            {'Name': 'Endpoint Type', 'Value': resource['VpcEndpointType']},
            {'Name': 'Service Name', 'Value': resource['ServiceName']},
            {'Name': 'VPC Endpoint Id', 'Value': resource['VpcEndpointId']},
            {'Name': 'VPC Id', 'Value': resource['VpcId']},
        ]


@VpcEndpoint.filter_registry.register('has-statement')
class EndpointPolicyStatementFilter(HasStatementFilter):
    """Find resources with matching endpoint policy statements.

    :example:

    .. code-block:: yaml

        policies:
            - name: vpc-endpoint-policy
              resource: aws.vpc-endpoint
              filters:
                  - type: has-statement
                    statements:
                      - Action: "*"
                        Effect: "Allow"
    """

    policy_attribute = 'PolicyDocument'
    permissions = ('ec2:DescribeVpcEndpoints',)

    def get_std_format_args(self, endpoint):
        return {
            'endpoint_id': endpoint['VpcEndpointId'],
            'account_id': self.manager.config.account_id,
            'region': self.manager.config.region
        }


@VpcEndpoint.filter_registry.register('cross-account')
class EndpointCrossAccountFilter(CrossAccountAccessFilter):

    policy_attribute = 'PolicyDocument'
    annotation_key = 'c7n:CrossAccountViolations'
    permissions = ('ec2:DescribeVpcEndpoints',)


@VpcEndpoint.filter_registry.register('security-group')
class EndpointSecurityGroupFilter(net_filters.SecurityGroupFilter):

    RelatedIdsExpression = "Groups[].GroupId"


@VpcEndpoint.filter_registry.register('subnet')
class EndpointSubnetFilter(net_filters.SubnetFilter):

    RelatedIdsExpression = "SubnetIds[]"


@VpcEndpoint.filter_registry.register('vpc')
class EndpointVpcFilter(net_filters.VpcFilter):

    RelatedIdsExpression = "VpcId"


@Vpc.filter_registry.register("vpc-endpoint")
class VPCEndpointFilter(RelatedResourceByIdFilter):
    """Filters vpcs based on their vpc-endpoints

    :example:

    .. code-block:: yaml

            policies:
              - name: s3-vpc-endpoint-enabled
                resource: vpc
                filters:
                  - type: vpc-endpoint
                    key: ServiceName
                    value: com.amazonaws.us-east-1.s3
    """
    RelatedResource = "c7n.resources.vpc.VpcEndpoint"
    RelatedIdsExpression = "VpcId"
    AnnotationKey = "matched-vpc-endpoint"

    schema = type_schema(
        'vpc-endpoint',
        rinherit=ValueFilter.schema)


@Subnet.filter_registry.register("vpc-endpoint")
class SubnetEndpointFilter(RelatedResourceByIdFilter):
    """Filters subnets based on their vpc-endpoints

    :example:

    .. code-block:: yaml

            policies:
              - name: athena-endpoint-enabled
                resource: subnet
                filters:
                  - type: vpc-endpoint
                    key: ServiceName
                    value: com.amazonaws.us-east-1.athena
    """
    RelatedResource = "c7n.resources.vpc.VpcEndpoint"
    RelatedIdsExpression = "SubnetId"
    RelatedResourceByIdExpression = "SubnetIds"
    AnnotationKey = "matched-vpc-endpoint"

    schema = type_schema(
        'vpc-endpoint',
        rinherit=ValueFilter.schema)


@resources.register('key-pair')
class KeyPair(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'key-pair'
        enum_spec = ('describe_key_pairs', 'KeyPairs', None)
        name = 'KeyName'
        id = 'KeyPairId'
        id_prefix = 'key-'
        filter_name = 'KeyNames'
        filter_type = 'list'


@KeyPair.filter_registry.register('unused')
class UnusedKeyPairs(Filter):
    """Filter for used or unused keys.

    The default is unused but can be changed by using the state property.

    :example:

    .. code-block:: yaml

      policies:
        - name: unused-key-pairs
          resource: aws.key-pair
          filters:
            - unused
        - name: used-key-pairs
          resource: aws.key-pair
          filters:
            - type: unused
              state: false
    """
    schema = type_schema('unused',
        state={'type': 'boolean'})

    def get_permissions(self):
        return list(itertools.chain(*[
            self.manager.get_resource_manager(m).get_permissions()
            for m in ('asg', 'launch-config', 'ec2')]))

    def _pull_asg_keynames(self):
        asgs = self.manager.get_resource_manager('asg').resources()
        key_names = set()
        lcfgs = set(a['LaunchConfigurationName'] for a in asgs if 'LaunchConfigurationName' in a)
        lcfg_mgr = self.manager.get_resource_manager('launch-config')

        if lcfgs:
            key_names.update([
                lcfg['KeyName'] for lcfg in lcfg_mgr.resources()
                if lcfg['LaunchConfigurationName'] in lcfgs])

        tmpl_mgr = self.manager.get_resource_manager('launch-template-version')
        for tversion in tmpl_mgr.get_resources(
                list(tmpl_mgr.get_asg_templates(asgs).keys())):
            key_names.add(tversion['LaunchTemplateData'].get('KeyName'))
        return key_names

    def _pull_ec2_keynames(self):
        ec2_manager = self.manager.get_resource_manager('ec2')
        return {i.get('KeyName', None) for i in ec2_manager.resources()}

    def process(self, resources, event=None):
        keynames = self._pull_ec2_keynames().union(self._pull_asg_keynames())
        if self.data.get('state', True):
            return [r for r in resources if r['KeyName'] not in keynames]
        return [r for r in resources if r['KeyName'] in keynames]


@KeyPair.action_registry.register('delete')
class DeleteUnusedKeyPairs(BaseAction):
    """Delete all ec2 keys that are not in use

    This should always be used with the unused filter
    and it will prevent you from using without it.

    :example:

    .. code-block:: yaml

      policies:
        - name: delete-unused-key-pairs
          resource: aws.key-pair
          filters:
            - unused
          actions:
            - delete
    """
    permissions = ('ec2:DeleteKeyPair',)
    schema = type_schema('delete')

    def validate(self):
        if not [f for f in self.manager.iter_filters() if isinstance(f, UnusedKeyPairs)]:
            raise PolicyValidationError(
                "delete should be used in conjunction with the unused filter on %s" % (
                    self.manager.data,))
        if [True for f in self.manager.iter_filters() if f.data.get('state') is False]:
            raise PolicyValidationError(
                "You policy has filtered used keys you should use this with unused keys %s" % (
                    self.manager.data,))
        return self

    def process(self, unused):
        client = local_session(self.manager.session_factory).client('ec2')
        for key in unused:
            client.delete_key_pair(KeyPairId=key['KeyPairId'])


@Vpc.action_registry.register('set-flow-log')
@Subnet.action_registry.register('set-flow-log')
@NetworkInterface.action_registry.register('set-flow-log')
@TransitGateway.action_registry.register('set-flow-log')
@TransitGatewayAttachment.action_registry.register('set-flow-log')
class SetFlowLogs(BaseAction):
    """Set flow logs for a network resource

    :example:

    .. code-block:: yaml

        policies:
          - name: vpc-enable-flow-logs
            resource: vpc
            filters:
              - type: flow-logs
                enabled: false
            actions:
              - type: set-flow-log
                attrs:
                  DeliverLogsPermissionArn: arn:iam:role
                  LogGroupName: /custodian/vpc/flowlogs/

    `attrs` are passed through to create_flow_log and are per the api
    documentation

    https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/create_flow_logs.html
    """  # noqa

    legacy_schema = {
        'DeliverLogsPermissionArn': {'type': 'string'},
        'LogGroupName': {'type': 'string'},
        'LogDestination': {'type': 'string'},
        'LogFormat': {'type': 'string'},
        'MaxAggregationInterval': {'type': 'integer'},
        'LogDestinationType': {'enum': ['s3', 'cloud-watch-logs']},
        'TrafficType': {
            'type': 'string',
            'enum': ['ACCEPT', 'REJECT', 'ALL']
        }
    }

    schema = type_schema(
        'set-flow-log',
        state={'type': 'boolean'},
        attrs={'type': 'object'},
        **legacy_schema
    )
    shape = 'CreateFlowLogsRequest'
    permissions = ('ec2:CreateFlowLogs', 'logs:CreateLogGroup',)

    RESOURCE_ALIAS = {
        'vpc': 'VPC',
        'subnet': 'Subnet',
        'eni': 'NetworkInterface',
        'transit-gateway': 'TransitGateway',
        'transit-attachment': 'TransitGatewayAttachment'
    }

    def get_deprecations(self):
        filter_name = self.data["type"]
        return [
            DeprecatedField(f"{filter_name}.{k}", f"set {k} under attrs: block")
            for k in set(self.legacy_schema).intersection(self.data)
        ]

    def validate(self):
        if set(self.legacy_schema).intersection(self.data) and 'attrs' in self.data:
            raise PolicyValidationError(
                "set-flow-log: legacy top level keys aren't compatible with `attrs` mapping"
            )

        self.convert()
        attrs = dict(self.data['attrs'])
        model = self.manager.get_model()
        attrs['ResourceType'] = self.RESOURCE_ALIAS[model.arn_type]
        attrs['ResourceIds'] = [model.id_prefix + '123']
        return shape_validate(attrs, self.shape, 'ec2')

    def convert(self):
        data = dict(self.data)
        attrs = {}
        for k in set(self.legacy_schema).intersection(data):
            attrs[k] = data.pop(k)
        self.source_data = self.data
        self.data['attrs'] = merge_dict(attrs, self.data.get('attrs', {}))

    def run_client_op(self, op, params, log_err_codes=()):
        try:
            results = op(**params)
            for r in results['Unsuccessful']:
                self.log.exception(
                    'Exception: %s for %s: %s',
                    op.__name__, r['ResourceId'], r['Error']['Message'])
        except ClientError as e:
            if e.response['Error']['Code'] in log_err_codes:
                self.log.exception(
                    'Exception: %s: %s',
                    op.response['Error']['Message'])
            else:
                raise

    def ensure_log_group(self, logroup):
        client = local_session(self.manager.session_factory).client('logs')
        try:
            client.create_log_group(logGroupName=logroup)
        except client.exceptions.ResourceAlreadyExistsException:
            pass

    def delete_flow_logs(self, client, rids):
        flow_logs = [
            r for r in self.manager.get_resource_manager('flow-log').resources()
            if r['ResourceId'] in rids]
        self.run_client_op(
            client.delete_flow_logs,
            {'FlowLogIds': [f['FlowLogId'] for f in flow_logs]},
            ('InvalidParameterValue', 'InvalidFlowLogId.NotFound',)
        )

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        enabled = self.data.get('state', True)

        if not enabled:
            model_id = self.manager.get_model().id
            rids = [r[model_id] for r in resources]
            return self.delete_flow_logs(client, rids)

        model = self.manager.get_model()
        params = {'ResourceIds': [r[model.id] for r in resources]}
        params['ResourceType'] = self.RESOURCE_ALIAS[model.arn_type]
        params.update(self.data['attrs'])
        if params.get('LogDestinationType', 'cloud-watch-logs') == 'cloud-watch-logs':
            self.ensure_log_group(params['LogGroupName'])
        self.run_client_op(
            client.create_flow_logs, params, ('FlowLogAlreadyExists',))


class PrefixListDescribe(query.DescribeSource):

    def get_resources(self, ids, cache=True):
        query = {'Filters': [
            {'Name': 'prefix-list-id',
             'Values': ids}]}
        return self.query.filter(self.manager, **query)


@resources.register('prefix-list')
class PrefixList(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        arn_type = 'prefix-list'
        enum_spec = ('describe_managed_prefix_lists', 'PrefixLists', None)
        config_type = cfn_type = "AWS::EC2::PrefixList"
        name = 'PrefixListName'
        id = 'PrefixListId'
        id_prefix = 'pl-'
        universal_taggable = object()

    source_mapping = {'describe': PrefixListDescribe}


@PrefixList.filter_registry.register('entry')
class Entry(Filter):

    schema = type_schema(
        'entry', rinherit=ValueFilter.schema)
    permissions = ('ec2:GetManagedPrefixListEntries',)

    annotation_key = 'c7n:prefix-entries'
    match_annotation_key = 'c7n:matched-entries'

    def process(self, resources, event=None):
        client = local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            if self.annotation_key in r:
                continue
            r[self.annotation_key] = client.get_managed_prefix_list_entries(
                PrefixListId=r['PrefixListId']).get('Entries', ())

        vf = ValueFilter(self.data)
        vf.annotate = False

        results = []
        for r in resources:
            matched = []
            for e in r[self.annotation_key]:
                if vf(e):
                    matched.append(e)
            if matched:
                results.append(r)
                r[self.match_annotation_key] = matched
        return results


@Subnet.action_registry.register('modify')
class SubnetModifyAtrributes(BaseAction):
    """Modify subnet attributes.

    :example:

    .. code-block:: yaml

            policies:
              - name: turn-on-public-ip-protection
                resource: aws.subnet
                filters:
                  - type: value
                    key: "MapPublicIpOnLaunch.enabled"
                    value: false
                actions:
                  - type: modify
                    MapPublicIpOnLaunch: false
    """

    schema = type_schema(
        "modify",
        AssignIpv6AddressOnCreation={'type': 'boolean'},
        CustomerOwnedIpv4Pool={'type': 'string'},
        DisableLniAtDeviceIndex={'type': 'boolean'},
        EnableLniAtDeviceIndex={'type': 'integer'},
        EnableResourceNameDnsAAAARecordOnLaunch={'type': 'boolean'},
        EnableResourceNameDnsARecordOnLaunch={'type': 'boolean'},
        EnableDns64={'type': 'boolean'},
        MapPublicIpOnLaunch={'type': 'boolean'},
        MapCustomerOwnedIpOnLaunch={'type': 'boolean'},
        PrivateDnsHostnameTypeOnLaunch={
            'type': 'string', 'enum': ['ip-name', 'resource-name']
        }
    )

    permissions = ("ec2:ModifySubnetAttribute",)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        params = dict(self.data)
        params.pop('type')

        for k in list(params):
            if isinstance(params[k], bool):
                params[k] = {'Value': params[k]}

        for r in resources:
            self.manager.retry(
                client.modify_subnet_attribute,
                SubnetId=r['SubnetId'], **params)
        return resources


@resources.register('mirror-session')
class TrafficMirrorSession(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        enum_spec = ('describe_traffic_mirror_sessions', 'TrafficMirrorSessions', None)
        name = id = 'TrafficMirrorSessionId'
        config_type = cfn_type = 'AWS::EC2::TrafficMirrorSession'
        arn_type = 'traffic-mirror-session'
        universal_taggable = object()
        id_prefix = 'tms-'


@TrafficMirrorSession.action_registry.register('delete')
class DeleteTrafficMirrorSession(BaseAction):
    """Action to delete traffic mirror session(s)

    :example:

    .. code-block:: yaml

            policies:
              - name: traffic-mirror-session-paclength
                resource: mirror-session
                filters:
                  - type: value
                    key: tag:Owner
                    value: xyz
                actions:
                  - delete
    """

    schema = type_schema('delete')
    permissions = ('ec2:DeleteTrafficMirrorSession',)

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('ec2')
        for r in resources:
            client.delete_traffic_mirror_session(TrafficMirrorSessionId=r['TrafficMirrorSessionId'])


@resources.register('mirror-target')
class TrafficMirrorTarget(query.QueryResourceManager):

    class resource_type(query.TypeInfo):
        service = 'ec2'
        enum_spec = ('describe_traffic_mirror_targets', 'TrafficMirrorTargets', None)
        name = id = 'TrafficMirrorTargetId'
        config_type = cfn_type = 'AWS::EC2::TrafficMirrorTarget'
        arn_type = 'traffic-mirror-target'
        universal_taggable = object()
        id_prefix = 'tmt-'


@RouteTable.filter_registry.register('cross-az-nat-gateway-route')
class CrossAZRouteTable(Filter):
    """Filter route-tables to find those with routes which send traffic
    from a subnet in an az to a nat gateway in a different az.

    This filter is useful for cost optimization, resiliency, and
    performance use-cases, where we don't want network traffic to
    cross from one availability zone (AZ) to another AZ.

    :Example:

    .. code-block:: yaml

            policies:
              - name: cross-az-nat-gateway-traffic
                resource: aws.route-table
                filters:
                    - type: cross-az-nat-gateway-route
                actions:
                  - notify

    """
    schema = type_schema('cross-az-nat-gateway-route')
    permissions = ("ec2:DescribeRouteTables", "ec2:DescribeNatGateways", "ec2:DescribeSubnets")

    table_annotation = "c7n:route-table"
    mismatch_annotation = "c7n:nat-az-mismatch"

    def resolve_subnets(self, resource, subnets):
        return {s['SubnetId'] for s in subnets
                if s[self.table_annotation] == resource['RouteTableId']}

    def annotate_subnets_table(self, tables: list, subnets: dict):
        # annotate route table associations onto their respective subnets
        main_tables = []
        # annotate explicit associations
        for t in tables:
            for association in t['Associations']:
                if association.get('SubnetId'):
                    subnets[association['SubnetId']][
                        self.table_annotation] = t['RouteTableId']
                if association.get('Main'):
                    main_tables.append(t)
        # annotate main tables
        for s in subnets.values():
            if self.table_annotation in s:
                continue
            for t in main_tables:
                if t['VpcId'] == s['VpcId']:
                    s[self.table_annotation] = t['RouteTableId']

    def process_route_table(self, subnets, nat_subnets, resource):
        matched = {}
        found = False
        associated_subnets = self.resolve_subnets(resource, subnets.values())
        for route in resource['Routes']:
            if not route.get("NatGatewayId") or route.get("State") != "active":
                continue
            nat_az = subnets[nat_subnets[route['NatGatewayId']]]['AvailabilityZone']
            mismatch_subnets = {
                s: subnets[s]['AvailabilityZone'] for s in associated_subnets
                if subnets[s]['AvailabilityZone'] != nat_az}
            if not mismatch_subnets:
                continue
            found = True
            matched.setdefault(route['NatGatewayId'], {})['NatGatewayAz'] = nat_az
            matched[route['NatGatewayId']].setdefault('Subnets', {}).update(mismatch_subnets)
        if not found:
            return
        resource[self.mismatch_annotation] = matched
        return resource

    def process(self, resources, event=None):
        subnets = {
            s['SubnetId']: s for s in
            self.manager.get_resource_manager('aws.subnet').resources()
        }
        nat_subnets = {
            nat_gateway['NatGatewayId']: nat_gateway["SubnetId"]
            for nat_gateway in self.manager.get_resource_manager('nat-gateway').resources()}

        results = []
        self.annotate_subnets_table(resources, subnets)
        for resource in resources:
            if self.process_route_table(subnets, nat_subnets, resource):
                results.append(resource)

        return results


@NetworkAddress.filter_registry.register('used-by')
class UsedByNetworkAddress(Filter):
    """Filter Elastic IPs to find the resource type that the network
    interface that the Elastic IP is associated with is attached to.

    This filter is useful for limiting the types of resources to
    enable AWS Shield Advanced protection.

    :Example:

    .. code-block:: yaml

            policies:
              - name: eip-shield-advanced-enable
                resource: aws.elastic-ip
                filters:
                  - type: used-by
                    resource-type: elb-net
                  - type: shield-enabled
                    state: false
                actions:
                  - type: set-shield
                    state: true
    """
    schema = type_schema(
        'used-by', required=['resource-type'], **{
            'resource-type': {'type': 'string'}}
    )
    permissions = ("ec2:DescribeNetworkInterfaces",)

    def process(self, resources, event=None):
        eni_ids = []
        for r in resources:
            if r.get('NetworkInterfaceId'):
                eni_ids.append(r['NetworkInterfaceId'])
        enis = self.manager.get_resource_manager('eni').get_resources(eni_ids)
        results = []
        for r in resources:
            for eni in enis:
                if r.get('NetworkInterfaceId') == eni['NetworkInterfaceId']:
                    rtype = get_eni_resource_type(eni)
                    if rtype == self.data.get('resource-type'):
                        results.append(r)
        return results
