# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from tc_common import BaseTest


class TestNatGateway(BaseTest):

    @pytest.mark.vcr
    def test_nat_gateway_unused(self):
        policy = self.load_policy(
            {
                "name": "nat-gateway-unused",
                "resource": "tencentcloud.nat-gateway",
                "query": [{
                        "NatGatewayIds": ["nat-lf1cl2ne"]
                }],
                "filters": [
                    {
                        "type": "value",
                        "key": "CreatedTime",
                        "value_type": "age",
                        "op": "greater-than",
                        "value": 0
                    }
                ]
            }
        )
        resources = policy.run()
        assert resources[0]["NatGatewayId"] == "nat-lf1cl2ne"

    @pytest.mark.vcr
    def test_metrics(self):
        policy = self.load_policy(
            {
                "name": "nat-gateway-metrics-filter",
                "resource": "tencentcloud.nat-gateway",
                "filters": [
                    {
                        "type": "value",
                        "key": "CreatedTime",
                        "value_type": "age",
                        "op": "greater-than",
                        "value": 7
                    },
                    {
                        "type": "metrics",
                        "name": "Conns",
                        "statistics": "Maximum",
                        "days": 7,
                        "value": 0,
                        "missing-value": 0,
                        "op": "equal",
                        "period": 3600
                    }
                ]
            }
        )
        resources = policy.run()
        assert len(resources) == 1
