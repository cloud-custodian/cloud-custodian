import json
import datetime
import os
import tempfile

from unittest import TestCase
from common import load_data, BaseTest
from test_offhours import mock_datetime_now

from dateutil import parser

from c7n.filters.iamaccess import check_cross_account, CrossAccountAccessFilter
from c7n.mu import LambdaManager, LambdaFunction, PythonPackageArchive
from c7n.resources.sns import SNS
from c7n.executor import MainThreadExecutor


class HealthResource(BaseTest):

    def test_health_query(self):
        session_factory = self.replay_flight_data('test_health_query')
        p = self.load_policy({
            'name': 'account-health-query',
            'resource': 'health-events'}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 0)

    def test_health_resource_query(self):
        session_factory = self.replay_flight_data('test_health_resource_query')
        p = self.load_policy({
            'name': 'account-health-ec2-query',
            'resource': 'health-events',
            'query': [{'services': 'EC2'}]}, session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]['service'], 'EC2')

    def test_health_augment(self):
        session_factory = self.replay_flight_data('test_health_augment')
        p = self.load_policy({
            'name': 'account-health-augment',
            'resource': 'health-events',
            'query': [{'services': ['BILLING', 'IAM']}]}, session_factory=session_factory)
        resources = p.run()
        for r in resources:
            self.assertTrue('eventDescription' in r)
            self.assertTrue('latestDescription' in r['eventDescription'])
            self.assertTrue((r['eventTypeCategory'] == 'accountNotification') ^('affectedEntities' in r))
            
