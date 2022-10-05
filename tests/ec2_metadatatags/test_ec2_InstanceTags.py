# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import time
from mock import mock
import pytest
from tests.common import BaseTest


@pytest.mark.parametrize(
    'botocore_version',
    ['1.26.7', '1.26.8', '1.27.0', '2.0.0']
)
def test_ec2_metadata_tags_above_botocore_version_validation(test, botocore_version):
    with mock.patch('botocore.__version__', botocore_version):
        policy = test.load_policy(
            {
                'name': 'ec2-imds-access',
                'resource': 'ec2',
                'filters': [{
                    'type': 'value',
                    'key': 'MetadataOptions.InstanceMetadataTags',
                    'value': 'enabled',
                    'op': 'eq'
                }],
            },
        )
        policy.validate()


class TestSetMetadataTags(BaseTest):

    def test_set_metadata_server(self):
        output = self.capture_logging('custodian.actions')
        session_factory = self.replay_flight_data('test_ec2_set_md_access')
        policy = self.load_policy({
            'name': 'ec2-imds-access',
            'resource': 'aws.ec2',
            'actions': [
                {'type': 'set-metadata-access',
                 'metadatatags': 'disabled'},
            ]},
            session_factory=session_factory)
        resources = policy.run()
        if self.recording:
            time.sleep(2)
        results = session_factory().client('ec2').describe_instances(
            InstanceIds=[r['InstanceId'] for r in resources])
        self.assertJmes('[0].MetadataOptions.InstanceMetadataTags', resources, 'disabled')
        self.assertJmes(
            'Reservations[].Instances[].MetadataOptions',
            results,
            [{'HttpEndpoint': 'enabled',
              'HttpPutResponseHopLimit': 1,
              'HttpTokens': 'required',
              'InstanceMetadataTags': 'enabled',
              'State': 'pending'},
             {'HttpEndpoint': 'enabled',
              'HttpPutResponseHopLimit': 1,
              'HttpTokens': 'optional',
              'InstanceMetadataTags': 'disabled',
              'State': 'applied'}])
        self.assertEqual(len(resources), 2)
        self.assertEqual(
            output.getvalue(),
            ('set-metadata-access implicitly filtered 1 of 2 resources '
             'key:MetadataOptions.InstanceMetadataTags on enabled\n'))
