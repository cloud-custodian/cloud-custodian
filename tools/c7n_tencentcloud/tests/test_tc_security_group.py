# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from tc_common import BaseTest


class TestSecurityGroup(BaseTest):

    @pytest.mark.vcr
    def test_security_group_default_restrict(self):
        policy = self.load_policy(
            {
                "name": "test_security_group_default_restrict",
                "resource": "tencentcloud.security-group",
                "query": [{
                    "SecurityGroupIds": ["sg-m5jbq9cu", "sg-1kmlb9mm"]
                }],
                "filters": [
                    {
                        "or": [
                            {
                                "SecurityGroupName": "ccsTest"
                            }, {
                                "SecurityGroupName": "base-ritch"
                            },
                        ]
                    },
                    {
                        "or": [
                            {
                                "IpPermissions": "not-null"
                            }, {
                                "IpPermissionsEgress": "not-null"
                            }
                        ]
                    }
                ]
            }
        )
        resources = policy.run()
        assert len(resources) == 1 and resources[0]["SecurityGroupName"] == "base-ritch"

    def test_ports_ingress(self):
        resources = [
            {
                'SecurityGroupId': 'sg-18k4jd20',
                'SecurityGroupName': 'dandiao_test',
                'TagSet': [],
                'IpPermissions': [
                    {
                        'PolicyIndex': 0,
                        'Port': 'ALL',
                        'CidrBlock': '192.168.0.0/16',
                        'Ipv6CidrBlock': '',
                        'SecurityGroupId': '',
                        'Action': 'ACCEPT'
                    }
                ],
                'IpPermissionsEgress': []}
        ]
        policy = self.load_policy(
            {
                "name": "test_ports_ingress",
                "resource": "tencentcloud.security-group",
                "filters": [{"type": "ingress", "Ports": [60]}]
            }
        )
        manager = policy.load_resource_manager()
        resources_all_ports = manager.filter_resources(resources)
        assert len(resources_all_ports) == 1

        resources[0]['IpPermissions'][0].update({'Port': '60, 70'})
        resources_multiple_ports = manager.filter_resources(resources)
        assert len(resources_multiple_ports) == 1

        resources[0]['IpPermissions'][0].update({'Port': '50-70'})
        resources_range_ports = manager.filter_resources(resources)
        assert len(resources_range_ports) == 1

        resources[0]['IpPermissions'][0].update({'Port': '60'})
        resources_only_port = manager.filter_resources(resources)
        assert len(resources_only_port) == 1

    def test_any_ports_except_ingress(self):
        resources = [
            {
                'SecurityGroupId': 'sg-18k4jd20',
                'SecurityGroupName': 'dandiao_test',
                'TagSet': [],
                'IpPermissions': [
                    {
                        'PolicyIndex': 0,
                        'Port': 'ALL',
                        'CidrBlock': '192.168.0.0/16',
                        'Ipv6CidrBlock': '',
                        'SecurityGroupId': '',
                        'Action': 'ACCEPT'
                    }, {
                        'PolicyIndex': 0,
                        'Port': '60',
                        'CidrBlock': '192.168.0.0/16',
                        'Ipv6CidrBlock': '',
                        'SecurityGroupId': '',
                        'Action': 'ACCEPT'
                    }
                ],
                'IpPermissionsEgress': []}
        ]
        policy = self.load_policy(
            {
                "name": "test_any_ports_except_ingress",
                "resource": "tencentcloud.security-group",
                "filters": [{"type": "ingress", "AnyPortsExcept": [60, 70]}]
            }
        )
        manager = policy.load_resource_manager()
        resources_all_ports = manager.filter_resources(resources)
        assert len(resources_all_ports) == 1

        resources[0]['IpPermissions'][0].update({'Port': '60, 70'})
        resources_multiple_ports = manager.filter_resources(resources)
        assert len(resources_multiple_ports) == 0

        resources[0]['IpPermissions'][0].update({'Port': '50-70'})
        resources_range_ports = manager.filter_resources(resources)
        assert len(resources_range_ports) == 1

        resources[0]['IpPermissions'][0].update({'Port': '60'})
        resources_only_port = manager.filter_resources(resources)
        assert len(resources_only_port) == 0

        policy = self.load_policy(
            {
                "name": "test_any_ports_except_ingress",
                "resource": "tencentcloud.security-group",
                "filters": [
                    {"type": "ingress",
                     "AnyPortsExcept": [70],
                     "Ports": [60]
                     }]
            }
        )
        manager = policy.load_resource_manager()
        resources_only_port = manager.filter_resources(resources)
        assert len(resources_only_port) == 1

    def test_cidr_egress(self):
        resources = [
            {
                'SecurityGroupId': 'sg-18k4jd20',
                'SecurityGroupName': 'dandiao_test',
                'TagSet': [],
                'IpPermissions': [],
                'IpPermissionsEgress': [
                    {
                        'PolicyIndex': 0,
                        'Port': 'ALL',
                        'CidrBlock': '192.168.0.0/24',
                        'Ipv6CidrBlock': '',
                        'SecurityGroupId': '',
                        'Action': 'ACCEPT'
                    }
                ]}
        ]
        policy = self.load_policy(
            {
                "name": "test_cidr_egress",
                "resource": "tencentcloud.security-group",
                "query": [{
                    "SecurityGroupIds": ["sg-18k4jd20"]
                }],
                "filters": [
                    {
                        "type": "egress",
                        "Cidr": {
                            "value": "192.168.0.0/16",
                            "op": "in",
                            "value_type": "cidr"
                        }
                    }
                ]
            }
        )
        manager = policy.load_resource_manager()
        policy_cidr_gt_range = manager.filter_resources(resources)
        assert len(policy_cidr_gt_range) == 1

        resources[0]['IpPermissionsEgress'][0].update({'CidrBlock': '192.168.0.0/16'})
        policy_ip_eq_range = manager.filter_resources(resources)
        assert len(policy_ip_eq_range) == 1

        resources[0]['IpPermissionsEgress'][0].update({'CidrBlock': '192.168.0.0/8'})
        policy_ip_lt_range = manager.filter_resources(resources)
        assert len(policy_ip_lt_range) == 0

    def test_cidr_ip_ingress(self):
        resources = [
            {
                'SecurityGroupId': 'sg-18k4jd20',
                'SecurityGroupName': 'dandiao_test',
                'TagSet': [],
                'IpPermissions': [
                    {
                        'PolicyIndex': 0,
                        'Port': 'ALL',
                        'CidrBlock': '192.168.0.0/24',
                        'Ipv6CidrBlock': '',
                        'SecurityGroupId': '',
                        'Action': 'ACCEPT'
                    }
                ],
                'IpPermissionsEgress': []}
        ]
        policy = self.load_policy(
            {
                "name": "test_cidr_ip_ingress",
                "resource": "tencentcloud.security-group",
                "filters": [
                    {"type": "ingress",
                     "Cidr": {
                         "value": "192.168.1.1",
                         "op": "in",
                         "value_type": "cidr"
                     }}
                ]
            }
        )
        manager = policy.load_resource_manager()
        resources_ip_not_in_range = manager.filter_resources(resources)
        assert len(resources_ip_not_in_range) == 0

        resources[0]['IpPermissions'][0].update({'CidrBlock': '192.168.0.0/16'})
        resources_ip_in_range = manager.filter_resources(resources)
        assert len(resources_ip_in_range) == 1

    def test_cidr_not_limit_filter(self):
        resources = [
            {
                'SecurityGroupId': 'sg-18k4jd20',
                'SecurityGroupName': 'dandiao_test',
                'TagSet': [],
                'IpPermissions': [
                    {
                        'PolicyIndex': 0,
                        'Port': 'ALL',
                        'CidrBlock': '',
                        'Ipv6CidrBlock': '::/0',
                        'SecurityGroupId': '',
                        'Action': 'ACCEPT'
                    }
                ],
                'IpPermissionsEgress': []}
        ]
        policy = self.load_policy(
            {
                "name": "test_cidr_not_limit_filter",
                "resource": "tencentcloud.security-group",
                "filters": [
                    {
                        "or": [
                            {
                                "type": "ingress",
                                "Cidr": {
                                    "value": "0.0.0.0/0"
                                }
                            },
                            {
                                "type": "ingress",
                                "CidrV6": {
                                    "value": "::/0"
                                }
                            }
                        ]
                    }
                ]
            }
        )
        manager = policy.load_resource_manager()
        resources_ip_not_in_range = manager.filter_resources(resources)
        assert len(resources_ip_not_in_range) == 1

    @pytest.mark.vcr
    def test_security_group_used(self):
        policy = self.load_policy(
            {
                "name": "test_security_group_used",
                "resource": "tencentcloud.security-group",
                "query": [{"SecurityGroupIds": ["sg-jep2pqxk"]}],
                "filters": [{
                    "type": "used",
                    "key": "CVM",
                    "value": 0,
                    "op": "greater-than"
                }]
            }
        )
        resources = policy.run()
        ok = [r for r in resources if r["SecurityGroupId"] == "sg-jep2pqxk"]
        assert len(ok) == 1
