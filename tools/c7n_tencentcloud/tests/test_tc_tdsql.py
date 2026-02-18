# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest

from c7n.config import Config
from tc_common import BaseTest


class TestTDSql(BaseTest):

    @pytest.mark.vcr
    def test_tdsql(self):
        policy = self.load_policy(
            {
                "name": "tdsql-check",
                "resource": "tencentcloud.tdsql",
                "filters": [
                    {
                        "type": "value",
                        "key": "InstanceName",
                        'value': "tdsqlshard-b1ckdxcx",
                    }
                ]
            },
            config=Config.empty(**{
                "region": "ap-nanjing",
                "account_id": "100009291175",
                "output_dir": "null://",
                "log_group": "null://",
                "cache": False,
            })
        )
        resources = policy.run()
        ok = [r for r in resources if r["InstanceName"] == "tdsqlshard-b1ckdxcx"]
        assert len(ok) > 0
