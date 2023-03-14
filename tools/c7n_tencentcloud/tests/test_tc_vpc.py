# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest

from c7n.config import Config
from tc_common import BaseTest


class TestVpc(BaseTest):

    @pytest.mark.vcr
    def test_vpc_flowlogs_enabled_pull(self):
        policy = self.load_policy(
            {
                "name": "vpc-flowlogs-enabled-pull",
                "resource": "tencentcloud.vpc",
                "query": [{"VpcIds": ["vpc-ha7fbuzt"]}],
                "filters": [
                    {
                        "type": "flow-logs",
                        "enabled": True,
                        'match': [
                            {'FlowLogId': 'fl-gjdtklll'}, {'Enable': True}],
                    }
                ]
            },
            config=Config.empty(**{
                "region": "ap-guangzhou",  # just for init, ignore the value
                "account_id": "100000750436",
                "output_dir": "null://",
                "log_group": "null://",
                "cache": False,
            })
        )
        resources = policy.run()
        ok = [r for r in resources if r["VpcId"] == "vpc-ha7fbuzt"]
        assert len(ok) > 0
