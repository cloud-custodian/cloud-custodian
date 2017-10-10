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

import boto3
import os
import unittest

from elasticmock import elasticmock
from elasticmock.fake_elasticsearch import FakeElasticsearch

from common import RESOURCE, SQS_MESSAGE
import c7n_dispatcher.cli as cli
import c7n_dispatcher.dispatcher as dispatcher


class ElasticsearchTest(unittest.TestCase):

    @elasticmock
    def setUp(self):
        config_file = '{}/sample_config.yml'.format(
            os.path.dirname(os.path.realpath(__file__)))
        self.config = cli.get_config(config_file)
        self.elasticsearch_messenger = dispatcher.get_messenger(self.config)
        self.logger = cli.get_logger()

    def test_valid_config(self):
        self.assertIsNotNone(self.config['queue_url'])
        self.assertIsNotNone(self.config['role'])
        self.assertEqual(self.config['memory'],1024)
        self.assertIsNotNone(self.config['messenger'])
        self.assertEqual(self.config['messenger']['type'], 'elasticsearch')

    def test_should_create_fake_elasticsearch_instance(self):
        self.assertIsInstance(
            self.elasticsearch_messenger.client, 
            FakeElasticsearch)

    @elasticmock
    def test_send_elasticsearch(self):
        res = self.elasticsearch_messenger.send(SQS_MESSAGE, self.logger)
        self.assertIsNotNone(res)
        self.assertEqual(res.get('_index'), 'custodian_index')
        self.assertTrue(res.get('created'))
