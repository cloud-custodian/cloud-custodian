# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import time

import pytest
from pytest_terraform import terraform

from c7n.exceptions import PolicyExecutionError, PolicyValidationError
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


ADVANCED_SELECTORS = [
    {
        'Name': 'Log all management events',
        'FieldSelectors': [
            {'Field': 'eventCategory', 'Equals': ['Management']},
        ],
    },
    {
        'Name': 'Log S3 object writes',
        'FieldSelectors': [
            {'Field': 'eventCategory', 'Equals': ['Data']},
            {'Field': 'resources.type', 'Equals': ['AWS::S3::Object']},
            {'Field': 'readOnly', 'Equals': ['false']},
        ],
    },
]


def set_selectors_policy(test, factory, trail_name, filters, action):
    return test.load_policy(
        {
            'name': 'cloudtrail-set-event-selectors',
            'resource': 'aws.cloudtrail',
            'filters': [{'Name': trail_name}] + filters,
            'actions': [dict(action, type='set-event-selectors')],
        },
        session_factory=factory,
    )


@terraform('cloudtrail_set_event_selectors', scope='session')
def test_cloudtrail_set_event_selectors(test, cloudtrail_set_event_selectors):
    """Basic -> advanced replaces the basic selectors, and a filter on the
    same selector type stops matching once the action has run."""
    factory = test.replay_flight_data('test_cloudtrail_set_event_selectors')
    trail_name = cloudtrail_set_event_selectors['aws_cloudtrail.advanced.name']
    policy = set_selectors_policy(
        test, factory, trail_name,
        [{'type': 'event-selectors', 'key': 'AdvancedEventSelectors', 'value': 'empty'}],
        {'advanced-event-selectors': ADVANCED_SELECTORS})

    resources = policy.run()

    assert [r['Name'] for r in resources] == [trail_name]
    client = factory().client('cloudtrail')
    selectors = client.get_event_selectors(TrailName=trail_name)
    assert not selectors.get('EventSelectors')
    assert [s['Name'] for s in selectors['AdvancedEventSelectors']] == [
        s['Name'] for s in ADVANCED_SELECTORS]

    assert policy.run() == []


@terraform('cloudtrail_set_event_selectors', scope='session')
def test_cloudtrail_set_event_selectors_basic(test, cloudtrail_set_event_selectors):
    """Advanced -> basic replaces the advanced selectors."""
    factory = test.replay_flight_data('test_cloudtrail_set_event_selectors_basic')
    trail_name = cloudtrail_set_event_selectors['aws_cloudtrail.basic.name']
    basic_selectors = [{
        'ReadWriteType': 'WriteOnly',
        'IncludeManagementEvents': True,
        'DataResources': [{
            'Type': 'AWS::S3::Object',
            'Values': [cloudtrail_set_event_selectors['aws_s3_bucket.trail.arn'] + '/'],
        }],
    }]
    set_selectors_policy(
        test, factory, trail_name, [],
        {'advanced-event-selectors': ADVANCED_SELECTORS}).run()
    policy = set_selectors_policy(
        test, factory, trail_name,
        [{'type': 'event-selectors', 'key': 'EventSelectors', 'value': 'empty'}],
        {'event-selectors': basic_selectors})

    resources = policy.run()

    assert [r['Name'] for r in resources] == [trail_name]
    client = factory().client('cloudtrail')
    selectors = client.get_event_selectors(TrailName=trail_name)
    assert not selectors.get('AdvancedEventSelectors')
    assert len(selectors['EventSelectors']) == 1
    selector = selectors['EventSelectors'][0]
    assert selector['ReadWriteType'] == 'WriteOnly'
    assert selector['DataResources'] == basic_selectors[0]['DataResources']


@terraform('cloudtrail_set_event_selectors', scope='session')
def test_cloudtrail_set_event_selectors_mismatch(test, cloudtrail_set_event_selectors):
    """A filter on basic selectors paired with an action writing advanced
    selectors keeps matching, so the policy re-applies on every run."""
    factory = test.replay_flight_data('test_cloudtrail_set_event_selectors_mismatch')
    trail_name = cloudtrail_set_event_selectors['aws_cloudtrail.mismatch.name']
    policy = set_selectors_policy(
        test, factory, trail_name,
        [{
            'type': 'event-selectors',
            'key': "EventSelectors[?DataResources[?Type=='AWS::S3::Object']] | []",
            'value': 'empty',
        }],
        {'advanced-event-selectors': ADVANCED_SELECTORS})

    assert [r['Name'] for r in policy.run()] == [trail_name]
    assert [r['Name'] for r in policy.run()] == [trail_name]


@terraform('cloudtrail_set_event_selectors', scope='session')
def test_cloudtrail_set_event_selectors_not_found(test, cloudtrail_set_event_selectors, caplog):
    """A trail deleted after it was described is skipped, not an error."""
    factory = test.replay_flight_data('test_cloudtrail_set_event_selectors_not_found')
    trail_name = cloudtrail_set_event_selectors['aws_cloudtrail.advanced.name']
    policy = set_selectors_policy(
        test, factory, trail_name, [],
        {'advanced-event-selectors': ADVANCED_SELECTORS})
    missing_arn = cloudtrail_set_event_selectors['aws_cloudtrail.advanced.arn'] + '-missing'

    with caplog.at_level(logging.WARNING):
        policy.resource_manager.actions[0].process(
            [{'Name': trail_name + '-missing', 'TrailARN': missing_arn}])

    assert f"trail {missing_arn} no longer exists" in caplog.text


@terraform('cloudtrail_set_event_selectors', scope='session')
def test_cloudtrail_set_event_selectors_error(test, cloudtrail_set_event_selectors):
    """A rejected trail doesn't stop the remaining trails from being attempted,
    and the failures are raised once every trail has been tried."""
    factory = test.replay_flight_data('test_cloudtrail_set_event_selectors_error')
    trail_names = [
        cloudtrail_set_event_selectors['aws_cloudtrail.advanced.name'],
        cloudtrail_set_event_selectors['aws_cloudtrail.basic.name'],
    ]
    # well formed, so it passes shape validation, but AWS rejects the field
    policy = test.load_policy(
        {
            'name': 'cloudtrail-set-event-selectors',
            'resource': 'aws.cloudtrail',
            'filters': [{'type': 'value', 'key': 'Name', 'op': 'in', 'value': trail_names}],
            'actions': [{
                'type': 'set-event-selectors',
                'advanced-event-selectors': [{
                    'Name': 'Invalid field',
                    'FieldSelectors': [{'Field': 'c7nInvalidField', 'Equals': ['x']}],
                }],
            }],
        },
        session_factory=factory,
    )

    with pytest.raises(PolicyExecutionError) as e:
        policy.run()

    assert "failed on 2 trail(s)" in str(e.value)
    for name in trail_names:
        assert f"trail/{name}" in str(e.value)


@pytest.mark.parametrize('action', [
    {'type': 'set-event-selectors'},
    {
        'type': 'set-event-selectors',
        'event-selectors': [{'ReadWriteType': 'All'}],
        'advanced-event-selectors': [
            {'FieldSelectors': [{'Field': 'eventCategory', 'Equals': ['Management']}]}],
    },
    {
        'type': 'set-event-selectors',
        'event-selectors': [{'IncludeManagementEvents': 'yes'}],
    },
    {'type': 'set-event-selectors', 'event-selectors': []},
    {'type': 'set-event-selectors', 'advanced-event-selectors': []},
])
@pytest.mark.parametrize('validate', [False, True])
def test_cloudtrail_set_event_selectors_validation(test, action, validate):
    with pytest.raises(PolicyValidationError):
        test.load_policy({
            'name': 'cloudtrail-set-event-selectors',
            'resource': 'aws.cloudtrail',
            'actions': [action],
        }, validate=validate)
