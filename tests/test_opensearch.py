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
                'filters': [{'name': 'c7n-test'}],
                'actions': [{'type': 'delete'}]
            },
            session_factory=session_factory
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = session_factory().client('opensearchserverless')
        collections = client.list_collections()['collectionSummaries']
        self.assertEqual(collections[0]["status"], "DELETING")
