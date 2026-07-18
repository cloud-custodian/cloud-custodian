# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from c7n.exceptions import PolicyValidationError
from c7n.resources.health import HealthQueryParser


from .common import BaseTest


class HealthResource(BaseTest):

    def test_health_query(self):
        session_factory = self.replay_flight_data("test_health_query")
        p = self.load_policy(
            {"name": "account-health-query", "resource": "health-event"},
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_health_resource_query(self):
        session_factory = self.replay_flight_data("test_health_resource_query")
        p = self.load_policy(
            {
                "name": "account-health-ec2-query",
                "resource": "health-event",
                "query": [{"services": "EC2"}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["service"], "EC2")

    def test_health_augment(self):
        session_factory = self.replay_flight_data("test_health_augment")
        p = self.load_policy(
            {
                "name": "account-health-augment",
                "resource": "health-event",
                "query": [{"services": ["BILLING", "IAM"]}],
            },
            session_factory=session_factory,
        )
        resources = p.run()
        for r in resources:
            self.assertTrue("Description" in r)
            self.assertTrue(
                (r["eventTypeCategory"] == "accountNotification") ^ ("AffectedEntities" in r)
            )


class TestHealthQueryParser(BaseTest):
    def test_query(self):
        self.assertEqual(HealthQueryParser.parse([]), [])

        query = [
            {'availabilityZones': 'us-east-1a'},
            {'availabilityZones': 'us-east-1b'},
            {'services': 'EC2'},
            {'maxResults': 10}
        ]
        result_query = [
            {'availabilityZones': ['us-east-1a', 'us-east-1b']},
            {'services': ['EC2']},
            {'maxResults': 10}
        ]
        self.assertEqual(HealthQueryParser.parse(query), result_query)

        query = [{'eventStatusCodes': ['open', 'upcoming']}]
        self.assertEqual(HealthQueryParser.parse(query), query)

        query = [{"eventTypeCategories": 'issue'}]
        self.assertEqual(HealthQueryParser.parse(query), [{"eventTypeCategories": ['issue']}])

    def test_invalid_query(self):
        self.assertRaises(PolicyValidationError, HealthQueryParser.parse, [{"maxResults": [10]}])

        self.assertRaises(PolicyValidationError, HealthQueryParser.parse, [
            {"maxResults": 10}, {"maxResults": 20}])

        self.assertRaises(PolicyValidationError, HealthQueryParser.parse, [{"tag:Test": "True"}])

        self.assertRaises(PolicyValidationError, HealthQueryParser.parse, [{"regions": None}])

        self.assertRaises(PolicyValidationError, HealthQueryParser.parse, [{"foo": "bar"}])

        self.assertRaises(PolicyValidationError, HealthQueryParser.parse, [
            {"too": "many", "keys": "error"}])

        self.assertRaises(PolicyValidationError, HealthQueryParser.parse, ["Not a dictionary"])

        self.assertRaises(PolicyValidationError, HealthQueryParser.parse, {
            'event-status-codes': ['open', 'upcoming']})

        self.assertRaises(PolicyValidationError, HealthQueryParser.parse, {
            'eventStatusCodes': ['done']})
