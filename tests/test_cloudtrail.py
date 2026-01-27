# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
from .common import BaseTest


class CloudTrail(BaseTest):

    def test_trail_tag_augment(self):
        factory = self.replay_flight_data('test_trail_tag_augment')
        p = self.load_policy({
            'name': 'resource',
            'resource': 'aws.cloudtrail',
            'filters': [{'tag:App': 'c7n'}]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'skunk-trails')

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

    def test_event_selectors(self):
        factory = self.replay_flight_data('test_cloudtrail_event_selectors')
        p = self.load_policy({
            'name': 'resource',
            'resource': 'cloudtrail',
            'filters': [{
                'type': 'event-selectors',
                'key': 'EventSelectors[].IncludeManagementEvents',
                'op': 'contains',
                'value': True
            }]},
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 4)

        for resource in resources:
            self.assertTrue('c7n:TrailEventSelectors' in resource)
            selectors = resource['c7n:TrailEventSelectors']['EventSelectors']
            self.assertEqual(len(selectors), 1)
            self.assertTrue('IncludeManagementEvents' in selectors[0])
            self.assertTrue(selectors[0]['IncludeManagementEvents'])

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
            session_factory=factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def test_cloudtrail_delete(self):
        factory = self.replay_flight_data("test_cloudtrail_delete")
        p = self.load_policy(
            {
                "name": "cloudtrail-resource",
                "resource": "cloudtrail",
                "filters": [{'type': 'value', 'key': 'Name', 'value': 'delete-me'}],
                'actions': [{'type': 'delete'}],
            },
            session_factory=factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['Name'], 'delete-me')

        if self.recording:
            time.sleep(3)

        client = factory().client('cloudtrail')
        self.assertRaises(
            client.exceptions.TrailNotFoundException,
            client.delete_trail,
            Name=resources[0]['Name'])
