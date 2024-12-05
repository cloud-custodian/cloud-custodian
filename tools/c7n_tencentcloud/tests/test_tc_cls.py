# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from tc_common import BaseTest


class TestLogGroup(BaseTest):

    @pytest.mark.vcr
    def test_cls_period(self):
        policy = self.load_policy(
            {
                "name": "cls_test",
                "resource": "tencentcloud.cls",
                "filters": [{"or": [{"Period": 7}, {"Period": None}, {"Period": 3600}]}]
            }
        )
        resources = policy.run()
        ok = [r for r in resources if r['TopicName'] == 'custodian-test']
        assert len(ok) > 0

    @pytest.mark.vcr
    def test_metrics(self):
        policy = self.load_policy(
            {
                "name": "filter-metrics-average",
                "resource": "tencentcloud.cls",
                "filters": [{
                    "type": "metrics",
                    "name": "TrafficWrite",
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
        assert len(resources) == 14
