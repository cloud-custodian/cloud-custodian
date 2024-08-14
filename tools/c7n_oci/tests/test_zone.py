# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0


import oci
from pytest_terraform import terraform

from oci_common import OciBaseTest


class TestZone(OciBaseTest):
    def _get_zone_details(self, zone):
        ocid = zone["oci_dns_zone.test_zone.id"]
        return ocid

    def _fetch_zone_validation_data(self, resource_manager, zone_id):
        client = resource_manager.get_client()
        resource = client.get_zone(zone_id, scope="PRIVATE")
        return oci.util.to_dict(resource.data)

    @terraform("zone", scope="class")
    def test_add_defined_tag_to_zone(self, test, zone, with_or_without_compartment):
        """
        test adding defined_tags tag to zone
        """
        zone_ocid = self._get_zone_details(zone)
        session_factory = test.oci_session_factory()

        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-zone",
                "resource": "oci.zone",
                "query": [{"scope": "PRIVATE"}],
                "filters": [
                    {"type": "value", "key": "id", "value": zone_ocid},
                ],
                "actions": [{"type": "update", "defined_tags": self.get_defined_tag("add_tag")}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_zone_validation_data(policy.resource_manager, zone_ocid)
        test.assertEqual(resource["id"], zone_ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "true")

    @terraform("zone", scope="class")
    def test_update_zone(self, test, zone, with_or_without_compartment):
        """
        test adding defined_tags tag to zone
        """
        zone_ocid = self._get_zone_details(zone)
        session_factory = test.oci_session_factory()

        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-zone",
                "resource": "oci.zone",
                "query": [{"scope": "PRIVATE"}],
                "filters": [
                    {"type": "value", "key": "id", "value": zone_ocid},
                ],
                "actions": [{"type": "update", "defined_tags": self.get_defined_tag("add_tag")}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_zone_validation_data(policy.resource_manager, zone_ocid)
        test.assertEqual(resource["id"], zone_ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "true")

    @terraform("zone", scope="class")
    def test_update_defined_tag_of_zone(self, test, zone):
        """
        test update defined_tags tag on zone
        """
        zone_ocid = self._get_zone_details(zone)
        session_factory = test.oci_session_factory()

        policy = test.load_policy(
            {
                "name": "update-defined-tag-of-zone",
                "resource": "oci.zone",
                "query": [{"scope": "PRIVATE"}],
                "filters": [
                    {"type": "value", "key": "freeform_tags.Project", "value": "CNCF"},
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
        resource = self._fetch_zone_validation_data(policy.resource_manager, zone_ocid)
        test.assertEqual(resource["id"], zone_ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "false")

    @terraform("zone", scope="class")
    def test_add_freeform_tag_to_zone(self, test, zone):
        """
        test adding freeform tag to zone
        """
        zone_ocid = self._get_zone_details(zone)
        session_factory = test.oci_session_factory()

        policy = test.load_policy(
            {
                "name": "add-tag-freeform-to-zone",
                "resource": "oci.zone",
                "query": [{"scope": "PRIVATE"}],
                "filters": [
                    {
                        "type": "value",
                        "key": "freeform_tags.Project",
                        "value": "CNCF",
                        "op": "eq",
                    },
                ],
                "actions": [{"type": "update", "freeform_tags": {"Environment": "Development"}}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_zone_validation_data(policy.resource_manager, zone_ocid)
        test.assertEqual(resource["id"], zone_ocid)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Development")

    @terraform("zone", scope="class")
    def test_update_freeform_tag_of_zone(self, test, zone):
        """
        test update freeform tag of zone
        """
        zone_ocid = self._get_zone_details(zone)
        session_factory = test.oci_session_factory()

        policy = test.load_policy(
            {
                "name": "update-freeform-tag-of-zone",
                "resource": "oci.zone",
                "query": [{"scope": "PRIVATE"}],
                "filters": [
                    {"type": "value", "key": "freeform_tags.Project", "value": "CNCF"},
                ],
                "actions": [{"type": "update", "freeform_tags": {"Environment": "Production"}}],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_zone_validation_data(policy.resource_manager, zone_ocid)
        test.assertEqual(resource["id"], zone_ocid)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Production")

    @terraform("zone", scope="class")
    def test_get_freeform_tagged_zone(self, test, zone):
        """
        test get freeform tagged zone
        """
        zone_ocid = self._get_zone_details(zone)
        session_factory = test.oci_session_factory()

        policy = test.load_policy(
            {
                "name": "get-freeform-tagged-zone",
                "resource": "oci.zone",
                "query": [{"scope": "PRIVATE"}],
                "filters": [
                    {"type": "value", "key": "freeform_tags.Project", "value": "CNCF"},
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], zone_ocid)
        test.assertEqual(resources[0]["freeform_tags"]["Project"], "CNCF")

    @terraform("zone", scope="class")
    def test_remove_freeform_tag(self, test, zone):
        """
        test remove freeform tag
        """
        zone_ocid = self._get_zone_details(zone)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "zone-remove-tag",
                "resource": "oci.zone",
                "query": [{"scope": "PRIVATE"}],
                "filters": [
                    {"type": "value", "key": "id", "value": zone_ocid},
                ],
                "actions": [
                    {"type": "remove-tag", "freeform_tags": ["Project"]},
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_zone_validation_data(policy.resource_manager, zone_ocid)
        test.assertEqual(resource["freeform_tags"].get("Project"), None)

    @terraform("zone", scope="class")
    def test_remove_defined_tag(self, test, zone):
        """
        test remove defined tag
        """
        zone_ocid = self._get_zone_details(zone)
        session_factory = test.oci_session_factory()
        policy = test.load_policy(
            {
                "name": "zone-remove-tag",
                "resource": "oci.zone",
                "query": [{"scope": "PRIVATE"}],
                "filters": [
                    {"type": "value", "key": "id", "value": zone_ocid},
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
        resource = self._fetch_zone_validation_data(policy.resource_manager, zone_ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), None)
