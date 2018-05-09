# Copyright 2018 Capital One Services, LLC
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

from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.provider import resources
from c7n.actions import BaseAction
from c7n.filters import Filter


@resources.register('networksecuritygroup')
class NetworkSecurityGroup(ArmResourceManager):
    class resource_type(object):
        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('network_security_groups', 'list_all')
        id = 'id'
        name = 'name'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )


class SecurityRuleFilter(Filter):
    """
    Filter on Security Rules within a Network Security Group
    """
    perm_attrs = set((
        'IpProtocol', 'FromPort', 'ToPort'))

    filter_attrs = set(('Cidr', 'Ports', 'OnlyPorts'))
    attrs = perm_attrs.union(filter_attrs)
    attrs.add('match-operator')

    def validate(self):
        # Check that variable values are valid
        if self.data.get('FromPort') and self.data.get('ToPort') and \
                self.data.get('FromPort') > self.data.get('ToPort'):
            raise ValueError('FromPort should be lower than ToPort')
        if (
                (self.data.get('FromPort') or self.data.get('ToPort')) and
                (self.data.get('Ports') or self.data.get('OnlyPorts'))
        ) or (self.data.get('Ports') and self.data.get('OnlyPorts')):
            raise ValueError(
                'Invalid port parameters. Choose port range (FromPort and/or ToPort) '
                'or specify specific ports (Ports or OnlyPorts)')

    def process(self, network_security_groups, event=None):

        # Get variables
        self.ip_protocol = self.data.get('IpProtocol')
        self.from_port = self.data.get('FromPort')
        self.to_port = self.data.get('ToPort')
        self.ports = self.data.get('Ports')
        self.only_ports = self.data.get('OnlyPorts')
        self.match_op = self.data.get('match-operator', 'and') == 'and' and all or any

        """
        For each Network Security Group, set the 'securityRules' property to contain
        only rules where there is a match, as defined in 'is_match'
        """
        for nsg in network_security_groups:
            nsg['properties']['securityRules'] = \
                [rule for rule in nsg['properties']['securityRules']
                 if self.is_match(rule)]
        """
        Set network_security_groups to include only those that still have 'securityRules'
        after the filtering has taken place
        """
        network_security_groups = \
            [nsg for nsg in network_security_groups if len(nsg['properties']['securityRules']) > 0]
        return network_security_groups

    """
    Check to see if range given matches range as defined by policy, return boolean
    """
    def is_range_match(self, dest_port_range):
        # destination port range is coming from Azure, existing rules, not policy input
        if len(dest_port_range) > 2:
            raise ValueError('Invalid range')

        # FromPort is specified, should be above FromPort
        if self.from_port:
            for port in dest_port_range:
                if port < self.from_port:
                    return False
        # ToPort is specified, should be below ToPort
        if self.to_port:
            for port in dest_port_range:
                if port > self.to_port:
                    return False
        # OnlyPorts is specified, anything NOT included in OnlyPorts should return True
        if self.only_ports:
            for op in self.only_ports:
                if len(dest_port_range) > 1:
                    if dest_port_range[0] <= op >= dest_port_range[1]:
                        return False
                else:
                    if dest_port_range[0] == op:
                        return False
        # Ports is specified, only those included in Ports should return true
        elif self.ports:
            if len(dest_port_range) > 1:
                # self.ports needs to have ALL ports in range (inclusive) to match
                range_set = set(range(dest_port_range[0], dest_port_range[1] + 1))
                ports_set = set(self.ports)
                return range_set.issubset(ports_set)
            else:
                return dest_port_range[0] in self.ports
        return True

    """
    Check to see if port ranges defined in security rule match range as defined by policy
    """
    def is_ranges_match(self, security_rule):
        if 'destinationPortRange' in security_rule['properties']:
            dest_port_ranges = \
                [self.get_port_range(security_rule['properties']['destinationPortRange'])]
        else:
            dest_port_ranges = \
                [self.get_port_range(range_str) for range_str
                 in security_rule['properties']['destinationPortRanges']]
        for range in dest_port_ranges:
            if not self.is_range_match(range):
                return False
        return True

    def get_port_range(self, range_str):
        return [int(item) for item in range_str.split('-')]

    """
    Determine if SecurityRule matches criteria as entered in policy

    Currently supporting filters:
        Ports - Specific Ports to target
        OnlyPorts - Ports to IGNORE
        FromPort - Lower bound of port range (inclusive)
        ToPort - Upper bound of port range (inclusive)
        IpProtocol - TCP/UDP protocol
    """
    def is_match(self, security_rule):
        if self.direction_key != security_rule['properties']['direction']:
            return False
        ranges_match = self.is_ranges_match(security_rule)
        protocol_match = (self.ip_protocol is None) or \
                         (self.ip_protocol == security_rule['properties']['protocol'])
        return self.match_op([ranges_match, protocol_match])


@NetworkSecurityGroup.filter_registry.register('ingress')
class IngressFilter(SecurityRuleFilter):
    direction_key = 'Inbound'

    schema = {
        'type': 'object',
        'properties': {
            'type': {'enum': ['ingress']},
            'match-operator': {'type': 'string', 'enum': ['or', 'and']},
            'Ports': {'type': 'array', 'items': {'type': 'integer'}},
            'OnlyPorts': {'type': 'array', 'items': {'type': 'integer'}},
            'FromPort': {'type': 'integer'},
            'ToPort': {'type': 'integer'},
            'IpProtocol': {'type': 'string', 'enum': ['TCP', 'UDP']}
        },
        'required': ['type']
    }


@NetworkSecurityGroup.filter_registry.register('egress')
class EgressFilter(SecurityRuleFilter):
    direction_key = 'Outbound'

    schema = {
        'type': 'object',
        # 'additionalProperties': True,
        'properties': {
            'type': {'enum': ['egress']},
            'match-operator': {'type': 'string', 'enum': ['or', 'and']},
            'Ports': {'type': 'array', 'items': {'type': 'integer'}},
            'OnlyPorts': {'type': 'array', 'items': {'type': 'integer'}},
            'FromPort': {'type': 'integer'},
            'ToPort': {'type': 'integer'},
            'IpProtocol': {'type': 'string', 'enum': ['TCP', 'UDP']}
            # 'SelfReference': {'type': 'boolean'}
        },
        'required': ['type']}


class RulesAction(BaseAction):
    """
    Action to perform on SecurityRules within a Network Security Group
    """

    def process(self, network_security_groups):

        for nsg in network_security_groups:
            nsg_name = nsg['name']
            resource_group = nsg['resourceGroup']
            for rule in nsg['properties']['securityRules']:
                self.manager.log.info(
                    'Updating access to \'%s\' for security rule '
                    '\'%s\' in resource group \'%s\''.format(
                        self.access_action, rule['name'], resource_group))
                rule['properties']['access'] = self.access_action
                self.manager.get_client().security_rules.create_or_update(
                    resource_group,
                    nsg_name,
                    rule['name'],
                    rule
                )


@NetworkSecurityGroup.action_registry.register('close')
class CloseRules(RulesAction):
    """
    Deny access to Security Rule
    """
    access_action = 'Deny'


@NetworkSecurityGroup.action_registry.register('open')
class OpenRules(RulesAction):
    """
    Allow access to Security Rule
    """
    access_action = 'Allow'
