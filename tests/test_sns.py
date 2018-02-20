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

import json, time

from .common import BaseTest, functional


class TestSNS(BaseTest):

    @functional
    def test_sns_remove_matched(self):
        session_factory = self.replay_flight_data('test_sns_remove_matched')
        client = session_factory().client('sns')
        name = 'test-sns-remove-matched'
        topic_arn = client.create_topic(Name=name)['TopicArn']
        self.addCleanup(client.delete_topic, TopicArn=topic_arn)

        client.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "SpecificAllow",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": "arn:aws:iam::644160558196:root"
                        },
                        "Action": [
                            "SNS:Subscribe"
                        ],
                        "Resource": topic_arn
                    },
                    {
                        "Sid": "Public",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": [
                            "SNS:GetTopicAttributes"
                        ],
                        "Resource": topic_arn
                    }
                ]
            })
        )

        p = self.load_policy({
            'name': 'sns-rm-matched',
            'resource': 'sns',
            'filters': [
                {'TopicArn': topic_arn},
                {'type': 'cross-account',
                 'whitelist': ["123456789012"]}
            ],
            'actions': [
                {'type': 'remove-statements',
                 'statement_ids': 'matched'}]
            },
            session_factory=session_factory)
        resources = p.run()

        self.assertEqual([r['TopicArn'] for r in resources], [topic_arn])

        data = json.loads(client.get_topic_attributes(
            TopicArn=resources[0]['TopicArn'])['Attributes']['Policy'])
        self.assertEqual(
            [s['Sid'] for s in data.get('Statement', ())],
            ['SpecificAllow'])

    @functional
    def test_sns_remove_named(self):
        session_factory = self.replay_flight_data('test_sns_remove_named')
        client = session_factory().client('sns')
        name = 'test-sns-remove-named'
        topic_arn = client.create_topic(Name=name)['TopicArn']
        self.addCleanup(client.delete_topic, TopicArn=topic_arn)

        client.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "SpecificAllow",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": ["SNS:Subscribe"],
                        "Resource": topic_arn
                    },
                    {
                        "Sid": "RemoveMe",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": ["SNS:GetTopicAttributes"],
                        "Resource": topic_arn
                    }
                ]
            })
        )

        p = self.load_policy({
            'name': 'sns-rm-named',
            'resource': 'sns',
            'filters': [{'TopicArn': topic_arn}],
            'actions': [
                {'type': 'remove-statements',
                 'statement_ids': ['RemoveMe']}]
            },
            session_factory=session_factory)

        resources = p.run()
        self.assertEqual(len(resources), 1)

        data = json.loads(client.get_topic_attributes(
            TopicArn=resources[0]['TopicArn'])['Attributes']['Policy'])
        self.assertTrue('RemoveMe' not in
            [s['Sid'] for s in data.get('Statement', ())])

