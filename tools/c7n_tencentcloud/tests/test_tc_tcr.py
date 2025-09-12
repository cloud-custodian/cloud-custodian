# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from tc_common import BaseTest


class TestTCR(BaseTest):

    @pytest.mark.vcr
    def test_tcr(self):
        policy = self.load_policy(
            {
                "name": "tcr-lifecycle-rule",
                "resource": "tencentcloud.tcr",
                "query": [{"Registryids": ["tcr-cguc6m2c"]}],
                "filters": [{"type": "lifecycle-rule",
                             "state": True,
                             'match': [{'NamespaceName': 'custodian-test-namespace-2'},
                                       {'RetentionRuleList[0].Value': 4}]}]
            }
        )
        resources = policy.run()
        ok = [r for r in resources if r["RegistryId"] == "tcr-cguc6m2c"]
        assert len(ok) > 0
