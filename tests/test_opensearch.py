# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class OpensearchServerless(BaseTest):

    def test_opensearch_serverless_tag(self):
        session_factory = self.replay_flight_data('test_opensearch_serverless_tag')
        p = self.load_policy(
            {
                'name': 'test-opensearch-serverless-tag',
                'resource': 'opensearch-serverless',
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
        client = session_factory().client('opensearchserverless')
        tags = client.list_tags_for_resource(resourceArn=resources[0]["arn"])['tags']
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags, [{'key': 'foo', 'value': 'bar'}])

    def test_opensearch_serverless_remove_tag(self):
        session_factory = self.replay_flight_data('test_opensearch_serverless_remove_tag')
        p = self.load_policy(
            {
                'name': 'test-opensearch-serverless-remove-tag',
                'resource': 'opensearch-serverless',
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
        client = session_factory().client('opensearchserverless')
        tags = client.list_tags_for_resource(resourceArn=resources[0]['arn'])['tags']
        self.assertEqual(len(tags), 0)

    def test_opensearch_serverless_delete(self):
        session_factory = self.replay_flight_data('test_opensearch_serverless_delete')
        p = self.load_policy(
            {
                'name': 'test-opensearch-serverless-delete',
                'resource': 'opensearch-serverless',
                'filters': [{'name': 'test-collection'}],
                'actions': [{'type': 'delete'}]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('opensearchserverless')
        collections = client.list_collections()['collectionSummaries']
        self.assertEqual(collections[0]["status"], "DELETING")

    def test_opensearch_serverless_kms_filter(self):
        session_factory = self.replay_flight_data("test_opensearch_serverless_kms_filter")
        p = self.load_policy(
            {
                "name": "opensearch-serverless-kms",
                "resource": "opensearch-serverless",
                'filters': [
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': 'alias/tes/pratyush'
                    }
                ]
            }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['kmsKeyArn'],
            'arn:aws:kms:us-east-1:644160558196:key/082cd05f-96d1-49f6-a5ac-32093d2cfe38')


class OpensearchInjestion(BaseTest):

    def test_opensearch_serverless_tag(self):
        session_factory = self.replay_flight_data('test_opensearch_injestion_tag')
        p = self.load_policy(
            {
                'name': 'test-opensearch-injestion-tag',
                'resource': 'opensearch-injestion',
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
        client = session_factory().client('osis')
        tags = client.list_tags_for_resource(Arn=resources[0]["PipelineArn"])['Tags']
        self.assertEqual(tags, [{'Key': 'foo', 'Value': 'bar'}])

        p = self.load_policy(
            {
                'name': 'test-opensearch-injestion-remove-tag',
                'resource': 'opensearch-injestion',
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
        client = session_factory().client('osis')
        tags = client.list_tags_for_resource(Arn=resources[0]['PipelineArn'])['Tags']
        self.assertEqual(len(tags), 0)

    def test_opensearch_injestion_kms_filter(self):
        session_factory = self.replay_flight_data("test_opensearch_injestion_kms_filter")
        p = self.load_policy(
            {
                "name": "opensearch-injestion-kms",
                "resource": "opensearch-injestion",
                'filters': [
                    {
                        'type': 'kms-key',
                        'key': 'c7n:AliasName',
                        'value': 'alias/tes/pratyush'
                    }
                ]
            }, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['EncryptionAtRestOptions']['KmsKeyArn'],
            'arn:aws:kms:us-east-1:644160558196:key/082cd05f-96d1-49f6-a5ac-32093d2cfe38')

    def test_opensearch_injestion_update(self):
        session_factory = self.replay_flight_data('test_opensearch_update_update')
        policy = {
                'name': 'test-opensearch-injestion-update',
                'resource': 'opensearch-injestion',
                'actions': [
                    {
                        'type': 'update',
                        'MinUnits': 1,
                        'MaxUnits': 2,
                        'LogPublishingOptions': {
                            'IsLoggingEnabled': True,
                            'CloudWatchLogDestination': {
                                'LogGroup': '/aws/vendedlogs/opensearch/c7n-log-group'
                            }
                        },
                        'EncryptionAtRestOptions': {
                            'KmsKeyArn': ('arn:aws:kms:us-east-1:644160558196:key/'
                                          '082cd05f-96d1-49f6-a5ac-32093d2cfe38')
                        }
                    }
                ]
            }
        p = self.load_policy(
            policy,
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('osis')
        pipeline = client.get_pipeline(PipelineName=resources[0]["PipelineName"])["Pipeline"]
        updated_config = policy['actions'][0]
        updated_config.pop('type')
        for key in updated_config.keys():
            self.assertEqual(pipeline[key], updated_config[key])

    def test_opensearch_injestion_stop(self):
        session_factory = self.replay_flight_data('test_opensearch_injestion_stop')
        p = self.load_policy(
            {
                'name': 'test-opensearch-injestion-stop',
                'resource': 'opensearch-injestion',
                'filters': [{'PipelineName': 'custodian-test'}],
                'actions': [{'type': 'stop'}]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('osis')
        pipeline = client.list_pipelines()['Pipelines'][0]
        self.assertEqual(pipeline["Status"], "STOPPING")

    def test_opensearch_injestion_delete(self):
        session_factory = self.replay_flight_data('test_opensearch_injestion_delete')
        p = self.load_policy(
            {
                'name': 'test-opensearch-injestion-delete',
                'resource': 'opensearch-injestion',
                'filters': [{'PipelineName': 'custodian-test'}],
                'actions': [{'type': 'delete'}]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('osis')
        pipeline = client.list_pipelines()['Pipelines'][0]
        self.assertEqual(pipeline["Status"], "DELETING")
