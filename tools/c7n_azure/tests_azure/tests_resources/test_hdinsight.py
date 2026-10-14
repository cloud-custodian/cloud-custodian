# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from ..azure_common import BaseTest, arm_template, cassette_name
from unittest.mock import patch


class HdinsightTest(BaseTest):

    def test_hdinsight_schema_validate(self):
        p = self.load_policy({
            'name': 'test-hdinsight-schema-validate',
            'resource': 'azure.hdinsight',
            'actions': [
                {
                    'type': 'resize',
                    'count': 1
                }
            ]
        }, validate=True)
        self.assertTrue(p)

    @arm_template('hdinsight.json')
    @cassette_name('common')
    def test_find_hdinsight_cluster_by_name(self):
        p = self.load_policy({
            'name': 'test-azure-hdinsight-by-name',
            'resource': 'azure.hdinsight',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctesthdinsight*'
                }
            ]
        }, validate=True)

        resources = p.run()
        self.assertEqual(len(resources), 1)

    @patch('azure.mgmt.hdinsight.operations.ClustersOperations.begin_resize')
    @arm_template('hdinsight.json')
    @cassette_name('common')
    def test_resize_hdinsight_cluster_action(self, resize_mock):
        p = self.load_policy({
            'name': 'test-azure-hdinsight-resize',
            'resource': 'azure.hdinsight',
            'filters': [
                {
                    'type': 'value',
                    'key': 'name',
                    'op': 'glob',
                    'value_type': 'normalize',
                    'value': 'cctesthdinsight*'
                }
            ],
            'actions': [
                {
                    'type': 'resize',
                    'count': 1
                }
            ]
        })

        resources = p.run()
        kwargs = resize_mock.mock_calls[0].kwargs

        self.assertEqual(1, len(resources))
        self.assertEqual(1, resize_mock.call_count)
        self.assertEqual(1, len(kwargs))
        self.assertEqual(1, kwargs.get('target_instance_count'))
