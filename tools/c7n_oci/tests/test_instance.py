import inspect

from c7n_oci.constants import COMPARTMENT_IDS
from oci_common import Module, OciBaseTest, Resource, Scope
from pytest_terraform import terraform


class TestInstance(OciBaseTest):
    def _get_instance_details(self, instance):
        compartment_id = instance["oci_core_instance.test_instance.compartment_id"]
        ocid = instance["oci_core_instance.test_instance.id"]
        return compartment_id, ocid

    def _fetch_instance_validation_data(self, resource_manager, instance_id):
        return self.fetch_validation_data(resource_manager, "get_instance", instance_id)

    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_add_defined_tag_to_instance(self, test, compute):
        """
        test adding defined_tags tag on compute instance
        """
        compartment_id, ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-instance",
                "resource": Resource.COMPUTE.value,
                "query": [{COMPARTMENT_IDS: [compartment_id]}],
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [
                    {
                        "type": "update-instance",
                        "params": {
                            "update_instance_details": {
                                "defined_tags": self.get_defined_tag("add_tag")
                            }
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "true")

    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_update_defined_tag_of_instance(self, test, compute):
        """
        test update defined_tags tag on compute instance
        """
        compartment_id, ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        compartment_id = compute["oci_core_instance.test_instance.compartment_id"]
        ocid = compute["oci_core_instance.test_instance.id"]

        policy = test.load_policy(
            {
                "name": "update-defined-tag-from-instance",
                "resource": Resource.COMPUTE.value,
                "query": [{COMPARTMENT_IDS: [compartment_id]}],
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [
                    {
                        "type": "update-instance",
                        "params": {
                            "update_instance_details": {
                                "defined_tags": self.get_defined_tag("update_tag")
                            }
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        test.assertEqual(self.get_defined_tag_value(resource["defined_tags"]), "false")

    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_add_freeform_tag_to_instance(self, test, compute):
        """
        test adding freeform tag on compute instance
        """
        compartment_id, ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "add-freeform-tag-to-instance",
                "resource": Resource.COMPUTE.value,
                "query": [{COMPARTMENT_IDS: [compartment_id]}],
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [
                    {
                        "type": "update-instance",
                        "params": {
                            "update_instance_details": {
                                "freeform_tags": {"Environment": "Development"}
                            }
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Development")

    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_update_freeform_tag_of_instance(self, test, compute):
        """
        test update freeform tag on compute instance
        """
        compartment_id, ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "update-freeform-tag-from-instance",
                "resource": Resource.COMPUTE.value,
                "query": [{COMPARTMENT_IDS: [compartment_id]}],
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [
                    {
                        "type": "update-instance",
                        "params": {
                            "update_instance_details": {
                                "freeform_tags": {"Environment": "Production"}
                            }
                        },
                    }
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        test.assertEqual(resource["freeform_tags"]["Environment"], "Production")

    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_get_freeform_tagged_instance(self, test, compute):
        """
        test get freeform tagged compute instances
        """
        compartment_id, ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "get-tagged-instance",
                "resource": Resource.COMPUTE.value,
                "query": [
                    {COMPARTMENT_IDS: [compartment_id]},
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

    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_remove_freeform_tag(self, test, compute):
        """
        test remove freeform tag
        """
        compartment_id, ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "instance-remove-tag",
                "resource": Resource.COMPUTE.value,
                "query": [{"compartment_id": [compartment_id]}],
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

    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_remove_defined_tag(self, test, compute):
        """
        test remove defined tag
        """
        compartment_id, ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "instance-remove-tag",
                "resource": Resource.COMPUTE.value,
                "query": [{"compartment_id": [compartment_id]}],
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
