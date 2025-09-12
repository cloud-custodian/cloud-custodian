# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest

from c7n.config import Config
from tc_common import BaseTest


class TestEIP(BaseTest):

    @pytest.mark.vcr
    def test_eip_list(self):
        policy = self.load_policy(
            {
                "name": "eip-list",
                "resource": "tencentcloud.eip",
                "filters": [{"AddressIp": "43.166.136.187"}]
            },
            config=Config.empty(**{
                "region": "na-ashburn",  # just for init, ignore the value
                "account_id": "100009291175",
                "output_dir": "null://",
                "log_group": "null://",
                "cache": False,
            })
        )
        resources = policy.run()
        ok = [r for r in resources if r["AddressIp"] == "43.166.136.187"]
        assert len(ok) > 0
