# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0

import inspect
import unittest

from pytest_terraform import terraform

from oci_common import OciBaseTest, Resource, Module, Scope


class TestIdentityTerraformTest(OciBaseTest):
    def _get_identity_compartment_details(self, identity_compartment):
        compartment_id = identity_compartment[
            "oci_identity_compartment.test_compartment.compartment_id"
        ]
        name = identity_compartment["oci_identity_compartment.test_compartment.name"]
        return compartment_id, name

    def _get_identity_compartment(self, name):
        return {"name": name}

    @terraform(Module.IDENTITY_COMPARTMENT.value, scope=Scope.CLASS.value)
    def test_identity_compartment(self, identity_compartment, test):
        compartment_id, name = self._get_identity_compartment_details(
            identity_compartment
        )
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy_str = {
            "name": "filter-and-add-tags-on-compartments",
            "description": "Filter and add tags on the compartment",
            "resource": Resource.COMPARTMENT.value,
            "filters": [
                {"type": "query", "params": {"compartment_id": compartment_id}},
                {
                    "type": "value",
                    "key": "freeform_tags.Cloud_Custodian",
                    "value": "True",
                    "op": "eq",
                },
            ],
            "actions": [
                {
                    "type": "update_compartment",
                    "params": {
                        "update_compartment_details": {
                            "freeform_tags": {"Environment": "Development"}
                        }
                    },
                }
            ],
        }
        policy = test.load_policy(policy_str, session_factory=session_factory)
        self.wait_for_resource_search_sync()
        policy.run()
        resources = self.get_resources(
            policy, compartment_id, **self._get_identity_compartment(name)
        )
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["name"], "Custodian-Test1")
        test.assertEqual(resources[0]["freeform_tags"]["Environment"], "Development")

    @terraform(Module.IDENTITY_GROUP.value, scope=Scope.CLASS.value)
    def test_identity_group(self, identity_group, test):
        compartment_id = identity_group["oci_identity_group.test_group.compartment_id"]
        name = identity_group["oci_identity_group.test_group.name"]
        policy_str = {
            "name": "filter-and-add-tags-on-group",
            "description": "Filter and add tags on the group",
            "resource": Resource.GROUP.value,
            "filters": [
                {"type": "query", "params": {"compartment_id": compartment_id}},
                {
                    "type": "value",
                    "key": "freeform_tags.Cloud_Custodian",
                    "value": "Present",
                    "op": "eq",
                },
            ],
            "actions": [
                {
                    "type": "update_group",
                    "params": {
                        "update_group_details": {
                            "freeform_tags": {"Environment": "Development"}
                        }
                    },
                }
            ],
        }
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(policy_str, session_factory=session_factory)
        self.wait_for_resource_search_sync(duration=65)
        policy.run()
        params = {"name": name}
        resources = self.get_resources(policy, compartment_id, **params)
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["name"], "Custodian-Dev-Group")
        test.assertEqual(resources[0]["freeform_tags"]["Environment"], "Development")

    @terraform(Module.IDENTITY_USER.value, scope=Scope.CLASS.value)
    def test_identity_user_tag(self, identity_user, test):
        compartment_id = identity_user["oci_identity_user.test_user.compartment_id"]
        name = identity_user["oci_identity_user.test_user.name"]
        user_ocid = identity_user["oci_identity_user.test_user.id"]
        policy_str = {
            "name": "filter-and-add-tags-on-user",
            "description": "Filter and add tags on the user",
            "resource": Resource.USER.value,
            "filters": [
                {"type": "query", "params": {"compartment_id": compartment_id}},
                {"type": "value", "key": "identifier", "value": user_ocid},
                {
                    "type": "value",
                    "key": "freeform_tags.Cloud_Custodian",
                    "value": "True",
                    "op": "eq",
                },
            ],
            "actions": [
                {
                    "type": "update_user",
                    "params": {
                        "update_user_details": {"freeform_tags": {"key_limit": "2"}}
                    },
                }
            ],
        }
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(policy_str, session_factory=session_factory)
        self.wait_for_resource_search_sync(duration=65)
        policy.run()
        params = {"name": name}
        self.wait_for_resource_search_sync()
        resources = self.get_resources(policy, compartment_id, **params)
        assert resources is not None
        test.assertEqual(resources[0]["name"], name)
        test.assertEqual(resources[0]["freeform_tags"]["key_limit"], "2")

    @terraform(Module.IDENTITY_USER.value, scope=Scope.CLASS.value)
    def test_identity_user_cross_filter_size(self, identity_user, test):
        compartment_id = identity_user["oci_identity_user.test_user.compartment_id"]
        name = identity_user["oci_identity_user.test_user.name"]
        ## Cross filter size policy testcase
        policy_str = {
            "name": "filter_auth_tokens_based_on_size",
            "description": "Filter users with auth tokens equal to 2",
            "resource": Resource.USER.value,
            "filters": [
                {"type": "query", "params": {"compartment_id": compartment_id}},
                {
                    "type": "auth_tokens",
                    "key": "auth_tokens",
                    "value": "2",
                    "op": "eq",
                    "value_type": "size",
                },
            ],
        }
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        params = {"name": name}
        resources = self.get_resources(policy, compartment_id, **params)
        assert resources is not None
        test.assertEqual(resources[0]["name"], name)

    @terraform(Module.IDENTITY_USER.value, scope=Scope.CLASS.value)
    def test_identity_user_cross_filter_age(self, identity_user, test):
        compartment_id = identity_user["oci_identity_user.test_user.compartment_id"]
        name = identity_user["oci_identity_user.test_user.name"]
        # Cross filter query filter based on the created time usecase
        policy_str = {
            "name": "filter_auth_tokens_based_on_age",
            "description": "Filter users with age less than 1",
            "resource": Resource.USER.value,
            "filters": [
                {"type": "query", "params": {"compartment_id": compartment_id}},
                {
                    "type": "auth_tokens",
                    "key": "auth_token.time_created",
                    "value": "2023/01/01",
                    "op": "greater-than",
                    "value_type": "date",
                },
            ],
        }
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        params = {"name": name}
        resources = self.get_resources(policy, compartment_id, **params)
        assert resources is not None
        test.assertEqual(resources[0]["name"], name)

    @terraform(Module.IDENTITY_USER.value, scope=Scope.CLASS.value)
    def test_identity_user_cross_size_age(self, identity_user, test):
        compartment_id = identity_user["oci_identity_user.test_user.compartment_id"]
        name = identity_user["oci_identity_user.test_user.name"]
        # Cross filter query filter with size & age filter
        policy_str = {
            "name": "filter_auth_tokens_based_on_size_age",
            "description": "Filter users with age less than 1 year and size equal to 2",
            "resource": Resource.USER.value,
            "filters": [
                {"type": "query", "params": {"compartment_id": compartment_id}},
                {
                    "type": "auth_tokens",
                    "key": "auth_tokens",
                    "value": "2",
                    "op": "eq",
                    "value_type": "size",
                },
                {
                    "type": "auth_tokens",
                    "key": "auth_token.time_created",
                    "value": "2023/01/01",
                    "op": "greater-than",
                    "value_type": "date",
                },
            ],
        }
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        params = {"name": name}
        resources = self.get_resources(policy, compartment_id, **params)
        assert resources is not None
        test.assertEqual(resources[0]["name"], name)

    @terraform(Module.IDENTITY_USER.value, scope=Scope.CLASS.value)
    def test_identity_user_cross_age_size(self, identity_user, test):
        compartment_id = identity_user["oci_identity_user.test_user.compartment_id"]
        name = identity_user["oci_identity_user.test_user.name"]
        # Cross filter query filter with age & size filter
        policy_str = {
            "name": "filter_auth_tokens_based_on_age",
            "description": "Filter users with age less than 1 yr and size equal to 2",
            "resource": Resource.USER.value,
            "filters": [
                {"type": "query", "params": {"compartment_id": compartment_id}},
                {
                    "type": "auth_tokens",
                    "key": "auth_token.time_created",
                    "value": "2023/01/01",
                    "op": "greater-than",
                    "value_type": "date",
                },
                {
                    "type": "auth_tokens",
                    "key": "auth_tokens",
                    "value": "2",
                    "op": "eq",
                    "value_type": "size",
                },
            ],
        }
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        params = {"name": name}
        resources = self.get_resources(policy, compartment_id, **params)
        assert resources is not None
        test.assertEqual(resources[0]["name"], name)


class IdentityUnitTest(unittest.TestCase, OciBaseTest):
    @staticmethod
    def get_policy(resource, filters=None, actions=None):
        policy = {"name": "test-identity"}
        policy["resource"] = "oci.{0}".format(resource)
        if filters:
            policy["filters"] = filters
        if actions:
            policy["actions"] = actions
        print(policy)
        return policy

    @staticmethod
    def get_tag_filter():
        return {
            "type": "value",
            "key": "freeform_tags.Cloud_Custodian",
            "value": "True",
            "op": "equal",
        }

    @staticmethod
    def get_query_filter(compartment_id=None):
        if not compartment_id:
            compartment_id = "ocid1.test.oc1..<unique_ID>EXAMPLE-compartmentId-Value"
        return {"type": "query", "params": {"compartment_id": compartment_id}}

    @staticmethod
    def get_cross_size_filter(resource):
        return {
            "type": resource,
            "key": resource,
            "value_type": "size",
            "op": "greater-than",
            "value": "0",
        }

    @staticmethod
    def get_cross_equal_size_filter(resource):
        return {
            "type": resource
            # 'key': resource
            # 'value_type': 'size',
            # 'op': 'equal',
            # 'value': '0'
        }

    @staticmethod
    def get_cross_filter_query(resource, field):
        f = resource + "." + field
        return {
            "type": resource + "s",
            "key": f,
            "value_type": "age",
            "op": "less-than",
            "value": "2",
        }

    @staticmethod
    def get_action(resource):
        method_name = "update_{0}".format(resource)
        method_param = "update_{0}_details".format(resource)
        return [
            {
                "type": method_name,
                "params": {
                    method_param: {
                        "freeform_tags": {"Environment": "Cloud-Custodian-Dev"}
                    }
                },
            }
        ]

    @staticmethod
    def get_cross_resource_filter(cross_filter_resource):
        plural_cross_filter_resource = cross_filter_resource + "s"
        cross_filter = {
            "type": plural_cross_filter_resource,
            "key": cross_filter_resource + ".lifecycle_state",
            "value": "INACTIVE",
            "op": "equal",
        }
        return cross_filter

    def test_identity_compartment_schema(self):
        self.assertTrue(
            self.load_policy(
                self.get_policy(
                    "compartment",
                    [self.get_query_filter()],
                    self.get_action("compartment"),
                ),
                validate=True,
            )
        )

    def test_identity_group_schema(self):
        self.assertTrue(
            self.load_policy(
                self.get_policy(
                    "group", [self.get_query_filter()], self.get_action("group")
                ),
                validate=True,
            )
        )

    def test_identity_user_schema(self):
        self.assertTrue(
            self.load_policy(
                self.get_policy(
                    "user", [self.get_query_filter()], self.get_action("user")
                ),
                validate=True,
            )
        )

    def test_identity_api_key_schema(self):
        self.assertTrue(
            self.load_policy(
                self.get_policy(
                    "user",
                    [
                        self.get_query_filter(),
                        self.get_cross_resource_filter("api_key"),
                    ],
                ),
                validate=True,
            )
        )

    def test_identity_auth_token_schema(self):
        self.assertTrue(
            self.load_policy(
                self.get_policy(
                    "user",
                    [
                        self.get_query_filter(),
                        self.get_cross_resource_filter("auth_token"),
                    ],
                ),
                validate=True,
            )
        )

    def test_identity_db_credential_schema(self):
        self.assertTrue(
            self.load_policy(
                self.get_policy(
                    "user",
                    [
                        self.get_query_filter(),
                        self.get_cross_resource_filter("db_credential"),
                    ],
                ),
                validate=True,
            )
        )

    def test_identity_customer_secret_key_schema(self):
        self.assertTrue(
            self.load_policy(
                self.get_policy(
                    "user",
                    [
                        self.get_query_filter(),
                        self.get_cross_resource_filter("customer_secret_key"),
                    ],
                ),
                validate=True,
            )
        )

    def test_identity_smtp_credential_schema(self):
        self.assertTrue(
            self.load_policy(
                self.get_policy(
                    "user",
                    [
                        self.get_query_filter(),
                        self.get_cross_resource_filter("smtp_credential"),
                    ],
                ),
                validate=True,
            )
        )

    def test_identity_oauth_credential_schema(self):
        self.assertTrue(
            self.load_policy(
                self.get_policy(
                    "user",
                    [
                        self.get_query_filter(),
                        self.get_cross_resource_filter("o_auth2_client_credential"),
                    ],
                ),
                validate=True,
            )
        )
