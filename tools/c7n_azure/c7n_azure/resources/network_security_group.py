# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import uuid

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.utils import StringUtils, PortsRangeHelper
from azure.core.exceptions import AzureError

from c7n.actions import BaseAction
from c7n.filters import Filter, FilterValidationError
from c7n.filters.core import PolicyValidationError, ValueFilter
from c7n.utils import type_schema

from msrestazure.tools import parse_resource_id


@resources.register('networksecuritygroup')
class NetworkSecurityGroup(ArmResourceManager):
    """Network Security Group Resource

    :example:

    This policy will deny access to all ports that are NOT 22, 23 or 24
    for all Network Security Groups

    .. code-block:: yaml

          policies:
           - name: close-inbound-except-22-24
             resource: azure.networksecuritygroup
             filters:
              - type: ingress
                exceptPorts: '22-24'
                match: 'any'
                access: 'Allow'
             actions:
              - type: close
                exceptPorts: '22-24'
                direction: 'Inbound'

    :example:

    This policy will find all NSGs with port 80 opened and port 443 closed,
    then it will open port 443

    .. code-block:: yaml

         policies:
           - name: close-egress-except-TCP
             resource: azure.networksecuritygroup
             filters:
              - type: ingress
                ports: '80'
                access: 'Allow'
              - type: ingress
                ports: '443'
                access: 'Deny'
             actions:
              - type: open
                ports: '443'


    :example:

    This policy will find all NSGs with port 22 opened from 'Any' source

    .. code-block:: yaml

         policies:
           - name: find-ingress-SSH-from-any-source
             resource: azure.networksecuritygroup
             filters:
              - type: ingress
                ports: '22'
                access: 'Allow'
                source: '*'


    :example:

    This policy will find all NSGs with port 8080 enabled to 'Any' destination

    .. code-block:: yaml

         policies:
           - name: find-egress-HTTP-to-any-destination
             resource: azure.networksecuritygroup
             filters:
              - type: egress
                ports: '8080'
                access: 'Allow'
                destination: '*'

    """

    class resource_type(ArmResourceManager.resource_type):
        doc_groups = ['Networking']

        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('network_security_groups', 'list_all', None)
        resource_type = 'Microsoft.Network/networkSecurityGroups'


DIRECTION = 'direction'
PORTS = 'ports'
MATCH = 'match'
EXCEPT_PORTS = 'exceptPorts'
IP_PROTOCOL = 'ipProtocol'
ACCESS = 'access'
PREFIX = 'prefix'

ALLOW_OPERATION = 'Allow'
DENY_OPERATION = 'Deny'

PRIORITY_STEP = 10

SOURCE = 'source'
DESTINATION = 'destination'

CIDR = 'Cidr'


class NetworkSecurityGroupFilter(Filter):
    """
    Filter Network Security Groups using opened/closed ports configuration
    """

    schema = {
        'type': 'object',
        'properties': {
            'type': {'enum': []},
            MATCH: {'type': 'string', 'enum': ['all', 'any']},
            PORTS: {'type': 'string'},
            EXCEPT_PORTS: {'type': 'string'},
            IP_PROTOCOL: {'type': 'string', 'enum': ['ICMP', 'TCP', 'UDP', '*']},
            ACCESS: {'type': 'string', 'enum': [ALLOW_OPERATION, DENY_OPERATION]},
            SOURCE: {'type': 'string'},
            DESTINATION: {'type': 'string'},
            CIDR: {}
        },
        'required': ['type', ACCESS]
    }

    def validate(self):
        # Check that variable values are valid

        if PORTS in self.data:
            if not PortsRangeHelper.validate_ports_string(self.data[PORTS]):
                raise FilterValidationError("ports string has wrong format.")

        if EXCEPT_PORTS in self.data:
            if not PortsRangeHelper.validate_ports_string(self.data[EXCEPT_PORTS]):
                raise FilterValidationError("exceptPorts string has wrong format.")
        return True

    def process(self, network_security_groups, event=None):
        # List of NSG matching the policies, to return
        matched = []
        # Get variables
        self.ip_protocol = self.data.get(IP_PROTOCOL, '*')
        self.IsAllowed = StringUtils.equal(self.data.get(ACCESS), ALLOW_OPERATION)
        self.match = self.data.get(MATCH, 'all')

        # Calculate ports from the settings:
        #   If ports not specified -- assuming the entire range
        #   If except_ports not specifed -- nothing
        ports_set = PortsRangeHelper.get_ports_set_from_string(self.data.get(PORTS, '0-65535'))
        except_set = PortsRangeHelper.get_ports_set_from_string(self.data.get(EXCEPT_PORTS, ''))
        self.ports = ports_set.difference(except_set)
        self.source_address = self.data.get(SOURCE, None)
        self.destination_address = self.data.get(DESTINATION, None)

        match_op = self.data.get('match-operator', 'and') == 'and' and all or any
        matching_nsg = {}
        for nsg in network_security_groups:
            matching_nsg['check_nsg'] = self._check_nsg(nsg)
            if self.data.get(CIDR):
                matching_nsg['check_cidr'] = False

                permissions_to_expand = []
                for security_rule in nsg['properties']['securityRules']:
                    if security_rule['properties']['direction'] == self.direction_key:
                        permissions_to_expand.append(security_rule['properties'])
                for perm in self.expand_permissions(permissions_to_expand):
                    if self._process_cidrs(perm):
                        matching_nsg['check_cidr'] = True
            matching_nsg_values = list(filter(
                    lambda x: x is not None, matching_nsg.values()))

            if match_op == all and not matching_nsg_values:
                continue

            match = match_op(matching_nsg_values)
            if match:
                matched.append(nsg)
        return matched

    def expand_permissions(self, permissions):
        for p in permissions:
            yield dict(p)

    def _process_cidr(self, cidr_key, cidr_type, range_type, perm):
        found = None
        access_perms = self.data.get(ACCESS)
        if perm['access'] != access_perms:
            return False

        ip_perms = perm.get(range_type, [])
        if not ip_perms:
            return False

        if ip_perms.lower() == "internet":
            return False

        match_range = self.data[cidr_key]

        if isinstance(match_range, dict):
            match_range['key'] = cidr_type
        else:
            match_range = {cidr_type: match_range}

        vf = ValueFilter(match_range, self.manager)
        vf.annotate = False

        found = vf({cidr_type: ip_perms})
        return found

    def _process_cidrs(self, perm):
        found_v4 = False
        if 'Cidr' in self.data:
            found_v4 = self._process_cidr(
                'Cidr',
                'CidrIp',
                f"{self.data['Cidr']['ipType'].lower()}AddressPrefix",
                perm)
        return found_v4

    def _check_nsg(self, nsg):
        nsg_ports = PortsRangeHelper.build_ports_dict(nsg, self.direction_key, self.ip_protocol,
                                                      self.source_address,
                                                      self.destination_address)

        num_allow_ports = len([p for p in self.ports if nsg_ports.get(p)])
        num_deny_ports = len(self.ports) - num_allow_ports

        if self.match == 'all':
            if self.IsAllowed:
                return num_deny_ports == 0
            else:
                return num_allow_ports == 0
        if self.match == 'any':
            if self.IsAllowed:
                return num_allow_ports > 0
            else:
                return num_deny_ports > 0


@NetworkSecurityGroup.filter_registry.register('ingress')
class IngressFilter(NetworkSecurityGroupFilter):
    direction_key = 'Inbound'
    schema = type_schema('ingress', rinherit=NetworkSecurityGroupFilter.schema)


@NetworkSecurityGroup.filter_registry.register('egress')
class EgressFilter(NetworkSecurityGroupFilter):
    direction_key = 'Outbound'
    schema = type_schema('egress', rinherit=NetworkSecurityGroupFilter.schema)


@NetworkSecurityGroup.filter_registry.register('flow-logs')
class FlowLogs(ValueFilter):
    """Filter a Network Security Group by its associated flow logs. NOTE: only one flow log
    can be assigned to a Network Security Group, but to maintain parity with the Azure API, a list
    of flow logs is returned to the filter.

    :example:

    Find all network security groups with a flow-log retention less than 90 days

    .. code-block:: yaml

        policies:
          - name: flow-logs
            resource: azure.networksecuritygroup
            filters:
              - or:
                - type: flow-logs
                  key: logs
                  value: empty
                - type: flow-logs
                  key: logs[0].retentionPolicy.days
                  op: lt
                  value: 90
    """

    schema = type_schema('flow-logs', rinherit=ValueFilter.schema)

    def _get_flow_logs(self, resource):
        parsed_ids = [
            parse_resource_id(log['id'])
            for log in resource['properties'].get('flowLogs', [])
        ]

        client = self.manager.get_client()

        return [
            client.flow_logs.get(
                parsed_id['resource_group'],
                parsed_id['name'],
                parsed_id['resource_name']
            ).serialize(True).get('properties')
            for parsed_id in parsed_ids
        ]

    def __call__(self, resource):
        key = 'c7n:flow-logs'

        if key not in resource['properties']:
            resource['properties'][key] = {'logs': self._get_flow_logs(resource)}

        return super().__call__(resource['properties'][key])


class NetworkSecurityGroupPortsAction(BaseAction):
    """
    Action to perform on Network Security Groups
    """

    schema = {
        'type': 'object',
        'properties': {
            'type': {'enum': []},
            PORTS: {'type': 'string'},
            EXCEPT_PORTS: {'type': 'string'},
            IP_PROTOCOL: {'type': 'string', 'enum': ['ICMP', 'TCP', 'UDP', '*']},
            DIRECTION: {'type': 'string', 'enum': ['Inbound', 'Outbound']},
            PREFIX: {'type': 'string', 'maxLength': 44}  # 80 symbols limit, guid takes 36
        },
        'required': ['type', DIRECTION]
    }

    def validate(self):
        # Check that variable values are valid

        if PORTS in self.data:
            if not PortsRangeHelper.validate_ports_string(self.data[PORTS]):
                raise PolicyValidationError("ports string has wrong format.")

        if EXCEPT_PORTS in self.data:
            if not PortsRangeHelper.validate_ports_string(self.data[EXCEPT_PORTS]):
                raise PolicyValidationError("exceptPorts string has wrong format.")
        return True

    def _build_ports_strings(self, nsg, direction_key, ip_protocol):
        nsg_ports = PortsRangeHelper.build_ports_dict(nsg, direction_key, ip_protocol)

        IsAllowed = StringUtils.equal(self.access_action, ALLOW_OPERATION)

        # Find ports with different access level from NSG and this action
        diff_ports = sorted([p for p in self.action_ports if nsg_ports.get(p, False) != IsAllowed])

        return PortsRangeHelper.get_ports_strings_from_list(diff_ports)

    def process(self, network_security_groups):

        ip_protocol = self.data.get(IP_PROTOCOL, '*')
        direction = self.data[DIRECTION]
        prefix = self.data.get(PREFIX, 'c7n-policy-')
        # Build a list of ports described in the action.
        ports = PortsRangeHelper.get_ports_set_from_string(self.data.get(PORTS, '0-65535'))
        except_ports = PortsRangeHelper.get_ports_set_from_string(self.data.get(EXCEPT_PORTS, ''))
        self.action_ports = ports.difference(except_ports)

        for nsg in network_security_groups:
            nsg_name = nsg['name']
            resource_group = nsg['resourceGroup']

            # Get list of ports to Deny or Allow access to.
            ports = self._build_ports_strings(nsg, direction, ip_protocol)
            if not ports:
                # If its empty, it means NSG already blocks/allows access to all ports,
                # no need to change.
                self.manager.log.info("Network security group %s satisfies provided "
                                      "ports configuration, no actions scheduled.", nsg_name)
                continue

            rules = nsg['properties']['securityRules']
            rules = sorted(rules, key=lambda k: k['properties']['priority'])
            rules = [r for r in rules
                     if StringUtils.equal(r['properties']['direction'], direction)]
            lowest_priority = rules[0]['properties']['priority'] if len(rules) > 0 else 4096

            # Create new top-priority rule to allow/block ports from the action.
            rule_name = prefix + str(uuid.uuid1())
            new_rule = {
                'name': rule_name,
                'properties': {
                    'access': self.access_action,
                    'destinationAddressPrefix': '*',
                    'destinationPortRanges': ports,
                    'direction': self.data[DIRECTION],
                    'priority': lowest_priority - PRIORITY_STEP,
                    'protocol': ip_protocol,
                    'sourceAddressPrefix': '*',
                    'sourcePortRange': '*',
                }
            }
            self.manager.log.info("NSG %s. Creating new rule to %s access for ports %s",
                                  nsg_name, self.access_action, ports)

            try:
                self.manager.get_client().security_rules.begin_create_or_update(
                    resource_group,
                    nsg_name,
                    rule_name,
                    new_rule
                )
            except AzureError as e:
                self.manager.log.error('Failed to create or update security rule for %s NSG.',
                                       nsg_name)
                self.manager.log.error(e)


@NetworkSecurityGroup.action_registry.register('close')
class CloseRules(NetworkSecurityGroupPortsAction):
    """
    Deny access to Security Rule
    """
    schema = type_schema('close', rinherit=NetworkSecurityGroupPortsAction.schema)
    access_action = DENY_OPERATION


@NetworkSecurityGroup.action_registry.register('open')
class OpenRules(NetworkSecurityGroupPortsAction):
    """
    Allow access to Security Rule
    """
    schema = type_schema('open', rinherit=NetworkSecurityGroupPortsAction.schema)
    access_action = ALLOW_OPERATION
