# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import time
import pytest

from c7n.exceptions import PolicyExecutionError

from tc_common import BaseTest


STATE_MISSING = "MISSING"


def assert_instance_states(policy, instance, states):
    manager = policy.resource_manager
    client = manager.get_client()
    result = client.execute_query(
        "DescribeInstances", {'InstanceIds': instance[manager.resource_type.id]})
    if states is STATE_MISSING:
        assert not result['Response']['InstanceSet']
        return
    data = result['Response']['InstanceSet'][0]
    assert data['InstanceState'] in states


class TestCvmAction(BaseTest):

    @pytest.mark.vcr
    def test_cvm_stop(self):
        policy = self.load_policy(
            {
                "name": "cvm-stop-test",
                "resource": "tencentcloud.cvm",
                "comment": "stop cvm",
                "query": [{
                    "InstanceIds": ["ins-00lycyy6"]
                }],
                "filters": [{"InstanceState": "RUNNING"}],
                "actions": [
                    {
                        "type": "stop"
                    }
                ]
            },
        )
        resources = policy.run()
        assert resources
        if self.recording:
            time.sleep(10)
        assert_instance_states(policy, resources.pop(), ("STOPPING", "STOPPED"))

    @pytest.mark.vcr
    def test_cvm_start(self):
        policy = self.load_policy(
            {
                "name": "cvm-start-test",
                "resource": "tencentcloud.cvm",
                "comment": "start cvm",
                "query": [{
                    "InstanceIds": ["ins-00lycyy6"]
                }],
                "filters": [{"InstanceState": "STOPPED"}],
                "actions": [
                    {
                        "type": "start"
                    }
                ]
            },
        )
        resources = policy.run()
        assert resources
        if self.recording:
            time.sleep(10)
        assert_instance_states(policy, resources.pop(), ("STARTING", "RUNNING"))

    @pytest.mark.vcr
    def test_cvm_terminate(self):
        policy = self.load_policy(
            {
                "name": "cvm-terminate-test",
                "resource": "tencentcloud.cvm",
                "comment": "terminate cvm",
                "query": [{
                    "InstanceIds": ["ins-8ktxnl0g"]
                }],
                "actions": [
                    {
                        "type": "terminate"
                    }
                ]
            },
        )
        resources = policy.run()
        assert len(resources) == 1
        if self.recording:
            time.sleep(10)
        assert_instance_states(policy, resources.pop(), STATE_MISSING)

    @pytest.mark.vcr
    def test_cvm_exec_exception(self, monkeypatch):
        def get_params(*args):
            return {"InstanceIds": "hello"}
        policy = self.load_policy({
            "name": "cvm-err-test",
            "resource": "tencentcloud.cvm",
            "actions": ["stop"]})

        stop = policy.resource_manager.actions[0]
        monkeypatch.setattr(stop, "get_request_params", get_params)
        with pytest.raises(PolicyExecutionError):
            stop.process([{'InstanceState': 'RUNNING'}])
