# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import pytest
from tc_common import BaseTest


class TestCAM(BaseTest):

    @pytest.mark.vcr
    def test_mfa_missing(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-user-mfa-missing-pull",
                "resource": "tencentcloud.cam-user",
                "description": "all Users who have console access should have an MFA assigned",
                "filters": [
                    {
                        "type": "credential",
                        "key": "ConsoleLogin",
                        "value": 1
                    },
                    {
                        "type": "credential",
                        "key": "login_mfa_active",
                        "value": False
                    }
                ]
            },
            account_id=100002098531
        )
        resources = policy.run()
        assert len(resources) == 1
        assert resources[0]["Uin"] == 100027755407

    @pytest.mark.vcr
    def test_stale_credentials(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-user-stale-credentials-pull",
                "resource": "tencentcloud.cam-user",
                "description": "check all users with stale credentials",
                "filters": [
                    {
                        "or": [
                            {
                                "and": [
                                    {
                                        "type": "credential",
                                        "key": "access_keys.Status",
                                        "value": "Active"
                                    },
                                    {
                                        "type": "credential",
                                        "key": "access_keys.LastUsedDate",
                                        "value_type": "age",
                                        "value": 1,
                                        "op": "gt"
                                    }
                                ]
                            },
                            {
                                "and": [
                                    {
                                        "type": "credential",
                                        "key": "ConsoleLogin",
                                        "value": 1
                                    },
                                    {
                                        "type": "credential",
                                        "key": "LastLoginTime",
                                        "value_type": "age",
                                        "value": 1,
                                        "op": "gt"
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            account_id=100002098531
        )
        resources = policy.run()
        assert len(resources) == 2

    @pytest.mark.vcr
    def test_too_many_credentials(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-user-too-many-access-keys-pull",
                "resource": "tencentcloud.cam-user",
                "description": "users have more than 1 active Access Key",
                "filters": [
                    {
                        "type": "credential",
                        "key": "access_keys.Status",
                        "value": "Active"
                    },
                    {
                        "type": "value",
                        "key": 'length("c7n:matched-keys")',
                        "value": 2
                    }
                ]
            },
            account_id=100002098531
        )
        resources = policy.run()
        assert len(resources) == 1
        assert resources[0]["Uin"] == 100027724164

    @pytest.mark.vcr
    def test_credential_rotation(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-user-access-key-rotation-pull",
                "resource": "tencentcloud.cam-user",
                "description": "users with Access Keys greater than 90 days old will be identified",
                "filters": [
                    {
                        "type": "credential",
                        "key": "access_keys.CreateTime",
                        "value_type": "age",
                        "value": 3,
                        "op": "greater-than"
                    },
                    {
                        "type": "credential",
                        "key": "access_keys.Status",
                        "value": "Active"
                    }
                ]
            },
            account_id=100002098531
        )
        resources = policy.run()
        assert len(resources) == 1
        assert resources[0]["Uin"] == 100027724164

    @pytest.mark.vcr
    def test_missing_group(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-user-missing-group-permissions-pull",
                "resource": "tencentcloud.cam-user",
                "description": "identify CAM Users who are not a member of any CAM group",
                "filters": [
                    {
                        "type": "group",
                        "key": "GroupName",
                        "value": None
                    }
                ]
            },
            account_id=100002098531
        )
        resources = policy.run()
        assert len(resources) == 1
        assert resources[0]["Uin"] == 100027724164

    @pytest.mark.vcr
    def test_group(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-user-missing-group-permissions-pull",
                "resource": "tencentcloud.cam-user",
                "description": "identify CAM Users who are not a member of any CAM group",
                "filters": [
                    {
                        "type": "group",
                        "key": "GroupName",
                        "value": "demo"
                    }
                ]
            },
            account_id=100002098531
        )
        resources = policy.run()
        assert len(resources) == 1
        assert resources[0]["Uin"] == 100027755407

    @pytest.mark.vcr
    def test_new_user_with_credential(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-user-new-with-credentials",
                "resource": "tencentcloud.cam-user",
                "description": "identify new users who use both access keys and console password",
                "filters": [
                    {
                        "type": "credential",
                        "key": "access_keys.Status",
                        "value": "Active"
                    },
                    {
                        "type": "credential",
                        "key": "ConsoleLogin",
                        "value": 1
                    },
                    {
                        "type": "value",
                        "key": "CreateTime",
                        "value_type": "age",
                        "value": 7000,
                        "op": "less-than"
                    }
                ]
            },
            account_id=100002098531
        )
        resources = policy.run()
        assert len(resources) == 1
        assert resources[0]["Uin"] == 100027755407

    @pytest.mark.vcr
    def test_unused_credentials(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-user-unused-credentials-pull",
                "resource": "tencentcloud.cam-user",
                "description": "check all users with unused credentials",
                "filters": [
                    {
                        "type": "credential",
                        "key": "access_keys.Status",
                        "value": "Active"
                    },
                    {
                        "type": "credential",
                        "key": "ConsoleLogin",
                        "value": 1
                    },
                    {
                        "type": "credential",
                        "key": "access_keys.LastUsedDate",
                        "value": "absent"
                    }
                ]
            },
            account_id=100002098531
        )
        resources = policy.run()
        assert len(resources) == 1
        assert resources[0]["Uin"] == 100027755407

    @pytest.mark.vcr
    def test_unused_credentials_in_period_third(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-user-unused-credentials-in-period-third",
                "resource": "tencentcloud.cam-user",
                "description": "users with credentials not used in the tracking period days",
                "filters": [
                    {
                        "type": "credential",
                        "key": "access_keys.Status",
                        "value": "Active"
                    },
                    {
                        "type": "credential",
                        "key": "access_keys.LastUsedDate",
                        "value": "absent"
                    }
                ]
            },
            account_id=100002098531
        )
        resources = policy.run()
        assert len(resources) == 2

    @pytest.mark.vcr
    def test_user_credentials_in_tracking_period(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-user-credentials-in-tracking-period",
                "resource": "tencentcloud.cam-user",
                "description": "users with credentials in the tracking period",
                "filters": [
                    {
                        "type": "credential",
                        "key": "access_keys.Status",
                        "value": "Active"
                    },
                    {
                        "type": "credential",
                        "key": "access_keys.LastUsedDate",
                        "value_type": "age",
                        "op": "gte",
                        "value": 1
                    },
                    {
                        "tag:access-key-unused": "present"
                    }
                ]
            },
            account_id=100002098531
        )
        resources = policy.run()
        assert len(resources) == 1
        assert resources[0]["Uin"] == 100027724164

    @pytest.mark.vcr
    def test_policy_with_admin_privileges(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-policy-overly-permissive-pull",
                "resource": "tencentcloud.cam-policy",
                "description": "Checks IAM Policies for Admin privileges.",
                "filters": [
                    {
                        "or": [
                            {
                                "type": "has-allow-all"
                            },
                            {
                                "type": "check-permissions",
                                "match": "allowed",
                                "actions": [
                                    "*:*"
                                ]
                            }
                        ]
                    }
                ]
            },
            account_id=100002098531
        )
        resources = policy.run()
        assert len(resources) == 2
        policy_ids = set([resources[0]["PolicyId"], resources[1]["PolicyId"]])
        assert policy_ids == set([141818449, 141834197])

    @pytest.mark.vcr
    def test_policy_check_permissions(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-policy-check-permissions",
                "resource": "tencentcloud.cam-policy",
                "description": "Checks IAM Policies for Admin privileges.",
                "filters": [
                    {
                        "type": "check-permissions",
                        "match": "allowed",
                        "actions": ["cos:GetBucket"],
                        "match-operator": "or"
                    }
                ]
            },
            account_id=100002098531
        )
        resources = policy.run()
        assert len(resources) == 1
        assert resources[0]["PolicyId"] == 141753149

    @pytest.mark.vcr
    def test_policy_used(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-policy-used",
                "resource": "tencentcloud.cam-policy",
                "description": "Checks IAM Policies if used",
                "filters": [
                    {
                        "type": "used",
                        "state": True
                    }
                ]
            },
        )
        resources = policy.run()
        assert len(resources) == 57
        assert resources[0]["PolicyId"] == 236806532

    @pytest.mark.vcr
    def test_policy_unused(self):
        policy = self.load_policy(
            {
                "name": "tencentcloud-cam-policy-unused",
                "resource": "tencentcloud.cam-policy",
                "description": "Checks IAM Policies if unused",
                "filters": [
                    {
                        "type": "used",
                        "state": False
                    }
                ]
            },
        )
        resources = policy.run()
        assert len(resources) == 130
        assert resources[0]["PolicyId"] == 232883536
