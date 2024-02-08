# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.utils import type_schema, chunks
from c7n_tencentcloud.provider import resources
from c7n_tencentcloud.query import ResourceTypeInfo, QueryResourceManager
from c7n_tencentcloud.utils import PageMethod
from c7n.filters.core import Filter, ValueFilter


@resources.register('security-group')
class SecurityGroup(QueryResourceManager):
    """security-group

    Docs on security-group
    https://www.tencentcloud.com/document/product/215/38750

    :example:

    .. code-block:: yaml

        policies:
        - name: security_group_default_restrict
          resource: tencentcloud.security-group
          filters:
            - or:
                - SecurityGroupName: ccsTest
                - SecurityGroupName: base-ritch
            - or:
                - IpPermissions: not-null
                - IpPermissionsEgress: not-null
    """

    class resource_type(ResourceTypeInfo):
        """resource_type"""
        id = "SecurityGroupId"
        endpoint = "vpc.tencentcloudapi.com"
        service = "vpc"
        version = "2017-03-12"
        enum_spec = ("DescribeSecurityGroups", "Response.SecurityGroupSet[]", {})
        paging_def = {"method": PageMethod.Offset, "limit": {"key": "Limit", "value": "20"}}
        resource_prefix = "sg"
        taggable = True

    def augment(self, resources_param):
        cli = self.get_client()
        for resource in resources_param:
            resp = cli.execute_query("DescribeSecurityGroupPolicies",
                                     {"SecurityGroupId": resource["SecurityGroupId"]})
            policy_set = resp["Response"]["SecurityGroupPolicySet"]
            resource["IpPermissions"] = policy_set["Ingress"]
            resource["IpPermissionsEgress"] = policy_set["Egress"]
        return resources_param


class SGPermission(Filter):
    def validate(self):
        pass

    def process(self, resources, event=None):
        self.ports = 'Ports' in self.data and self.data['Ports'] or ()
        self.any_ports_except = \
            ('AnyPortsExcept' in self.data and self.data['AnyPortsExcept'] or ())
        return super(SGPermission, self).process(resources, event)

    # Supported Tencentcloud security-group policy port schema:
    #    Single Port:  80
    #    Multi Ports:  80,443
    #    Range Ports:  3306-2000
    #    All Ports: ALL
    def process_ports(self, perm):
        port_found = any_ports_except_found = None
        if 'Port' in perm:
            if perm['Port'] == 'ALL':
                if self.ports:
                    port_found = True
                if self.any_ports_except:
                    any_ports_except_found = True
            elif '-' in perm['Port']:
                f, t = perm['Port'].split('-', 1)
                for port in self.ports:
                    if int(f) <= port <= int(t):
                        port_found = True
                        break
                    port_found = False
                if self.any_ports_except:
                    # Ranges do not support equality
                    any_ports_except_found = True
            elif perm['Port']:
                ports = {int(p) for p in perm['Port'].split(',')}
                if self.ports:
                    intersection = ports.intersection(self.ports)
                    if intersection:
                        port_found = True
                    else:
                        port_found = False
                if self.any_ports_except:
                    any_ports_except_found = not ports.issubset(self.any_ports_except)
            else:
                port_found = False
        match = [k for k in (port_found, any_ports_except_found) if k is not None]
        if not match:
            return None
        return all(match)

    def _process_cidr(self, cidr_key, range_type, perm):
        ip_range = perm.get(range_type, "")
        if not ip_range:
            return False
        match_range = self.data[cidr_key]
        if isinstance(match_range, dict):
            match_range['key'] = range_type
        else:
            match_range = {range_type: match_range}
        vf = ValueFilter(match_range, self.manager)
        vf.annotate = False
        return vf(perm)

    def process_cidrs(self, perm):
        found_v6 = found_v4 = None
        if 'CidrV6' in self.data:
            found_v6 = self._process_cidr('CidrV6', 'Ipv6CidrBlock', perm)
        if 'Cidr' in self.data:
            found_v4 = self._process_cidr('Cidr', 'CidrBlock', perm)
        match_op = self.data.get('match-operator', 'and') == 'and' and all or any
        cidr_match = [k for k in (found_v6, found_v4) if k is not None]
        if not cidr_match:
            return None
        return match_op(cidr_match)

    def __call__(self, resource):
        matched = []
        match_op = self.data.get('match-operator', 'and') == 'and' and all or any
        for perm in resource[self.ip_permissions_key]:
            perm_matches = {}
            perm_matches['ports'] = self.process_ports(perm)
            perm_matches['cidrs'] = self.process_cidrs(perm)
            """None means that the term does not exist in the filter condition,
            and the none result is ignored"""
            perm_match_values = list(filter(
                lambda x: x is not None, perm_matches.values()))

            """ if process_xxx() method returns None, it means there is no related rule config in
            security group. In Python all([]) returns True, which should be fixed in this case:
            if perm_match_values == [] that means no rules is satisfied, this security group should
            be ignored.
            """
            if match_op == all and not perm_match_values:
                continue

            match = match_op(perm_match_values)
            if match:
                matched.append(perm)

        if matched:
            resource.setdefault('Matched%s' % self.ip_permissions_key, []).extend(matched)
            return True


@SecurityGroup.filter_registry.register('ingress')
class IPPermission(SGPermission):
    """
    :example:

    .. code-block:: yaml

        policies:
        - name: cidr_not_limit_filter
          resource: tencentcloud.security-group
          filters:
            - or:
                - type: ingress
                  Cidr:
                    value: 0.0.0.0/0
                - type: ingress
                  CidrV6:
                    value: '::/0'
    """
    ip_permissions_key = "IpPermissions"
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['ingress']},
            'Ports': {'type': 'array', 'items': {'type': 'integer'}},
            'AnyPortsExcept': {'type': 'array', 'items': {'type': 'integer'}},
            'Cidr': {},
            'CidrV6': {}
        },
        'required': ['type']}


@SecurityGroup.filter_registry.register('egress')
class IPPermissionEgress(SGPermission):
    ip_permissions_key = "IpPermissionsEgress"
    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'type': {'enum': ['egress']},
            'Ports': {'type': 'array', 'items': {'type': 'integer'}},
            'AnyPortsExcept': {'type': 'array', 'items': {'type': 'integer'}},
            'Cidr': {},
            'CidrV6': {}
        },
        'required': ['type']}


@SecurityGroup.filter_registry.register('used')
class StatisticsFilter(ValueFilter):
    """statistics

    :example:

    .. code-block:: yaml

        policies:
        - name: used
          resource: tencentcloud.security-group
          description: security group used statistical
          filters:
            - type: used
              key: CVM
              op: greater-than
              value: 0
    """

    schema = type_schema('used', rinherit=ValueFilter.schema)
    annotation_key = "c7n:usage_stats"

    def match(self, i):
        return super().match(i[self.annotation_key])

    def process(self, resources, event=None):
        self.augment([r for r in resources if self.annotation_key not in r])
        return super().process(resources)

    def augment(self, resources):
        client = self.manager.get_client()

        # DescribeSecurityGroupAssociationStatistics Maximum support 100
        for batch in chunks(resources, 50):
            id_resource_map = {r['SecurityGroupId']: r for r in batch}
            resp = client.execute_query(
                "DescribeSecurityGroupAssociationStatistics",
                {"SecurityGroupIds": list(id_resource_map)}
            )
            statistics = resp["Response"]["SecurityGroupAssociationStatisticsSet"]
            for stat in statistics:
                group = id_resource_map[stat['SecurityGroupId']]
                group[self.annotation_key] = {
                    istat['InstanceType']: istat['InstanceCount'] for istat
                    in stat['InstanceStatistics']
                }
                group[self.annotation_key].update(
                    {'TotalCount': stat['TotalCount'], 'SG': stat['SG']}
                )
        return resources
