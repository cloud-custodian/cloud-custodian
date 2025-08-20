# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.resources.kinesis import DeliveryStream
from .common import BaseTest, event_data


def test_stream_config_source(test):
    p = test.load_policy({
        'name': 'stream-config',
        'resource': 'aws.kinesis',
        'mode': {'type': 'config-rule'}})
    item = event_data('kinesis-stream.json', 'config')
    source = p.resource_manager.get_source('config')
    resource = source.load_resource(item)
    assert resource['StreamName'] == 'stream-encrypted'
    assert resource['KeyId'] == 'alias/aws/kinesis'


class Kinesis(BaseTest):

    def test_stream_query(self):
        factory = self.replay_flight_data("test_kinesis_stream_query")
        p = self.load_policy(
            {
                "name": "kstream",
                "resource": "kinesis",
                "filters": [
                    {"type": "value", "value_type": "size", "value": 3, "key": "Shards"}
                ],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["Tags"], [{"Key": "Origin", "Value": "home"}])
        self.assertEqual(resources[0]["StreamStatus"], "ACTIVE")

    def test_stream_delete(self):
        factory = self.replay_flight_data("test_kinesis_stream_delete")
        p = self.load_policy(
            {
                "name": "kstream",
                "resource": "kinesis",
                "filters": [{"StreamName": "sock-drawer"}],
                "actions": [{"type": "delete", "force": True}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        stream = factory().client("kinesis").describe_stream(StreamName="sock-drawer")[
            "StreamDescription"
        ]
        self.assertEqual(stream["StreamStatus"], "DELETING")

    def test_stream_encrypt(self):
        factory = self.replay_flight_data("test_kinesis_encrypt")
        p = self.load_policy(
            {
                "name": "kstream",
                "resource": "kinesis",
                "filters": [{"StreamName": "sock-drawer"}],
                "actions": [{"type": "encrypt", "key": "aws/kinesis"}],
            },
            session_factory=factory,
        )
        p.run()
        stream = factory().client("kinesis").describe_stream(StreamName="sock-drawer")[
            "StreamDescription"
        ]
        self.assertEqual(stream["EncryptionType"], "KMS")

    def test_stream_cross_account(self):
        factory = self.replay_flight_data("test_kinesis_cross_account")
        p = self.load_policy(
            {
                "name": "kinesis-cross-account",
                "resource": "kinesis",
                "filters": [{"type": "cross-account"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['CrossAccountViolations'][0]['Resource'],
            'arn:aws:kinesis:us-east-1:644160558196:stream/test-stream-2')

    def test_hose_paginate(self):
        self.patch(
            DeliveryStream.resource_type, "enum_spec",
            ('list_delivery_streams', 'DeliveryStreamNames', {'Limit': 5})
        )
        factory = self.record_flight_data("test_kinesis_hose_paginate")
        p = self.load_policy(
            {
                "name": "paginate_hole",
                "resource": "firehose"
            },
            session_factory=factory
        )
        resources = p.run()
        assert len(resources) == 12

    def test_hose_query(self):
        factory = self.replay_flight_data("test_kinesis_hose_query")
        p = self.load_policy(
            {
                "name": "khole",
                "resource": "firehose",
                "filters": [{"DeliveryStreamName": "sock-index-hose"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["DeliveryStreamStatus"], "ACTIVE")

    def test_firehose_delete(self):
        factory = self.replay_flight_data("test_kinesis_hose_delete")
        p = self.load_policy(
            {
                "name": "khole",
                "resource": "firehose",
                "filters": [{"DeliveryStreamName": "sock-index-hose"}],
                "actions": ["delete"]
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            factory().client("firehose").describe_delivery_stream(
                DeliveryStreamName="sock-index-hose"
            )[
                "DeliveryStreamDescription"
            ][
                "DeliveryStreamStatus"
            ],
            "DELETING",
        )

    def test_firehose_extended_s3_encrypt_s3_destination(self):
        factory = self.replay_flight_data("test_firehose_ext_s3_encrypt_s3_destination")
        p = self.load_policy(
            {
                "name": "khole",
                "resource": "firehose",
                "filters": [{"type": "value",
                    "key": "Destinations[0].S3DestinationDescription.EncryptionConfiguration.NoEncryptionConfig",  # noqa: E501
                             "value": "present"}],
                "actions": [{"type": "encrypt-s3-destination",
                             "key_arn": "arn:aws:kms:us-east-1:123456789:alias/aws/s3"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        s = factory().client("firehose").describe_delivery_stream(
            DeliveryStreamName="firehose-s3"
        )['DeliveryStreamDescription']['Destinations'][0]
        assert 'KMSEncryptionConfig' in s['S3DestinationDescription']['EncryptionConfiguration'].keys()  # noqa: E501

    def test_firehose_splunk_encrypt_s3_destination(self):
        factory = self.replay_flight_data("test_firehose_splunk_encrypt_s3_destination")
        p = self.load_policy(
            {
                "name": "khole",
                "resource": "firehose",
                "filters": [{"type": "value",
                    "key": "Destinations[0].SplunkDestinationDescription.S3DestinationDescription.EncryptionConfiguration.NoEncryptionConfig",  # noqa: E501
                             "value": "present"}],
                "actions": [{"type": "encrypt-s3-destination",
                             "key_arn": "arn:aws:kms:us-east-1:123456789:alias/aws/s3"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        s = factory().client("firehose").describe_delivery_stream(
            DeliveryStreamName="firehose-splunk"
        )['DeliveryStreamDescription']['Destinations'][0]['SplunkDestinationDescription']
        assert 'KMSEncryptionConfig' in \
            s['S3DestinationDescription']['EncryptionConfiguration'].keys()

    def test_firehose_elasticsearch_encrypt_s3_destination(self):
        factory = self.replay_flight_data("test_firehose_elasticsearch_encrypt_s3_destination")
        p = self.load_policy(
            {
                "name": "khole",
                "resource": "firehose",
                "filters": [{"type": "value",
                    "key": "Destinations[0].ElasticsearchDestinationDescription.S3DestinationDescription.EncryptionConfiguration.NoEncryptionConfig",  # noqa: E501
                             "value": "present"}],
                "actions": [{"type": "encrypt-s3-destination",
                             "key_arn": "arn:aws:kms:us-east-1:123456789:alias/aws/s3"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        s = factory().client("firehose").describe_delivery_stream(
            DeliveryStreamName="firehose-splunk"
        )['DeliveryStreamDescription']['Destinations'][0]['ElasticsearchDestinationDescription']
        assert 'KMSEncryptionConfig' in \
            s['S3DestinationDescription']['EncryptionConfiguration'].keys()

    def test_firehose_redshift_encrypt_s3_destination(self):
        factory = self.replay_flight_data("test_firehose_redshift_encrypt_s3_destination")
        p = self.load_policy(
            {
                "name": "khole",
                "resource": "firehose",
                "filters": [{"type": "value",
                    "key": "Destinations[0].RedshiftDestinationDescription.S3DestinationDescription.EncryptionConfiguration.NoEncryptionConfig",  # noqa: E501
                             "value": "present"}],
                "actions": [{"type": "encrypt-s3-destination",
                             "key_arn": "arn:aws:kms:us-east-1:123456789:alias/aws/s3"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        s = factory().client("firehose").describe_delivery_stream(
            DeliveryStreamName="firehose-redshift"
        )['DeliveryStreamDescription']['Destinations'][0]['RedshiftDestinationDescription']
        assert 'KMSEncryptionConfig' in \
            s['S3DestinationDescription']['EncryptionConfiguration'].keys()

    def test_app_query(self):
        factory = self.replay_flight_data("test_kinesis_analytics_query")
        p = self.load_policy(
            {
                "name": "kapp",
                "resource": "kinesis-analytics",
                "filters": [{"ApplicationStatus": "RUNNING"}],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["ApplicationName"], "sock-app")

    def test_app_delete(self):
        factory = self.replay_flight_data("test_kinesis_analytics_delete")
        p = self.load_policy(
            {
                "name": "kapp",
                "resource": "kinesis-analytics",
                "filters": [{"ApplicationName": "sock-app"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            factory().client("kinesisanalytics").describe_application(
                ApplicationName="sock-app"
            )[
                "ApplicationDetail"
            ][
                "ApplicationStatus"
            ],
            "DELETING",
        )

    def test_video_stream_delete(self):
        factory = self.replay_flight_data("test_kinesis_video_stream_delete")
        p = self.load_policy(
            {
                "name": "kinesis-video-delete",
                "resource": "kinesis-video",
                "filters": [{"StreamName": "test-video"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        stream = factory().client("kinesisvideo").describe_stream(StreamName="test-video")[
            "StreamInfo"
        ]
        self.assertEqual(stream["Status"], "DELETING")

    def test_kinesis_video_kms_key(self):
        session_factory = self.replay_flight_data("test_kinesis_video_kms_key")
        p = self.load_policy(
            {
                "name": "kinesis-video-kms-alias",
                "resource": "kinesis-video",
                "filters": [
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "^(alias/alias/aws/lambda)",
                        "op": "regex"
                    }
                ]
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['KmsKeyId'],
            'arn:aws:kms:us-east-1:123456789012:key/0d543df5-915c-42a1-afa1-c9c5f1f97955')

    def test_kinesis_video_kms_key_alias(self):
        p = self.load_policy(
            {
                "name": "kinesis-video-kms-alias",
                "resource": "kinesis-video",
                "filters": [
                    {
                        "type": "kms-key",
                        "key": "c7n:AliasName",
                        "value": "alias/aws/lambda",
                    }
                ]
            },
            session_factory=self.replay_flight_data("test_kinesis_video_kms_key_alias"),
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['KmsKeyId'],
                         'arn:aws:kms:us-east-1:123456789012:alias/aws/lambda')

    def test_kinesis_video_tag(self):
        session_factory = self.replay_flight_data('test_kinesis_video_tag')
        p = self.load_policy(
            {
                'name': 'test-kinesis-video-tag',
                'resource': 'kinesis-video',
                'filters': [
                    {
                        'tag:foo': 'absent',
                    }
                ],
                'actions': [
                    {
                        'type': 'tag',
                        'tags': {'foo': 'bar'}
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('kinesisvideo')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]["StreamARN"])["Tags"]
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, {'foo': 'bar'})

    def test_kinesis_video_remove_tag(self):
        session_factory = self.replay_flight_data('test_kinesis_video_remove_tag')
        p = self.load_policy(
            {
                'name': 'test-kinesis-video-remove-tag',
                'resource': 'kinesis-video',
                'filters': [
                    {
                        'tag:foo': 'present',
                    }
                ],
                'actions': [
                    {
                        'type': 'remove-tag',
                        'tags': ['foo']
                    }
                ]
            }, session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('kinesisvideo')
        tags = client.list_tags_for_resource(ResourceARN=resources[0]['StreamARN'])['Tags']
        self.assertEqual(len(tags), 0)


class KinesisAnalyticsAppV2(BaseTest):

    def test_kinesis_analyticsv2_app_delete(self):
        factory = self.replay_flight_data("test_kinesis_analyticsv2_app_delete")
        p = self.load_policy(
            {
                "name": "kapp",
                "resource": "kinesis-analyticsv2",
                "filters": [{"type": "subnet", "key": "tag:Name", "value": "implied", "op": "eq"}],
                "actions": ["delete"],
            },
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            factory().client("kinesisanalyticsv2").describe_application(
                ApplicationName=resources[0]['ApplicationName']
            )[
                "ApplicationDetail"
            ][
                "ApplicationStatus"
            ],
            "DELETING",
        )
