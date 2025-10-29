# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
from .common import BaseTest


class TestOpsworksCM(BaseTest):
    def test_query_CM(self):
        p = self.load_policy(
            {"name": "get-opswork-cm", "resource": "opswork-cm"},
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)


class TestOpsWorksStack(BaseTest):
    def test_query_opsworks_stacks(self):
        p = self.load_policy(
            {"name": "get-opswork-stack", "resource": "opswork-stack"},
        )
        resources = p.run()
        self.assertEqual(len(resources), 0)
