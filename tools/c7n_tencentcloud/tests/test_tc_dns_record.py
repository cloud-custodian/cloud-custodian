# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest

from c7n.config import Config
from tc_common import BaseTest


class TestDnsRecord(BaseTest):

    @pytest.mark.vcr
    def test_dns_records(self):
        policy = self.load_policy(
            {
                "name": "dns-record-list",
                "resource": "tencentcloud.dns-record",
                "filters": [{"domain": "c7n.tonykai.xyz"}]
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
        ok = [r for r in resources if r["Value"] == "8.8.8.8"]
        assert len(ok) > 0
