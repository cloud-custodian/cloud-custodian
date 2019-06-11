# Copyright 2018 Capital One Services, LLC
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

import time

from .common import BaseTest, TestConfig as Config


class CloudTrail(BaseTest):

    def test_trail_status(self):
        factory = self.replay_flight_data('test_cloudtrail_status')
        p = self.load_policy({
            'name': 'resource',
            'resource': 'cloudtrail',
            'filters': [{'type': 'status', 'key': 'IsLogging', 'value': True}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertTrue('c7n:TrailStatus' in resources[0])

    def test_trail_update(self):
        factory = self.replay_flight_data('test_cloudtrail_update')
        p = self.load_policy({
            'name': 'resource',
            'resource': 'cloudtrail',
            'filters': [
                {'Name': 'skunk-trails'}],
            'actions': [{
                'type': 'update-trail',
                'attributes': {
                    'EnableLogFileValidation': True}
            }]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(1)
        trails = factory().client('cloudtrail').describe_trails(trailNameList=['skunk-trails'])
        self.assertEqual(resources[0]['LogFileValidationEnabled'], False)
        self.assertEqual(trails['trailList'][0]['LogFileValidationEnabled'], True)

    def test_set_logging(self):
        factory = self.replay_flight_data('test_cloudtrail_set_logging')
        client = factory().client('cloudtrail')
        stat = client.get_trail_status(Name='orgTrail')

        self.assertEqual(stat['IsLogging'], True)
        p = self.load_policy({
            'name': 'resource',
            'resource': 'cloudtrail',
            'filters': [{
                'Name': 'orgTrail'}],
            'actions': [{
                'type': 'set-logging', 'enabled': False}]},
            session_factory=factory, config={'account_id': '644160558196'})

        resources = p.run()
        self.assertEqual(len(resources), 1)

        if self.recording:
            time.sleep(2)

        stat = client.get_trail_status(Name='orgTrail')
        self.assertEqual(stat['IsLogging'], False)

    def test_is_shadow(self):
        factory = self.replay_flight_data('test_cloudtrail_is_shadow')
        p = self.load_policy({
            'name': 'resource',
            'resource': 'cloudtrail',
            'filters': ['is-shadow']},
            session_factory=factory, config={'account_id': '111000111222'})
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(
            resources[0]['TrailARN'],
            'arn:aws:cloudtrail:us-east-1:644160558196:trail/orgTrail')

    def test_is_shadow_or_not(self):
        factory = self.replay_flight_data('test_cloudtrail_is_shadow_or_not')
        p = self.load_policy({
            'name': 'resource',
            'resource': 'cloudtrail',
            'filters': ['is-shadow']},
            session_factory=factory, config={'region': 'us-east-1'})
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(
            'arn:aws:cloudtrail:us-east-2:123456789012:trail/MultiRegion2CloudTrail',
            resources[0]['TrailARN'])

    def test_is_shadow_not(self):
        factory = self.replay_flight_data('test_cloudtrail_is_shadow_or_not')
        p = self.load_policy({
            'name': 'resource',
            'resource': 'cloudtrail',
            'filters': [{'type': 'is-shadow', 'state': False}]},
            session_factory=factory, config={'region': 'us-east-1'})
        resources = p.run()
        self.assertEqual(2, len(resources))
        self.assertEqual(
            'arn:aws:cloudtrail:us-east-1:123456789012:trail/MultiRegion1CloudTrail',
            resources[0]['TrailARN'])
        self.assertEqual(
            'arn:aws:cloudtrail:us-east-1:123456789012:trail/SingleCloudTrail',
            resources[1]['TrailARN'])

    def test_is_shadow_multiregion(self):
        factory = self.replay_flight_data('test_cloudtrail_is_shadow_or_not')
        p = self.load_policy({
            'name': 'resource',
            'resource': 'cloudtrail',
            'filters': ['is-shadow']},
            session_factory=factory, config={'region': 'us-east-2'})
        resources = p.run()
        self.assertEqual(1, len(resources))
        self.assertEqual(
            'arn:aws:cloudtrail:us-east-1:123456789012:trail/MultiRegion1CloudTrail',
            resources[0]['TrailARN'])

    def test_cloudtrail_resource_with_not_filter(self):
        factory = self.replay_flight_data("test_cloudtrail_resource_with_not_filter")
        p = self.load_policy(
            {
                "name": "cloudtrail-resource",
                "resource": "cloudtrail",
                "filters": [{
                    "not": [{
                        "type": "value",
                        "key": "Name",
                        "value": "skunk-trails"
                    }]
                }]
            },
            config=Config.empty(),
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
