import inspect

from oci_common import Module, OciBaseTest, Resource, Scope
from pytest_terraform import terraform


class TestZone(OciBaseTest):
    def _get_zone_details(self, zone):
        compartment_id = zone["oci_dns_zone.test_zone.compartment_id"]
        ocid = zone["oci_dns_zone.test_zone.id"]
        name = zone["oci_dns_zone.test_zone.name"]
        return compartment_id, ocid, name

    def _get_zone_params(self, name):
        return {"name": name, "scope": "PRIVATE"}

    @terraform(Module.ZONE.value, scope=Scope.CLASS.value)
    def test_add_defined_tag_to_zone(self, test, zone):
        """
        test adding defined_tags tag to zone
        """
        compartment_id, zone_ocid, zone_name = self._get_zone_details(zone)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )

        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-zone",
                "resource": Resource.ZONE.value,
                "filters": [
                    {
                        "type": "query",
                        "params": {
                            "compartment_id": compartment_id,
                        },
                    },
                    {"type": "value", "key": "identifier", "value": zone_ocid},
                ],
                "actions": [
                    {
                        "type": "update_zone",
                        "params": {
                            "update_zone_details": {
                                "defined_tags": self.get_defined_tag("add_tag")
                            }
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        self.wait_for_resource_search_sync()
        policy.run()
        resources = self.get_resources(
            policy, compartment_id, id=zone_ocid, **self._get_zone_params(zone_name)
        )
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], zone_ocid)
        test.assertEqual(
            self.get_defined_tag_value(resources[0]["defined_tags"]), "true"
        )

    @terraform(Module.ZONE.value, scope=Scope.CLASS.value)
    def test_update_defined_tag_of_zone(self, test, zone):
        """
        test update defined_tags tag on zone
        """
        compartment_id, zone_ocid, zone_name = self._get_zone_details(zone)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )

        policy = test.load_policy(
            {
                "name": "update-defined-tag-of-zone",
                "resource": Resource.ZONE.value,
                "filters": [
                    {"type": "query", "params": {"compartment_id": compartment_id}},
                    {"type": "value", "key": "identifier", "value": zone_ocid},
                ],
                "actions": [
                    {
                        "type": "update_zone",
                        "params": {
                            "update_zone_details": {
                                "defined_tags": self.get_defined_tag("update_tag")
                            }
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resources = self.get_resources(
            policy, compartment_id, id=zone_ocid, **self._get_zone_params(zone_name)
        )
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], zone_ocid)
        test.assertEqual(
            self.get_defined_tag_value(resources[0]["defined_tags"]), "false"
        )

    @terraform(Module.ZONE.value, scope=Scope.CLASS.value)
    def test_add_freeform_tag_to_zone(self, test, zone):
        """
        test adding freeform tag to zone
        """
        compartment_id, zone_ocid, zone_name = self._get_zone_details(zone)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )

        policy = test.load_policy(
            {
                "name": "add-tag-freeform-to-zone",
                "resource": Resource.ZONE.value,
                "filters": [
                    {"type": "query", "params": {"compartment_id": compartment_id}},
                    {"type": "value", "key": "identifier", "value": zone_ocid},
                ],
                "actions": [
                    {
                        "type": "update_zone",
                        "params": {
                            "update_zone_details": {
                                "freeform_tags": {"Environment": "Development"}
                            }
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resources = self.get_resources(
            policy, compartment_id, id=zone_ocid, **self._get_zone_params(zone_name)
        )
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], zone_ocid)
        test.assertEqual(resources[0]["freeform_tags"]["Environment"], "Development")

    @terraform(Module.ZONE.value, scope=Scope.CLASS.value)
    def test_update_freeform_tag_of_zone(self, test, zone):
        """
        test update freeform tag of zone
        """
        compartment_id, zone_ocid, zone_name = self._get_zone_details(zone)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )

        policy = test.load_policy(
            {
                "name": "update-freeform-tag-of-zone",
                "resource": Resource.ZONE.value,
                "filters": [
                    {"type": "query", "params": {"compartment_id": compartment_id}},
                    {"type": "value", "key": "identifier", "value": zone_ocid},
                ],
                "actions": [
                    {
                        "type": "update_zone",
                        "params": {
                            "update_zone_details": {
                                "freeform_tags": {"Environment": "Production"}
                            }
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resources = self.get_resources(
            policy, compartment_id, id=zone_ocid, **self._get_zone_params(zone_name)
        )
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], zone_ocid)
        test.assertEqual(resources[0]["freeform_tags"]["Environment"], "Production")

    @terraform(Module.ZONE.value, scope=Scope.CLASS.value)
    def test_get_freeform_tagged_zone(self, test, zone):
        """
        test get freeform tagged zone
        """
        compartment_id, zone_ocid, _ = self._get_zone_details(zone)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )

        policy = test.load_policy(
            {
                "name": "get-freeform-tagged-zone",
                "resource": Resource.ZONE.value,
                "filters": [
                    {"type": "query", "params": {"compartment_id": compartment_id}},
                    {"type": "value", "key": "freeform_tags.Project", "value": "CNCF"},
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["identifier"], zone_ocid)
        test.assertEqual(resources[0]["freeform_tags"]["Project"], "CNCF")
