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
from c7n.filters.core import PolicyValidationError
from c7n.utils import type_schema
from copy import deepcopy


@resources.register('networksecuritygroup')
class NetworkSecurityGroup(ArmResourceManager):
    class resource_type(object):
        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('network_security_groups', 'list_all', None)
        id = 'id'
        name = 'name'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )


FROM_PORT = 'fromPort'
TO_PORT = 'toPort'
PORTS = 'ports'
EXCEPT_PORTS = 'exceptPorts'
IP_PROTOCOL = 'ipProtocol'


class SecurityRuleFilter(Filter):
    """
    Filter on Security Rules within a Network Security Group
    """

    perm_attrs = set((
        IP_PROTOCOL, FROM_PORT, TO_PORT))

    filter_attrs = set(('Cidr', PORTS, EXCEPT_PORTS))
    attrs = perm_attrs.union(filter_attrs)
    attrs.add('match-operator')

    def validate(self):
        # Check that variable values are valid
        if self.data.get(FROM_PORT) and self.data.get(TO_PORT) and \
                self.data.get(FROM_PORT) > self.data.get(TO_PORT):
            raise PolicyValidationError('{} should be lower than {}'.format(FROM_PORT, TO_PORT))
        if (
                (self.data.get(FROM_PORT) or self.data.get(TO_PORT)) and
                (self.data.get(PORTS) or self.data.get(EXCEPT_PORTS))
        ) or (self.data.get(PORTS) and self.data.get(EXCEPT_PORTS)):
            raise PolicyValidationError(
                'Invalid port parameters. Choose port range ({} and/or {}) '
                'or specify specific ports ({} or {})'.format(
                    FROM_PORT, TO_PORT, PORTS, EXCEPT_PORTS))

    def process(self, network_security_groups, event=None):

        # Get variables
        self.ip_protocol = self.data.get(IP_PROTOCOL)
        self.from_port = self.data.get(FROM_PORT)
        self.to_port = self.data.get(TO_PORT)
        self.ports = self.data.get(PORTS)
        self.except_ports = self.data.get(EXCEPT_PORTS)
        self.match_op = self.data.get('match-operator', 'and') == 'and' and all or any

        """
        For each Network Security Group, set the 'securityRules' property to contain
        only rules where there is a match, as defined in 'is_match'
        """
        # Because the filtering actually takes elements out of the list,
        # seemed best to create a copy.
        # Without the deepcopy, in testing, the list is being accessed and
        # altered by different tests, causing each other to fail
        nsgs = deepcopy(network_security_groups)

        for nsg in nsgs:
            nsg['properties']['securityRules'] = \
                [rule for rule in nsg['properties']['securityRules']
                 if self.is_match(rule)]
        """
        Set network_security_groups to include only those that still have 'securityRules'
        after the filtering has taken place
        """
        nsgs = \
            [nsg for nsg in nsgs if len(nsg['properties']['securityRules']) > 0]
        return nsgs

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
        if self.except_ports:
            for port in self.except_ports:
                if len(dest_port_range) > 1:
                    if port >= dest_port_range[0] and port <= dest_port_range[1]:
                        return False
                else:
                    if dest_port_range[0] == port:
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
        if not any([self.from_port, self.to_port, self.except_ports, self.ports]):
            return True
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
        {} - Specific Ports to target
        {} - Ports to IGNORE
        {} - Lower bound of port range (inclusive)
        {} - Upper bound of port range (inclusive)
        {} - TCP/UDP protocol
    """.format(PORTS, EXCEPT_PORTS, FROM_PORT, TO_PORT, IP_PROTOCOL)

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
            PORTS: {'type': 'array', 'items': {'type': 'integer'}},
            EXCEPT_PORTS: {'type': 'array', 'items': {'type': 'integer'}},
            FROM_PORT: {'type': 'integer'},
            TO_PORT: {'type': 'integer'},
            IP_PROTOCOL: {'type': 'string', 'enum': ['TCP', 'UDP']}
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
            PORTS: {'type': 'array', 'items': {'type': 'integer'}},
            EXCEPT_PORTS: {'type': 'array', 'items': {'type': 'integer'}},
            FROM_PORT: {'type': 'integer'},
            TO_PORT: {'type': 'integer'},
            IP_PROTOCOL: {'type': 'string', 'enum': ['TCP', 'UDP']}
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
                self.manager.log.info("Updating access to '%s' for security rule "
                                      "'%s' in resource group '%s'",
                                      self.access_action, rule['name'], resource_group)
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
    schema = type_schema('close')
    access_action = 'Deny'


@NetworkSecurityGroup.action_registry.register('open')
class OpenRules(RulesAction):
    """
    Allow access to Security Rule
    """
    schema = type_schema('open')
    access_action = 'Allow'
