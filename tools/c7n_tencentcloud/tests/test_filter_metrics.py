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
