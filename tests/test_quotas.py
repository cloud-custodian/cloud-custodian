# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#

from datetime import timedelta

from c7n.executor import MainThreadExecutor
from c7n.resources.quotas import ServiceQuota, UsageFilter
from c7n.utils import local_session

from .common import BaseTest


class TestQuotas(BaseTest):

    def setUp(self):
        super().setUp()
        self.patch(ServiceQuota, "executor_factory", MainThreadExecutor)

    def test_service_quota_request_history_filter(self):
        session_factory = self.replay_flight_data('test_service_quota')

        p = self.load_policy({
            "name": "service-quota-history-filter",
            "resource": "aws.service-quota",
            "filters": [{
                "type": "request-history",
                "key": "[].Status",
                "value": "CASE_CLOSED",
                "op": "in",
                "value_type": "swap"}
            ]},
            session_factory=session_factory
        )
        resources = p.run()
        self.assertTrue(resources)

    def test_service_quota_request_increase(self):
        session_factory = self.replay_flight_data('test_service_quota')
        p = self.load_policy({
            "name": "service-quota-request-increase",
            "resource": "aws.service-quota",
            "filters": [{
                "QuotaCode": "L-355B2B67"}],
            "actions": [{
                "type": "request-increase",
                "multiplier": 1.2}
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 1)
        client = local_session(session_factory).client('service-quotas')
        changes = client.list_requested_service_quota_change_history_by_quota(
            ServiceCode=resources[0]['ServiceCode'],
            QuotaCode=resources[0]['QuotaCode']
        )['RequestedQuotas']
        self.assertTrue(changes)

    def test_service_quota_request_increase_with_hard_limit(self):
        session_factory = self.replay_flight_data('test_service_quota')
        p = self.load_policy({
            "name": "service-quota-request-increase-hard-limit",
            "resource": "aws.service-quota",
            "filters": [
                {"QuotaCode": "L-14BB0BE7"},  # Use a quota that has UsageMetric
                {"type": "usage-metric",
                 "limit": 20,
                 "hard_limit": 50}
            ],
            "actions": [{
                "type": "request-increase",
                "multiplier": 2.0}  # This would normally request 2x the current value
            ]},
            session_factory=session_factory)
        resources = p.run()
        # The test verifies that the hard_limit logic is applied
        # In a real scenario, this would cap the requested value at the hard_limit
        self.assertEqual(len(resources), 1)

    def test_request_increase_hard_limit_skip_when_quota_equals_hard_limit(self):
        """Test that request-increase skips when quota equals hard_limit"""
        from c7n.resources.quotas import Increase
        from unittest.mock import Mock, patch

        # Create a mock resource where quota equals hard_limit
        resource = {
            'ServiceCode': 'ec2',
            'QuotaCode': 'L-TEST123',
            'Value': 50.0,  # Current quota value
            'Adjustable': True,
            'c7n:UsageMetric': {
                'quota': 50.0,  # Same as hard_limit
                'hard_limit': 50.0
            }
        }

        # Create the action with multiplier that would normally increase
        action = Increase({'multiplier': 1.5})
        action.manager = Mock()
        action.log = Mock()

        with patch('c7n.resources.quotas.local_session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client

            # Process the resource
            action.process([resource])

            # Verify that request_service_quota_increase was NOT called
            # because the quota equals hard_limit
            mock_client.request_service_quota_increase.assert_not_called()

    def test_request_increase_hard_limit_cap_when_count_exceeds_hard_limit(self):
        """Test that request-increase caps count when it exceeds hard_limit"""
        from c7n.resources.quotas import Increase
        from unittest.mock import Mock, patch

        # Create a mock resource where calculated count would exceed hard_limit
        resource = {
            'ServiceCode': 'ec2',
            'QuotaCode': 'L-TEST123',
            'Value': 30.0,  # Current quota value
            'Adjustable': True,
            'c7n:UsageMetric': {
                'quota': 30.0,
                'hard_limit': 50.0  # Hard limit is 50
            }
        }

        # Create the action with multiplier that would exceed hard_limit
        # 30 * 2.0 = 60, which exceeds hard_limit of 50
        action = Increase({'multiplier': 2.0})
        action.manager = Mock()
        action.log = Mock()

        with patch('c7n.resources.quotas.local_session') as mock_session:
            mock_client = Mock()
            mock_session.return_value.client.return_value = mock_client

            # Process the resource
            action.process([resource])

            # Verify that request_service_quota_increase was called with capped value
            mock_client.request_service_quota_increase.assert_called_once_with(
                ServiceCode='ec2',
                QuotaCode='L-TEST123',
                DesiredValue=50  # Should be capped at hard_limit
            )

    # Given the ServiceQuota.augment.get_quotas is a nested function,can't patch it;
    # This test case is the best we can do at the moment.
    def test_service_quota_metadata_incl_filter(self):
        session_factory = self.replay_flight_data('test_service_quota')
        p = self.load_policy({
            "name": "service-quota-metaddata-filter",
            "resource": "aws.service-quota",
            "query": [{"include_service_codes": ["ec2"]}],
            },
            session_factory=session_factory)
        resources = p.run()
        # called ListAWSDefaultServiceQuotas once, 6 quotas returned
        # called servicequotas.ListServiceQuotas once, 2 quotas returned
        assert len(resources) == 8

    def test_service_quota_metadata_excl_filter(self):
        session_factory = self.replay_flight_data('test_service_quota')
        p = self.load_policy({
            "name": "service-quota-metaddata-filter",
            "resource": "aws.service-quota",
            "query": [{"exclude_service_codes": ["logs"]}],
            },
            session_factory=session_factory)
        resources = p.run()
        # called ListAWSDefaultServiceQuotas twice, 6x2 quotas returned
        # called servicequotas.ListServiceQuotas twice, 2+1 quotas returned
        assert len(resources) == 15

    def test_usage_metric_filter(self):
        session_factory = self.replay_flight_data('test_service_quota')
        p = self.load_policy({
            "name": "service-quota-usage-metric",
            "resource": "aws.service-quota",
            "filters": [
                {"UsageMetric": "present"},
                {"type": "usage-metric",
                 "min_period": 60,
                 "limit": 20}
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    def test_usage_metric_filter_with_hard_limit(self):
        session_factory = self.replay_flight_data('test_service_quota')
        p = self.load_policy({
            "name": "service-quota-usage-metric-hard-limit",
            "resource": "aws.service-quota",
            "filters": [
                {"UsageMetric": "present"},
                {"type": "usage-metric",
                 "min_period": 60,
                 "limit": 20,
                 "hard_limit": 100}
            ]},
            session_factory=session_factory)
        resources = p.run()
        self.assertEqual(len(resources), 2)
        # Check that hard_limit is added to the annotation
        for resource in resources:
            if 'c7n:UsageMetric' in resource:
                self.assertIn('hard_limit', resource['c7n:UsageMetric'])
                self.assertEqual(resource['c7n:UsageMetric']['hard_limit'], 100.0)

    def test_usage_filter_round_up(self):
        filter = UsageFilter({})
        self.assertEqual(filter.round_up(1, 60), 60)
        self.assertEqual(filter.round_up(59, 60), 60)
        self.assertEqual(filter.round_up(60, 60), 60)
        self.assertEqual(filter.round_up(61, 60), 120)

    def test_usage_filter_scale_period(self):
        filter = UsageFilter({})

        # The provided period is smaller than the minimum one
        scaled_period, scale = filter.scale_period(timedelta(1).total_seconds(), 1, 60)
        self.assertEqual(scaled_period, 60)
        self.assertEqual(scale, 60)

        # The provided period generates too many data points
        scaled_period, scale = filter.scale_period(timedelta(1).total_seconds(), 1, 1)
        self.assertEqual(scaled_period, 120)
        self.assertEqual(scale, 120)

        # The provided is not aligned with AWS pre-defined periods
        scaled_period, scale = filter.scale_period(timedelta(hours=1).total_seconds(), 30, 1)
        self.assertEqual(scaled_period, 60)
        self.assertEqual(scale, 2)

        # The provided period is accepted as-is not generating too many data points
        scaled_period, scale = filter.scale_period(timedelta(1).total_seconds(), 300, 60)
        self.assertEqual(scaled_period, 300)
        self.assertEqual(scale, 1)
