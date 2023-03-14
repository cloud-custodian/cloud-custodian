# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from tc_common import BaseTest
import time


class TestCbs(BaseTest):

    @pytest.mark.vcr
    def test_cbs_not_encrypt(self):
        policy = self.load_policy(
            {
                "name": "test_cbs_not_encrypt",
                "resource": "tencentcloud.cbs",
                "query": [{
                    "DiskIds": ["disk-96jhcorq"]
                }],
                "filters": [
                    {
                        "type": "value",
                        "key": "Encrypt",
                        "value": False
                    }
                ]
            }
        )
        resources = policy.run()
        assert len(resources) == 1 and not resources[0]["Encrypt"]

    @pytest.mark.vcr
    def test_cbs_available(self):
        policy = self.load_policy(
            {
                "name": "test_cbs_available",
                "resource": "tencentcloud.cbs",
                "comment": "Identify CBS Volumes that are not attached to any instances. "
                           "These volumes should be investigated and deleted if they are no "
                           "longer in use.",
                "query": [{
                    "DiskIds": ["disk-3i2gnf0k"]
                }],
                "filters": [
                    {
                        "DiskState": "UNATTACHED"
                    }
                ]
            }
        )
        resources = policy.run()
        assert len(resources) == 1 and resources[0]["DiskState"] == "UNATTACHED"

    @pytest.mark.vcr
    def test_cbs_copy_instance_tags(self):
        policy = self.load_policy(
            {
                "name": "test_cbs_copy_instance_tags",
                "resource": "tencentcloud.cbs",
                "query": [{
                    "DiskIds": ["disk-96jhcorq"]
                }],
                "filters": [
                    {
                        "DiskState": "ATTACHED"
                    },
                    {
                        "type": "value",
                        "key": "InstanceIdList[0]",
                        "value": "not-null"
                    }
                ],
                "actions": [
                    {
                        "type": "copy-instance-tags",
                        "tags": ["test_pro_25", "test_pro_26"]
                    },
                    {
                        "type": "copy-instance-tags",
                        "tags": ["test_pro_27"]
                    },
                ]
            }
        )
        resources = policy.run()
        tags = resources[0]["Tags"]
        tag_not_exist = True
        new_tag_set = {"test_pro_25", "test_pro_26", "test_pro_27"}
        for tag in tags:
            tag_not_exist = tag["Key"] not in new_tag_set
            if not tag_not_exist:
                break
        assert tag_not_exist
        if self.recording:
            time.sleep(10)
        resources = policy.resource_manager.source.get_resource_tag(resources)
        tags = resources[0]["Tags"]
        for new_tag in new_tag_set:
            new_tag_exist = False
            for tag in tags:
                if tag["Key"] == new_tag:
                    new_tag_exist = True
                    break
            assert new_tag_exist

    @pytest.mark.vcr
    def test_metrics(self):
        policy = self.load_policy(
            {
                "name": "filter-metrics",
                "resource": "tencentcloud.cbs",
                "filters": [{
                    "type": "metrics",
                    "name": "DiskReadTraffic",
                    "statistics": "Average",
                    "days": 3,
                    "op": "less-than",
                    "value": 1,
                    "missing-value": 0,
                    "period": 3600
                }]
            }
        )
        resources = policy.run()
        assert len(resources) == 14
