# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
from botocore.exceptions import ClientError
import pytest
from pytest_terraform import terraform
from .common import (
    BaseTest
)


@terraform('s3_access_point', teardown=terraform.TEARDOWN_IGNORE)
def test_s3_access_point(test, s3_access_point):
    factory = test.record_flight_data('s3_access_point_query')
    client = factory().client('s3control')
    sts_client = factory().client('sts')
    account_id = sts_client.get_caller_identity()['Account']
    p = test.load_policy(
        {
            'name': 'ap',
            'resource': 'aws.s3-access-point',
            'filters': ['cross-account'],
            'actions': ['delete'],
        },
        session_factory=factory,
        config={'account_id': account_id}
    )

    resources = p.run()
    assert len(resources) == 1
    assert resources[0]['Name'].startswith('c7n-ap-')

    if test.recording:
        time.sleep(2)

    with pytest.raises(ClientError):
        client.get_access_point(
            AccountId=p.options['account_id'], Name=resources[0]['Name']
        )


class TestStorageLens(BaseTest):

    def test_s3_storage_lens(self):
        factory = self.replay_flight_data('s3_storage_lens')
        p = self.load_policy(
            {
                'name': 's3_storage_lens',
                'resource': 'aws.s3-storage-lens',
                'filters': [
                    {
                        "type": "value",
                        "key": "Id",
                        "op": "eq",
                        "value": "test-2",
                    }
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'resource': 'storagelens'}
                    },
                    {
                        'type': 'remove-tag',
                        'tags': ['owner']
                    }
                ]
            },
            session_factory=factory
        )

        resources = p.run()
        assert len(resources) == 1
        client = factory().client('s3control')
        tags = client.get_storage_lens_configuration_tagging(
            AccountId=self.account_id, ConfigId=resources[0]['Id'])
        self.assertEqual(len(tags['Tags']), 1)
        self.assertEqual(tags['Tags'], [
            {'Key': 'resource', 'Value': 'storagelens'}
            ])

    def test_s3_storage_lens_mark_for_op(self):
        session_factory = self.replay_flight_data("test_s3_storage_lens_mark_for_op")
        p = self.load_policy(
            {
                "name": "s3-storage-lens-mark",
                "resource": "aws.s3-storage-lens",
                "filters": [
                    {'tag:owner': 'policy'},
                ],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "days": 1,
                    }
                ],
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

        p = self.load_policy(
            {
                "name": "s3-storage-lens-marked",
                "resource": "aws.s3-storage-lens",
                "filters": [
                    {
                        "type": "marked-for-op",
                        "tag": "custodian_cleanup",
                        "op": "delete",
                        "skew": 3,
                    }
                ],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        assert resources[0]['Id'] == 'test-dashboard'

    def test_s3_storage_lens_delete(self):
        session_factory = self.replay_flight_data('test_s3_storage_lens_delete')
        p = self.load_policy(
            {
                'name': 'storage-lens-delete',
                'resource': 's3-storage-lens',
                'filters': [
                    {
                        "type": "value",
                        "key": "Id",
                        "op": "eq",
                        "value": "test-3",
                    }
                ],
                'actions': [{'type': 'delete'}]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('s3control')
        with self.assertRaises(ClientError) as e:
            resources = client.get_storage_lens_configuration(
                    ConfigId='test-3',
                    AccountId=self.account_id)
        self.assertEqual(e.exception.response['Error']['Code'], 'NoSuchConfiguration')


class TestMultiRegionAccessPoint(BaseTest):

    def test_s3_multi_region_access_point(self):
        factory = self.replay_flight_data('test_s3_multi_region_access_point', region='us-west-2')
        p = self.load_policy(
            {
                'name': 'mr-access-point',
                'resource': 'aws.s3-access-point-multi',
                'filters': [
                    {'type': 'cross-account'}
                ],
            },
            session_factory=factory,
            config={'region': 'us-west-2'}
        )

        resources = p.run()
        self.assertEqual(len(resources), 1)
