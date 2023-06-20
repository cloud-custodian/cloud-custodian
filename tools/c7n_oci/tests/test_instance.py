import inspect

from pytest_terraform import terraform

from oci_common import Module, OciBaseTest, Resource, Scope


class TestInstance(OciBaseTest):
    def _get_instance_details(self, instance):
        ocid = instance["oci_core_instance.test_instance.id"]
        return ocid

    def _fetch_instance_validation_data(self, resource_manager, instance_id):
        return self.fetch_validation_data(resource_manager, "get_instance", instance_id)

    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_add_defined_tag_to_instance(self, test, compute, with_or_without_compartment):
        """
        test adding defined_tags tag on compute instance
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "add-defined-tag-to-instance",
                "resource": Resource.INSTANCE.value,
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
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        ocid = compute["oci_core_instance.test_instance.id"]

        policy = test.load_policy(
            {
                "name": "update-defined-tag-from-instance",
                "resource": Resource.INSTANCE.value,
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
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "add-freeform-tag-to-instance",
                "resource": Resource.INSTANCE.value,
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
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "update-freeform-tag-from-instance",
                "resource": Resource.INSTANCE.value,
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
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "get-tagged-instance",
                "resource": Resource.INSTANCE.value,
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

    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_remove_freeform_tag(self, test, compute):
        """
        test remove freeform tag
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "instance-remove-tag",
                "resource": Resource.INSTANCE.value,
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
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "instance-remove-tag",
                "resource": Resource.INSTANCE.value,
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

    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_instance_monitoring(self, test, compute):
        """
        test instance monitoring
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "instance-with-low-cpu-utilization",
                "resource": Resource.INSTANCE.value,
                "filters": [
                    {"type": "monitoring", "query": "CpuUtilization[1m].max() < 100"},
                ],
            },
            session_factory=session_factory,
        )
        self.wait(180)
        resources = policy.run()
        test_instance_found = False
        for resource in resources:
            if resource["id"] == ocid:
                test_instance_found = True
                break
        assert test_instance_found

    @terraform(Module.COMPUTE.value, scope=Scope.CLASS.value)
    def test_instance_power_off(self, test, compute):
        """
        test instance power off
        """
        ocid = self._get_instance_details(compute)
        session_factory = test.oci_session_factory(
            self.__class__.__name__, inspect.currentframe().f_code.co_name
        )
        policy = test.load_policy(
            {
                "name": "instance-power-off",
                "resource": Resource.INSTANCE.value,
                "filters": [
                    {"type": "value", "key": "id", "value": ocid},
                ],
                "actions": [
                    {
                        "type": "instance-action",
                        "params": {"action": "STOP"},
                    },
                ],
            },
            session_factory=session_factory,
        )
        policy.run()
        resource = self._fetch_instance_validation_data(policy.resource_manager, ocid)
        test.assertEqual(resource["id"], ocid)
        assert resource["lifecycle_state"] in ["STOPPING", "STOPPED"]
