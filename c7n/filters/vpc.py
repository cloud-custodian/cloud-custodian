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

from c7n.utils import local_session, type_schema

from .core import Filter, ValueFilter, FilterValidationError
from .related import RelatedResourceFilter


class SecurityGroupFilter(RelatedResourceFilter):
    """Filter a resource by its associated security groups."""
    schema = type_schema(
        'security-group', rinherit=ValueFilter.schema,
        **{'match-resource':{'type': 'boolean'},
           'operator': {'enum': ['and', 'or']}})

    RelatedResource = "c7n.resources.vpc.SecurityGroup"
    AnnotationKey = "matched-security-groups"


class SubnetFilter(RelatedResourceFilter):
    """Filter a resource by its associated subnets."""
    schema = type_schema(
        'subnet', rinherit=ValueFilter.schema,
        **{'match-resource':{'type': 'boolean'},
           'operator': {'enum': ['and', 'or']}})

    RelatedResource = "c7n.resources.vpc.Subnet"
    AnnotationKey = "matched-subnets"


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
    """

    schema = type_schema(
        'network-location',
        **{'missing-ok': {
            'type': 'boolean',
            'default': False,
            'description': (
                "How to handle missing keys on elements, by default this causes "
                "resources to be considered not-equal")},
           'match': {'type': 'string', 'enum': ['equal', 'non-equal'],
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
           'required': ['key']
           })

    permissions = ('ec2:DescribeSecurityGroups', 'ec2:DescribeSubnets')

    def validate(self):
        rfilters = self.manager.filter_registry.keys()
        if 'subnet' not in rfilters:
            raise FilterValidationError(
                "network-location requires resource subnet filter availability")
        if 'security-group' not in rfilters:
            raise FilterValidationError(
                "network-location requires resource security-group filter availability")
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
            resource_sgs = [related_sg[sid] for sid in self.sg.get_related_ids([r])]
            resource_subnets = [
                related_subnet[sid] for sid in self.subnet.get_related_ids([r])]
            found = self.process_resource(r, resource_sgs, resource_subnets, key)
            if found:
                results.append(found)

        return results

    def process_resource(self, r, resource_sgs, resource_subnets, key):
        evaluation = []
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
            elif 'security-group' in self.compare and r_value not in sg_space:
                evaluation.append({
                    'reason': 'ResourceLocationMismatch',
                    'resource': r_value,
                    'security-groups': sg_values})
            elif 'subnet' in self.compare and r_value not in subnet_space:
                evaluation.append({
                    'reason': 'ResourceLocationMismatch',
                    'resource': r_value,
                    'subnet': subnet_values})

        if evaluation and self.match == 'not-equal':
            r['c7n:NetworkLocation'] = evaluation
            return r
        elif not evaluation and self.match == 'equal':
            return r
