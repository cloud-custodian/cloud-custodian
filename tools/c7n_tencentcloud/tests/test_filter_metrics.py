# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from freezegun import freeze_time
import pytest
from tc_common import BaseTest
from c7n.exceptions import PolicyValidationError
from c7n_tencentcloud.filters import MetricsFilter
from c7n_tencentcloud.query import QueryResourceManager


class TestFilterMetrics(BaseTest):
    instance_ids = ["ins-dq1dmpgk", "ins-n198q4gc"]

    @pytest.mark.vcr
    def test_average(self):
        policy = self.load_policy(
            {
                "name": "filter-metrics-average",
                "resource": "tencentcloud.cvm",
                "query": [{
                    "InstanceIds": self.instance_ids
                }],
                "filters": [{
                    "type": "metrics",
                    "name": "CPUUsage",
                    "statistics": "Average",
                    "days": 3,
                    "op": "less-than",
                    "value": 1.5,
                    "missing-value": 0,
                    "period": 3600
                }]
            }
        )
        resources = policy.run()
        assert len(resources) == 2

    @pytest.mark.vcr
    def test_max(self):
        policy = self.load_policy(
            {
                "name": "filter-metrics-max",
                "resource": "tencentcloud.cvm",
                "query": [{
                    "InstanceIds": self.instance_ids
                }],
                "filters": [{
                    "type": "metrics",
                    "name": "CvmDiskUsage",
                    "statistics": "Maximum",
                    "days": 1,
                    "op": "less-than",
                    "value": 20,
                    "missing-value": 0,
                    "period": 300
                }]
            }
        )
        resources = policy.run()
        assert len(resources) == 1

        metrics_data = resources[0]['c7n.metrics']
        key = "QCE/CVM.CvmDiskUsage.Maximum.1"
        assert key in metrics_data
        annotation = metrics_data[key]
        assert annotation['Period'] == 300
        assert annotation['Statistic'] == 'Maximum'
        assert annotation['AggregatedValue'] <= 20

    @freeze_time("2022-08-01 00:00:00")
    def test_time_window(self, ctx):
        class Resource(QueryResourceManager):
            resource_type = None

        filter_config = {
            "type": "metrics",
            "name": "time_window_test",
            "namespace": "QCE/CVM",
            "statistics": "Maximum",
            "value": 0,
            "days": 1,
        }
        metrics_filter = MetricsFilter(filter_config, Resource(ctx, {}))
        start_time, end_time = metrics_filter.get_metric_window()
        assert start_time == "2022-07-31T00:00:00+00:00"
        assert end_time == "2022-08-01T00:00:00+00:00"

    def test_batch_size_limits(self, ctx):
        manager = self.load_policy({
            "name": "filter-metrics-batch-size",
            "resource": "tencentcloud.cvm",
            "query": [{
                "InstanceIds": self.instance_ids
            }]
        }).resource_manager

        filter_ten = MetricsFilter({
            "type": "metrics",
            "name": "CPUUsage",
            "statistics": "Average",
            "days": 3,
            "op": "less-than",
            "value": 10,
            "missing-value": 0,
            "period": 3600
        }, manager)
        filter_ten.validate()
        assert filter_ten.batch_size == 10

        filter_single = MetricsFilter({
            "type": "metrics",
            "name": "CPUUsage",
            "statistics": "Average",
            "days": 1,
            "op": "less-than",
            "value": 10,
            "missing-value": 0,
            "period": 60
        }, manager)
        filter_single.validate()
        assert filter_single.batch_size == 1

    def test_too_many_data_points(self):
        with pytest.raises(PolicyValidationError):
            policy = self.load_policy(
                {
                    "name": "filter-metrics-too-many-data-points",
                    "resource": "tencentcloud.cvm",
                    "query": [{
                        "InstanceIds": self.instance_ids
                    }],
                    "filters": [{
                        "type": "metrics",
                        "name": "CvmDiskUsage",
                        "statistics": "Maximum",
                        "days": 100,
                        "op": "less-than",
                        "value": 20,
                        "missing-value": 0,
                        "period": 300
                    }]
                }
            )
            policy.run()

    def test_validate_unknown_statistics(self, ctx):
        """Test validation error for unknown statistics"""
        manager = self.load_policy({
            "name": "test-policy",
            "resource": "tencentcloud.cvm",
        }).resource_manager
        
        metrics_filter = MetricsFilter({
            "type": "metrics",
            "name": "CPUUsage",
            "statistics": "Median",  # Invalid statistic
            "days": 1,
            "op": "less-than",
            "value": 10,
            "period": 300
        }, manager)
        
        with pytest.raises(PolicyValidationError, match="unknown statistics"):
            metrics_filter.validate()

    def test_validate_unknown_operator(self, ctx):
        """Test validation error for unknown operator"""
        manager = self.load_policy({
            "name": "test-policy",
            "resource": "tencentcloud.cvm",
        }).resource_manager
        
        metrics_filter = MetricsFilter({
            "type": "metrics",
            "name": "CPUUsage",
            "statistics": "Average",
            "days": 1,
            "op": "invalid-op",  # Invalid operator
            "value": 10,
            "period": 300
        }, manager)
        
        with pytest.raises(PolicyValidationError, match="unknown op"):
            metrics_filter.validate()

    def test_validate_zero_days(self, ctx):
        """Test validation error for zero days"""
        manager = self.load_policy({
            "name": "test-policy",
            "resource": "tencentcloud.cvm",
        }).resource_manager
        
        metrics_filter = MetricsFilter({
            "type": "metrics",
            "name": "CPUUsage",
            "statistics": "Average",
            "days": 0,  # Invalid: zero days
            "op": "less-than",
            "value": 10,
            "period": 300
        }, manager)
        
        with pytest.raises(PolicyValidationError, match="days value cannot be 0"):
            metrics_filter.validate()
