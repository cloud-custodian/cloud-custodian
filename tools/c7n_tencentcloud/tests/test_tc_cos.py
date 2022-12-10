# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import pytest
from tc_common import BaseTest


class TestCos(BaseTest):

    @pytest.mark.vcr
    def test_bucket_encryption(self):
        policy = self.load_policy(
            {
                "name": "test_bucket_encryption",
                "resource": "tencentcloud.cos",
                "filters": [
                    {"type": "bucket-encryption", "state": True, "crypto": "AES256"},
                    {"Name": "custodian-test-1253831162"}
                ]
            }
        )
        resources = policy.run()
        assert resources[0]["Name"] == "custodian-test-1253831162"

    @pytest.mark.vcr
    def test_bucket_logging(self):
        policy = self.load_policy(
            {
                "name": "test_bucket_logging",
                "resource": "tencentcloud.cos",
                "filters": [
                    {
                        "type": "bucket-logging",
                        "op": "not-equal",
                        "target_prefix": "{account_id}/{source_bucket_name}/",
                        "target_bucket": "42342-1253831162"
                    },
                    {"Name": "custodian-test-1253831162"}
                ]
            }
        )
        resources = policy.run()
        assert resources[0]["Name"] == "custodian-test-1253831162"

    @pytest.mark.vcr
    def test_bucket_has_statement(self):
        policy = self.load_policy(
            {
                "name": "test_has_statement",
                "resource": "tencentcloud.cos",
                "filters": [
                    {
                        "type": "has-statement",
                        "statements": [
                            {
                                "Effect": "Allow",
                                "Action": "name/cos:GetObject",
                                "Principal": "qcs::cam::anyone:anyone"
                            }
                        ]
                    },
                    {"Name": "custodian-test-1253831162"}
                ],
            }
        )
        resources = policy.run()
        assert resources[0]["Name"] == "custodian-test-1253831162"

    @pytest.mark.vcr
    def test_bucket_lifecycle(self):
        policy = self.load_policy(
            {
                "name": "test_bucket_lifecycle",
                "resource": "tencentcloud.cos",
                "filters": [
                    {
                        "type": "bucket-lifecycle",
                        "key": "Rule[?Status==`Enabled`].AbortIncompleteMultipartUpload"
                               ".DaysAfterInitiation",
                        "value": "30",
                        "value_type": "swap",
                        "op": "equal"
                    },
                    {"Name": "custodian-test-1253831162"}
                ]
            }
        )
        resources = policy.run()
        assert resources[0]["Name"] == "custodian-test-1253831162"

    @pytest.mark.vcr
    def test_bucket_tag(self):
        policy = self.load_policy(
            {
                "name": "test_bucket_tag",
                "resource": "tencentcloud.cos",
                "filters": [
                    {
                        "tag:test_pro_00001": "this is test"
                    },
                    {"Name": "custodian-test-1253831162"}
                ]
            }
        )
        resources = policy.run()
        assert resources[0]["Name"] == "custodian-test-1253831162"
