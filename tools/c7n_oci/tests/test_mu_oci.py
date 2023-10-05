# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import json
import os
from unittest.mock import Mock, patch

import oci
import pytest
from c7n_oci import mu
from c7n_oci.constants import COMPARTMENT_IDS
from c7n_oci.policy import EventMode
from c7n_oci.session import SessionFactory
from oci_common import OciBaseTest
from pytest_terraform import terraform

from c7n.testing import C7N_FUNCTIONAL


class TestMuOci(OciBaseTest):
    def _get_subnet_details(self, subnet):
        compartment_id = subnet["oci_core_subnet.test_subnet.compartment_id"]
        ocid = subnet["oci_core_subnet.test_subnet.id"]
        return compartment_id, ocid

    def _create_bucket(self, resource_manager, compartment_id, bucket_name):
        storage_client = resource_manager.get_client()
        namespace = storage_client.get_namespace().data
        bucket_details = oci.object_storage.models.CreateBucketDetails(
            compartment_id=compartment_id, name=bucket_name
        )
        storage_client.create_bucket(namespace, create_bucket_details=bucket_details)
        return namespace

    def _delete_bucket(self, resource_manager, bucket_name):
        storage_client = resource_manager.get_client()
        namespace = storage_client.get_namespace().data
        storage_client.delete_bucket(namespace, bucket_name=bucket_name)

    def _fetch_bucket_validation_data(self, resource_manager, namespace_name, bucket_name):
        client = resource_manager.get_client()
        resource = client.get_bucket(namespace_name, bucket_name)
        return oci.util.to_dict(resource.data)

    @pytest.mark.skipif((not C7N_FUNCTIONAL), reason="Functional test")
    @terraform("mu_resources", scope="function")
    def test_event_mode_auto_tag_bucket(self, test, mu_resources):
        bucket_name = "custodian-auto-tag-bucket-test"
        compartment_id, subnet_ocid = self._get_subnet_details(mu_resources)
        policy = test.load_policy(
            {
                "name": "auto-tag-instance",
                "resource": "oci.bucket",
                "mode": {
                    "type": "oci-event",
                    "subnets": [subnet_ocid],
                    "events": ["createbucket"],
                },
                "actions": [{"type": "update", "freeform_tags": {"Source": "Custodian-function"}}],
            },
            session_factory=SessionFactory(region='us-ashburn-1'),
        )
        try:
            policy.run()
            namespace_name = self._create_bucket(
                policy.resource_manager, compartment_id, bucket_name
            )
            self.wait(40)

            resource = self._fetch_bucket_validation_data(
                policy.resource_manager, namespace_name, bucket_name
            )
            test.assertEqual(resource["name"], bucket_name)
            test.assertEqual(resource["freeform_tags"]["Source"], "Custodian-function")

        finally:
            event_mode = EventMode(policy)
            event_mode.deprovision()
            self._delete_bucket(policy.resource_manager, bucket_name)

    @pytest.mark.skipif((C7N_FUNCTIONAL), reason="Non Functional test")
    @terraform("mu_resources", scope="function")
    def test_create_function_event_mode(self, test, mu_resources):
        try:
            policy_name = "test-create-function-event-mode"
            function_object_name = f"custodian-{policy_name}"
            session_factory = test.oci_session_factory_for_repeated_api_calls()
            _, subnet_ocid = self._get_subnet_details(mu_resources)
            policy = test.load_policy(
                {
                    "name": policy_name,
                    "resource": "oci.bucket",
                    "mode": {
                        "type": "oci-event",
                        "subnets": [subnet_ocid],
                        "events": ["createbucket"],
                    },
                    "actions": [
                        {"type": "update", "freeform_tags": {"Source": "Custodian-function"}}
                    ],
                },
                session_factory=session_factory,
            )
            mock = Mock()
            registry_mock_public = Mock()
            registry_mock_ocir = Mock()
            with patch('docker.from_env') as mock_from_env:
                mock_docker_client = Mock(spec_set=['images', 'login'])
                mock_from_env.return_value = mock_docker_client
                mock_docker_client.login.return_value = mock
                mock_docker_client.images.pull.return_value = mock
                mock_docker_client.images.push.return_value = mock
                mock_docker_client.images.tag.return_value = mock
                registry_mock_public.attrs = {"Descriptor": {"digest": "sha:abc"}}
                registry_mock_ocir.attrs = {"Descriptor": {"digest": "sha:def"}}
                mock_docker_client.images.get_registry_data.side_effect = [
                    registry_mock_public,
                    registry_mock_ocir,
                ]

                policy.run()

            fm = mu.FunctionManager(session_factory)
            compartments = fm.get_compartments()
            apps = fm.list_applications(compartments[0], function_object_name)
            assert len(apps) == 1
            assert apps[0].display_name == function_object_name

            er = mu.EventRule(session_factory())
            event_rules = er.list_event_rules(compartments[0], function_object_name)
            assert len(event_rules) == 1
            assert event_rules[0].display_name == function_object_name

        finally:
            event_mode = EventMode(policy)
            event_mode.deprovision()

    @pytest.mark.skipif((C7N_FUNCTIONAL), reason="Non Functional test")
    @terraform("mu_resources", scope="function")
    def test_update_function_event_mode(self, test, mu_resources):
        try:
            policy_name = "test-update-function-event-mode"
            function_object_name = f"custodian-{policy_name}"
            session_factory = test.oci_session_factory_for_repeated_api_calls()
            _, subnet_ocid = self._get_subnet_details(mu_resources)
            policy = test.load_policy(
                {
                    "name": policy_name,
                    "resource": "oci.bucket",
                    "mode": {
                        "type": "oci-event",
                        "subnets": [subnet_ocid],
                        "events": ["createbucket"],
                    },
                    "actions": [
                        {"type": "update", "freeform_tags": {"Source": "Custodian-function"}}
                    ],
                },
                session_factory=session_factory,
            )
            mock = Mock()
            registry_mock = Mock()
            with patch('docker.from_env') as mock_from_env:
                mock_docker_client = Mock(spec_set=['images', 'login'])
                mock_from_env.return_value = mock_docker_client
                mock_docker_client.login.return_value = mock
                mock_docker_client.images.pull.return_value = mock
                mock_docker_client.images.push.return_value = mock
                mock_docker_client.images.tag.return_value = mock
                registry_mock.attrs = {"Descriptor": {"digest": "sha:test"}}
                mock_docker_client.images.get_registry_data.return_value = registry_mock

                policy.run()

                # update
                policy = test.load_policy(
                    {
                        "name": policy_name,
                        "resource": "oci.bucket",
                        "mode": {
                            "type": "oci-event",
                            "subnets": [subnet_ocid],
                            "events": ["createbucket", "updatebucket"],
                            "memory": 1024,
                            "timeout": 60,
                            "freeform_tags": {"Project": "CNCF"},
                        },
                        "actions": [
                            {"type": "update", "freeform_tags": {"Source": "Custodian-function"}}
                        ],
                    },
                    session_factory=session_factory,
                )
                policy.run()

            fm = mu.FunctionManager(session_factory)
            compartments = fm.get_compartments()
            apps = fm.list_applications(compartments[0], function_object_name)
            assert len(apps) == 1
            assert apps[0].display_name == function_object_name
            fns = fm.list_functions(apps[0].id)
            assert fns[0].memory_in_mbs == 1024
            assert fns[0].timeout_in_seconds == 60

            er = mu.EventRule(session_factory())
            event_rules = er.list_event_rules(compartments[0], function_object_name)
            assert len(event_rules) == 1
            assert event_rules[0].display_name == function_object_name
            assert len(json.loads(event_rules[0].condition)['eventType']) == 2

        finally:
            event_mode = EventMode(policy)
            event_mode.deprovision()

    @pytest.mark.skipif((C7N_FUNCTIONAL), reason="Non Functional test")
    @terraform("mu_resources", scope="function")
    def test_deprovision(self, test, mu_resources):
        policy_name = "test-delete-function-event-mode"
        function_object_name = f"custodian-{policy_name}"
        session_factory = test.oci_session_factory_for_repeated_api_calls()
        _, subnet_ocid = self._get_subnet_details(mu_resources)
        policy = test.load_policy(
            {
                "name": policy_name,
                "resource": "oci.bucket",
                "mode": {
                    "type": "oci-event",
                    "subnets": [subnet_ocid],
                    "events": ["createbucket"],
                },
                "actions": [{"type": "update", "freeform_tags": {"Source": "Custodian-function"}}],
            },
            session_factory=session_factory,
        )
        mock = Mock()
        registry_mock_public = Mock()
        registry_mock_ocir = Mock()
        with patch('docker.from_env') as mock_from_env:
            mock_docker_client = Mock(spec_set=['images', 'login'])
            mock_from_env.return_value = mock_docker_client
            mock_docker_client.login.return_value = mock
            mock_docker_client.images.pull.return_value = mock
            mock_docker_client.images.push.return_value = mock
            mock_docker_client.images.tag.return_value = mock
            registry_mock_public.attrs = {"Descriptor": {"digest": "sha:abc"}}
            registry_mock_ocir.attrs = {"Descriptor": {"digest": "sha:def"}}
            mock_docker_client.images.get_registry_data.side_effect = [
                registry_mock_public,
                registry_mock_ocir,
            ]

            policy.run()

        event_mode = EventMode(policy)
        event_mode.deprovision()
        fm = mu.FunctionManager(session_factory)
        compartments = fm.get_compartments()
        apps = fm.list_applications(compartments[0], function_object_name)
        assert len(apps) == 0

        er = mu.EventRule(session_factory())
        event_rules = er.list_event_rules(compartments[0], function_object_name)
        assert len(event_rules) == 0

    def test_update_dynamic_group(self, test):
        dynamic_groups = None
        permission_mgr = None
        oci_policy = None
        try:
            session_factory = test.oci_session_factory_for_repeated_api_calls()
            session = session_factory()
            tenancy_id = os.environ.get('OCI_TENANCY')
            permission_mgr = mu.PermissionManager(session, tenancy_id)
            compartments = os.environ.get(COMPARTMENT_IDS).split(",")
            permission_mgr.add_permissions(compartments[0], "test.function")

            # Calling again to add new function in dynamic group
            permission_mgr.add_permissions(compartments[0], "abc.function")

            dynamic_groups = permission_mgr.get_dynamic_groups(
                tenancy_id, f"custodian-fn-{compartments[0]}"
            )

            assert dynamic_groups[0].name == f"custodian-fn-{compartments[0]}"
            assert ("abc.function" in dynamic_groups[0].matching_rule) is True

            oci_policy = permission_mgr.get_oci_policy(tenancy_id)
            assert oci_policy[0].name == permission_mgr.oci_policy_name

        finally:
            if dynamic_groups and permission_mgr:
                permission_mgr.delete_dynamic_group(dynamic_groups[0].id)
            if permission_mgr and oci_policy:
                permission_mgr.delete_oci_policy(oci_policy[0].id)
