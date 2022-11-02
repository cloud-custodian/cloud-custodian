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
