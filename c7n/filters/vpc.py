# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import jmespath
import re

from c7n.exceptions import PolicyValidationError
from c7n.utils import local_session, type_schema

from .core import Filter, ValueFilter
from .related import RelatedResourceFilter


class MatchResourceValidator:

    def validate(self):
        if self.data.get('match-resource'):
            self.required_keys = set('key',)
        return super(MatchResourceValidator, self).validate()


class SecurityGroupFilter(MatchResourceValidator, RelatedResourceFilter):
    """Filter a resource by its associated security groups."""
    schema = type_schema(
        'security-group', rinherit=ValueFilter.schema,
        **{'match-resource': {'type': 'boolean'},
           'operator': {'enum': ['and', 'or']}})
    schema_alias = True

    RelatedResource = "c7n.resources.vpc.SecurityGroup"
    AnnotationKey = "matched-security-groups"


class SubnetFilter(MatchResourceValidator, RelatedResourceFilter):
    """Filter a resource by its associated subnets attributes.

    This filter is generally available for network attached resources.

    ie. to find lambda functions that are vpc attached to subnets with
    a tag key Location and value Database.

    :example:

    .. code-block:: yaml

      policies:
        - name: lambda
          resource: aws.lambda
          filters:
            - type: subnet
              key: tag:Location
              value: Database

    It also supports finding resources on public or private subnets
    via route table introspection to determine if the subnet is
    associated to an internet gateway.

    :example:

    .. code-block:: yaml

      policies:
         - name: public-ec2
           resource: aws.ec2
           filters:
             - type: subnet
               igw: True
               key: SubnetId
               value: present

    """

    schema = type_schema(
        'subnet', rinherit=ValueFilter.schema,
        **{'match-resource': {'type': 'boolean'},
           'operator': {'enum': ['and', 'or']},
           'igw': {'enum': [True, False]},
           })

    schema_alias = True
    RelatedResource = "c7n.resources.vpc.Subnet"
    AnnotationKey = "matched-subnets"

    def get_permissions(self):
        perms = super().get_permissions()
        if self.data.get('igw') in (True, False):
            perms += self.manager.get_resource_manager(
                'aws.route-table').get_permissions()
        return perms

    def validate(self):
        super().validate()
        self.check_igw = self.data.get('igw')

    def match(self, related):
        if self.check_igw in [True, False]:
            if not self.match_igw(related):
                return False
        return super().match(related)

    def process(self, resources, event=None):
        related = self.get_related(resources)
        if self.check_igw in [True, False]:
            self.route_tables = self.get_route_tables()
        return [r for r in resources if self.process_resource(r, related)]

    def get_route_tables(self):
        rmanager = self.manager.get_resource_manager('aws.route-table')
        route_tables = {}
        for r in rmanager.resources():
            for a in r['Associations']:
                if a['Main']:
                    route_tables[r['VpcId']] = r
                elif 'SubnetId' in a:
                    route_tables[a['SubnetId']] = r
        return route_tables

    def match_igw(self, subnet):
        rtable = self.route_tables.get(
            subnet['SubnetId'],
            self.route_tables.get(subnet['VpcId']))
        if rtable is None:
            self.log.debug('route table for %s not found', subnet['SubnetId'])
            return
        found_igw = False
        for route in rtable['Routes']:
            if route.get('GatewayId') and route['GatewayId'].startswith('igw-'):
                found_igw = True
                break
        if self.check_igw and found_igw:
            return True
        elif not self.check_igw and not found_igw:
            return True
        return False


class VpcFilter(MatchResourceValidator, RelatedResourceFilter):
    """Filter a resource by its associated vpc."""
    schema = type_schema(
        'vpc', rinherit=ValueFilter.schema,
        **{'match-resource': {'type': 'boolean'},
           'operator': {'enum': ['and', 'or']}})

    schema_alias = True
    RelatedResource = "c7n.resources.vpc.Vpc"
    AnnotationKey = "matched-vpcs"


class DefaultVpcBase(Filter):
    """Filter to resources in a default vpc."""
    vpcs = None
    default_vpc = None
    permissions = ('ec2:DescribeVpcs',)

    def match(self, vpc_id):
        if self.default_vpc is None:
            self.log.debug("querying default vpc %s" % vpc_id)
            client = local_session(self.manager.session_factory).client('ec2')
            vpcs = [v['VpcId'] for v
                    in client.describe_vpcs()['Vpcs']
                    if v['IsDefault']]
            if vpcs:
                self.default_vpc = vpcs.pop()
        return vpc_id == self.default_vpc and True or False


class NetworkLocation(Filter):
    """On a network attached resource, determine intersection of
    security-group attributes, subnet attributes, and resource attributes.

    The use case is a bit specialized, for most use cases using `subnet`
    and `security-group` filters suffice. but say for example you wanted to
    verify that an ec2 instance was only using subnets and security groups
    with a given tag value, and that tag was not present on the resource.

    :Example:

    .. code-block:: yaml

        policies:
          - name: ec2-mismatched-sg-remove
            resource: ec2
            filters:
              - type: network-location
                compare: ["resource","security-group"]
                key: "tag:TEAM_NAME"
                ignore:
                  - "tag:TEAM_NAME": Enterprise
            actions:
              - type: modify-security-groups
                remove: network-location
                isolation-group: sg-xxxxxxxx
    """

    schema = type_schema(
        'network-location',
        **{'missing-ok': {
            'type': 'boolean',
            'default': False,
            'description': (
                "How to handle missing keys on elements, by default this causes"
                "resources to be considered not-equal")},
           'match': {'type': 'string', 'enum': ['equal', 'not-equal'],
                     'default': 'non-equal'},
           'compare': {
            'type': 'array',
            'description': (
                'Which elements of network location should be considered when'
                ' matching.'),
            'default': ['resource', 'subnet', 'security-group'],
            'items': {
                'enum': ['resource', 'subnet', 'security-group']}},
           'key': {
               'type': 'string',
               'description': 'The attribute expression that should be matched on'},
           'max-cardinality': {
               'type': 'integer', 'default': 1,
               'title': ''},
           'ignore': {'type': 'array', 'items': {'type': 'object'}},
           'required': ['key'],

           })
    schema_alias = True
    permissions = ('ec2:DescribeSecurityGroups', 'ec2:DescribeSubnets')

    def validate(self):
        rfilters = self.manager.filter_registry.keys()
        if 'subnet' not in rfilters:
            raise PolicyValidationError(
                "network-location requires resource subnet filter availability on %s" % (
                    self.manager.data))

        if 'security-group' not in rfilters:
            raise PolicyValidationError(
                "network-location requires resource security-group filter availability on %s" % (
                    self.manager.data))
        return self

    def process(self, resources, event=None):
        self.sg = self.manager.filter_registry.get('security-group')({}, self.manager)
        related_sg = self.sg.get_related(resources)

        self.subnet = self.manager.filter_registry.get('subnet')({}, self.manager)
        related_subnet = self.subnet.get_related(resources)

        self.sg_model = self.manager.get_resource_manager('security-group').get_model()
        self.subnet_model = self.manager.get_resource_manager('subnet').get_model()
        self.vf = self.manager.filter_registry.get('value')({}, self.manager)

        # filter options
        key = self.data.get('key')
        self.compare = self.data.get('compare', ['subnet', 'security-group', 'resource'])
        self.max_cardinality = self.data.get('max-cardinality', 1)
        self.match = self.data.get('match', 'not-equal')
        self.missing_ok = self.data.get('missing-ok', False)

        results = []
        for r in resources:
            resource_sgs = self.filter_ignored(
                [related_sg[sid] for sid in self.sg.get_related_ids([r]) if sid in related_sg])
            resource_subnets = self.filter_ignored(
                [related_subnet[sid] for sid in self.subnet.get_related_ids([r])
                if sid in related_subnet])
            found = self.process_resource(r, resource_sgs, resource_subnets, key)
            if found:
                results.append(found)

        return results

    def filter_ignored(self, resources):
        ignores = self.data.get('ignore', ())
        results = []

        for r in resources:
            found = False
            for i in ignores:
                for k, v in i.items():
                    if self.vf.get_resource_value(k, r) == v:
                        found = True
                if found is True:
                    break
            if found is True:
                continue
            results.append(r)
        return results

    def process_resource(self, r, resource_sgs, resource_subnets, key):
        evaluation = []
        sg_space = set()
        subnet_space = set()

        if 'subnet' in self.compare:
            subnet_values = {
                rsub[self.subnet_model.id]: self.subnet.get_resource_value(key, rsub)
                for rsub in resource_subnets}

            if not self.missing_ok and None in subnet_values.values():
                evaluation.append({
                    'reason': 'SubnetLocationAbsent',
                    'subnets': subnet_values})
            subnet_space = set(filter(None, subnet_values.values()))

            if len(subnet_space) > self.max_cardinality:
                evaluation.append({
                    'reason': 'SubnetLocationCardinality',
                    'subnets': subnet_values})

        if 'security-group' in self.compare:
            sg_values = {
                rsg[self.sg_model.id]: self.sg.get_resource_value(key, rsg)
                for rsg in resource_sgs}
            if not self.missing_ok and None in sg_values.values():
                evaluation.append({
                    'reason': 'SecurityGroupLocationAbsent',
                    'security-groups': sg_values})

            sg_space = set(filter(None, sg_values.values()))

            if len(sg_space) > self.max_cardinality:
                evaluation.append({
                    'reason': 'SecurityGroupLocationCardinality',
                    'security-groups': sg_values})

        if ('subnet' in self.compare and
                'security-group' in self.compare and
                sg_space != subnet_space):
            evaluation.append({
                'reason': 'LocationMismatch',
                'subnets': subnet_values,
                'security-groups': sg_values})

        if 'resource' in self.compare:
            r_value = self.vf.get_resource_value(key, r)
            if not self.missing_ok and r_value is None:
                evaluation.append({
                    'reason': 'ResourceLocationAbsent',
                    'resource': r_value})
            elif 'security-group' in self.compare and resource_sgs and r_value not in sg_space:
                evaluation.append({
                    'reason': 'ResourceLocationMismatch',
                    'resource': r_value,
                    'security-groups': sg_values})
            elif 'subnet' in self.compare and resource_subnets and r_value not in subnet_space:
                evaluation.append({
                    'reason': 'ResourceLocationMismatch',
                    'resource': r_value,
                    'subnet': subnet_values})
            if 'security-group' in self.compare and resource_sgs:
                mismatched_sgs = {sg_id: sg_value
                                for sg_id, sg_value in sg_values.items()
                                if sg_value != r_value}
                if mismatched_sgs:
                    evaluation.append({
                        'reason': 'SecurityGroupMismatch',
                        'resource': r_value,
                        'security-groups': mismatched_sgs})

        if evaluation and self.match == 'not-equal':
            r['c7n:NetworkLocation'] = evaluation
            return r
        elif not evaluation and self.match == 'equal':
            return r


class PortRangeFilter(Filter):
    """
    Allows to check if all the ports specified in the policy
    are within the ones stored in the firewall rule.
    Example 1: ports 10-20 are within 10, 11-25.
    Example 2: port 19 is within 18-22.
    Example 3: ports 20-24 are within 20-21, 22-24.
    Example 4: ports 20-24 are NOT within 20-21, 23-24. (or specify allow-partial: True)
    Example 5: ports 20,23-24 are within 20-21, 23-24.

    :Example:

    .. code-block:: yaml

        filters:
          - type: port-range
            key: allowed[?IPProtocol=='tcp'].ports[]
            required-ports: 20, 50-60
            allow-partial: False
    """
    key_key = 'key'
    ranges_key = 'required-ports'
    partial_key = 'allow-partial'
    pattern = '^(-?\\d+)-(-?\\d+)$'
    schema = type_schema(
        'port-range',
        required=[key_key, ranges_key],
        **{
            key_key: {'$ref': '#/definitions/filters_common/value'},
            ranges_key: {'$ref': '#/definitions/filters_common/value'},
            partial_key: {'type': 'boolean'}
        })

    def __init__(self, data, manager):
        super(PortRangeFilter, self).__init__(data, manager)
        if PortRangeFilter.partial_key not in self.data:
            self.data[PortRangeFilter.partial_key] = False

    def process(self, resources, event=None):
        return list(filter(lambda resource: self.is_valid_resource(resource), resources))

    def extract_policy_port_ranges(self) -> str:
        return str(self.data[PortRangeFilter.ranges_key])

    def extract_resource_port_ranges(self, resource) -> str:
        ranges = jmespath.search(self.data[PortRangeFilter.key_key], resource)
        return ','.join(ranges) if ranges else ''

    def is_valid_resource(self, resource):
        policy_ranges = self.extract_policy_port_ranges()
        resource_ranges = self.extract_resource_port_ranges(resource)
        return self.check_ranges_match(policy_ranges, resource_ranges)

    def check_ranges_match(self, policy_ranges: str, resource_ranges: str):
        """
        :param policy_ranges: a comma-separated string containing either
               integers or ranges; e.g. 0,25-443,1024,3389
        :param resource_ranges: in the same format as policy_ranges
        :return: True or False depending on PortRangeFilter.partial_key
        """
        unmerged_policy_ports = PortRangeFilter._parse_ranges(policy_ranges)
        unmerged_resource_ports = PortRangeFilter._parse_ranges(resource_ranges)
        policy_ports = PortRangeFilter._sort_and_merge_intersecting_ranges(
            unmerged_policy_ports)
        resource_ports = PortRangeFilter._sort_and_merge_intersecting_ranges(
            unmerged_resource_ports)
        if self.data[PortRangeFilter.partial_key]:
            return PortRangeFilter._is_partial_match(policy_ports, resource_ports)
        return PortRangeFilter._is_subset(policy_ports, resource_ports)

    @classmethod
    def _is_subset(cls, maybe_range_container_subset, range_container):
        """
        :param maybe_range_container_subset: sorted and merged
        :param range_container: sorted and merged
        """
        range_container_index = 0
        range_container_last_index = len(range_container) - 1
        is_subset = True
        for maybe_range_container_subset_element in maybe_range_container_subset:
            is_subset_element = False
            while range_container_index <= range_container_last_index:
                range_container_element = range_container[range_container_index]
                if cls._is_range_before_another_range(
                        range_container_element, maybe_range_container_subset_element):
                    pass
                elif cls._is_range_within_another_range(
                        maybe_range_container_subset_element, range_container_element):
                    is_subset_element = True
                    break
                range_container_index += 1
            if not is_subset_element:
                is_subset = False
            if not is_subset:
                break
        return is_subset

    @classmethod
    def _is_partial_match(cls, maybe_range_container_partial_match, range_container):
        """
        :param maybe_range_container_partial_match: sorted and merged
        :param range_container: sorted and merged
        """
        a = range_container
        b = maybe_range_container_partial_match
        range_container_last_index = len(a) - 1
        partial_match = False
        for maybe_range_container_subset_element in b:
            range_container_index = 0
            while range_container_index <= range_container_last_index:
                range_container_element = a[range_container_index]
                if cls._is_range_intersecting_another_range(
                        range_container_element, maybe_range_container_subset_element):
                    partial_match = True
                    break
                range_container_index += 1
            if partial_match:
                break
        return partial_match

    @classmethod
    def _is_range_within_another_range(cls, range_to_check, another_range):
        return another_range[0] <= range_to_check[0] and range_to_check[1] <= another_range[1]

    @classmethod
    def _is_range_before_another_range(cls, range_to_check, another_range):
        return range_to_check[1] < another_range[0]

    @classmethod
    def _is_range_before_and_next_to_another_range(cls, range_to_check, another_range):
        return range_to_check[1] + 1 == another_range[0]

    @classmethod
    def _is_range_intersecting_or_touching_another_range(cls, range_to_check, another_range):
        if cls._is_range_before_another_range(range_to_check, another_range):
            return cls._is_range_before_and_next_to_another_range(range_to_check, another_range)
        if cls._is_range_before_another_range(another_range, range_to_check):
            return cls._is_range_before_and_next_to_another_range(another_range, range_to_check)
        return True

    @classmethod
    def _is_range_intersecting_another_range(cls, range_to_check, another_range):
        if cls._is_range_before_another_range(range_to_check, another_range):
            return False
        if cls._is_range_before_another_range(another_range, range_to_check):
            return False
        return True

    @classmethod
    def _sort_and_merge_intersecting_ranges(cls, ranges):
        if len(ranges) > 1:
            merged_ranges = []
            sorted_ranges = sorted(ranges)
            current_merged_range = [sorted_ranges[0][0], sorted_ranges[0][1]]
            for current_range in sorted_ranges[1:]:
                if cls._is_range_intersecting_or_touching_another_range(
                        current_merged_range, current_range):
                    current_merged_range_max = max(current_range[1], current_merged_range[1])
                    current_merged_range = [current_merged_range[0], current_merged_range_max]
                else:
                    merged_ranges.append(tuple(current_merged_range))
                    current_merged_range = [current_range[0], current_range[1]]
            merged_ranges.append(tuple(current_merged_range))
            return merged_ranges
        return sorted(ranges)

    @classmethod
    def _parse_ranges(cls, raw_ranges):
        tokens = cls._parse_tokens(raw_ranges)
        ranges = cls._parse_port_range_or_port_tokens(tokens)
        return ranges

    @classmethod
    def _parse_port_range_or_port_tokens(cls, port_range_or_port_tokens):
        ranges = set()
        for token in port_range_or_port_tokens:
            ranges.add(ParseMaxAndMinPorts.parse_port_range_token(token)
                       if cls._is_port_range_token(token)
                       else cls._parse_port_token_as_port_range(token))
        return ranges

    @classmethod
    def _parse_tokens(cls, raw_tokens):
        tokens = [token.strip() for token in raw_tokens.split(',')]
        if len(tokens) == 1 and tokens[0] == '':
            tokens = []
        return tokens

    @classmethod
    def _is_port_range_token(cls, token):
        return re.match(PortRangeFilter.pattern, token) is not None

    @classmethod
    def _parse_port_token_as_port_range(cls, port_token):
        port = ParseMaxAndMinPorts.parse_port_token(port_token)
        return port, port


class ParseMaxAndMinPorts:
    pattern = '^(-?\\d+)-(-?\\d+)$'

    @classmethod
    def parse_port_range_token(cls, port_range_token):
        (min_port, max_port) = re.match(ParseMaxAndMinPorts.pattern, port_range_token).groups()
        parsed_min_port, parsed_max_port = cls.parse_port_token(
            min_port), cls.parse_port_token(max_port)
        if parsed_min_port == -1:
            parsed_min_port = 0
        if parsed_max_port == -1:
            parsed_max_port = 65535
        return parsed_min_port, parsed_max_port

    @classmethod
    def parse_port_token(cls, port_token):
        return int(port_token)
