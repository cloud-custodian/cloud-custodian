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

    @pytest.mark.vcr
    def test_mysql_backup_create_time_running(self):
        policy = self.load_policy(
            {
                "name": "test_mysql_backup_create_time_running",
                "resource": "tencentcloud.mysql-backup",
                "filters": [
                    {
                        "type": "value",
                        "key": "Status",
                        "value": "RUNNING"
                    },
                    {
                        "not": [
                            {
                                "type": "value",
                                "key": "Date",
                                "value": 0,
                                "value_type": "age",
                                "op": "greater-than"
                            }
                        ]
                    }
                ]
            }, config={"region": "na-ashburn"}
        )
        resources = policy.run()
        assert len(resources) == 1
