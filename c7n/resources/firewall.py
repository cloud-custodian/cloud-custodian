# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


from c7n.query import (
    QueryResourceManager,
    TypeInfo,
    DescribeSource,
    ConfigSource)


class FirewallDescribe(DescribeSource):

    def augment(self, resources):
        resources = super().augment(resources)
        for r in resources:
            status = r.pop('FirewallStatus', {})
            r = r.pop('Firewall')
            r['FirewallStatus'] = status
        return resources


class NetworkFirewall(QueryResourceManager):

    source_mapping = {
        'describe': FirewallDescribe,
        'config': ConfigSource
    }

    class resource_type(TypeInfo):

        service = 'network-firewall'
        enum_spec = ('list_firewalls', 'Firewalls', None)
        arn = 'FirewallArn'
        detail_spec = ('describe_firewall', 'FirewallArn', 'FirewallArn', '')
        id = name = 'FirewallName'
        cfn_type = config_type = 'AWS::Network::Firewall'
        metrics_namespace = 'AWS/NetworkFirewall'
