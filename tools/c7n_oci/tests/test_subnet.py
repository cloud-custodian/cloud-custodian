import inspect

from oci_common import OciBaseTest, Resource, Scope, Module
from pytest_terraform import terraform


class TestSubnet(OciBaseTest):
    def _get_subnet_details(self, subnet):
        compartment_id = subnet["oci_core_subnet.test_subnet.compartment_id"]
        ocid = subnet["oci_core_subnet.test_subnet.id"]
        name = subnet["oci_core_subnet.test_subnet.display_name"]
        vcn_id = subnet["oci_core_vcn.test_vcn.id"]
        return compartment_id, ocid, name, vcn_id

    def _get_subnet_params(self, name, vcn_id):
        return {"display_name": name, "vcn_id": vcn_id}

    @terraform(Module.SUBNET.value, scope=Scope.CLASS.value)
    def test_add_defined_tag_to_subnet(self, test, subnet):
        """
        test adding defined_tags tag to subnet
        """
        compartment_id, subnet_ocid, subnet_name, vcn_id = self._get_subnet_details(
            subnet
        )
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-subnet",
                "resource": Resource.SUBNET.value,
                "filters": [
                    {
                        "type": "query",
                        "params": {
                            "compartment_id": compartment_id,
                        },
                    },
                    {"type": "value", "key": "identifier", "value": subnet_ocid},
                ],
                "actions": [
                    {
                        "type": "update_subnet",
                        "params": {
                            "update_subnet_details": {
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
            policy,
            compartment_id,
            id=subnet_ocid,
            **self._get_subnet_params(subnet_name, vcn_id)
        )
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], subnet_ocid)
        test.assertEqual(
            self.get_defined_tag_value(resources[0]["defined_tags"]), "true"
        )

    @terraform(Module.SUBNET.value, scope=Scope.CLASS.value)
    def test_update_defined_tag_of_subnet(self, test, subnet):
        """
        test update defined_tags tag on subnet
        """
        compartment_id, subnet_ocid, subnet_name, vcn_id = self._get_subnet_details(
            subnet
        )
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "update-defined-tag-of-subnet",
                "resource": Resource.SUBNET.value,
                "filters": [
                    {"type": "query", "params": {"compartment_id": compartment_id}},
                    {"type": "value", "key": "identifier", "value": subnet_ocid},
                ],
                "actions": [
                    {
                        "type": "update_subnet",
                        "params": {
                            "update_subnet_details": {
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
            policy,
            compartment_id,
            id=subnet_ocid,
            **self._get_subnet_params(subnet_name, vcn_id)
        )
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], subnet_ocid)
        test.assertEqual(
            self.get_defined_tag_value(resources[0]["defined_tags"]), "false"
        )

    @terraform(Module.SUBNET.value, scope=Scope.CLASS.value)
    def test_add_freeform_tag_to_subnet(self, test, subnet):
        """
        test adding freeform tag to subnet
        """
        compartment_id, subnet_ocid, subnet_name, vcn_id = self._get_subnet_details(
            subnet
        )
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "add-tag-freeform-to-subnet",
                "resource": Resource.SUBNET.value,
                "filters": [
                    {"type": "query", "params": {"compartment_id": compartment_id}},
                    {"type": "value", "key": "identifier", "value": subnet_ocid},
                ],
                "actions": [
                    {
                        "type": "update_subnet",
                        "params": {
                            "update_subnet_details": {
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
            policy,
            compartment_id,
            id=subnet_ocid,
            **self._get_subnet_params(subnet_name, vcn_id)
        )
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], subnet_ocid)
        test.assertEqual(resources[0]["freeform_tags"]["Environment"], "Development")

    @terraform(Module.SUBNET.value, scope=Scope.CLASS.value)
    def test_update_freeform_tag_of_subnet(self, test, subnet):
        """
        test update freeform tag of subnet
        """
        compartment_id, subnet_ocid, subnet_name, vcn_id = self._get_subnet_details(
            subnet
        )
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "update-freeform-tag-of-subnet",
                "resource": Resource.SUBNET.value,
                "filters": [
                    {"type": "query", "params": {"compartment_id": compartment_id}},
                    {"type": "value", "key": "identifier", "value": subnet_ocid},
                ],
                "actions": [
                    {
                        "type": "update_subnet",
                        "params": {
                            "update_subnet_details": {
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
            policy,
            compartment_id,
            id=subnet_ocid,
            **self._get_subnet_params(subnet_name, vcn_id)
        )
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], subnet_ocid)
        test.assertEqual(resources[0]["freeform_tags"]["Environment"], "Production")

    @terraform(Module.SUBNET.value, scope=Scope.CLASS.value)
    def test_get_freeform_tagged_subnet(self, test, subnet):
        """
        test get freeform tagged subnet
        """
        compartment_id, subnet_ocid, _, _ = self._get_subnet_details(subnet)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "get-freeform-tagged-subnet",
                "resource": Resource.SUBNET.value,
                "filters": [
                    {"type": "query", "params": {"compartment_id": compartment_id}},
                    {"type": "value", "key": "freeform_tags.Project", "value": "CNCF"},
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["identifier"], subnet_ocid)
        test.assertEqual(resources[0]["freeform_tags"]["Project"], "CNCF")
