# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import re

from c7n_gcp.actions import MethodAction
from c7n_gcp.query import QueryResourceManager, TypeInfo

from c7n_gcp.provider import resources
from c7n.filters.core import ListItemFilter
from c7n.utils import type_schema, local_session
from c7n_gcp.utils import get_firewall_port_ranges


@resources.register('vpc')
class Network(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/networks
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'networks'
        scope_template = "{}"
        name = id = "name"
        default_report_fields = [
            "name", "description", "creationTimestamp",
            "autoCreateSubnetworks", "IPv4Range", "gatewayIPv4"]
        asset_type = "compute.googleapis.com/Network"
        scc_type = "google.compute.Network"
        urn_component = "vpc"

        @staticmethod
        def get(client, resource_info):
            path_param_re = re.compile('.*?/projects/(.*?)/global/networks/(.*)')
            project, network = path_param_re.match(
                resource_info["resourceName"]).groups()
            return client.execute_query(
                'get', {'project': project, 'network': network})


@Network.filter_registry.register('firewall')
class VPCFirewallFilter(ListItemFilter):
    schema = type_schema(
        'firewall',
        attrs={'$ref': '#/definitions/filters_common/list_item_attrs'}
    )
    annotate_items = True
    permissions = ("vpcaccess.locations.list",)

    def get_item_values(self, resource):
        session = local_session(self.manager.session_factory)
        client = session.client(service_name='compute', version='v1',
                                component='networks')
        project = session.get_default_project()
        firewalls = client.execute_query('getEffectiveFirewalls', {
            'project': project, 'network': resource['name']}).get('firewalls')
        return firewalls


@resources.register('subnet')
class Subnet(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/subnetworks
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'subnetworks'
        enum_spec = ('aggregatedList', 'items.*.subnetworks[]', None)
        name = id = "name"
        default_report_fields = [
            "name", "description", "creationTimestamp", "ipCidrRange",
            "gatewayAddress", "region", "state"]
        asset_type = "compute.googleapis.com/Subnetwork"
        scc_type = "google.compute.Subnetwork"
        metric_key = "resource.labels.subnetwork_name"
        urn_component = "subnet"

        @staticmethod
        def get(client, resource_info):

            path_param_re = re.compile(
                '.*?projects/(.*?)/regions/(.*?)/subnetworks/(.*)')
            project, region, subnet = path_param_re.match(
                resource_info["resourceName"]).groups()
            return client.execute_query(
                'get', {'project': project, 'region': region, 'subnetwork': subnet})


class SubnetAction(MethodAction):

    path_param_re = re.compile(
        '.*?/projects/(.*?)/regions/(.*?)/subnetworks/(.*)')

    def get_resource_params(self, model, resource):
        project, region, subnet = self.path_param_re.match(
            resource['selfLink']).groups()
        return {'project': project, 'region': region, 'subnetwork': subnet}


@Subnet.action_registry.register('set-flow-log')
class SetFlowLog(SubnetAction):
    """Enable vpc flow logs on a subnet.

    :example: Enable flow logs on all subnets

    .. yaml:

     policies:
       - name: flow-active
         resource: gcp.subnet
         filters:
          - enableFlowLogs: empty
         actions:
          - set-flow-log

    """

    schema = type_schema(
        'set-flow-log',
        state={'type': 'boolean', 'default': True})
    method_spec = {'op': 'patch'}
    method_perm = 'update'

    def get_resource_params(self, m, r):
        params = super(SetFlowLog, self).get_resource_params(m, r)
        return {
            'project': params['project'],
            'region': params['region'],
            'subnetwork': params['subnetwork'],
            'body': {
                'fingerprint': r['fingerprint'],
                'enableFlowLogs': self.data.get('state', True)}
        }


@Subnet.action_registry.register('set-private-api')
class SetGcpPrivateAccess(SubnetAction):
    """Enable/Disable GCP Private IP Access for a subnet"""

    schema = type_schema(
        'set-gcp-private',
        state={'type': 'boolean', 'default': True})
    method_spec = {'op': 'setPrivateIpGoogleAccess'}

    def get_resource_params(self, m, r):
        params = super(SetGcpPrivateAccess, self).get_resource_params(m, r)
        params['body'] = {
            'privateIpGoogleAccess': self.data.get('state', True)}
        return params


@resources.register('firewall')
class Firewall(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/firewalls
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'firewalls'
        name = id = "name"
        default_report_fields = [
            name, "description", "network", "priority", "creationTimestamp",
            "logConfig.enable", "disabled"]
        asset_type = "compute.googleapis.com/Firewall"
        scc_type = "google.compute.Firewall"
        metric_key = 'metric.labels.firewall_name'
        urn_component = "firewall"

        @staticmethod
        def get(client, resource_info):
            return client.execute_query(
                'get', {'project': resource_info['project_id'],
                        'firewall': resource_info['resourceName'].rsplit('/', 1)[-1]})

    def augment(self, resources):
        if not resources:
            return []
        return get_firewall_port_ranges(resources)


@Firewall.action_registry.register('delete')
class DeleteFirewall(MethodAction):
    """Delete filtered Firewall Rules

    :example: Delete firewall rule

    .. yaml:

     policies:
       - name: delete-public-access-firewall-rules
         resource: gcp.firewall
         filters:
         - type: value
           key: sourceRanges
           value: "0.0.0.0/0"
           op: in
           value_type: swap
         actions:
         - delete
    """

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    path_param_re = re.compile('.*?/projects/(.*?)/global/firewalls/(.*)')

    def get_resource_params(self, m, r):
        project, resource_name = self.path_param_re.match(
            r['selfLink']).groups()
        return {'project': project, 'firewall': resource_name}


@Firewall.action_registry.register('modify')
class ModifyFirewall(MethodAction):
    """Modify filtered Firewall Rules

    :example: Enable logging on filtered firewalls

    .. yaml:

     policies:
       - name: enable-firewall-logging
         resource: gcp.firewall
         filters:
         - type: value
           key: name
           value: no-logging
         actions:
         - type: modify
           logConfig:
             enabled: true
    """

    schema = type_schema(
        'modify',
        **{'description': {'type': 'string'},
           'network': {'type': 'string'},
           'priority': {'type': 'number'},
           'sourceRanges': {'type': 'array', 'items': {'type': 'string'}},
           'destinationRanges': {'type': 'array', 'items': {'type': 'string'}},
           'sourceTags': {'type': 'array', 'items': {'type': 'string'}},
           'targetTags': {'type': 'array', 'items': {'type': 'string'}},
           'sourceServiceAccounts': {'type': 'array', 'items': {'type': 'string'}},
           'targetServiceAccounts': {'type': 'array', 'items': {'type': 'string'}},
           'allowed': {'type': 'array', 'items': {'type': 'object'}},
           'denied': {'type': 'array', 'items': {'type': 'object'}},
           'direction': {'enum': ['INGRESS', 'EGRESS']},
           'logConfig': {'type': 'object'},
           'disabled': {'type': 'boolean'}})
    method_spec = {'op': 'patch'}
    permissions = ('compute.networks.updatePolicy', 'compute.firewalls.update')
    path_param_re = re.compile('.*?/projects/(.*?)/global/firewalls/(.*)')

    def get_resource_params(self, m, r):
        project, resource_name = self.path_param_re.match(
            r['selfLink']).groups()
        return {'project': project, 'firewall': resource_name, 'body': self.data}


@resources.register('router')
class Router(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/routers
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'routers'
        enum_spec = ('aggregatedList', 'items.*.routers[]', None)
        name = id = 'name'
        default_report_fields = [
            "name", "description", "creationTimestamp", "region", "network"]
        asset_type = "compute.googleapis.com/Router"
        urn_component = "router"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project_id'],
                        'region': resource_info['region'],
                        'router': resource_info['resourceName'].rsplit('/', 1)[-1]})


@Router.action_registry.register('delete')
class DeleteRouter(MethodAction):
    """`Deletes <https://cloud.google.com/compute/docs/reference/rest/v1/routers/delete>`_ a router

    :Example:

    .. code-block:: yaml

        policies:
          - name: gcp-network-unattached-routers
            description: Deletes unattached Cloud Routers
            resource: gcp.router
            filters:
               - type: value
                 key: interfaces
                 value: absent
            actions:
               - delete
    """

    schema = type_schema('delete')
    method_spec = {'op': 'delete'}
    path_param_re = re.compile('.*?/projects/(.*?)/regions/(.*?)/routers/(.*)')

    def get_resource_params(self, m, r):
        project, region, router = self.path_param_re.match(r['selfLink']).groups()
        return {'project': project, 'region': region, 'router': router}


@resources.register('route')
class Route(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/routes
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'routes'
        enum_spec = ('list', 'items[]', None)
        name = id = 'name'
        default_report_fields = [
            "name", "description", "creationTimestamp", "network", "priority", "destRange"]
        asset_type = "compute.googleapis.com/Route"
        urn_component = "route"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project_id'],
                        'route': resource_info['resourceName'].rsplit('/', 1)[-1]})


@resources.register('interconnect')
class Interconnect(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/interconnects
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'interconnects'
        enum_spec = ('list', 'items[]', None)
        name = id = 'name'
        default_report_fields = [
            "name", "description", "creationTimestamp", "operationalStatus",
            "linkType", "location"]
        asset_type = "compute.googleapis.com/Interconnect"

        @staticmethod
        def get(client, resource_info):
            return client.execute_command(
                'get', {'project': resource_info['project_id'],
                        'interconnect': resource_info['resourceName'].rsplit('/', 1)[-1]})


@resources.register('interconnect-attachment')
class InterconnectAttachment(QueryResourceManager):
    """GCP resource: https://cloud.google.com/compute/docs/reference/rest/v1/interconnectAttachments
    """
    class resource_type(TypeInfo):
        service = 'compute'
        version = 'v1'
        component = 'interconnectAttachments'
        enum_spec = ('aggregatedList', 'items.*.interconnectAttachments[]', None)
        name = id = 'name'
        default_report_fields = [
            "name", "description", "creationTimestamp", "interconnect",
            "router", "region", "operationalStatus"]
        asset_type = "compute.googleapis.com/InterconnectAttachment"

        @staticmethod
        def get(client, resource_info):
            project, region, name = re.match(
                'projects/(.*?)/regions/(.*?)/interconnectAttachments/(.*?)',
                resource_info['resourceName']).groups()

            return client.execute_command(
                'get', {'project': project,
                        'interconnectAttachment': name,
                        'region': region})
