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

from .common import BaseTest, functional
from c7n.filters import FilterValidationError


class VpcTest(BaseTest):

    @functional
    def test_flow_logs(self):
        factory = self.replay_flight_data(
            'test_vpc_flow_logs')

        session = factory()
        ec2 = session.client('ec2')
        logs = session.client('logs')

        vpc_id = ec2.create_vpc(CidrBlock="10.4.0.0/16")['Vpc']['VpcId']
        self.addCleanup(ec2.delete_vpc, VpcId=vpc_id)

        p = self.load_policy({
            'name': 'net-find',
            'resource': 'vpc',
            'filters': [
                {'VpcId': vpc_id},
                'flow-logs']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['VpcId'], vpc_id)

        log_group = 'vpc-logs'
        logs.create_log_group(logGroupName=log_group)
        self.addCleanup(logs.delete_log_group, logGroupName=log_group)

        ec2.create_flow_logs(
            ResourceIds=[vpc_id],
            ResourceType='VPC',
            TrafficType='ALL',
            LogGroupName=log_group,
            DeliverLogsPermissionArn='arn:aws:iam::644160558196:role/flowlogsRole')

        p = self.load_policy({
            'name': 'net-find',
            'resource': 'vpc',
            'filters': [
                {'VpcId': vpc_id},
                {'type': 'flow-logs',
                 'enabled': True,
                 'status': 'active',
                 'traffic-type': 'all',
                 'log-group': log_group}]
        }, session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)

    @functional
    def test_flow_logs_absent(self):
        """Test that ONLY vpcs with no flow logs are retained

        'vpc-4a9ff72e' - has no flow logs
        'vpc-d0e386b7' - has flow logs
        """
        factory = self.replay_flight_data(
            'test_vpc_flow_logs_absent')

        vpc_id1 = 'vpc-4a9ff72e'

        p = self.load_policy({
            'name': 'net-find',
            'resource': 'vpc',
            'filters': [
                {'VpcId': vpc_id1},
                'flow-logs']},
            session_factory=factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['VpcId'], vpc_id1)

    @functional
    def test_flow_logs_misconfiguration(self):
        # Validate that each VPC has at least one valid configuration
        #
        # In terms of filters, we then want to flag VPCs for which every
        # flow log configuration has at least one invalid value
        #
        # Here - have 2 vpcs ('vpc-4a9ff72e','vpc-d0e386b7')
        #
        # The first has three flow logs which each have different
        # misconfigured properties The second has one correctly
        # configured flow log, and one where all config is bad
        #
        # Only the first should be returned by the filter

        factory = self.replay_flight_data(
            'test_vpc_flow_logs_misconfigured')

        vpc_id1 = 'vpc-4a9ff72e'

        traffic_type = 'all'
        log_group = '/aws/lambda/myIOTFunction'
        status = 'active'

        p = self.load_policy({
            'name': 'net-find',
            'resource': 'vpc',
            'filters': [
                {'not': [{
                        'type': 'flow-logs',
                        'enabled': True,
                        'op': 'equal',
                        'set-op': 'or',
                        'status': status,
                        'traffic-type': traffic_type,
                        'log-group': log_group
                    }]
                }
            ]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['VpcId'], vpc_id1)


class NetworkLocationTest(BaseTest):

    @functional
    def test_network_location_sg_missing(self):
        self.factory = self.replay_flight_data(
            'test_network_location_sg_missing_loc')
        client = self.factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(
            VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
                'Subnet']['SubnetId']
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier",
            VpcId=vpc_id,
            Description="for apps")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        sg_id = client.create_security_group(
            GroupName="some-tier",
            VpcId=vpc_id,
            Description="for rabbits")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=sg_id)

        nic = client.create_network_interface(
            SubnetId=web_sub_id,
            Groups=[sg_id, web_sg_id]
            )['NetworkInterface']['NetworkInterfaceId']
        self.addCleanup(
            client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[nic, web_sg_id, web_sub_id],
            Tags=[{'Key': 'Location', 'Value': 'web'}])

        p = self.load_policy({
            'name': 'netloc',
            'resource': 'eni',
            'filters': [
                {'NetworkInterfaceId': nic},
                {'type': 'network-location',
                 'key': 'tag:Location'}]
            }, session_factory=self.factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        matched = resources.pop()
        self.assertEqual(
            matched['c7n:NetworkLocation'], [{
                'reason': 'SecurityGroupLocationAbsent',
                'security-groups': {sg_id: None, web_sg_id: 'web'}
            }])

    @functional
    def test_network_location_sg_cardinality(self):
        self.factory = self.replay_flight_data(
            'test_network_location_sg_cardinality')
        client = self.factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(
            VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
                'Subnet']['SubnetId']
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier",
            VpcId=vpc_id,
            Description="for apps")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        db_sg_id = client.create_security_group(
            GroupName="db-tier",
            VpcId=vpc_id,
            Description="for dbs")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=db_sg_id)

        nic = client.create_network_interface(
            SubnetId=web_sub_id,
            Groups=[web_sg_id, db_sg_id])['NetworkInterface']['NetworkInterfaceId']
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[web_sg_id, web_sub_id, nic],
            Tags=[{'Key': 'Location', 'Value': 'web'}])
        client.create_tags(
            Resources=[db_sg_id],
            Tags=[{'Key': 'Location', 'Value': 'db'}])

        p = self.load_policy({
            'name': 'netloc',
            'resource': 'eni',
            'filters': [
                {'NetworkInterfaceId': nic},
                {'type': 'network-location',
                 'key': 'tag:Location'}]
            }, session_factory=self.factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        matched = resources.pop()
        self.assertEqual(
            matched['c7n:NetworkLocation'],
            [{'reason': 'SecurityGroupLocationCardinality',
              'security-groups': {db_sg_id: 'db', web_sg_id: 'web'}},
             {'reason': 'LocationMismatch',
              'security-groups': {db_sg_id: 'db', web_sg_id: 'web'},
              'subnets': {web_sub_id: 'web'}}])

    @functional
    def test_network_location_resource_missing(self):
        self.factory = self.replay_flight_data('test_network_location_resource_missing')
        client = self.factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(
            VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
                'Subnet']['SubnetId']
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier",
            VpcId=vpc_id,
            Description="for apps")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        nic = client.create_network_interface(
            SubnetId=web_sub_id,
            Groups=[web_sg_id])['NetworkInterface']['NetworkInterfaceId']
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[web_sg_id, web_sub_id],
            Tags=[{'Key': 'Location', 'Value': 'web'}])

        p = self.load_policy({
            'name': 'netloc',
            'resource': 'eni',
            'filters': [
                {'NetworkInterfaceId': nic},
                {'type': 'network-location',
                 'key': 'tag:Location'}]
            }, session_factory=self.factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        matched = resources.pop()
        self.assertEqual(
            matched['c7n:NetworkLocation'],
            [{'reason': 'ResourceLocationAbsent', 'resource': None}])

    @functional
    def test_network_location_triple_intersect(self):
        self.factory = self.replay_flight_data('test_network_location_intersection')
        client = self.factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        web_sub_id = client.create_subnet(
            VpcId=vpc_id, CidrBlock="10.4.9.0/24")[
                'Subnet']['SubnetId']
        self.addCleanup(client.delete_subnet, SubnetId=web_sub_id)

        web_sg_id = client.create_security_group(
            GroupName="web-tier",
            VpcId=vpc_id,
            Description="for apps")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=web_sg_id)

        nic = client.create_network_interface(
            SubnetId=web_sub_id,
            Groups=[web_sg_id])['NetworkInterface']['NetworkInterfaceId']
        self.addCleanup(client.delete_network_interface, NetworkInterfaceId=nic)

        client.create_tags(
            Resources=[web_sg_id, web_sub_id, nic],
            Tags=[{'Key': 'Location', 'Value': 'web'}])
        p = self.load_policy({
            'name': 'netloc',
            'resource': 'eni',
            'filters': [
                {'NetworkInterfaceId': nic},
                {'type': 'network-location',
                 'key': 'tag:Location'}]
            }, session_factory=self.factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)



class NetworkAclTest(BaseTest):

    @functional
    def test_s3_cidr_network_acl_present(self):
        factory = self.replay_flight_data('test_network_acl_s3_present')
        client = factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        p = self.load_policy({
            'name': 'nacl-check',
            'resource': 'network-acl',
            'filters': [
                {'VpcId': vpc_id},
                {'type': 's3-cidr', 'present': True}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @functional
    def test_s3_cidr_network_acl_not_present(self):
        factory = self.replay_flight_data(
            'test_network_acl_s3_missing')
        client = factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        acls = client.describe_network_acls(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])['NetworkAcls']

        client.delete_network_acl_entry(
            NetworkAclId=acls[0]['NetworkAclId'],
            RuleNumber=acls[0]['Entries'][0]['RuleNumber'],
            Egress=True)

        p = self.load_policy({
            'name': 'nacl-check',
            'resource': 'network-acl',
            'filters': [
                {'VpcId': vpc_id}, 's3-cidr']},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)


class NetworkInterfaceTest(BaseTest):

    @functional
    def test_interface_subnet(self):
        factory = self.replay_flight_data(
            'test_network_interface_filter')

        client = factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)

        sub_id = client.create_subnet(
            VpcId=vpc_id, CidrBlock="10.4.8.0/24")[
                'Subnet']['SubnetId']
        self.addCleanup(client.delete_subnet, SubnetId=sub_id)

        sg_id = client.create_security_group(
            GroupName="web-tier",
            VpcId=vpc_id,
            Description="for apps")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=sg_id)

        qsg_id = client.create_security_group(
            GroupName="quarantine-group",
            VpcId=vpc_id,
            Description="for quarantine")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=qsg_id)

        net = client.create_network_interface(
            SubnetId=sub_id, Groups=[sg_id])['NetworkInterface']
        net_id = net['NetworkInterfaceId']
        self.addCleanup(
            client.delete_network_interface, NetworkInterfaceId=net_id)

        p = self.load_policy({
            'name': 'net-find',
            'resource': 'eni',
            'filters': [
                {'type': 'subnet',
                 'key': 'SubnetId',
                 'value': sub_id},
                {'type': 'security-group',
                 'key': 'Description',
                 'value': 'for apps'}
            ],
            'actions': [{
                'type': 'modify-security-groups',
                'remove': 'matched',
                'isolation-group': qsg_id}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['NetworkInterfaceId'], net_id)
        self.assertEqual(resources[0]['c7n:matched-security-groups'], [sg_id])
        results = client.describe_network_interfaces(
            NetworkInterfaceIds=[net_id])['NetworkInterfaces']
        self.assertEqual([g['GroupId'] for g in results[0]['Groups']], [qsg_id])


class SecurityGroupTest(BaseTest):

    def test_id_selector(self):
        p = self.load_policy({
            'name': 'sg',
            'resource': 'security-group'})
        self.assertEqual(
            p.resource_manager.match_ids(
                ['vpc-asdf', 'i-asdf3e', 'sg-1235a', 'sg-4671']),
            ['sg-1235a', 'sg-4671'])

    @functional
    def test_stale(self):
        # setup a multi vpc security group reference, break the ref
        # and look for stale
        factory = self.replay_flight_data('test_security_group_stale')
        client = factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")['Vpc']['VpcId']
        vpc2_id = client.create_vpc(CidrBlock="10.5.0.0/16")['Vpc']['VpcId']
        peer_id = client.create_vpc_peering_connection(
            VpcId=vpc_id, PeerVpcId=vpc2_id)[
            'VpcPeeringConnection']['VpcPeeringConnectionId']
        client.accept_vpc_peering_connection(
            VpcPeeringConnectionId=peer_id)
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        self.addCleanup(client.delete_vpc, VpcId=vpc2_id)
        self.addCleanup(client.delete_vpc_peering_connection,
                        VpcPeeringConnectionId=peer_id)
        sg_id = client.create_security_group(
            GroupName="web-tier",
            VpcId=vpc_id,
            Description="for apps")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        t_sg_id = client.create_security_group(
            GroupName="db-tier",
            VpcId=vpc2_id,
            Description="for apps")['GroupId']
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {'IpProtocol': 'tcp',
                 'FromPort': 60000,
                 'ToPort': 62000,
                 'UserIdGroupPairs': [
                     {'GroupId': t_sg_id,
                      'VpcId': vpc2_id,
                      'VpcPeeringConnectionId': peer_id}]}])
        client.delete_security_group(GroupId=t_sg_id)
        p = self.load_policy({
            'name': 'sg-stale',
            'resource': 'security-group',
            'filters': ['stale']
        }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['GroupId'], sg_id)
        self.assertEqual(
            resources[0]['MatchedIpPermissions'],
            [{u'FromPort': 60000,
              u'IpProtocol': u'tcp',
              u'ToPort': 62000,
              u'UserIdGroupPairs': [
                  {u'GroupId': t_sg_id,
                   u'PeeringStatus': u'active',
                   u'VpcId': vpc2_id,
                   u'VpcPeeringConnectionId': peer_id}]}])

    def test_used(self):
        factory = self.replay_flight_data(
            'test_security_group_used')
        p = self.load_policy({
            'name': 'sg-used',
            'resource': 'security-group',
            'filters': ['used']
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 3)
        self.assertEqual(
            set(['sg-f9cc4d9f', 'sg-13de8f75', 'sg-ce548cb7']),
            set([r['GroupId'] for r in resources]))

    def test_unused(self):
        factory = self.replay_flight_data(
            'test_security_group_unused')
        p = self.load_policy({
            'name': 'sg-unused',
            'resource': 'security-group',
            'filters': ['unused'],
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @functional
    def test_only_ports(self):
        factory = self.replay_flight_data(
            'test_security_group_only_ports')
        client = factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="web-tier",
            VpcId=vpc_id,
            Description="for apps")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol='tcp',
            FromPort=60000,
            ToPort=62000,
            CidrIp='10.2.0.0/16')
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol='tcp',
            FromPort=61000,
            ToPort=61000,
            CidrIp='10.2.0.0/16')
        p = self.load_policy({
            'name': 'sg-find',
            'resource': 'security-group',
            'filters': [
                {'type': 'ingress',
                 'OnlyPorts': [61000]},
                {'GroupName': 'web-tier'}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['MatchedIpPermissions'],
            [{u'FromPort': 60000,
              u'IpProtocol': u'tcp',
              u'Ipv6Ranges': [],
              u'IpRanges': [{u'CidrIp': u'10.2.0.0/16'}],
              u'PrefixListIds': [],
              u'ToPort': 62000,
              u'UserIdGroupPairs': []}])

    @functional
    def test_self_reference(self):
        factory = self.replay_flight_data(
            'test_security_group_self_reference')
        client = factory().client('ec2')

        vpc_id = client.create_vpc(CidrBlock='10.4.0.0/16')['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        # Find the ID of the default security group.
        default_sg_id = client.describe_security_groups(Filters=[
            {'Name': 'vpc-id', 'Values': [vpc_id]},
            {'Name': 'group-name', 'Values': ['default']}]
            )['SecurityGroups'][0]['GroupId']

        sg1_id = client.create_security_group(
            GroupName='sg1',
            VpcId=vpc_id,
            Description='SG 1')['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=sg1_id)
        client.authorize_security_group_ingress(
            GroupId=sg1_id,
            IpPermissions=[{
                'IpProtocol': 'tcp',
                'FromPort': 80,
                'ToPort': 80,
                'UserIdGroupPairs': [
                    {
                        'GroupId': default_sg_id
                    },
                    {
                        'GroupId': sg1_id
                    }]
            }])
        client.authorize_security_group_ingress(
            GroupId=sg1_id,
            IpProtocol='tcp',
            FromPort=60000,
            ToPort=62000,
            CidrIp='10.2.0.0/16')
        client.authorize_security_group_ingress(
            GroupId=sg1_id,
            IpProtocol='tcp',
            FromPort=61000,
            ToPort=61000,
            CidrIp='10.2.0.0/16')

        sg2_id = client.create_security_group(
            GroupName='sg2',
            VpcId=vpc_id,
            Description='SG 2')['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=sg2_id)
        client.authorize_security_group_egress(
            GroupId=sg2_id,
            IpPermissions=[{
                'IpProtocol': 'tcp',
                'FromPort': 443,
                'ToPort': 443,
                'UserIdGroupPairs': [
                    {
                        'GroupId': sg1_id
                    }]
            }])

        p = self.load_policy({
            'name': 'sg-find0',
            'resource': 'security-group',
            'filters': [
                {'type': 'ingress',
                 'SelfReference': False},
                {'GroupName': 'sg1'}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

        p = self.load_policy({
            'name': 'sg-find1',
            'resource': 'security-group',
            'filters': [
                {'type': 'ingress',
                 'SelfReference': True},
                {'GroupName': 'sg1'}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy({
            'name': 'sg-find2',
            'resource': 'security-group',
            'filters': [
                {'type': 'egress',
                 'SelfReference': True},
                {'GroupName': 'sg2'}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    @functional
    def test_security_group_delete(self):
        factory = self.replay_flight_data(
            'test_security_group_delete')
        client = factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="web-tier",
            VpcId=vpc_id,
            Description="for apps")['GroupId']

        def delete_sg():
            try:
                client.delete_security_group(GroupId=sg_id)
            except Exception:
                pass

        self.addCleanup(delete_sg)

        p = self.load_policy({
            'name': 'sg-delete',
            'resource': 'security-group',
            'filters': [
                {'GroupId': sg_id}],
            'actions': [
                'delete']}, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['GroupId'], sg_id)
        try:
            group_info = client.describe_security_groups(GroupIds=[sg_id])
        except:
            pass
        else:
            self.fail("group not deleted")

    @functional
    def test_port_within_range(self):
        factory = self.replay_flight_data(
            'test_security_group_port_in_range')
        client = factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="web-tier",
            VpcId=vpc_id,
            Description="for apps")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol='tcp',
            FromPort=60000,
            ToPort=62000,
            CidrIp='10.2.0.0/16')
        p = self.load_policy({
            'name': 'sg-find',
            'resource': 'security-group',
            'filters': [
                {'type': 'ingress',
                 'IpProtocol': 'tcp',
                 'FromPort': 60000},
                {'GroupName': 'web-tier'}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['GroupName'], 'web-tier')
        self.assertEqual(
            resources[0]['MatchedIpPermissions'],
            [{u'FromPort': 60000,
              u'IpProtocol': u'tcp',
              u'Ipv6Ranges': [],
              u'IpRanges': [{u'CidrIp': u'10.2.0.0/16'}],
              u'PrefixListIds': [],
              u'ToPort': 62000,
              u'UserIdGroupPairs': []}])

    @functional
    def test_ingress_remove(self):
        factory = self.replay_flight_data(
            'test_security_group_ingress_filter')
        client = factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.4.0.0/16")['Vpc']['VpcId']
        sg_id = client.create_security_group(
            GroupName="web-tier",
            VpcId=vpc_id,
            Description="for apps")['GroupId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol='tcp',
            FromPort=0,
            ToPort=62000,
            CidrIp='10.2.0.0/16')
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        p = self.load_policy({
            'name': 'sg-find',
            'resource': 'security-group',
            'filters': [
                {'VpcId': vpc_id},
                {'type': 'ingress',
                 'IpProtocol': 'tcp',
                 'FromPort': 0},
                {'GroupName': 'web-tier'}],
            'actions': [
                {'type': 'remove-permissions',
                 'ingress': 'matched'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['GroupId'], sg_id)
        group_info = client.describe_security_groups(
            GroupIds=[sg_id])['SecurityGroups'][0]
        self.assertEqual(group_info.get('IpPermissions', []), [])

    def test_default_vpc(self):
        # preconditions, more than one vpc, each with at least one
        # security group
        factory = self.replay_flight_data(
            'test_security_group_default_vpc_filter')
        p = self.load_policy({
            'name': 'sg-test',
            'resource': 'security-group',
            'filters': [
                {'type': 'default-vpc'},
                {'GroupName': 'default'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_config_source(self):
        factory = self.replay_flight_data(
            'test_security_group_config_source')
        p = self.load_policy({
            'name': 'sg-test',
            'source': 'config',
            'resource': 'security-group',
            'filters': [
                {'type': 'default-vpc'},
                {'GroupName': 'default'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['GroupId'], 'sg-6c7fa917')

    def test_only_ports_ingress(self):
        p = self.load_policy({
            'name': 'ingress-access',
            'resource': 'security-group',
            'filters': [
                {'type': 'ingress', 'OnlyPorts': [80]}
                ]})
        resources = [
            {'Description': 'Typical Internet-Facing Security Group',
             'GroupId': 'sg-abcd1234',
             'GroupName': 'TestInternetSG',
             'IpPermissions': [{'FromPort': 53,
                                'IpProtocol': 'tcp',
                                'IpRanges': ['10.0.0.0/8'],
                                'PrefixListIds': [],
                                'ToPort': 53,
                                'UserIdGroupPairs': []}],
             'IpPermissionsEgress': [],
             'OwnerId': '123456789012',
             'Tags': [{'Key': 'Value',
                       'Value': 'InternetSecurityGroup'},
                      {'Key': 'Key', 'Value': 'Name'}],
             'VpcId': 'vpc-1234abcd'}
        ]
        manager = p.get_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 1)

    def test_multi_attribute_ingress(self):
        p = self.load_policy({
            'name': 'ingress-access',
            'resource': 'security-group',
            'filters': [
                {'type': 'ingress',
                 'Cidr': {'value': '10.0.0.0/8'},
                 'Ports': [53]}
                ]})
        resources = [
            {'Description': 'Typical Internet-Facing Security Group',
             'GroupId': 'sg-abcd1234',
             'GroupName': 'TestInternetSG',
             'IpPermissions': [{'FromPort': 53,
                                'IpProtocol': 'tcp',
                                'IpRanges': [{'CidrIp': '10.0.0.0/8'}],
                                'PrefixListIds': [],
                                'ToPort': 53,
                                'UserIdGroupPairs': []}],
             'IpPermissionsEgress': [],
             'OwnerId': '123456789012',
             'Tags': [{'Key': 'Value',
                       'Value': 'InternetSecurityGroup'},
                      {'Key': 'Key', 'Value': 'Name'}],
             'VpcId': 'vpc-1234abcd'}
        ]
        manager = p.get_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 1)

    def test_ports_ingress(self):
        p = self.load_policy({
            'name': 'ingress-access',
            'resource': 'security-group',
            'filters': [
                {'type': 'ingress', 'Ports': [53]}
                ]})
        resources = [
            {'Description': 'Typical Internet-Facing Security Group',
             'GroupId': 'sg-abcd1234',
             'GroupName': 'TestInternetSG',
             'IpPermissions': [{'FromPort': 53,
                                'IpProtocol': 'tcp',
                                'IpRanges': ['10.0.0.0/8'],
                                'PrefixListIds': [],
                                'ToPort': 53,
                                'UserIdGroupPairs': []}],
             'IpPermissionsEgress': [],
             'OwnerId': '123456789012',
             'Tags': [{'Key': 'Value',
                       'Value': 'InternetSecurityGroup'},
                      {'Key': 'Key', 'Value': 'Name'}],
             'VpcId': 'vpc-1234abcd'}
        ]
        manager = p.get_resource_manager()
        self.assertEqual(len(manager.filter_resources(resources)), 1)

    def test_permission_expansion(self):
        factory = self.replay_flight_data('test_security_group_perm_expand')
        client = factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.42.0.0/16")['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="allow-some-ingress",
            VpcId=vpc_id,
            Description="inbound access")['GroupId']
        sg2_id = client.create_security_group(
            GroupName="allowed-reference",
            VpcId=vpc_id,
            Description="inbound ref access")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=sg2_id)
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{
                'IpProtocol': 'tcp',
                'FromPort': 443,
                'ToPort': 443,
                'IpRanges': [
                    {
                        'CidrIp': '10.42.1.0/24'
                    }]
            }])
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{
                'IpProtocol': 'tcp',
                'FromPort': 443,
                'ToPort': 443,
                'IpRanges': [
                    {
                        'CidrIp': '10.42.2.0/24'
                    }]
            }])
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{
                'IpProtocol': 'tcp',
                'FromPort': 443,
                'ToPort': 443,
                'UserIdGroupPairs': [{'GroupId': sg2_id}]
                }])
        p = self.load_policy({
            'name': 'ingress-access',
            'resource': 'security-group',
            'filters': [
                {'type': 'ingress',
                 'Cidr': {
                     'value': '10.42.1.1',
                     'op': 'in',
                     'value_type': 'cidr'}}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            len(resources[0].get('MatchedIpPermissions', [])), 1)
        self.assertEqual(
            resources[0].get('MatchedIpPermissions', []),
            [{u'FromPort': 443,
              u'IpProtocol': u'tcp',
              u'Ipv6Ranges': [],
              u'PrefixListIds': [],
              u'UserIdGroupPairs': [],
              u'IpRanges': [{u'CidrIp': u'10.42.1.0/24'}],
              u'ToPort': 443}])

    @functional
    def test_cidr_ingress(self):
        factory = self.replay_flight_data('test_security_group_cidr_ingress')
        client = factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.42.0.0/16")['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="allow-https-ingress",
            VpcId=vpc_id,
            Description="inbound access")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{
                'IpProtocol': 'tcp',
                'FromPort': 443,
                'ToPort': 443,
                'IpRanges': [
                    {
                        'CidrIp': '10.42.1.0/24'
                    }]
            }])
        p = self.load_policy({
            'name': 'ingress-access',
            'resource': 'security-group',
            'filters': [
                {'type': 'ingress',
                 'Cidr': {
                     'value': '10.42.1.239',
                     'op': 'in',
                     'value_type': 'cidr'}}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            len(resources[0].get('MatchedIpPermissions', [])), 1)

    @functional
    def test_cidr_size_egress(self):
        factory = self.replay_flight_data('test_security_group_cidr_size')
        client = factory().client('ec2')
        vpc_id = client.create_vpc(CidrBlock="10.42.0.0/16")['Vpc']['VpcId']
        self.addCleanup(client.delete_vpc, VpcId=vpc_id)
        sg_id = client.create_security_group(
            GroupName="wide-egress",
            VpcId=vpc_id,
            Description="unnecessarily large egress CIDR rule")['GroupId']
        self.addCleanup(client.delete_security_group, GroupId=sg_id)
        client.revoke_security_group_egress(
            GroupId=sg_id,
            IpPermissions=[
                {'IpProtocol': '-1',
                 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}])
        client.authorize_security_group_egress(
            GroupId=sg_id,
            IpPermissions=[{
                'IpProtocol': 'tcp',
                'FromPort': 443,
                'ToPort': 443,
                'IpRanges': [
                    {'CidrIp': '10.42.0.0/16'},
                    {'CidrIp': '10.42.1.0/24'}]}])
        p = self.load_policy({
            'name': 'wide-egress',
            'resource': 'security-group',
            'filters': [
                {'GroupName': 'wide-egress'},
                {'type': 'egress',
                 'Cidr': {
                     'value': 24,
                     'op': 'lt',
                     'value_type': 'cidr_size'}}]
            }, session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            len(resources[0].get('MatchedIpPermissionsEgress', [])), 1)

        self.assertEqual(
            resources[0]['MatchedIpPermissionsEgress'],
            [{u'FromPort': 443,
              u'IpProtocol': u'tcp',
              u'Ipv6Ranges': [],
              u'IpRanges': [
                  {u'CidrIp': u'10.42.0.0/16'}],
              u'PrefixListIds': [],
              u'ToPort': 443,
              u'UserIdGroupPairs': []}])

    def test_egress_validation_error(self):
        self.assertRaises(
            FilterValidationError,
            self.load_policy,
            {'name': 'sg-find2',
             'resource': 'security-group',
             'filters': [
                 {'type': 'egress',
                  'InvalidKey': True},
                 {'GroupName': 'sg2'}]})

    def test_vpc_by_security_group(self):
        factory = self.replay_flight_data('test_vpc_by_security_group')
        p = self.load_policy(
            {
                'name': 'vpc-sg',
                'resource': 'vpc',
                'filters': [
                    {
                        'type': 'security-group',
                        'key': 'tag:Name',
                        'value': 'FancyTestGroupPublic',
                    },
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Tags'][0]['Value'], 'FancyTestVPC')
