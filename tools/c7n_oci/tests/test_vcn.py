import inspect

from oci_common import OciBaseTest, Resource, Scope, Module
from pytest_terraform import terraform


class TestVcn(OciBaseTest):
    def _get_vcn_details(self, vcn):
        compartment_id = vcn["oci_core_vcn.test_virtual_network_vcn.compartment_id"]
        ocid = vcn["oci_core_vcn.test_virtual_network_vcn.id"]
        name = vcn["oci_core_vcn.test_virtual_network_vcn.display_name"]
        return compartment_id, ocid, name

    def _get_vcn_params(self, name):
        return {"display_name": name}

    @terraform(Module.VCN.value, scope=Scope.CLASS.value)
    def test_add_defined_tag_to_vcn(self, test, vcn):
        """
        test adding defined_tags tag to vcn
        """
        compartment_id, vcn_ocid, name = self._get_vcn_details(vcn)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-vcn",
                "resource": Resource.VCN.value,
                "filters": [
                    {
                        "type": "query",
                        "params": {
                            "compartment_id": compartment_id,
                        },
                    },
                    {"type": "value", "key": "identifier", "value": vcn_ocid},
                ],
                "actions": [
                    {
                        "type": "update_vcn",
                        "params": {
                            "update_vcn_details": {
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
            policy, compartment_id, id=vcn_ocid, **self._get_vcn_params(name)
        )
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], vcn_ocid)
        test.assertEqual(
            self.get_defined_tag_value(resources[0]["defined_tags"]), "true"
        )

    @terraform(Module.VCN.value, scope=Scope.CLASS.value)
    def test_update_defined_tag_of_vcn(self, test, vcn):
        """
        test update defined_tags tag on vcn
        """
        compartment_id, vcn_ocid, name = self._get_vcn_details(vcn)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "update-defined-tag-of-vcn",
                "resource": Resource.VCN.value,
                "filters": [
                    {"type": "query", "params": {"compartment_id": compartment_id}},
                    {"type": "value", "key": "identifier", "value": vcn_ocid},
                ],
                "actions": [
                    {
                        "type": "update_vcn",
                        "params": {
                            "update_vcn_details": {
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
            policy, compartment_id, id=vcn_ocid, **self._get_vcn_params(name)
        )
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], vcn_ocid)
        test.assertEqual(
            self.get_defined_tag_value(resources[0]["defined_tags"]), "false"
        )

    @terraform(Module.VCN.value, scope=Scope.CLASS.value)
    def test_add_freeform_tag_to_vcn(self, test, vcn):
        """
        test adding freeform tag to vcn
        """
        compartment_id, vcn_ocid, name = self._get_vcn_details(vcn)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "add-tag-freeform-to-vcn",
                "resource": Resource.VCN.value,
                "filters": [
                    {"type": "query", "params": {"compartment_id": compartment_id}},
                    {"type": "value", "key": "identifier", "value": vcn_ocid},
                ],
                "actions": [
                    {
                        "type": "update_vcn",
                        "params": {
                            "update_vcn_details": {
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
            policy, compartment_id, id=vcn_ocid, **self._get_vcn_params(name)
        )
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], vcn_ocid)
        test.assertEqual(resources[0]["freeform_tags"]["Environment"], "Development")

    @terraform(Module.VCN.value, scope=Scope.CLASS.value)
    def test_update_freeform_tag_of_vcn(self, test, vcn):
        """
        test update freeform tag of vcn
        """
        compartment_id, vcn_ocid, name = self._get_vcn_details(vcn)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "update-freeform-tag-of-vcn",
                "resource": Resource.VCN.value,
                "filters": [
                    {"type": "query", "params": {"compartment_id": compartment_id}},
                    {"type": "value", "key": "identifier", "value": vcn_ocid},
                ],
                "actions": [
                    {
                        "type": "update_vcn",
                        "params": {
                            "update_vcn_details": {
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
            policy, compartment_id, id=vcn_ocid, **self._get_vcn_params(name)
        )
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], vcn_ocid)
        test.assertEqual(resources[0]["freeform_tags"]["Environment"], "Production")

    @terraform(Module.VCN.value, scope=Scope.CLASS.value)
    def test_get_freeform_tagged_vcn(self, test, vcn):
        """
        test get freeform tagged vcn
        """
        compartment_id, vcn_ocid, _ = self._get_vcn_details(vcn)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "get-freeform-tagged-vcn",
                "resource": Resource.VCN.value,
                "filters": [
                    {"type": "query", "params": {"compartment_id": compartment_id}},
                    {"type": "value", "key": "freeform_tags.Project", "value": "CNCF"},
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["identifier"], vcn_ocid)
        test.assertEqual(resources[0]["freeform_tags"]["Project"], "CNCF")
