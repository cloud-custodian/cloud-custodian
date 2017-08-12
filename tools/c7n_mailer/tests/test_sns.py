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

import boto3
import copy
import unittest

from c7n_mailer.sns_delivery import SnsDelivery
from common import MAILER_CONFIG, RESOURCE_1, SQS_MESSAGE_1, logger


class SnsTest(unittest.TestCase):

    def setUp(self):
        self.sns_delivery = SnsDelivery(MAILER_CONFIG, boto3.Session(), logger)
        self.sns_topic_example = 'arn:aws:sns:us-east-1:172519456306:cloud-custodian'

    def test_target_is_sns(self):
        self.assertEqual(self.sns_delivery.target_is_sns('lksdjl'), False)
        self.assertEqual(self.sns_delivery.target_is_sns('baz@qux.bar'), False)
        self.assertEqual(self.sns_delivery.target_is_sns(self.sns_topic_example), True)

    def test_get_valid_sns_from_list(self):
        targets = ['resource-owner', 'milton@initech.com', self.sns_topic_example]
        sns_list = self.sns_delivery.get_valid_sns_from_list(targets)
        self.assertEqual(sns_list, [self.sns_topic_example])

    def test_get_sns_to_resources_map(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        SQS_MESSAGE['action']['to'].append(self.sns_topic_example)
        sns_to_resources = self.sns_delivery.get_sns_addrs_to_resources_map(SQS_MESSAGE)
        self.assertEqual(sns_to_resources, {self.sns_topic_example: [RESOURCE_1]})
