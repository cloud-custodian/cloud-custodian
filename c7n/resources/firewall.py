# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

from .aws import AWS
from c7n.query import (
    QueryResourceManager, TypeInfo, DescribeSource, ConfigSource)
from c7n.filters.vpc import VpcFilter, SubnetFilter


class FirewallDescribe(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        for r in resources:
            status = r.pop('FirewallStatus', {})
            r['Firewall']['UpdateToken'] = r['UpdateToken']
            r = r.pop('Firewall')
            r['FirewallStatus'] = status
        return resources


class FirewallConfig(ConfigSource):

    def load_resource(self, item):
        resource = super().load_resource(item)
        resource.update(resource.pop('Firewall'))
        return resource


@AWS.resources.register('firewall')
class NetworkFirewall(QueryResourceManager):
    """AWS Network Firewall

    https://docs.aws.amazon.com/network-firewall/latest/developerguide/what-is-aws-network-firewall.html
    """
    source_mapping = {
        'describe': FirewallDescribe,
        'config': FirewallConfig
    }

    class resource_type(TypeInfo):

        service = 'network-firewall'
        enum_spec = ('list_firewalls', 'Firewalls', None)
        arn = 'FirewallArn'
        arn_type = 'firewall'
        detail_spec = ('describe_firewall', 'FirewallArn', 'FirewallArn', '')
        id = name = 'FirewallName'
        cfn_type = config_type = 'AWS::NetworkFirewall::Firewall'
        metrics_namespace = 'AWS/NetworkFirewall'
        universal_taggable = object()


@NetworkFirewall.filter_registry.register('vpc')
class FirewallVpcFilter(VpcFilter):

    RelatedIdsExpression = 'VpcId'


@NetworkFirewall.filter_registry.register('subnet')
class FirewallSubnetFilter(SubnetFilter):

    RelatedIdsExpression = 'SubnetMappings[].SubnetId'
