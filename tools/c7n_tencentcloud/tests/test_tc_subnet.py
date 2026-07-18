import pytest

from c7n.config import Config
from tc_common import BaseTest


class TestSubnet(BaseTest):

    @pytest.mark.vcr
    def test_tencentcloud_subnet_list(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-subnet",
                "resource": "tencentcloud.subnet",
                "filters": [{"SubnetId": "subnet-8i3da4re"}]
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
        ok = [r for r in resources if r["SubnetId"] == "subnet-8i3da4re"]
        assert len(ok) > 0
