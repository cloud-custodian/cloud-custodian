# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from tc_common import BaseTest


class TestElasticsearch(BaseTest):

    @pytest.mark.vcr
    def test_elasticsearch_key(self):
        policy = self.load_policy(
            {
                "name": "elasticsearch-instance-generation",
                "resource": "tencentcloud.elasticsearch",
                "filters": [
                    {
                        "type": "value",
                        "key": "NodeInfoList[0].NodeType",
                        "op": "in",
                        "value": ['ES.S1.MEDIUM4']
                    }
                ]
            }
        )
        resources = policy.run()

        ok = [r for r in resources if r["InstanceId"] == "es-2j1xw4ab"]
        assert len(ok) > 0
