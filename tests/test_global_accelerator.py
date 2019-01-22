# Copyright 2019 Capital One Services, LLC
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

from .common import BaseTest

# as of now the only region global accelerator is available is us-west-2
available_ga_region = 'us-west-2'


class TestEndpointInstance(BaseTest):

    def test_modify_endpoint_configuration(self):

        session_factory = self.replay_flight_data('test_modify_endpoint_configuration_1')
        client = session_factory().client('globalaccelerator',
            region_name=available_ga_region)
        endpoint_group_arn = 'arn:aws:globalaccelerator::644160558196:accelerator/' \
            '1460ad64-e386-41e4-9715-d8bcc665963e/listener/56de20d3/endpoint-group/db9a1ad66002'

        result = client.describe_endpoint_group(
            EndpointGroupArn=endpoint_group_arn)['EndpointGroup']
        endpoint_id = 'eipalloc-0b0cb213820a08ae6'
        self.assertEqual(result['EndpointGroupArn'], endpoint_group_arn)
        self.assertEqual(result['ThresholdCount'], 3)
        endpoint_descriptions = result['EndpointDescriptions']
        self.assertEqual(endpoint_descriptions[0]['EndpointId'], endpoint_id)
        self.assertEqual(endpoint_descriptions[0]['Weight'], 100)
        p = self.load_policy(
            {
                'name': 'modify-global-accelerator-endpoint',
                'resource': 'global-accelerator-endpoint-group',
                'filters': [
                    {
                        'type': 'value', 'key': 'HealthCheckProtocol', 'value': 'HTTPS',
                        'op': 'not-equal'
                    }, ],
                'actions': [{'type': 'modify',
                    'update-accelerator-endpoint': [
                        {
                            'property': 'ThresholdCount',
                            'value': 4,
                        },
                        {
                            'EndpointConfigurations': [
                                {'EndpointId': endpoint_id, 'Weight': 0},
                            ]
                        },
                    ],
                }],
            },
            session_factory=session_factory,
        )
        p.run()

        result = client.describe_endpoint_group(
            EndpointGroupArn=endpoint_group_arn)['EndpointGroup']
        self.assertEqual(result['EndpointGroupArn'], endpoint_group_arn)
        self.assertEqual(result['ThresholdCount'], 4)
        endpoint_descriptions = result['EndpointDescriptions']
        self.assertEqual(endpoint_descriptions[0]['EndpointId'], endpoint_id)
        self.assertEqual(endpoint_descriptions[0]['Weight'], 0)

    def test_delete_endpoint_group(self):

        session_factory = self.replay_flight_data('test_delete_endpoint_groups_1')
        client = session_factory().client('globalaccelerator', region_name=available_ga_region)
        listener_arn = 'arn:aws:globalaccelerator::644160558196:accelerator/' \
            '1460ad64-e386-41e4-9715-d8bcc665963e/listener/56de20d3'

        result = client.list_endpoint_groups(ListenerArn=listener_arn)
        self.assertEqual(len(result['EndpointGroups']), 2)

        p = self.load_policy(
            {
                'name': 'delete-accelerator-endpoint-group',
                'resource': 'global-accelerator-endpoint-group',
                'filters': [{'EndpointGroupRegion': 'us-east-2'}],
                'actions': [{'type': 'delete'}],
            },
            session_factory=session_factory,
        )
        p.run()

        session_factory = self.replay_flight_data('test_delete_endpoint_groups_2')
        client = session_factory().client('globalaccelerator', region_name=available_ga_region)
        result = client.list_endpoint_groups(ListenerArn=listener_arn)
        self.assertEqual(len(result['EndpointGroups']), 1)


class TestListener(BaseTest):

    def test_delete_listener(self):
        accelerator_arn = 'arn:aws:globalaccelerator::644160558196:accelerator/' \
            '1460ad64-e386-41e4-9715-d8bcc665963e'
        session_factory = self.replay_flight_data('test_delete_listeners1')
        client = session_factory().client('globalaccelerator', region_name=available_ga_region)
        accelerator_arn = 'arn:aws:globalaccelerator::644160558196:accelerator/' \
            '1460ad64-e386-41e4-9715-d8bcc665963e'
        result = client.list_listeners(AcceleratorArn=accelerator_arn)
        self.assertEqual(len(result['Listeners']), 2)

        p = self.load_policy(
            {
                'name': 'delete-accelerator-listener',
                'resource': 'global-accelerator-listener',
                'filters': [{'Protocol': 'UDP'}],
                'actions': [{'type': 'delete'}],
            },
            session_factory=session_factory,
        )
        p.run()

        session_factory = self.replay_flight_data('test_delete_listeners_2')
        client = session_factory().client('globalaccelerator', region_name=available_ga_region)
        result = client.list_listeners(AcceleratorArn=accelerator_arn)
        self.assertEqual(len(result['Listeners']), 1)

    def test_modify_listener(self):

        session_factory = self.replay_flight_data('test_modify_listener_1')
        client = session_factory().client('globalaccelerator', region_name=available_ga_region)
        listener_arn = 'arn:aws:globalaccelerator::644160558196:accelerator/' \
            '1460ad64-e386-41e4-9715-d8bcc665963e/listener/56de20d3'

        result = client.describe_listener(ListenerArn=listener_arn)['Listener']

        self.assertEqual(result['ListenerArn'], listener_arn)
        self.assertEqual(result['ClientAffinity'], 'NONE')
        self.assertEqual(result['PortRanges'][0]['FromPort'], 80)
        self.assertEqual(result['PortRanges'][0]['ToPort'], 80)

        p = self.load_policy(
            {
                'name': 'modify-global-accelerator-listener',
                'resource': 'global-accelerator-listener',
                'actions': [{'type': 'modify',
                    'update-accelerator-listener': [
                        {
                            'property': 'ClientAffinity',
                            'value': 'SOURCE_IP',
                        },
                        {
                            'PortRanges': [
                                {'FromPort': 82, 'ToPort': 83}
                            ]
                        },
                    ],
                }],
            },
            session_factory=session_factory,
        )
        p.run()

        session_factory = self.replay_flight_data('test_modify_listener_2')
        client = session_factory().client('globalaccelerator', region_name=available_ga_region)
        result = client.describe_listener(ListenerArn=listener_arn)['Listener']
        self.assertEqual(result['ListenerArn'], listener_arn)
        self.assertEqual(result['ClientAffinity'], 'SOURCE_IP')
        self.assertEqual(result['PortRanges'][0]['FromPort'], 82)
        self.assertEqual(result['PortRanges'][0]['ToPort'], 83)


class TestAcceleratorInstance(BaseTest):

    def test_list_accelerator_instances(self):
        session_factory = self.replay_flight_data('test_global_accelerator_instances')
        p = self.load_policy(
            {
                'name': 'list-ga',
                'resource': 'global-accelerator',
                'filters': [
                    {'type': 'value', 'key': 'Name', 'value': 'test-custodian'}
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_delete_global_accelerator_instance(self):

        session_factory = self.replay_flight_data(
            'test_global_accelerator_delete_instance'
        )
        client = session_factory().client('globalaccelerator', region_name=available_ga_region)

        result = client.list_accelerators(MaxResults=100)
        counts = self.count_enabled(result['Accelerators'])
        self.assertEqual(counts['enabled'], 1)
        self.assertEqual(counts['disabled'], 2)

        p = self.load_policy(
            {
                'name': 'delete-disabled-accelerator-instance',
                'resource': 'global-accelerator',
                'filters': [{'Enabled': False}],
                'actions': [{'type': 'delete'}],
            },
            session_factory=session_factory,
        )
        p.run()

        result = client.list_accelerators()
        counts = self.count_enabled(result['Accelerators'])
        self.assertEqual(counts['enabled'], 1)
        self.assertEqual(counts['disabled'], 0)

    def test_modify_global_accelerator_instance(self):

        # test attributes set with update_accelerator_attributes()

        session_factory = self.replay_flight_data(
            'test_modify_global_accelerator_instance_with_bucket'
        )
        client = session_factory().client('globalaccelerator', region_name=available_ga_region)
        result = client.list_accelerators(MaxResults=100)
        self.assertEqual(len(result['Accelerators']), 1)
        accelerator_arn = 'arn:aws:globalaccelerator::644160558196:accelerator/' \
            '1460ad64-e386-41e4-9715-d8bcc665963e'
        result = client.describe_accelerator(AcceleratorArn=accelerator_arn)['Accelerator']
        self.assertEqual(result['Enabled'], False)
        result = client.describe_accelerator_attributes(AcceleratorArn=accelerator_arn)
        self.assertFalse(result['AcceleratorAttributes']['FlowLogsEnabled'])
        bucket_name = 'test-for-global-accelerator-bucket/test-custodian'
        p = self.load_policy(
            {
                'name': 'modify-global-accelerator-attributes',
                'resource': 'global-accelerator',
                'filters': [
                    {'type': 'value', 'key': 'Name', 'value': 'test-custodian'}
                ],
                'actions': [
                    {
                        'type': 'modify-global-accelerator',
                        'update-accelerator': [{'property': 'Enabled', 'value': True}],
                        'update-accelerator-attributes': [
                            {'property': 'FlowLogsEnabled', 'value': True},
                            {'property': 'FlowLogsS3Bucket', 'value': bucket_name},
                            {'property': 'FlowLogsS3Prefix', 'value': 'us-west-2'},
                        ],
                    }
                ],
            },
            session_factory=session_factory,
        )
        p.run()

        session_factory = self.replay_flight_data(
            'test_modify_global_accelerator_instance_with_bucket_2'
        )
        client = session_factory().client('globalaccelerator', region_name=available_ga_region)

        result = client.describe_accelerator(AcceleratorArn=accelerator_arn)['Accelerator']
        self.assertEqual(result['Enabled'], True)

        result = client.describe_accelerator_attributes(
            AcceleratorArn=accelerator_arn)

        self.assertTrue(result['AcceleratorAttributes']['FlowLogsEnabled'])
        self.assertEqual(result['AcceleratorAttributes']['FlowLogsS3Bucket'], bucket_name)
        self.assertEqual(result['AcceleratorAttributes']['FlowLogsS3Prefix'], 'us-west-2')

    def count_enabled(self, list_output):
        enabled_count = 0
        disabled_count = 0
        for accelerator in list_output:
            if accelerator['Enabled']:
                enabled_count += 1
            else:
                disabled_count += 1
        return {
            'enabled': enabled_count,
            'disabled': disabled_count
        }
