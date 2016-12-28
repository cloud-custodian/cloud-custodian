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

    def test_resource(self):
        session_factory = self.record_flight_data('test_health_resources')
        p = self.load_policy({
            'name': 'health-events',
            'resource': 'health'
        }, session_factory=session_factory)
        resources = p.run()
        self.assertGreater(len(resources), 0)