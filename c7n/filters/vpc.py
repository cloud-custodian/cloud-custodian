# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import PolicyValidationError
from c7n.manager import resources
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
           'match': {'type': 'string', 'enum': ['equal', 'not-equal', 'in'],
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
           'value': {'type': 'array', 'items': {'type': 'string'}}
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

        if self.match == 'in':
            return self.process_match_in(r, resource_sgs, resource_subnets, key)

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

    def process_match_in(self, r, resource_sgs, resource_subnets, key):
        network_location_vals = set(self.data.get('value', []))

        if 'subnet' in self.compare:
            subnet_values = {
                rsub[self.subnet_model.id]: self.subnet.get_resource_value(key, rsub)
                for rsub in resource_subnets}
            # import pdb; pdb.set_trace()
            if not self.missing_ok and None in subnet_values.values():
                return

            subnet_space = set(filter(None, subnet_values.values()))
            if not subnet_space.issubset(network_location_vals):
                return

        if 'security-group' in self.compare:
            sg_values = {
                rsg[self.sg_model.id]: self.sg.get_resource_value(key, rsg)
                for rsg in resource_sgs}
            if not self.missing_ok and None in sg_values.values():
                return

            sg_space = set(filter(None, sg_values.values()))

            if not sg_space.issubset(network_location_vals):
                return

        if 'resource' in self.compare:
            r_value = self.vf.get_resource_value(key, r)
            if not self.missing_ok and r_value is None:
                return

            if r_value not in network_location_vals:
                return

        return r


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
            resource.setdefault('Matched%s' % self.ip_permissions_key, []).extend(matched)
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


class IPPermission(SGPermission):

    ip_permissions_key = "IpPermissions"
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {'type': {'enum': ['ingress']}},
        'required': ['type']}
    schema['properties'].update(SGPermissionSchema)


class IPPermissionEgress(SGPermission):

    ip_permissions_key = "IpPermissionsEgress"
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {'type': {'enum': ['egress']}},
        'required': ['type']}
    schema['properties'].update(SGPermissionSchema)


class ResourceAccess(Filter):

    access_class = None
    schema_alias = True
    schema = None
    permissions = ("ec2:DescribeSecurityGroups",)
    annotation_key = "c7n:MatchedGroups"

    def process(self, resources, event=None):
        group_fetch = self.manager.filter_registry['security-group']
        resource_group_map = group_fetch.get_related(resources)
        access_check = self.access_class(self.data, None)

        matched = []
        for r in resources:
            rid = r[self.manager.resource_type.id]
            rgroups = resource_group_map.get(rid)
            if not rgroups:
                continue
            mgroups = access_check.process(rgroups)
            if mgroups:
                r.setdefault(self.annotation_key, []).extend(
                    [g['GroupId'] for g in mgroups]
                )
                matched.append(r)
        return matched


class ResourceIngress(Filter):

    resource_class = IPPermission
    schema = IPPermission.schema
    annotation_key = "c7n:IngressGroups"


class ResourceEgress(Filter):

    resource_class = IPPermissionEgress
    schema = IPPermissionEgress.schema
    annotation_key = "c7n:EgressGroups"


def register_resource_access(registry, resource_class):
    if 'security-group' in resource_class.filter_registry:
        resource_class.filter_registry.register('ingress', ResourceIngress)
        resource_class.filter_registry.register('egress', ResourceEgress)


resources.subscribe(register_resource_access)
