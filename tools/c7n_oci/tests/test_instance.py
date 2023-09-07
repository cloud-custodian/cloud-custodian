# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
import logging
import sys

import pytest

from pytest_terraform import terraform
from oci_common import OciBaseTest
from c7n_oci.resources.compute import InstanceMetrics


class TestInstance(OciBaseTest):
    def _get_instance_details(self, instance):
        ocid = instance["oci_core_instance.test_instance.id"]
        return ocid

    def _fetch_instance_validation_data(self, resource_manager, instance_id):
        return self.fetch_validation_data(resource_manager, "get_instance", instance_id)

    @pytest.mark.skipif(sys.platform == "win32", reason="This test does not run on Windows")
    @terraform("compute", scope="class")
    def test_add_defined_tag_to_instance(
        self, test, compute, with_or_without_compartment, tmp_path
    ):
        """
        test adding defined_tags tag on compute instance
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-instance",
                "resource": "oci.instance",
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [{"type": "update", "defined_tags": self.get_defined_tag("add_tag")}],
            },
            session_factory=session_factory,
            cache="memory",
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        assert resource["id"] == ocid
        assert self.get_defined_tag_value(resource["defined_tags"]) == "true"
        output = test.capture_logging(name=policy.resource_manager.log.name, level=logging.DEBUG)
        policy.run()
        assert 'Using cached oci.instance' in output.getvalue()

    @terraform("compute", scope="class")
    def test_update_defined_tag_of_instance(self, test, compute):
        """
        test update defined_tags tag on compute instance
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        ocid = compute["oci_core_instance.test_instance.id"]

        policy = test.load_policy(
            {
                "name": "update-defined-tag-from-instance",
                "resource": "oci.instance",
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [
                    {
                        "type": "update",
                        "defined_tags": self.get_defined_tag("update_tag"),
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "false")

    @terraform("compute", scope="class")
    def test_add_freeform_tag_to_instance(self, test, compute):
        """
        test adding freeform tag on compute instance
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "add-freeform-tag-to-instance",
                "resource": "oci.instance",
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [{"type": "update", "freeform_tags": {"Environment": "Development"}}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Development")

    @terraform("compute", scope="class")
    def test_update_freeform_tag_of_instance(self, test, compute):
        """
        test update freeform tag on compute instance
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "update-freeform-tag-from-instance",
                "resource": "oci.instance",
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [{"type": "update", "freeform_tags": {"Environment": "Production"}}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Production")

    @terraform("compute", scope="class")
    def test_get_freeform_tagged_instance(self, test, compute):
        """
        test get freeform tagged compute instances
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "get-tagged-instance",
                "resource": "oci.instance",
                "query": [
                    {"lifecycle_state": "RUNNING"},
                ],
                "filters": [{"type": "value", "key": "freeform_tags.Project", "value": "CNCF"}],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], ocid)
        test.assertEqual(resources[0]["freeform_tags"]["Project"], "CNCF")

    @terraform("compute", scope="class")
    def test_remove_freeform_tag(self, test, compute):
        """
        test remove freeform tag
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "instance-remove-tag",
                "resource": "oci.instance",
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [
                    {"type": "remove-tag", "freeform_tags": ["Project"]},
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        test.assertEqual(resource["freeform_tags"].get("Project"), None)

    @terraform("compute", scope="class")
    def test_remove_defined_tag(self, test, compute):
        """
        test remove defined tag
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "instance-remove-tag",
                "resource": "oci.instance",
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [
                    {
                        "type": "remove-tag",
                        "defined_tags": ["cloud-custodian-test.mark-for-resize"],
                    },
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), None)

    @terraform("compute", scope="class")
    def test_instance_power_off(self, test, compute):
        """
        test instance power off
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "instance-power-off",
                "resource": "oci.instance",
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [
                    {"type": "stop"},
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        assert resource["lifecycle_state"] in ["STOPPING", "STOPPED"]

    @terraform("compute", scope="class")
    def test_instance_metrics(self, test, compute):
        """
        test instance metrics
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "instance-with-low-cpu-utilization",
                "resource": "oci.instance",
                "filters": [
                    {"type": "metrics", "query": "CpuUtilization[1m].max() < 100"},
                ],
            },
            session_factory=session_factory,
        )
        if test.recording:
            self.wait(180)
        resources = policy.run()
        test_instance_found = False
        for resource in resources:
            if resource["id"] == ocid:
                test_instance_found = True
                break
        assert test_instance_found

    @terraform("compute", scope="class")
    @pytest.mark.parametrize("limit", [1, 10, 25])
    def test_instance_metrics_by_chunks(self, test, compute, limit):
        """
        test instance metrics by chunks
        """
        ocid = self._get_instance_details(compute)
        resource = {"id": ocid}
        filter_resources = [resource] * limit
        resource_query = resource_query = 'resourceId=~"{}"'.format(
            "|".join(resource["id"] for resource in filter_resources)
        )
        query = f"CpuUtilization[1m]{{{resource_query}}}.max() < 100"
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "instance-with-low-cpu-utilization",
                "resource": "oci.instance",
                "filters": [
                    {"type": "metrics", "query": query},
                ],
            },
            session_factory=session_factory,
        )
        if test.recording:
            self.wait(180)
        resources = policy.run()
        test_instance_found = False
        for resource in resources:
            if resource["id"] == ocid:
                test_instance_found = True
                break
        assert test_instance_found

    @pytest.mark.parametrize("data_size,expected", [(1, True), (10, True), (25, False)])
    def test_instance_metrics_query(self, data_size, expected):
        query = "CpuUtilization[1m].max() < 100"
        ocid = "ocid1.instance.oc1..<unique_ID>"
        filter_resources = [ocid] * data_size
        query = InstanceMetrics.get_metrics_resource_query(query, filter_resources)
        result = "resourceId" in query
        assert result == expected

    @pytest.mark.parametrize("data_size,expected", [(1, True), (10, True), (25, False)])
    def test_instance_metrics_query_region(self, data_size, expected):
        query = "CpuUtilization[1m]{region='us-ashburn-1'}.max() < 100"
        ocid = "ocid1.instance.oc1..<unique_ID>"
        filter_resources = [ocid] * data_size
        query = InstanceMetrics.get_metrics_resource_query(query, filter_resources)
        result = "resourceId" in query
        assert result == expected

    @terraform("compute", scope="class")
    def test_instance_start(self, test, compute):
        """
        test instance start
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "instance-start",
                "resource": "oci.instance",
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [{"type": "start"}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        assert resource["lifecycle_state"] in ["STARTING", "RUNNING"]

    @terraform("compute", scope="class")
    def test_instance_stop(self, test, compute):
        """
        test instance stop
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "instance-stop",
                "resource": "oci.instance",
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [{"type": "stop"}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        assert resource["lifecycle_state"] in ["STOPPING", "STOPPED"]

    @terraform("compute", scope="class")
    def test_instance_stop_force(self, test, compute):
        """
        test instance stop
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "instance-stop",
                "resource": "oci.instance",
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [{"type": "stop", "force": True}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        assert resource["lifecycle_state"] in ["STOPPING", "STOPPED"]

    @terraform("compute", scope="class")
    def test_instance_reboot(self, test, compute):
        """
        test instance reboot
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "instance-reboot",
                "resource": "oci.instance",
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [{"type": "reboot"}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        assert resource["lifecycle_state"] in [
            "STOPPING",
            "STOPPED",
            "STARTING",
            "RUNNING",
        ]

    @terraform("compute", scope="class")
    def test_instance_reboot_force(self, test, compute):
        """
        test instance reboot
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "instance-reboot",
                "resource": "oci.instance",
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [{"type": "reboot", "force": True}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        assert resource["lifecycle_state"] in [
            "STOPPING",
            "STOPPED",
            "STARTING",
            "RUNNING",
        ]

    @terraform("compute", scope="class")
    def test_add_defined_tag_to_instance_new(self, test, compute, with_or_without_compartment):
        """
        test adding defined_tags tag on compute instance
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-instance",
                "resource": "oci.instance",
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [{"type": "update", "defined_tags": self.get_defined_tag("add_tag")}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "true")
