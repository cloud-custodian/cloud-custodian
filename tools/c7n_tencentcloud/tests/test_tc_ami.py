# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from tc_common import BaseTest


class TestAmi(BaseTest):

    @pytest.mark.vcr
    def test_ami_old_and_not_used(self):
        policy = self.load_policy(
            {
                "name": "test_ami_old_and_not_used",
                "resource": "tencentcloud.ami",
                "filters": [
                    {
                        "type": "unused",
                        "value": True
                    }, {
                        "type": "value",
                        "key": "CreatedTime",
                        "value_type": "date",
                        "value": "2022-06-16",
                        "op": "lt"
                    }
                ]
            }
        )
        resources = policy.run()
        assert resources[0]["ImageId"] == "img-8uhppmle"
