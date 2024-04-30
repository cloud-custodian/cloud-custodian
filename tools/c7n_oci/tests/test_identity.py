# Copyright The Cloud Custodian Authors.
# SPDX-License-id: Apache-2.0

import os

import pytest
from pytest_terraform import terraform
from mock import patch, Mock
from oci.response import Response

from c7n.testing import C7N_FUNCTIONAL
from c7n_oci.resources.identity import (
    UserOAuth2ClientCredentialsValueFilter,
    UserApiKeysValueFilter,
    UserDbCredentialsValueFilter,
    UserCustomerSecretKeysValueFilter,
    UserSmtpCredentialsValueFilter,
)
from oci_common import OciBaseTest


class TestIdentityTerraformTest(OciBaseTest):
    @pytest.fixture
    def setCompartmentIdToTenancyOcid(self):
        compartment_ids = os.getenv("OCI_COMPARTMENTS")
        tenancy_ocid = os.getenv("TF_VAR_OCI_TENANCY_ID")
        os.environ["OCI_COMPARTMENTS"] = tenancy_ocid
        yield
        os.environ["OCI_COMPARTMENTS"] = compartment_ids

    def _get_identity_compartment_details(self, identity_compartment):
        compartment_id = identity_compartment[
            "oci_identity_compartment.test_compartment.compartment_id"
        ]
        new_compartment_id = identity_compartment["oci_identity_compartment.test_compartment.id"]
        return compartment_id, new_compartment_id

    @terraform("identity_compartment", scope="class")
    def test_identity_compartment(self, identity_compartment, test):
        _, new_compartment_id = self._get_identity_compartment_details(identity_compartment)
        session_factory = test.oci_session_factory()
        policy_str = {
            "name": "filter-and-add-tags-on-compartments",
            "description": "Filter and add tags on the compartment",
            "resource": "oci.compartment",
            "query": [
                {"lifecycle_state": "ACTIVE"},
            ],
            "filters": [
                {
                    "type": "value",
                    "key": "freeform_tags.Cloud_Custodian_Test",
                    "value": "True",
                    "op": "eq",
                },
            ],
            "actions": [{"type": "update", "freeform_tags": {"Environment": "Development"}}],
        }
        policy = test.load_policy(policy_str, session_factory=session_factory)
        resources = policy.run()
        assert len(resources) == 1
        resource = self.fetch_validation_data(
            policy.resource_manager, "get_compartment", new_compartment_id
        )
        assert resource is not None
        test.assertEqual(resource["freeform_tags"]["Environment"], "Development")

    @terraform("identity_compartment", scope="class")
    def test_identity_update_compartment(self, identity_compartment, test):
        _, new_compartment_id = self._get_identity_compartment_details(identity_compartment)
        session_factory = test.oci_session_factory()
        policy_str = {
            "name": "filter-and-add-tags-on-compartments",
            "description": "Filter and add tags on the compartment",
            "resource": "oci.compartment",
            "query": [
                {"lifecycle_state": "ACTIVE"},
            ],
            "filters": [
                {
                    "type": "value",
                    "key": "freeform_tags.Cloud_Custodian_Test",
                    "value": "True",
                    "op": "eq",
                },
            ],
            "actions": [{"type": "update", "freeform_tags": {"Environment": "Development"}}],
        }
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        resource = self.fetch_validation_data(
            policy.resource_manager, "get_compartment", new_compartment_id
        )
        assert resource is not None
        test.assertEqual(resource["freeform_tags"]["Environment"], "Development")

    @terraform("identity_compartment", scope="class")
    def test_remove_tag_compartment(self, identity_compartment, test):
        _, new_compartment_id = self._get_identity_compartment_details(identity_compartment)
        session_factory = test.oci_session_factory()
        policy_str = {
            "name": "remove-tag-from-compartment",
            "description": "Remove tag from the compartment",
            "resource": "oci.compartment",
            "filters": [
                {"type": "value", "key": "id", "value": new_compartment_id},
            ],
            "actions": [{"type": "remove-tag", "freeform_tags": ["Cloud_Custodian_Test"]}],
        }
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        resource = self.fetch_validation_data(
            policy.resource_manager, "get_compartment", new_compartment_id
        )
        assert resource is not None
        test.assertEqual(resource["freeform_tags"].get("Cloud_Custodian_Test"), None)

    @terraform("identity_compartment", scope="class")
    def test_remove_invalidtag_compartment(self, identity_compartment, test):
        _, new_compartment_id = self._get_identity_compartment_details(identity_compartment)
        session_factory = test.oci_session_factory()
        policy_str = {
            "name": "remove-invalidtag-from-compartment",
            "description": "Remove tag from the compartment that doesn't exists",
            "resource": "oci.compartment",
            "filters": [
                {"type": "value", "key": "id", "value": new_compartment_id},
            ],
            "actions": [{"type": "remove-tag", "freeform_tags": ["Cloud_Custodian_Test1"]}],
        }
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        resource = self.fetch_validation_data(
            policy.resource_manager, "get_compartment", new_compartment_id
        )
        assert resource is not None
        test.assertEqual(resource["freeform_tags"].get("Cloud_Custodian_Test1"), None)

    @terraform("identity_group", scope="class")
    @pytest.mark.usefixtures("setCompartmentIdToTenancyOcid")
    def test_identity_group(self, identity_group, test):
        group_id = identity_group["oci_identity_group.test_group.id"]
        policy_str = {
            "name": "filter-and-add-tags-on-group",
            "description": "Filter and add tags on the group",
            "resource": "oci.group",
            "filters": [
                {
                    "type": "value",
                    "key": "freeform_tags.Cloud_Custodian",
                    "value": "Present",
                    "op": "eq",
                },
            ],
            "actions": [{"type": "update", "freeform_tags": {"Environment": "Development"}}],
        }
        session_factory = test.oci_session_factory()
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        resource = self.fetch_validation_data(policy.resource_manager, "get_group", group_id)
        assert resource is not None
        test.assertEqual(resource["name"], "Custodian-Dev-Group")
        test.assertEqual(resource["freeform_tags"]["Environment"], "Development")

    @terraform("identity_group", scope="class")
    @pytest.mark.usefixtures("setCompartmentIdToTenancyOcid")
    def test_identity_update_group(self, identity_group, test):
        group_id = identity_group["oci_identity_group.test_group.id"]
        policy_str = {
            "name": "filter-and-add-tags-on-group",
            "description": "Filter and add tags on the group",
            "resource": "oci.group",
            "filters": [
                {
                    "type": "value",
                    "key": "freeform_tags.Cloud_Custodian",
                    "value": "Present",
                    "op": "eq",
                },
            ],
            "actions": [{"type": "update", "freeform_tags": {"Environment": "Development"}}],
        }
        session_factory = test.oci_session_factory()
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        resource = self.fetch_validation_data(policy.resource_manager, "get_group", group_id)
        assert resource is not None
        test.assertEqual(resource["name"], "Custodian-Dev-Group")
        test.assertEqual(resource["freeform_tags"]["Environment"], "Development")

    @terraform("identity_group", scope="class")
    @pytest.mark.usefixtures("setCompartmentIdToTenancyOcid")
    def test_remove_tag_group(self, identity_group, test):
        group_id = identity_group["oci_identity_group.test_group.id"]
        policy_str = {
            "name": "remove-tag-on-group",
            "description": "Remove tag from the group",
            "resource": "oci.group",
            "filters": [
                {
                    "type": "value",
                    "key": "id",
                    "value": group_id,
                },
            ],
            "actions": [{"type": "remove-tag", "freeform_tags": ["Cloud_Custodian"]}],
        }
        session_factory = test.oci_session_factory()
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        resource = self.fetch_validation_data(policy.resource_manager, "get_group", group_id)
        assert resource is not None
        test.assertEqual(resource["freeform_tags"].get("Cloud_Custodian"), None)

    @terraform("identity_group", scope="class")
    @pytest.mark.usefixtures("setCompartmentIdToTenancyOcid")
    def test_remove_invalidtag_group(self, identity_group, test):
        group_id = identity_group["oci_identity_group.test_group.id"]
        policy_str = {
            "name": "remove-invalid-tag-on-group",
            "description": "Remove tag from the group that doesn't exists",
            "resource": "oci.group",
            "filters": [
                {
                    "type": "value",
                    "key": "id",
                    "value": group_id,
                },
            ],
            "actions": [{"type": "remove-tag", "freeform_tags": ["Cloud_Custodian1"]}],
        }
        session_factory = test.oci_session_factory()
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        resource = self.fetch_validation_data(policy.resource_manager, "get_group", group_id)
        assert resource is not None
        test.assertEqual(resource["freeform_tags"].get("Cloud_Custodian1"), None)

    def _get_user_details(self, identity_user):
        compartment_id = identity_user["oci_identity_user.test_user.compartment_id"]
        user_ocid = identity_user["oci_identity_user.test_user.id"]
        return compartment_id, user_ocid

    @terraform("identity_user", scope="class")
    @pytest.mark.usefixtures("setCompartmentIdToTenancyOcid")
    def test_identity_user_tag(self, identity_user, test):
        _, user_ocid = self._get_user_details(identity_user)
        policy_str = {
            "name": "filter-and-add-tags-on-user",
            "description": "Filter and add tags on the user",
            "resource": "oci.user",
            "filters": [
                {"type": "value", "key": "id", "value": user_ocid},
                {
                    "type": "value",
                    "key": "freeform_tags.Cloud_Custodian",
                    "value": "True",
                    "op": "eq",
                },
            ],
            "actions": [{"type": "update", "freeform_tags": {"key_limit": "2"}}],
        }
        session_factory = test.oci_session_factory()
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        resource = self.fetch_validation_data(policy.resource_manager, "get_user", user_ocid)
        assert resource is not None
        test.assertEqual(resource["freeform_tags"]["key_limit"], "2")

    @terraform("identity_user", scope="class")
    @pytest.mark.usefixtures("setCompartmentIdToTenancyOcid")
    def test_remove_tag_user(self, identity_user, test):
        _, user_ocid = self._get_user_details(identity_user)
        policy_str = {
            "name": "remove-tag-from-user",
            "description": "Remove tag from the user",
            "resource": "oci.user",
            "filters": [{"type": "value", "key": "id", "value": user_ocid}],
            "actions": [{"type": "remove-tag", "freeform_tags": ["Cloud_Custodian"]}],
        }
        session_factory = test.oci_session_factory()
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        resource = self.fetch_validation_data(policy.resource_manager, "get_user", user_ocid)
        assert resource is not None
        test.assertEqual(resource["freeform_tags"].get("Cloud_Custodian"), None)

    @terraform("identity_user", scope="class")
    @pytest.mark.usefixtures("setCompartmentIdToTenancyOcid")
    def test_remove_invalidtag_user(self, identity_user, test):
        _, user_ocid = self._get_user_details(identity_user)
        policy_str = {
            "name": "remove-invalid-tag-from-user",
            "description": "Remove tag from the user that doesn't exists",
            "resource": "oci.user",
            "filters": [{"type": "value", "key": "id", "value": user_ocid}],
            "actions": [{"type": "remove-tag", "freeform_tags": ["Cloud_Custodian_test"]}],
        }
        session_factory = test.oci_session_factory()
        policy = test.load_policy(policy_str, session_factory=session_factory)
        policy.run()
        resource = self.fetch_validation_data(policy.resource_manager, "get_user", user_ocid)
        assert resource is not None
        test.assertEqual(resource["freeform_tags"].get("Cloud_Custodian_test"), None)

    @terraform("identity_user", scope="class")
    @pytest.mark.usefixtures("setCompartmentIdToTenancyOcid")
    def test_attributes_user(self, identity_user, test):
        _, user_ocid = self._get_user_details(identity_user)
        policy_str = {
            "name": "fetch-attributes-from-user",
            "description": "Fetch all attributes from the user",
            "resource": "oci.user",
            "filters": [{"type": "attributes", "key": "id", "value": user_ocid}],
        }
        session_factory = test.oci_session_factory()
        policy = test.load_policy(policy_str, session_factory=session_factory)
        resource = policy.run()
        assert resource[0] is not None
        assert resource[0]["is_mfa_activated"] is not None

    @terraform("identity_user", scope="class")
    @pytest.mark.usefixtures("setCompartmentIdToTenancyOcid")
    def test_identity_user_cross_filter_size(self, identity_user, test):
        """
        Cross filter size policy testcase
        """
        _, user_ocid = self._get_user_details(identity_user)
        policy_str = {
            "name": "filter_auth_tokens_based_on_size",
            "description": "Filter users with auth tokens equal to 2",
            "resource": "oci.user",
            "filters": [
                {
                    "type": "auth-tokens",
                    "key": "auth_tokens",
                    "value": 2,
                    "op": "eq",
                    "value_type": "size",
                },
            ],
        }
        session_factory = test.oci_session_factory()
        policy = test.load_policy(policy_str, session_factory=session_factory)
        resources = self.fetch_validation_data(
            policy.resource_manager, "list_auth_tokens", user_ocid
        )
        resources = policy.run()
        test_user_found = False
        for resource in resources:
            if resource["id"] == user_ocid:
                test_user_found = True
                break
        assert test_user_found

    @terraform("identity_user", scope="class")
    @pytest.mark.usefixtures("setCompartmentIdToTenancyOcid")
    def test_identity_user_cross_filter_age(self, identity_user, test):
        """
        Cross filter query filter based on the created time usecase
        """
        _, user_ocid = self._get_user_details(identity_user)
        policy_str = {
            "name": "filter_auth_tokens_based_on_age",
            "description": "Filter users with age less than 1 year",
            "resource": "oci.user",
            "filters": [
                {
                    "type": "auth-tokens",
                    "key": "auth_token.time_created",
                    "value": "2023/01/01",
                    "op": "greater-than",
                    "value_type": "date",
                },
            ],
        }
        session_factory = test.oci_session_factory()
        policy = test.load_policy(policy_str, session_factory=session_factory)
        resources = policy.run()
        test_user_found = False
        for resource in resources:
            if resource["id"] == user_ocid:
                test_user_found = True
                break
        assert test_user_found

    @terraform("identity_user", scope="class")
    @pytest.mark.usefixtures("setCompartmentIdToTenancyOcid")
    def test_identity_user_cross_size_age(self, identity_user, test):
        """
        Cross filter query filter with size & age filter
        """
        _, user_ocid = self._get_user_details(identity_user)
        policy_str = {
            "name": "filter_auth_tokens_based_on_size_age",
            "description": "Filter users with age less than 1 year and size equal to 2",
            "resource": "oci.user",
            "filters": [
                {
                    "type": "auth-tokens",
                    "key": "auth_tokens",
                    "value": 2,
                    "op": "eq",
                    "value_type": "size",
                },
                {
                    "type": "auth-tokens",
                    "key": "auth_token.time_created",
                    "value": "2023/01/01",
                    "op": "greater-than",
                    "value_type": "date",
                },
            ],
        }
        session_factory = test.oci_session_factory()
        policy = test.load_policy(policy_str, session_factory=session_factory)
        resources = policy.run()
        test_user_found = False
        for resource in resources:
            if resource["id"] == user_ocid:
                test_user_found = True
                break
        assert test_user_found

    @pytest.mark.skipif((not C7N_FUNCTIONAL), reason="Functional test")
    @terraform("identity_user", scope="class")
    @pytest.mark.usefixtures("setCompartmentIdToTenancyOcid")
    def test_identity_user_cross_age_size(self, identity_user, test):
        """
        Cross filter query filter with age & size filter
        """
        _, user_ocid = self._get_user_details(identity_user)
        policy_str = {
            "name": "filter_auth_tokens_based_on_age",
            "description": "Filter users with age less than 1 yr and size equal to 2",
            "resource": "oci.user",
            "filters": [
                {
                    "type": "auth-tokens",
                    "key": "auth_token.time_created",
                    "value": "2023/01/01",
                    "op": "greater-than",
                    "value_type": "date",
                },
                {
                    "type": "auth-tokens",
                    "key": "auth_tokens",
                    "value": 2,
                    "op": "eq",
                    "value_type": "size",
                },
            ],
        }
        session_factory = test.oci_session_factory()
        policy = test.load_policy(policy_str, session_factory=session_factory)
        resources = policy.run()
        test_user_found = False
        for resource in resources:
            if resource["id"] == user_ocid:
                test_user_found = True
                break
        assert test_user_found


class TestIdentity(OciBaseTest):
    @staticmethod
    def get_policy(resource, filters=None, actions=None):
        policy = {
            "name": "test-identity",
            "resource": "oci.{0}".format(resource),
        }
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
        method_name = "update"
        return [
            {
                "type": method_name,
                "freeform_tags": {"Environment": "Cloud-Custodian-Dev"},
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

    def test_identity_compartment_schema(self, test):
        test.assertTrue(
            test.load_policy(
                self.get_policy(
                    "compartment",
                    filters=None,
                    actions=self.get_action("compartment"),
                ),
                validate=True,
            )
        )

    def test_identity_group_schema(self, test):
        test.assertTrue(
            test.load_policy(
                self.get_policy("group", filters=None, actions=self.get_action("group")),
                validate=True,
            )
        )

    def test_identity_user_schema(self, test):
        test.assertTrue(
            test.load_policy(
                self.get_policy("user", filters=None, actions=self.get_action("user")),
                validate=True,
            )
        )

    def test_identity_api_key_schema(self, test):
        test.assertTrue(
            test.load_policy(
                self.get_policy("user", filters=None, actions=None),
                validate=True,
            )
        )

    def test_identity_auth_token_schema(self, test):
        test.assertTrue(
            test.load_policy(
                self.get_policy(
                    "user",
                    filters=None,
                    actions=None,
                ),
                validate=True,
            )
        )

    def test_identity_db_credential_schema(self, test):
        test.assertTrue(
            test.load_policy(
                self.get_policy(
                    "user",
                    filters=None,
                    actions=None,
                ),
                validate=True,
            )
        )

    def test_identity_customer_secret_key_schema(self, test):
        test.assertTrue(
            test.load_policy(
                self.get_policy(
                    "user",
                    filters=None,
                    actions=None,
                ),
                validate=True,
            )
        )

    def test_identity_smtp_credential_schema(self, test):
        test.assertTrue(
            test.load_policy(
                self.get_policy(
                    "user",
                    filters=None,
                    actions=None,
                ),
                validate=True,
            )
        )

    def test_identity_oauth_credential_schema(self, test):
        test.assertTrue(
            test.load_policy(
                self.get_policy(
                    "user",
                    filters=None,
                    actions=None,
                ),
                validate=True,
            )
        )

    def test_oauth_size_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "o-auth2-client-credentials",
                "key": "o_auth2_client_credentials",
                "value": 1,
                "op": "eq",
                "value_type": "size",
            }
            identity_client = Mock()
            response = Response(200, None, [{"display_name": "cloud_custodian_oauth"}], None)
            identity_client.list_o_auth_client_credentials.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [{"id": "ocid1.user.oc1..<unique_ID>", "description": "Cloud Custodian"}]
            filter = UserOAuth2ClientCredentialsValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_oauth_exists_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "o-auth2-client-credentials",
                "key": "o_auth2_client_credentials",
                "value": 1,
                "op": "eq",
                "value_type": "size",
            }
            identity_client = Mock()
            oauth_data = [{"display_name": "cloud_custodian_oauth"}]
            response = Response(200, None, oauth_data, None)
            identity_client.list_o_auth_client_credentials.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [
                {
                    "id": "ocid1.user.oc1..<unique_ID>",
                    "description": "Cloud Custodian",
                    "o_auth2_client_credentials": oauth_data,
                }
            ]
            filter = UserOAuth2ClientCredentialsValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_oauth_filter_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "o-auth2-client-credentials",
                "key": "o_auth2_client_credential.lifecycle_state",
                "value": "ACTIVE",
                "op": "eq",
            }
            identity_client = Mock()
            data = [{"display_name": "cloud_custodian_oauth", "lifecycle_state": "ACTIVE"}]
            response = Response(200, None, data, None)
            identity_client.list_o_auth_client_credentials.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [{"id": "ocid1.user.oc1..<unique_ID>", "description": "Cloud Custodian"}]
            filter = UserOAuth2ClientCredentialsValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_apikeys_size_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "api-keys",
                "key": "api_keys",
                "value": 1,
                "op": "eq",
                "value_type": "size",
            }
            identity_client = Mock()
            response = Response(200, None, [{"lifecycle_state": "ACTIVE"}], None)
            identity_client.list_api_keys.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [{"id": "ocid1.user.oc1..<unique_ID>", "description": "Cloud Custodian"}]
            filter = UserApiKeysValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_apikeys_exists_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "api-keys",
                "key": "api_keys",
                "value": 1,
                "op": "eq",
                "value_type": "size",
            }
            identity_client = Mock()
            api_data = [{"lifecycle_state": "ACTIVE"}]
            response = Response(200, None, api_data, None)
            identity_client.list_api_keys.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [
                {
                    "id": "ocid1.user.oc1..<unique_ID>",
                    "description": "Cloud Custodian",
                    "api_keys": api_data,
                }
            ]
            filter = UserApiKeysValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_apikeys_filter_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "api-keys",
                "key": "api_key.lifecycle_state",
                "value": "ACTIVE",
                "op": "eq",
            }
            identity_client = Mock()
            response = Response(200, None, [{"lifecycle_state": "ACTIVE"}], None)
            identity_client.list_api_keys.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [{"id": "ocid1.user.oc1..<unique_ID>", "description": "Cloud Custodian"}]
            filter = UserApiKeysValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_dbcred_size_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "db-credentials",
                "key": "db_credentials",
                "value": 1,
                "op": "eq",
                "value_type": "size",
            }
            identity_client = Mock()
            response = Response(200, None, [{"lifecycle_state": "ACTIVE"}], None)
            identity_client.list_db_credentials.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [{"id": "ocid1.user.oc1..<unique_ID>", "description": "Cloud Custodian"}]
            filter = UserDbCredentialsValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_dbcred_exists_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "db-credentials",
                "key": "db_credentials",
                "value": 1,
                "op": "eq",
                "value_type": "size",
            }
            identity_client = Mock()
            dbcred_data = [{"lifecycle_state": "ACTIVE"}]
            response = Response(200, None, dbcred_data, None)
            identity_client.list_db_credentials.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [
                {
                    "id": "ocid1.user.oc1..<unique_ID>",
                    "description": "Cloud Custodian",
                    "db_credentials": dbcred_data,
                }
            ]
            filter = UserDbCredentialsValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_dbcred_filter_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "db-credentials",
                "key": "db_credential.lifecycle_state",
                "value": "ACTIVE",
                "op": "eq",
            }
            identity_client = Mock()
            response = Response(200, None, [{"lifecycle_state": "ACTIVE"}], None)
            identity_client.list_db_credentials.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [{"id": "ocid1.user.oc1..<unique_ID>", "description": "Cloud Custodian"}]
            filter = UserDbCredentialsValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_cuskey_size_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "customer-secret-keys",
                "key": "customer_secret_keys",
                "value": 1,
                "op": "eq",
                "value_type": "size",
            }
            identity_client = Mock()
            response = Response(200, None, [{"lifecycle_state": "ACTIVE"}], None)
            identity_client.list_customer_secret_keys.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [{"id": "ocid1.user.oc1..<unique_ID>", "description": "Cloud Custodian"}]
            filter = UserCustomerSecretKeysValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_cuskey_exists_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "customer-secret-keys",
                "key": "customer_secret_keys",
                "value": 1,
                "op": "eq",
                "value_type": "size",
            }
            identity_client = Mock()
            cus_data = ([{"lifecycle_state": "ACTIVE"}],)
            response = Response(200, None, cus_data, None)
            identity_client.list_customer_secret_keys.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [
                {
                    "id": "ocid1.user.oc1..<unique_ID>",
                    "description": "Cloud Custodian",
                    "customer_secret_keys": cus_data,
                }
            ]
            filter = UserCustomerSecretKeysValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_cuskey_filter_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "customer-secret-keys",
                "key": "customer_secret_key.lifecycle_state",
                "value": "ACTIVE",
                "op": "eq",
            }
            identity_client = Mock()
            response = Response(200, None, [{"lifecycle_state": "ACTIVE"}], None)
            identity_client.list_customer_secret_keys.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [{"id": "ocid1.user.oc1..<unique_ID>", "description": "Cloud Custodian"}]
            filter = UserCustomerSecretKeysValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_smtpcred_size_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "smtp-credentials",
                "key": "smtp_credentials",
                "value": 1,
                "op": "eq",
                "value_type": "size",
            }
            identity_client = Mock()
            response = Response(200, None, [{"lifecycle_state": "ACTIVE"}], None)
            identity_client.list_smtp_credentials.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [{"id": "ocid1.user.oc1..<unique_ID>", "description": "Cloud Custodian"}]
            filter = UserSmtpCredentialsValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_smtpcred_exists_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "smtp-credentials",
                "key": "smtp_credentials",
                "value": 1,
                "op": "eq",
                "value_type": "size",
            }
            identity_client = Mock()
            smtp_data = [{"lifecycle_state": "ACTIVE"}]
            response = Response(200, None, smtp_data, None)
            identity_client.list_smtp_credentials.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [
                {
                    "id": "ocid1.user.oc1..<unique_ID>",
                    "description": "Cloud Custodian",
                    "smtp_credentials": smtp_data,
                }
            ]
            filter = UserSmtpCredentialsValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)

    def test_smtpcred_filter_identity(self, test):
        with patch("c7n_oci.resources.identity.User") as user_mock:
            policy_str = {
                "type": "smtp-credentials",
                "key": "smtp_credential.lifecycle_state",
                "value": "ACTIVE",
                "op": "eq",
            }
            identity_client = Mock()
            response = Response(200, None, [{"lifecycle_state": "ACTIVE"}], None)
            identity_client.list_smtp_credentials.return_value = response
            user_mock.get_client.return_value = identity_client
            resources = [{"id": "ocid1.user.oc1..<unique_ID>", "description": "Cloud Custodian"}]
            filter = UserSmtpCredentialsValueFilter(policy_str)
            filter.manager = user_mock
            filtered_resources = filter.process(resources, None)
            test.assertEqual(len(filtered_resources), 1)
