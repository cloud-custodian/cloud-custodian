# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time

import pytest

from tc_common import BaseTest
from test_tc_cvm import assert_instance_states


def get_tags(policy, resource):
    r = dict(resource)
    policy.resource_manager.source.get_resource_tag([r])
    return {t['Key']: t['Value'] for t in r.get('Tags', ())}


class TestCvmTagAction(BaseTest):

    @pytest.mark.vcr
    def test_cvm_mark_op_stop(self):
        policy = self.load_policy(
            {
                "name": "cvm-mark-for-op-stop",
                "resource": "tencentcloud.cvm",
                "query": [{
                    "InstanceIds": ["ins-00lycyy6"]
                }],
                "filters": [{"tag:maid_status": "absent"}],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "op": "stop",
                        "days": 14
                    }
                ]
            },
        )
        resources = policy.run()
        assert resources
        if self.recording:
            time.sleep(3)
        assert 'maid_status' in get_tags(policy, resources.pop())

    @pytest.mark.vcr
    def test_cvm_marked_op_stop_not_filter(self):
        policy = self.load_policy(
            {
                "name": "cvm-marked-for-op-stop",
                "resource": "tencentcloud.cvm",
                "query": [{
                    "InstanceIds": ["ins-00lycyy6"]
                }],
                "filters": [
                    {
                        "type": "marked-for-op",
                        "op": "stop",
                        "skew": 14
                    }, {
                        "not": [{
                            "type": "marked-for-op",
                            "op": "stop",
                            "skew": 14
                        }]
                    }
                ], "actions": [
                    {
                        "type": "stop"
                    }
                ]
            },
        )
        resources = policy.run()
        assert not resources
        if self.recording:
            time.sleep(10)

    @pytest.mark.vcr
    def test_cvm_marked_op_stop(self):
        policy = self.load_policy(
            {
                "name": "cvm-marked-for-op-stop",
                "resource": "tencentcloud.cvm",
                "query": [{
                    "InstanceIds": ["ins-00lycyy6"]
                }],
                "filters": [
                    {
                        "type": "marked-for-op",
                        "op": "stop",
                        "skew": 14
                    }
                ], "actions": [
                    {
                        "type": "stop"
                    }
                ]
            },
        )
        resources = policy.run()
        assert resources[0]["InstanceState"] == "RUNNING"
        if self.recording:
            time.sleep(10)
        assert_instance_states(policy, resources.pop(), ("STOPPING", "STOPPED"))

    @pytest.mark.vcr
    def test_cvm_mark_op_terminate_and_stop(self):
        policy = self.load_policy(
            {
                "name": "cvm-mark-for-op-terminate",
                "resource": "tencentcloud.cvm",
                "query": [{
                    "InstanceIds": ["ins-nhhm5ppo"]
                }],
                "actions": [
                    {
                        "type": "mark-for-op",
                        "op": "terminate",
                        "days": 7
                    },
                ]
            },
        )
        resources = policy.run()
        tags = get_tags(policy, resources.pop())
        assert 'maid_status' in tags

    @pytest.mark.vcr
    def test_add_tag(self):
        policy = self.load_policy(
            {
                "name": "cvm-test-tag",
                "resource": "tencentcloud.cvm",
                "query": [{
                    "InstanceIds": ["ins-00lycyy6", "ins-nhhm5ppo"]
                }],
                "filters": [{"tag:tag_add_test_key_for_test": "absent"}],
                "actions": [
                    {
                        "type": "tag",
                        "key": "tag_add_test_key_for_test",
                        "value": "tag_add_test_value_for_test"
                    }
                ]
            },
        )
        resources = policy.run()
        assert len(resources) == 2
        if self.recording:
            time.sleep(3)

        rtags = get_tags(policy, resources[-1])
        assert rtags.get('tag_add_test_key_for_test') == 'tag_add_test_value_for_test'

    @pytest.mark.vcr
    def test_modify_tag(self):
        policy = self.load_policy(
            {
                "name": "cvm-test-rename-tag",
                "resource": "tencentcloud.cvm",
                "query": [{
                    "InstanceIds": ["ins-00lycyy6", "ins-nhhm5ppo"]
                }],
                "filters": [{"tag:tag_add_test_key_for_test": "present"}],
                "actions": [
                    {
                        "type": "rename-tag",
                        "old_key": "tag_add_test_key_for_test",
                        "new_key": "tag_add_test_key_for_test_rename"
                    }
                ]
            },
        )
        resources = policy.run()
        assert len(resources) == 2
        if self.recording:
            time.sleep(10)

        rtags = get_tags(policy, resources[0])
        assert 'tag_add_test_key_for_test' not in rtags
        assert 'tag_add_test_key_for_test_rename' in rtags

    @pytest.mark.vcr
    def test_remove_tag(self):
        policy = self.load_policy(
            {
                "name": "cvm-test-remove-tag",
                "resource": "tencentcloud.cvm",
                "query": [{
                    "InstanceIds": ["ins-00lycyy6"]
                }],
                "filters": [{
                    "tag:tag_add_test_key_for_test_rename": "present"}],
                "actions": [
                    {
                        "type": "remove-tag",
                        "tags": ["tag_add_test_key_for_test_rename"]
                    }
                ]
            },
        )
        resources = policy.run()
        assert resources
        if self.recording:
            time.sleep(3)
        assert 'tag_add_test_key_for_test_rename' not in get_tags(policy, resources.pop())
