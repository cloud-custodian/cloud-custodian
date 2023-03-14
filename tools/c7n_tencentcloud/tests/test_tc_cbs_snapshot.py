# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from tc_common import BaseTest


class TestCbsSnapshot(BaseTest):

    @pytest.mark.vcr
    def test_cbs_old_snapshot(self):
        policy = self.load_policy(
            {
                "name": "cbs-old-snapshot",
                "resource": "tencentcloud.cbs-snapshot",
                "query": [{"SnapshotIds": ["snap-lbwv0qm5"]}],
                "filters": [
                    {
                        "type": "value",
                        "key": "CreateTime",
                        "value_type": "age",
                        "op": "greater-than",
                        "value": 90
                    }
                ]
            }
        )
        resources = policy.run()
        assert resources[0]["SnapshotId"] == "snap-lbwv0qm5"
