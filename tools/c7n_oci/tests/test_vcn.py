# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


from pytest_terraform import terraform

from oci_common import OciBaseTest


class TestVcn(OciBaseTest):
    def _get_vcn_details(self, vcn):
        ocid = vcn["oci_core_vcn.test_virtual_network_vcn.id"]
        return ocid

    def _fetch_instance_validation_data(self, resource_manager, vcn_id):
        return self.fetch_validation_data(resource_manager, "get_vcn", vcn_id)

    @terraform("vcn", scope="class")
    def test_add_defined_tag_to_vcn(self, test, vcn, with_or_without_compartment):
        """
        test adding defined_tags tag to vcn
        """
        vcn_ocid = self._get_vcn_details(vcn)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-vcn",
                "resource": "oci.vcn",
                "filters": [
                    {"type": "value", "key": "id", "value": vcn_ocid},
                ],
                "actions": [{"type": "update", "defined_tags": self.get_defined_tag("add_tag")}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, vcn_ocid)
        test.assertEqual(resource["id"], vcn_ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "true")

    @terraform("vcn", scope="class")
    def test_update_defined_tag_of_vcn(self, test, vcn):
        """
        test update defined_tags tag on vcn
        """
        vcn_ocid = self._get_vcn_details(vcn)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "update-defined-tag-of-vcn",
                "resource": "oci.vcn",
                "filters": [
                    {"type": "value", "key": "id", "value": vcn_ocid},
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
        resource = self._fetch_instance_validation_data(policy.resource_manager, vcn_ocid)
        test.assertEqual(resource["id"], vcn_ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "false")

    @terraform("vcn", scope="class")
    def test_add_freeform_tag_to_vcn(self, test, vcn):
        """
        test adding freeform tag to vcn
        """
        vcn_ocid = self._get_vcn_details(vcn)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "add-tag-freeform-to-vcn",
                "resource": "oci.vcn",
                "filters": [
                    {"type": "value", "key": "id", "value": vcn_ocid},
                ],
                "actions": [{"type": "update", "freeform_tags": {"Environment": "Development"}}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, vcn_ocid)
        test.assertEqual(resource["id"], vcn_ocid)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Development")

    @terraform("vcn", scope="class")
    def test_update_vcn(self, test, vcn):
        """
        test adding freeform tag to vcn
        """
        vcn_ocid = self._get_vcn_details(vcn)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "add-tag-freeform-to-vcn",
                "resource": "oci.vcn",
                "filters": [
                    {"type": "value", "key": "id", "value": vcn_ocid},
                ],
                "actions": [{"type": "update", "freeform_tags": {"Environment": "Development"}}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, vcn_ocid)
        test.assertEqual(resource["id"], vcn_ocid)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Development")

    @terraform("vcn", scope="class")
    def test_update_freeform_tag_of_vcn(self, test, vcn):
        """
        test update freeform tag of vcn
        """
        vcn_ocid = self._get_vcn_details(vcn)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "update-freeform-tag-of-vcn",
                "resource": "oci.vcn",
                "filters": [
                    {"type": "value", "key": "id", "value": vcn_ocid},
                ],
                "actions": [{"type": "update", "freeform_tags": {"Environment": "Production"}}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, vcn_ocid)
        test.assertEqual(resource["id"], vcn_ocid)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Production")

    @terraform("vcn", scope="class")
    def test_get_freeform_tagged_vcn(self, test, vcn):
        """
        test get freeform tagged vcn
        """
        vcn_ocid = self._get_vcn_details(vcn)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "get-freeform-tagged-vcn",
                "resource": "oci.vcn",
                "filters": [
                    {"type": "value", "key": "freeform_tags.Project", "value": "CNCF"},
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], vcn_ocid)
        test.assertEqual(resources[0]["freeform_tags"]["Project"], "CNCF")

    @terraform("vcn", scope="class")
    def test_remove_freeform_tag(self, test, vcn):
        """
        test remove freeform tag
        """
        vcn_ocid = self._get_vcn_details(vcn)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "vcn-remove-tag",
                "resource": "oci.vcn",
                "filters": [
                    {"type": "value", "key": "id", "value": vcn_ocid},
                ],
                "actions": [
                    {"type": "remove-tag", "freeform_tags": ["Project"]},
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, vcn_ocid)
        test.assertEqual(resource["id"], vcn_ocid)
        test.assertEqual(resource["freeform_tags"].get("Project"), None)

    @terraform("vcn", scope="class")
    def test_remove_defined_tag(self, test, vcn):
        """
        test remove defined tag
        """
        vcn_ocid = self._get_vcn_details(vcn)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "vcn-remove-tag",
                "resource": "oci.vcn",
                "filters": [
                    {"type": "value", "key": "id", "value": vcn_ocid},
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
        resource = self._fetch_instance_validation_data(policy.resource_manager, vcn_ocid)
        test.assertEqual(resource["id"], vcn_ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), None)
