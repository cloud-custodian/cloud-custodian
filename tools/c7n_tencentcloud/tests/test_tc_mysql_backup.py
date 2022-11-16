# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from tc_common import BaseTest


class TestMySQLBackUp(BaseTest):

    @pytest.mark.vcr
    def test_mysql_backup_create_time(self):
        policy = self.load_policy(
            {
                "name": "test_mysql_backup_create_time",
                "resource": "tencentcloud.mysql-backup",
                "filters": [
                    {
                        "type": "value",
                        "key": "Date",
                        "value": 0,
                        "value_type": "age",
                        "op": "greater-than"
                    }
                ]
            }
        )
        resources = policy.run()
        assert len(resources) > 0
