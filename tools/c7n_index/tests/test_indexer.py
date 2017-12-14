# Copyright 2017 Capital One Services, LLC
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

import os
import yaml
import unittest
from elasticmock import elasticmock
from c7n_index.metrics import get_indexer
from elasticmock.fake_elasticsearch import FakeElasticsearch

RESOURCE = {
    "Website": None,
    "Logging": {},
    "Name": "teapot",
    "Tags": [
        {
            "Value": "418",
            "Key": "Status"
        }
    ],
    "Notification": {
        "LambdaFunctionConfigurations": []
    },
    "Acl": {
        "Owner": {
            "DisplayName": "teapot-owner",
            "ID": "imalittleteapot"
        },
        "Grants": []
    },
    "Replication": None,
    "Location": {
        "LocationConstraint": None
    },
    "Policy": None,
    "CreationDate": "2016-10-21T18:47:14+00:00",
    "Lifecycle": {
        "Rules": [
            {
                "Status": "Enabled",
                "Prefix": "",
                "AbortIncompleteMultipartUpload": {
                    "DaysAfterInitiation": 1
                },
                "Expiration": {
                    "Days": 15
                },
                "ID": "dev-standard"
            }
        ]
    },
    "Versioning": {}
}
SQS_MESSAGE = {
    "account": "dev",
    "account_id": "123456789012",
    "region": "us-east-1",
    "action": {
        "to": [],
        "type": "notify",
        "transport": {
            "topic": "arn:aws:sns:us-east-1:123456789012:noteafy",
            "type": "sns"
        }
    },
    "policy": {
        "resource": "s3",
        "name": "test-s3",
        "region": "us-east-1",
        "actions": [
            {
                "to": [],
                "type": "notify",
                "transport": {
                    "topic": "arn:aws:sns:us-east-1:123456789012:noteafy",
                    "type": "sns"
                }
            }
        ]
    },
    "event": None,
    "resources": [RESOURCE]
}


class ElasticsearchTest(unittest.TestCase):

    @elasticmock
    def setUp(self):
        file = '{}/sample_config.yml'.format(
            os.path.dirname(os.path.realpath(__file__)))
        with open(file) as fh:
            config = yaml.safe_load(fh.read())
        self.config = config
        self.elasticsearch_obj = get_indexer(self.config)

    def test_valid_config(self):
        self.assertIsNotNone(self.config['indexer'])
        self.assertIsNotNone(self.config['indexer']['host'])
        self.assertIsNotNone(self.config['indexer']['port'])
        self.assertEqual(self.config['indexer']['type'], 'es')

    @elasticmock
    def test_client_connection(self):
        self.assertIsInstance(self.elasticsearch_obj.client, FakeElasticsearch)

    @elasticmock
    def test_send_elasticsearch(self):
        res = self.elasticsearch_obj.index_sqs(SQS_MESSAGE)
        self.assertIsNotNone(res)
        self.assertEqual(res.get('_index'), 'c7n')
        self.assertTrue(res.get('created'))