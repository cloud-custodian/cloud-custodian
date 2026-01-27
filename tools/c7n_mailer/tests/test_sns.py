# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import boto3
import copy
import unittest

from c7n_mailer.sns_delivery import SnsDelivery
from common import MAILER_CONFIG, RESOURCE_1, SQS_MESSAGE_1, logger


class SnsTest(unittest.TestCase):
    def setUp(self):
        self.sns_delivery = SnsDelivery(MAILER_CONFIG, boto3.Session(), logger)
        self.sns_topic_example = "arn:aws:sns:us-east-1:172519456306:cloud-custodian"

    def test_target_is_sns(self):
        self.assertEqual(self.sns_delivery.target_is_sns("lksdjl"), False)
        self.assertEqual(self.sns_delivery.target_is_sns("baz@qux.bar"), False)
        self.assertEqual(self.sns_delivery.target_is_sns(self.sns_topic_example), True)

    def test_get_valid_sns_from_list(self):
        targets = ["resource-owner", "milton@initech.com", self.sns_topic_example]
        sns_list = self.sns_delivery.get_valid_sns_from_list(targets)
        self.assertEqual(sns_list, [self.sns_topic_example])

    def test_get_sns_to_resources_map(self):
        SQS_MESSAGE = copy.deepcopy(SQS_MESSAGE_1)
        SQS_MESSAGE["action"].get("to", []).append(self.sns_topic_example)
        sns_to_resources = self.sns_delivery.get_sns_addrs_to_resources_map(SQS_MESSAGE)
        self.assertEqual(sns_to_resources, {self.sns_topic_example: [RESOURCE_1]})
