import inspect

from pytest_terraform import terraform

from oci_common import OciBaseTest, Resource, Scope, Module


class TestSubnet(OciBaseTest):
    def _get_subnet_details(self, subnet):
        compartment_id = subnet["oci_core_subnet.test_subnet.compartment_id"]
        ocid = subnet["oci_core_subnet.test_subnet.id"]
        return compartment_id, ocid

    def _fetch_instance_validation_data(self, resource_manager, subnet_id):
        return self.fetch_validation_data(resource_manager, "get_subnet", subnet_id)

    @terraform(Module.SUBNET.value, scope=Scope.CLASS.value)
    def test_add_defined_tag_to_subnet(self, test, subnet, with_or_without_compartment):
        """
        test adding defined_tags tag to subnet
        """
        compartment_id, subnet_ocid = self._get_subnet_details(subnet)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-subnet",
                "resource": Resource.SUBNET.value,
                "filters": [
                    {"type": "value", "key": "id", "value": subnet_ocid},
                ],
                "actions": [
                    {
                        "type": "update-subnet",
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
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, subnet_ocid)
        test.assertEqual(resource["id"], subnet_ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "true")

    @terraform(Module.SUBNET.value, scope=Scope.CLASS.value)
    def test_update_defined_tag_of_subnet(self, test, subnet):
        """
        test update defined_tags tag on subnet
        """
        compartment_id, subnet_ocid = self._get_subnet_details(subnet)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "update-defined-tag-of-subnet",
                "resource": Resource.SUBNET.value,
                "filters": [
                    {"type": "value", "key": "id", "value": subnet_ocid},
                ],
                "actions": [
                    {
                        "type": "update-subnet",
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
        resource = self._fetch_instance_validation_data(policy.resource_manager, subnet_ocid)
        test.assertEqual(resource["id"], subnet_ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "false")

    @terraform(Module.SUBNET.value, scope=Scope.CLASS.value)
    def test_add_freeform_tag_to_subnet(self, test, subnet):
        """
        test adding freeform tag to subnet
        """
        compartment_id, subnet_ocid = self._get_subnet_details(subnet)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "add-tag-freeform-to-subnet",
                "resource": Resource.SUBNET.value,
                "filters": [
                    {"type": "value", "key": "id", "value": subnet_ocid},
                ],
                "actions": [
                    {
                        "type": "update-subnet",
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
        resource = self._fetch_instance_validation_data(policy.resource_manager, subnet_ocid)
        test.assertEqual(resource["id"], subnet_ocid)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Development")

    @terraform(Module.SUBNET.value, scope=Scope.CLASS.value)
    def test_update_freeform_tag_of_subnet(self, test, subnet):
        """
        test update freeform tag of subnet
        """
        compartment_id, subnet_ocid = self._get_subnet_details(subnet)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "update-freeform-tag-of-subnet",
                "resource": Resource.SUBNET.value,
                "filters": [
                    {"type": "value", "key": "id", "value": subnet_ocid},
                ],
                "actions": [
                    {
                        "type": "update-subnet",
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
        resource = self._fetch_instance_validation_data(policy.resource_manager, subnet_ocid)
        test.assertEqual(resource["id"], subnet_ocid)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Production")

    @terraform(Module.SUBNET.value, scope=Scope.CLASS.value)
    def test_get_freeform_tagged_subnet(self, test, subnet):
        """
        test get freeform tagged subnet
        """
        compartment_id, subnet_ocid = self._get_subnet_details(subnet)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "get-freeform-tagged-subnet",
                "resource": Resource.SUBNET.value,
                "filters": [
                    {"type": "value", "key": "freeform_tags.Project", "value": "CNCF"},
                ],
            },
            session_factory=session_factory,
        )
        resources = policy.run()
        test.assertEqual(len(resources), 1)
        test.assertEqual(resources[0]["id"], subnet_ocid)
        test.assertEqual(resources[0]["freeform_tags"]["Project"], "CNCF")

    @terraform(Module.SUBNET.value, scope=Scope.CLASS.value)
    def test_remove_freeform_tag(self, test, subnet):
        """
        test remove freeform tag
        """
        compartment_id, subnet_ocid = self._get_subnet_details(subnet)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "subnet-remove-tag",
                "resource": Resource.SUBNET.value,
                "filters": [
                    {"type": "value", "key": "id", "value": subnet_ocid},
                ],
                "actions": [
                    {"type": "remove-tag", "freeform_tags": ["Project"]},
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, subnet_ocid)
        test.assertEqual(resource["id"], subnet_ocid)
        test.assertEqual(resource["freeform_tags"].get("Project"), None)

    @terraform(Module.SUBNET.value, scope=Scope.CLASS.value)
    def test_remove_defined_tag(self, test, subnet):
        """
        test remove defined tag
        """
        compartment_id, subnet_ocid = self._get_subnet_details(subnet)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "subnet-remove-tag",
                "resource": Resource.SUBNET.value,
                "filters": [
                    {"type": "value", "key": "id", "value": subnet_ocid},
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
        resource = self._fetch_instance_validation_data(policy.resource_manager, subnet_ocid)
        test.assertEqual(resource["id"], subnet_ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), None)
