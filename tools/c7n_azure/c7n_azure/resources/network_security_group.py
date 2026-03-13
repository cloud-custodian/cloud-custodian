# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import uuid

from azure.core.exceptions import AzureError
from msrestazure.tools import parse_resource_id

from c7n.actions import BaseAction
from c7n.filters import Filter, FilterValidationError
from c7n.filters.core import PolicyValidationError, ValueFilter
from c7n.utils import type_schema
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.utils import PortsRangeHelper, StringUtils


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

        # If no port or cider filters to apply, we don't match any groups.
        filter_on_ports = PORTS in self.data
        filter_on_cidr = CIDR in self.data
        if not filter_on_ports and not filter_on_cidr:
            return matched

        if filter_on_ports:
            # Set up a helper outside the loop to pass relevant filter data through to processing
            ports_set = PortsRangeHelper.get_ports_set_from_string(self.data[PORTS])
            except_set = PortsRangeHelper.get_ports_set_from_string(self.data.get(EXCEPT_PORTS, ''))

            def process_ports(nsg):
                return self._process_ports(
                    nsg,
                    ports=ports_set.difference(except_set),
                    ip_protocol=self.data.get(IP_PROTOCOL, '*'),
                    source_address=self.data.get(SOURCE),
                    destination_address=self.data.get(DESTINATION),
                    IsAllowed=StringUtils.equal(self.data.get(ACCESS), ALLOW_OPERATION),
                    match=self.data.get(MATCH, 'all'),
                )

        match_op = self.data.get('match-operator', 'and') == 'and' and all or any
        for nsg in network_security_groups:
            subfilter_evaluations = []  # Boolean results of each subfilter (for any/all evaluation)
            matched_rule_ids = []  # Sets of matched rule ids (empty where subfilter did not match)

            if filter_on_ports:
                ports_matched, port_matched_rule_ids = process_ports(nsg)
                subfilter_evaluations.append(ports_matched)
                matched_rule_ids.append(port_matched_rule_ids)

            if filter_on_cidr:
                cidr_matched, cidr_matched_rule_ids = self._process_cidrs(nsg)
                subfilter_evaluations.append(cidr_matched)
                matched_rule_ids.append(cidr_matched_rule_ids)

            if match_op(subfilter_evaluations):
                if match_op == all:
                    # If rules need to match port AND cidr, report rules that matched both.
                    matched_rule_ids = set.intersection(*matched_rule_ids)
                else:
                    # If rules only need to match port OR cidr, report rules that matched either.
                    matched_rule_ids = set.union(*matched_rule_ids)
                nsg[self.matched_annotation_key] = [
                    r for r in nsg['properties']['securityRules'] if r['id'] in matched_rule_ids
                ]
                matched.append(nsg)
        return matched

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

    def _process_cidrs(self, nsg):
        matched = False
        matched_rules = set()
        for security_rule in nsg['properties']['securityRules']:
            if security_rule['properties']['direction'] == self.direction_key:
                rule_matched = self._process_cidr(
                    'Cidr',
                    'CidrIp',
                    f"{self.data['Cidr']['ipType'].lower()}AddressPrefix",
                    security_rule['properties'],
                )
                if rule_matched:
                    matched = True
                    matched_rules.add(security_rule['id'])
        return matched, matched_rules

    def _process_ports(
        self, nsg, ports, ip_protocol, source_address, destination_address, IsAllowed, match
    ):
        nsg_ports = PortsRangeHelper.build_ports_rules_dict(
            nsg, self.direction_key, ip_protocol, source_address, destination_address
        )

        matched_ports = 0  # Number ports on the filter that were matched to NSGs.
        matched_rules = set()  # Set of rule IDs that caused those port matches.
        for port in ports:
            if info := nsg_ports.get(port):
                if info['allowed'] is IsAllowed:
                    matched_ports += 1
                    matched_rules |= info['by_rules']

        if match == 'all':
            return len(ports) == matched_ports, matched_rules
        if match == 'any':
            return matched_ports > 0, matched_rules


@NetworkSecurityGroup.filter_registry.register('ingress')
class IngressFilter(NetworkSecurityGroupFilter):
    direction_key = 'Inbound'
    schema = type_schema('ingress', rinherit=NetworkSecurityGroupFilter.schema)

    matched_annotation_key = 'c7n:matched-ingress-security-rules'


@NetworkSecurityGroup.filter_registry.register('egress')
class EgressFilter(NetworkSecurityGroupFilter):
    direction_key = 'Outbound'
    schema = type_schema('egress', rinherit=NetworkSecurityGroupFilter.schema)

    matched_annotation_key = 'c7n:matched-egress-security-rules'


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
